"""
Celery-based Doctolib phone number checker
This replaces browser automation with HTTP requests for better performance and stealth
"""

from celery import Celery
import requests
import json
import random
import time
import os
from urllib.parse import urlencode
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Celery configuration
app = Celery('doctolib_checker')
app.config_from_object('celeryconfig')

# Base configuration
BASE_PATH = os.path.dirname(os.path.abspath(__file__))

def load_config():
    """Load configuration from config.json"""
    config_path = os.path.join(BASE_PATH, 'config.json')
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return get_default_config()

def get_default_config():
    """Default configuration for API-based approach"""
    return {
        "api": {
            "base_url": "https://www.doctolib.de",
            "registration_endpoint": "/authn/patient/realms/doctolib-patient/protocol/openid-connect/registrations",
            "timeout": 10,          # Reduced from 30 to 10 seconds
            "max_retries": 2        # Reduced from 3 to 2 retries
        },
        "proxy": {
            "use_rotating_proxies": True,
            "proxy_file": "proxies.txt",
            "rotation": {
                "min_requests": 5,
                "max_requests": 15
            }
        },
        "delays": {
            "base_delay": 0.5,      # Reduced from 2.0 to 0.5 seconds
            "randomization": 0.3,   # Reduced from 1.0 to 0.3 seconds  
            "retry_delay": 2.0      # Reduced from 5.0 to 2.0 seconds
        },
        "files": {
            "phone_numbers_file": "results/phone_numbers.txt",
            "output_file": "results/downloadable.txt"
        }
    }

def create_session_with_retries():
    """Create a requests session with retry strategy"""
    session = requests.Session()
    
    retry_strategy = Retry(
        total=2,                # Reduced from 3 to 2 total retries
        backoff_factor=0.5,     # Reduced from 1 to 0.5 seconds
        status_forcelist=[429, 500, 502, 503, 504],
    )
    
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    
    # Set realistic headers
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'de-DE,de;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    })
    
    return session

def setup_proxy(session, proxy_info):
    """Setup proxy for the session"""
    if proxy_info:
        proxy_url = f"http://{proxy_info['username']}:{proxy_info['password']}@{proxy_info['host']}:{proxy_info['port']}"
        session.proxies = {
            'http': proxy_url,
            'https': proxy_url
        }
        return True
    return False

def get_random_delay(base_delay, randomization):
    """Get a randomized delay"""
    return max(0.1, random.uniform(base_delay - randomization, base_delay + randomization))

@app.task(bind=True, max_retries=2)  # Reduced from 3 to 2 retries
def check_phone_registration(self, phone_number, proxy_info=None, config=None):
    """
    Celery task to check if a phone number is registered with Doctolib
    Uses HTTP requests instead of browser automation
    """
    if config is None:
        config = load_config()
    task_id = self.request.id
    
    print(f"[Task {task_id}] Checking phone number: {phone_number}")
    print(f"[Task {task_id}] Output file: {config.get('files', {}).get('output_file', 'Not set')}")
    
    try:
        # Create session
        session = create_session_with_retries()
        
        # Setup proxy if provided
        if proxy_info:
            setup_proxy(session, proxy_info)
            print(f"[Task {task_id}] Using proxy: {proxy_info['host']}:{proxy_info['port']}")
        
        # Add random delay for human-like behavior
        delay = get_random_delay(config['delays']['base_delay'], config['delays']['randomization'])
        time.sleep(delay)
        
        # Step 1: Get initial page and extract necessary tokens/cookies
        initial_url = f"{config['api']['base_url']}{config['api']['registration_endpoint']}"
        params = {
            'client_id': 'patient-de-client',
            'context': 'navigation_bar',
            'from': '/sessions/new?context=navigation_bar',
            'redirect_uri': 'https://www.doctolib.de/auth/patient_de/callback',
            'response_type': 'code',
            'scope': 'openid email',
            'ui_locales': 'de'
        }
        
        full_url = f"{initial_url}?{urlencode(params)}#step-username_sign_up"
        
        print(f"[Task {task_id}] Fetching registration page...")
        response = session.get(full_url, timeout=config['api']['timeout'])
        response.raise_for_status()
        
        # Extract CSRF token or other required data from the response
        # This would need to be customized based on Doctolib's actual implementation
        html_content = response.text
        
        # Step 2: Submit phone number
        # You'll need to analyze the actual form submission to get the correct endpoint and parameters
        submit_data = {
            'username': phone_number,
            # Add other required fields based on the form analysis
        }
        
        # Add necessary headers for the POST request
        session.headers.update({
            'Content-Type': 'application/x-www-form-urlencoded',
            'Referer': full_url,
            'Origin': config['api']['base_url']
        })
        
        print(f"[Task {task_id}] Submitting phone number...")
        
        # This endpoint would need to be determined by analyzing the actual form submission
        submit_response = session.post(
            f"{config['api']['base_url']}/submit-endpoint",  # Replace with actual endpoint
            data=submit_data,
            timeout=config['api']['timeout'],
            allow_redirects=True
        )
        
        # Step 3: Analyze response to determine registration status
        response_text = submit_response.text.lower()
        final_url = submit_response.url.lower()
        
        # Check for registration indicators
        registration_keywords = [
            'bereits registriert', 'already registered', 'andere telefonnummer nutzen',
            'use another phone number', 'anderes konto', 'different account',
            'telefonnummer ist bereits', 'phone number is already'
        ]
        
        not_registered_keywords = [
            'wie heißen sie', 'what is your name', 'first name', 'vorname',
            'last name', 'nachname', 'enter your'
        ]
        
        registration_status = None
        
        # Check for already registered
        for keyword in registration_keywords:
            if keyword in response_text:
                registration_status = 'registered'
                print(f"[Task {task_id}] ✓ REGISTERED: {phone_number}")
                break
        
        # Check for not registered
        if not registration_status:
            for keyword in not_registered_keywords:
                if keyword in response_text:
                    registration_status = 'not_registered'
                    print(f"[Task {task_id}] ✗ NOT REGISTERED: {phone_number}")
                    break
        
        if not registration_status:
            registration_status = 'unknown'
            print(f"[Task {task_id}] ? UNKNOWN STATUS: {phone_number}")
        
        # Save result
        result = {
            'phone_number': phone_number,
            'status': registration_status,
            'task_id': task_id,
            'success': True
        }
        
        save_result_to_file(result, config)
        
        return result
        
    except requests.exceptions.RequestException as e:
        print(f"[Task {task_id}] Network error for {phone_number}: {e}")
        
        # Retry with exponential backoff
        if self.request.retries < self.max_retries:
            retry_delay = config['delays']['retry_delay'] * (2 ** self.request.retries)
            print(f"[Task {task_id}] Retrying in {retry_delay} seconds...")
            raise self.retry(countdown=retry_delay)
        
        # Max retries reached
        result = {
            'phone_number': phone_number,
            'status': 'failed',
            'task_id': task_id,
            'success': False,
            'error': str(e)
        }
        save_result_to_file(result, config)
        return result
        
    except Exception as e:
        print(f"[Task {task_id}] Unexpected error for {phone_number}: {e}")
        result = {
            'phone_number': phone_number,
            'status': 'failed',
            'task_id': task_id,
            'success': False,
            'error': str(e)
        }
        save_result_to_file(result, config)
        return result

def save_result_to_file(result, config):
    """Save result to output file"""
    if not config['files'].get('output_file'):
        return
    
    try:
        output_file = os.path.join(BASE_PATH, config['files']['output_file'])
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        
        with open(output_file, 'a', encoding='utf-8') as f:
            if result['success']:
                status_text = {
                    'registered': 'Registered',
                    'not_registered': 'Not Registered',
                    'unknown': 'Unknown Status'
                }.get(result['status'], 'Unknown')
                
                f.write(f"{result['phone_number']} - {status_text} (Task {result['task_id']})\n")
            else:
                f.write(f"{result['phone_number']} - Failed (Task {result['task_id']}): {result.get('error', 'Unknown error')}\n")
                
    except Exception as e:
        print(f"Error saving result: {e}")

@app.task
def process_phone_batch(phone_numbers, proxy_list=None):
    """
    Process a batch of phone numbers using Celery
    """
    results = []
    proxy_index = 0
    
    for phone_number in phone_numbers:
        # Rotate proxy if available
        proxy_info = None
        if proxy_list:
            proxy_info = proxy_list[proxy_index % len(proxy_list)]
            proxy_index += 1
        
        # Submit task to Celery
        task = check_phone_registration.delay(phone_number, proxy_info)
        results.append({
            'phone_number': phone_number,
            'task_id': task.id
        })
    
    return results

if __name__ == '__main__':
    # This would be run by Celery workers
    app.start()
