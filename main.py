import time
import os
import platform
import json
import threading
import concurrent.futures
import random
from DrissionPage import ChromiumPage, ChromiumOptions, Chromium

# Detect operating system and set paths accordingly
def get_base_path():
    """Get the base path for the current operating system"""
    # Use the directory where this script is located
    return os.path.dirname(os.path.abspath(__file__))

BASE_PATH = get_base_path()

def load_config():
    """Load configuration from config.json"""
    config_path = os.path.join(BASE_PATH, 'config.json')
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        print(f"Configuration loaded from {config_path}")
        return config
    except FileNotFoundError:
        print(f"Config file not found at {config_path}. Using default configuration.")
        return get_default_config()
    except Exception as e:
        print(f"Error loading config: {e}. Using default configuration.")
        return get_default_config()

def get_default_config():
    """Return default configuration if config file is not found"""
    return {
        "multiprocessing": {
            "enabled": True,
            "max_workers": 3,
            "phones_per_worker": 10
        },
        "browser": {
            "headless": False,
            "timeout": 30,
            "delay_between_phones": 1
        },
        "proxy": {
            "username": "r_c7c72217b5-country-de-sid-bhf5f598",
            "password": "9871a9d8a9",
            "host": "v2.proxyempire.io",
            "port": "5000"
        },
        "files": {
            "phone_numbers_file": "results/phone_numbers.txt",
            "output_file": "results/downloadable.txt",
            "create_backup": False,
            "save_results": True
        },
        "debug": {
            "enable_screenshots": False,
            "verbose_logging": True
        }
    }

def load_proxies(config):
    """Load rotating proxies from file"""
    if not config['proxy']['use_rotating_proxies']:
        return []
    
    proxy_file = os.path.join(BASE_PATH, config['proxy']['proxy_file'])
    proxies = []
    
    try:
        with open(proxy_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and ':' in line:
                    parts = line.split(':')
                    if len(parts) == 4:
                        proxy = {
                            'host': parts[0],
                            'port': parts[1],
                            'username': parts[2],
                            'password': parts[3]
                        }
                        proxies.append(proxy)
        
        print(f"Loaded {len(proxies)} rotating proxies from {proxy_file}")
        return proxies
    except FileNotFoundError:
        print(f"Proxy file not found: {proxy_file}")
        return []
    except Exception as e:
        print(f"Error loading proxies: {e}")
        return []

class ProxyRotator:
    """Manages proxy rotation for workers"""
    def __init__(self, proxies, config, worker_id):
        self.proxies = proxies
        self.config = config
        self.worker_id = worker_id
        self.current_proxy_index = worker_id % len(proxies) if proxies else 0
        self.requests_with_current_proxy = 0
        self.max_requests_for_current_proxy = random.randint(
            config['proxy']['rotation']['min_requests'],
            config['proxy']['rotation']['max_requests']
        )
        print(f"[Worker {worker_id}] Proxy rotator initialized - will use proxy {self.current_proxy_index} for {self.max_requests_for_current_proxy} requests")
    
    def get_current_proxy(self):
        """Get the current proxy for this worker"""
        if not self.proxies:
            return None
        return self.proxies[self.current_proxy_index]
    
    def should_rotate(self):
        """Check if proxy should be rotated"""
        return self.requests_with_current_proxy >= self.max_requests_for_current_proxy
    
    def rotate_proxy(self):
        """Rotate to next proxy"""
        if not self.proxies or len(self.proxies) <= 1:
            return
        
        old_index = self.current_proxy_index
        # Move to next proxy, with some randomization
        self.current_proxy_index = (self.current_proxy_index + random.randint(1, 3)) % len(self.proxies)
        self.requests_with_current_proxy = 0
        self.max_requests_for_current_proxy = random.randint(
            self.config['proxy']['rotation']['min_requests'],
            self.config['proxy']['rotation']['max_requests']
        )
        
        print(f"[Worker {self.worker_id}] Rotated proxy from index {old_index} to {self.current_proxy_index} - will use for {self.max_requests_for_current_proxy} requests")
    
    def increment_request_count(self):
        """Increment request count and rotate if needed"""
        self.requests_with_current_proxy += 1
        if self.should_rotate():
            self.rotate_proxy()

def create_proxy_auth_extension(proxy_info, worker_id=0):
    """Create a Chrome extension for proxy authentication - Solution from GitHub issue #83"""
    
    if not proxy_info:
        print(f"[Worker {worker_id}] No proxy info provided - creating extension without proxy")
        return None
    
    # Create proxy_files directory if it doesn't exist
    proxy_files_dir = os.path.join(BASE_PATH, "proxy_files")
    os.makedirs(proxy_files_dir, exist_ok=True)
    
    directory_name = os.path.join(proxy_files_dir, f"proxy_auth_extension_worker_{worker_id}")
    
    manifest_json = """
    {
        "version": "1.0.0",
        "manifest_version": 2,
        "name": "Proxies",
        "permissions": [
            "proxy",
            "tabs",
            "unlimitedStorage",
            "storage",
            "<all_urls>",
            "webRequest",
            "webRequestBlocking"
        ],
        "background": {
            "scripts": ["background.js"]
        },
        "minimum_chrome_version":"22.0.0"
    }
    """

    background_js = """
    var config = {
            mode: "fixed_servers",
            rules: {
              singleProxy: {
                scheme: "http",
                host: "%s",
                port: parseInt(%s)
              },
              bypassList: ["localhost"]
            }
          };

    chrome.proxy.settings.set({value: config, scope: "regular"}, function() {});

    function callbackFn(details) {
        return {
            authCredentials: {
                username: "%s",
                password: "%s"
            }
        };
    }

    chrome.webRequest.onAuthRequired.addListener(
                callbackFn,
                {urls: ["<all_urls>"]},
                ['blocking']
    );
    """ % (proxy_info['host'], proxy_info['port'], proxy_info['username'], proxy_info['password'])

    # Create directory if it doesn't exist
    if not os.path.exists(directory_name):
        os.makedirs(directory_name)

    # Write files
    manifest_path = os.path.join(directory_name, "manifest.json")
    background_path = os.path.join(directory_name, "background.js")

    with open(manifest_path, 'w') as manifest_file:
        manifest_file.write(manifest_json)

    with open(background_path, 'w') as background_file:
        background_file.write(background_js)
    
    print(f"[Worker {worker_id}] Proxy auth extension created with proxy {proxy_info['host']}:{proxy_info['port']}")
    return directory_name

def read_phone_numbers(config):
    """Read phone numbers from a text file, one per line"""
    file_path = os.path.join(BASE_PATH, config['files']['phone_numbers_file'])
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            phone_numbers = [line.strip() for line in f if line.strip()]
        print(f"Loaded {len(phone_numbers)} phone numbers from {file_path}")
        return phone_numbers
    except FileNotFoundError:
        print(f"Error: Could not find phone numbers file: {file_path}")
        return []
    except Exception as e:
        print(f"Error reading phone numbers file: {e}")
        return []

def load_initial_page(dp, url):
    """Load the page for the first time"""
    print(f"Loading initial page: {url}")
    dp.get(url)

    # Wait for page to load completely
    print("Waiting for initial page to load...")
    time.sleep(5)

    # Check if page loaded successfully
    if "doctolib" in dp.url.lower():
        print("Successfully loaded Doctolib page")
        return True
    else:
        print(f"Warning: May not have loaded correctly. Current URL: {dp.url}")
        return False

def process_phone_number(dp, phone_number, phone_index, config, worker_id, is_first_load=False):
    """Process a single phone number"""
    url = 'https://www.doctolib.de/authn/patient/realms/doctolib-patient/protocol/openid-connect/registrations?client_id=patient-de-client&context=navigation_bar&esid=utltfamkbuRkzGVkQ3K8kz_m&from=%2Fsessions%2Fnew%3Fcontext%3Dnavigation_bar&nonce=b1a6c0a5100b9c9fb7e92a8adf341f30&redirect_uri=https%3A%2F%2Fwww.doctolib.de%2Fauth%2Fpatient_de%2Fcallback&response_type=code&scope=openid+email&ssid=c138000win-cA1Yckyz62yC&state=4e29a9bacc124be9ee4a4781da33c438&ui_locales=de#step-username_sign_up'
    
    print(f"\n[Worker {worker_id}] {'='*60}")
    print(f"[Worker {worker_id}] Processing phone number {phone_index}: {phone_number}")
    print(f"[Worker {worker_id}] {'='*60}")
    
    try:
        # Only navigate to URL on first load
        if is_first_load:
            if not load_initial_page(dp, url):
                return False, None
        else:
            # For subsequent numbers, just refresh the form or navigate back to input
            print(f"[Worker {worker_id}] Navigating back to phone input form...")
            try:
                # Try to go back to the phone input step
                dp.back()
                time.sleep(2)
                # If back doesn't work, reload the page
                if 'step-username_sign_up' not in dp.url:
                    print(f"[Worker {worker_id}] Back navigation failed, reloading page...")
                    dp.get(url)
                    time.sleep(3)
            except:
                print(f"[Worker {worker_id}] Navigation issue, reloading page...")
                dp.get(url)
                time.sleep(3)

        # Take a screenshot for debugging (if enabled)
        if config['debug']['enable_screenshots']:
            try:
                screenshot_path = os.path.join(BASE_PATH, f'debug_screenshot_w{worker_id}_{phone_index}_{phone_number.replace("+", "")}.png')
                dp.get_screenshot(path=screenshot_path)
                print(f"[Worker {worker_id}] Screenshot saved for debugging")
            except Exception as e:
                print(f"[Worker {worker_id}] Could not save screenshot: {e}")

        # Try multiple selectors to find the input field
        phone_element = None
        selectors = [
            'xpath://input[@id="input_:r0:"]',
            'xpath://input[contains(@class, "oxygen-input-field__input")]',
            'xpath://input[@autocomplete="username"]',
            'xpath://div[contains(@class, "oxygen-input-field__inputWrapper")]/input',
            'css:input[id^="input_"]',
            'css:.oxygen-input-field__input'
        ]

        for i, selector in enumerate(selectors):
            try:
                if config['debug']['verbose_logging']:
                    print(f"[Worker {worker_id}] Trying selector {i+1}: {selector}")
                phone_element = dp.ele(selector, timeout=2)
                if phone_element:
                    print(f"[Worker {worker_id}] Success! Found input field with selector: {selector}")
                    break
            except Exception as e:
                if config['debug']['verbose_logging']:
                    print(f"[Worker {worker_id}] Selector {i+1} failed: {e}")
                continue

        if not phone_element:
            print(f"[Worker {worker_id}] Could not find the phone input field. Please check the page structure.")
            return False, None

        # Clear the input field and enter the new phone number
        time.sleep(2)
        try:
            # Clear any existing content
            phone_element.clear()
            time.sleep(1)
        except:
            # If clear doesn't work, try selecting all and deleting
            try:
                phone_element.click()
                phone_element.input('\b' * 20)  # Send multiple backspaces
                time.sleep(1)
            except:
                pass
        
        # Enter the phone number
        phone_element.input(phone_number)
        print(f"[Worker {worker_id}] Phone number entered successfully: {phone_number}")
        time.sleep(2)

        # Find and click the "Further" or "Weiter" button
        button = None
        button_selectors = [
            'xpath://button[contains(text(), "Further") or contains(text(), "Weiter")]',
            'xpath://input[@type="submit" and (contains(@value, "Further") or contains(@value, "Weiter"))]',
            'xpath://*[contains(@class, "button") and (contains(text(), "Further") or contains(text(), "Weiter"))]',
            'xpath://button[contains(@class, "submit") or contains(@class, "continue")]',
            'css:button[type="submit"]'
        ]
        
        for i, selector in enumerate(button_selectors):
            try:
                if config['debug']['verbose_logging']:
                    print(f"[Worker {worker_id}] Trying button selector {i+1}: {selector}")
                button = dp.ele(selector, timeout=2)
                if button:
                    print(f"[Worker {worker_id}] Success! Found button with selector: {selector}")
                    break
            except Exception as e:
                if config['debug']['verbose_logging']:
                    print(f"[Worker {worker_id}] Button selector {i+1} failed: {e}")
                continue

        if not button:
            print(f"[Worker {worker_id}] Could not find the Further/Weiter button.")
            return False, None

        # Check for CAPTCHA and wait for completion if needed
        print(f"[Worker {worker_id}] Checking for CAPTCHA...")
        try:
            captcha_element = dp.ele('css:.frc-captcha', timeout=3)
            if captcha_element:
                print(f"[Worker {worker_id}] CAPTCHA detected! Waiting for completion...")
                max_captcha_wait = 60
                for i in range(max_captcha_wait):
                    try:
                        progress_element = dp.ele('css:.frc-progress', timeout=1)
                        if progress_element:
                            progress_value = progress_element.attr('value')
                            print(f"[Worker {worker_id}] CAPTCHA progress: {float(progress_value)*100:.1f}%")
                            if float(progress_value) >= 1.0:
                                print(f"[Worker {worker_id}] CAPTCHA completed!")
                                break
                        else:
                            print(f"[Worker {worker_id}] CAPTCHA completed!")
                            break
                    except:
                        print(f"[Worker {worker_id}] CAPTCHA completed!")
                        break
                    time.sleep(1)
        except:
            print(f"[Worker {worker_id}] No CAPTCHA detected")

        # Wait a bit more for any dynamic updates
        time.sleep(3)

        # Check if button is enabled before clicking
        try:
            if button.attr('disabled'):
                print(f"[Worker {worker_id}] Button is disabled, waiting for it to be enabled...")
                for i in range(config['browser']['timeout']):
                    time.sleep(1)
                    if not button.attr('disabled'):
                        print(f"[Worker {worker_id}] Button is now enabled!")
                        break
                    if config['debug']['verbose_logging']:
                        print(f"[Worker {worker_id}] Still waiting for button... ({i+1}/{config['browser']['timeout']})")
        except:
            pass

        print(f"[Worker {worker_id}] Attempting to click the button...")
        button.click()
        print(f"[Worker {worker_id}] Button clicked successfully!")

        # Enhanced registration detection
        print(f"[Worker {worker_id}] Waiting for page response...")
        time.sleep(5)

        registration_detected = False
        registration_status = None  # Will be 'registered', 'not_registered', or None
        max_attempts = 90

        for attempt in range(max_attempts):
            try:
                if config['debug']['verbose_logging']:
                    print(f"[Worker {worker_id}] Checking registration status (attempt {attempt + 1}/{max_attempts})...")
                time.sleep(3)

                current_url = dp.url
                current_title = dp.title.lower()
                if config['debug']['verbose_logging']:
                    print(f"[Worker {worker_id}] Current URL: {current_url}")
                    print(f"[Worker {worker_id}] Current Title: {current_title}")

                # Always check page source for registration keywords first
                try:
                    page_source = dp.html.lower()
                    
                    registration_keywords = [
                        'andere telefonnummer nutzen',
                        'use another phone number',
                        'bereits registriert',
                        'already registered',
                        'anderes konto',
                        'different account',
                        'telefonnummer ist bereits',
                        'phone number is already',
                        'konto existiert bereits',
                        'account already exists',
                        'diese telefonnummer ist bereits',
                        'this phone number is already',
                        'nummer ist bereits registriert',
                        'number is already registered'
                    ]
                    
                    not_registered_keywords = [
                        'what is your name?',
                        'wie heißen Sie?',
                        'wie heißen sie?',
                        'wie heissen sie?',
                        'first name',
                        'vorname',
                        'last name',
                        'nachname',
                        'enter your first name',
                        'enter your last name',
                        'geben sie ihren vornamen',
                        'geben sie ihren nachnamen'
                    ]

                    if config['debug']['verbose_logging']:
                        print(f"[Worker {worker_id}] Page source snippet (first 1000 chars): {page_source[:1000]}")

                    # Check for "already registered" keywords first (these are more specific)
                    for keyword in registration_keywords:
                        if keyword in page_source:
                            print(f"[Worker {worker_id}] FOUND 'ALREADY REGISTERED' KEYWORD: '{keyword}'")
                            print(f"[Worker {worker_id}] Number ALREADY registered - The phone number is already registered with Doctolib.")
                            registration_detected = True
                            registration_status = 'registered'
                            break
                    
                    # If not already registered, check for "not registered" indicators
                    if not registration_detected:
                        for keyword in not_registered_keywords:
                            if keyword in page_source:
                                print(f"[Worker {worker_id}] FOUND 'NOT REGISTERED' KEYWORD: '{keyword}'")
                                print(f"[Worker {worker_id}] Number NOT registered - The phone number is not registered with Doctolib.")
                                registration_detected = True
                                registration_status = 'not_registered'
                                break

                except Exception as e:
                    print(f"[Worker {worker_id}] Could not check page source: {e}")

                # If we found a definitive answer, break immediately
                if registration_detected:
                    break

                # Only check for page transitions if no keywords were found
                if 'telefonnummer ein' in current_title or 'phone number' in current_title:
                    if config['debug']['verbose_logging']:
                        print(f"[Worker {worker_id}] Still on phone number input page - waiting for page transition...")
                    continue
                
                # If page changed but no keywords found, continue checking for a few more attempts
                # This handles cases where page loads but content is still loading
                if attempt < 5:  # Give it 5 more attempts after page change
                    if config['debug']['verbose_logging']:
                        print(f"[Worker {worker_id}] Page changed but no registration keywords found yet, continuing...")
                    continue
                else:
                    print(f"[Worker {worker_id}] Page changed but no clear registration status detected")
                    break

            except Exception as e:
                print(f"[Worker {worker_id}] Error during registration check (attempt {attempt + 1}): {e}")
                continue

        if not registration_detected:
            print(f"[Worker {worker_id}] No registration message found after all attempts - proceeding with registration or unknown state.")

        # Save a final screenshot for debugging (if enabled)
        if config['debug']['enable_screenshots']:
            try:
                final_screenshot_path = os.path.join(BASE_PATH, f'final_state_w{worker_id}_{phone_index}_{phone_number.replace("+", "")}.png')
                dp.get_screenshot(path=final_screenshot_path)
                print(f"[Worker {worker_id}] Final state screenshot saved")
            except Exception as e:
                print(f"[Worker {worker_id}] Could not save final screenshot: {e}")

        return True, registration_status

    except Exception as e:
        print(f"[Worker {worker_id}] Error processing phone number {phone_number}: {e}")
        return False, None

def process_phone_batch(phone_batch, worker_id, config):
    """Process a batch of phone numbers in a single worker"""
    print(f"[Worker {worker_id}] Starting to process {len(phone_batch)} phone numbers")
    
    # Load proxies and setup rotation for this worker
    proxies = load_proxies(config)
    proxy_rotator = None
    extension_dir = None
    
    if proxies:
        proxy_rotator = ProxyRotator(proxies, config, worker_id)
        current_proxy = proxy_rotator.get_current_proxy()
        extension_dir = create_proxy_auth_extension(current_proxy, worker_id)
    else:
        print(f"[Worker {worker_id}] No rotating proxies available - running without proxy")
    
    # Configure Chrome options for this worker
    co = ChromiumOptions()
    co.auto_port()  # Automatically assign a free port
    co.headless(config['browser']['headless'])
    
    # Add proxy extension if available
    if extension_dir:
        co.add_extension(extension_dir)
    
    co.set_argument('--no-sandbox')
    co.set_argument('--disable-dev-shm-usage')
    co.set_argument('--disable-gpu')
    co.set_argument('--window-size=1920,1080')
    co.set_argument('--disable-blink-features=AutomationControlled')
    co.set_argument('--disable-plugins')
    co.set_argument('--disable-images')
    co.set_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    
    # Additional Linux-specific arguments
    if platform.system() != "Windows":
        co.set_argument('--disable-setuid-sandbox')
        co.set_argument('--disable-dev-shm-usage')
        co.set_argument('--single-process')
        co.set_argument('--no-zygote')
        if extension_dir:
            co.set_argument('--disable-extensions-except=' + extension_dir)
        co.set_argument('--disable-extensions-file-access-check')

    # Initialize browser for this worker
    browser = Chromium(addr_or_opts=co)
    dp = browser.latest_tab

    # Add stealth scripts
    try:
        dp.run_js("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
        dp.run_js("Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});")
        dp.run_js("Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en', 'de']});")
        print(f"[Worker {worker_id}] Stealth scripts applied successfully")
    except Exception as e:
        print(f"[Worker {worker_id}] Warning: Could not apply stealth scripts: {e}")

    # Results for this worker
    worker_results = []
    
    # Process each phone number in the batch
    for index, phone_number in enumerate(phone_batch):
        # Check if we need to rotate proxy
        if proxy_rotator and proxy_rotator.should_rotate() and index > 0:
            print(f"[Worker {worker_id}] Rotating proxy for next batch of requests...")
            
            # Close current browser
            try:
                browser.quit()
            except:
                pass
            
            # Get new proxy and create new extension
            proxy_rotator.rotate_proxy()
            current_proxy = proxy_rotator.get_current_proxy()
            extension_dir = create_proxy_auth_extension(current_proxy, worker_id)
            
            # Reconfigure browser with new proxy
            co = ChromiumOptions()
            co.auto_port()
            co.headless(config['browser']['headless'])
            if extension_dir:
                co.add_extension(extension_dir)
            co.set_argument('--no-sandbox')
            co.set_argument('--disable-dev-shm-usage')
            co.set_argument('--disable-gpu')
            co.set_argument('--window-size=1920,1080')
            co.set_argument('--disable-blink-features=AutomationControlled')
            co.set_argument('--disable-plugins')
            co.set_argument('--disable-images')
            co.set_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
            
            if platform.system() != "Windows":
                co.set_argument('--disable-setuid-sandbox')
                co.set_argument('--disable-dev-shm-usage')
                co.set_argument('--single-process')
                co.set_argument('--no-zygote')
                if extension_dir:
                    co.set_argument('--disable-extensions-except=' + extension_dir)
                co.set_argument('--disable-extensions-file-access-check')
            
            # Initialize new browser
            browser = Chromium(addr_or_opts=co)
            dp = browser.latest_tab
            
            # Reapply stealth scripts
            try:
                dp.run_js("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
                dp.run_js("Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});")
                dp.run_js("Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en', 'de']});")
            except:
                pass
        
        is_first_load = (index == 0) or (proxy_rotator and proxy_rotator.requests_with_current_proxy == 0)
        phone_index = f"W{worker_id}-{index+1}"
        
        success, status = process_phone_number(dp, phone_number, phone_index, config, worker_id, is_first_load)
        
        # Increment proxy request count
        if proxy_rotator:
            proxy_rotator.increment_request_count()
        
        result = {
            'phone_number': phone_number,
            'success': success,
            'status': status,
            'worker_id': worker_id,
            'index': index
        }
        worker_results.append(result)
        
        # Add delay between numbers
        if index < len(phone_batch) - 1:
            print(f"[Worker {worker_id}] Waiting {config['browser']['delay_between_phones']}s before processing next number...")
            time.sleep(config['browser']['delay_between_phones'])
    
    # Close browser
    try:
        browser.quit()
        print(f"[Worker {worker_id}] Browser closed successfully")
    except Exception as e:
        print(f"[Worker {worker_id}] Error closing browser: {e}")
    
    # Clean up proxy extension directory
    if extension_dir and os.path.exists(extension_dir):
        try:
            import shutil
            shutil.rmtree(extension_dir)
            print(f"[Worker {worker_id}] Cleaned up proxy extension directory: {os.path.basename(extension_dir)}")
            
            # Try to remove proxy_files directory if empty
            proxy_files_dir = os.path.join(BASE_PATH, "proxy_files")
            try:
                if os.path.exists(proxy_files_dir) and not os.listdir(proxy_files_dir):
                    os.rmdir(proxy_files_dir)
                    print(f"[Worker {worker_id}] Removed empty proxy_files directory")
            except:
                pass  # Directory not empty or other issue, ignore
        except Exception as e:
            print(f"[Worker {worker_id}] Could not clean up extension directory: {e}")
    
    print(f"[Worker {worker_id}] Completed processing {len(phone_batch)} phone numbers")
    return worker_results

# Thread-safe file writing
file_lock = threading.Lock()

# Export file_lock for use by other modules (telegram_bot.py)
__all__ = ['main', 'load_config', 'get_base_path', 'file_lock', 'process_phone_batch', 'save_result_to_file']

def save_result_to_file(result, config):
    """Thread-safe function to save results to file"""
    # Check if file saving is enabled and output file is specified
    if not config['files'].get('save_results', True) or not config['files'].get('output_file'):
        # Just print the results to console
        phone_number = result['phone_number']
        success = result['success']
        status = result['status']
        worker_id = result['worker_id']
        
        if success:
            if status == 'registered':
                print(f"[Worker {worker_id}] ✓ REGISTERED: {phone_number}")
            elif status == 'not_registered':
                print(f"[Worker {worker_id}] ✗ NOT REGISTERED: {phone_number}")
            else:
                print(f"[Worker {worker_id}] ? UNKNOWN STATUS: {phone_number}")
        else:
            print(f"[Worker {worker_id}] ✗ FAILED to process {phone_number}")
        return
    
    phone_number = result['phone_number']
    success = result['success']
    status = result['status']
    worker_id = result['worker_id']
    
    with file_lock:
        try:
            downloadable_file = os.path.join(BASE_PATH, config['files']['output_file'])
            with open(downloadable_file, 'a', encoding='utf-8') as f:
                if success:
                    if status == 'registered':
                        f.write(f"{phone_number} - Registered (Worker {worker_id})\n")
                        print(f"[Worker {worker_id}] ✓ REGISTERED: {phone_number} (saved to {config['files']['output_file']})")
                    elif status == 'not_registered':
                        f.write(f"{phone_number} - Not Registered (Worker {worker_id})\n")
                        print(f"[Worker {worker_id}] ✗ NOT REGISTERED: {phone_number} (saved to {config['files']['output_file']})")
                    else:
                        f.write(f"{phone_number} - Unknown Status (Worker {worker_id})\n")
                        print(f"[Worker {worker_id}] ? UNKNOWN STATUS: {phone_number} (saved to {config['files']['output_file']})")
                else:
                    f.write(f"{phone_number} - Failed to Process (Worker {worker_id})\n")
                    print(f"[Worker {worker_id}] ✗ FAILED to process {phone_number} (saved to {config['files']['output_file']})")
        except Exception as e:
            print(f"[Worker {worker_id}] Error saving result for {phone_number} to {config['files']['output_file']}: {e}")

def cleanup_proxy_files_on_startup():
    """Clean up any leftover proxy extension files from previous runs"""
    try:
        import shutil
        proxy_files_dir = os.path.join(BASE_PATH, "proxy_files")
        if os.path.exists(proxy_files_dir):
            shutil.rmtree(proxy_files_dir)
            print(f"🧹 Cleaned up leftover proxy_files directory from previous run")
        os.makedirs(proxy_files_dir, exist_ok=True)
        print(f"📁 Created fresh proxy_files directory: {proxy_files_dir}")
    except Exception as e:
        print(f"⚠️ Warning: Could not clean up proxy_files directory: {e}")

def main():
    """Main execution function"""
    print("🚀 Starting Doctolib Bot with Multiprocessing Support")
    
    # Clean up any leftover proxy files from previous runs
    cleanup_proxy_files_on_startup()
    
    # Load configuration
    config = load_config()
    
    # Print configuration summary
    print(f"\n📋 Configuration Summary:")
    print(f"   Multiprocessing: {'Enabled' if config['multiprocessing']['enabled'] else 'Disabled'}")
    print(f"   Max Workers: {config['multiprocessing']['max_workers']}")
    print(f"   Phones per Worker: {config['multiprocessing']['phones_per_worker']}")
    print(f"   Headless Mode: {config['browser']['headless']}")
    print(f"   Debug Screenshots: {config['debug']['enable_screenshots']}")
    print(f"   Verbose Logging: {config['debug']['verbose_logging']}")
    
    # Load phone numbers
    phone_numbers = read_phone_numbers(config)
    
    if not phone_numbers:
        print("No phone numbers loaded. Exiting...")
        return

    # Ensure results directory exists
    results_dir = os.path.join(BASE_PATH, 'results')
    os.makedirs(results_dir, exist_ok=True)

    # Clear the output file at the start (only if saving is enabled)
    if config['files'].get('save_results', True) and config['files'].get('output_file'):
        try:
            downloadable_file = os.path.join(BASE_PATH, config['files']['output_file'])
            with open(downloadable_file, 'w', encoding='utf-8') as f:
                f.write("")  # Clear the file
            print(f"Cleared {config['files']['output_file']} file for fresh start")
        except Exception as e:
            print(f"Could not clear {config['files']['output_file']}: {e}")
    else:
        print("File saving is disabled - results will only be shown in console")

    # Results tracking
    all_results = {
        'registered': [],
        'not_registered': [],
        'unknown': [],
        'failed': []
    }

    if config['multiprocessing']['enabled']:
        print(f"\n🔄 Starting multiprocessing with {config['multiprocessing']['max_workers']} workers...")
        
        # Split phone numbers into batches
        phones_per_worker = config['multiprocessing']['phones_per_worker']
        phone_batches = [phone_numbers[i:i+phones_per_worker] for i in range(0, len(phone_numbers), phones_per_worker)]
        
        print(f"📦 Split {len(phone_numbers)} phone numbers into {len(phone_batches)} batches")
        for i, batch in enumerate(phone_batches):
            print(f"   Batch {i+1}: {len(batch)} phones")
        
        # Process batches using ThreadPoolExecutor
        with concurrent.futures.ThreadPoolExecutor(max_workers=config['multiprocessing']['max_workers']) as executor:
            # Submit all batches
            future_to_batch = {
                executor.submit(process_phone_batch, batch, i, config): i 
                for i, batch in enumerate(phone_batches)
            }
            
            # Process completed futures
            for future in concurrent.futures.as_completed(future_to_batch):
                batch_id = future_to_batch[future]
                try:
                    worker_results = future.result()
                    print(f"✅ Batch {batch_id + 1} completed with {len(worker_results)} results")
                    
                    # Save results and update tracking
                    for result in worker_results:
                        save_result_to_file(result, config)
                        
                        # Update tracking
                        if result['success']:
                            if result['status'] == 'registered':
                                all_results['registered'].append(result['phone_number'])
                            elif result['status'] == 'not_registered':
                                all_results['not_registered'].append(result['phone_number'])
                            else:
                                all_results['unknown'].append(result['phone_number'])
                        else:
                            all_results['failed'].append(result['phone_number'])
                            
                except Exception as exc:
                    print(f"❌ Batch {batch_id + 1} generated an exception: {exc}")
    
    else:
        print("\n🔄 Running in single-process mode...")
        # Single process mode (original logic)
        # This would use the original main logic but adapted for the config system
        print("Single-process mode not implemented in this version. Please enable multiprocessing in config.json")
        return

    # Print final summary
    print(f"\n🎉 Completed processing all {len(phone_numbers)} phone numbers.")
    
    print(f"\n{'='*60}")
    print("📊 FINAL RESULTS SUMMARY")
    print(f"{'='*60}")
    print(f"Total processed: {len(phone_numbers)}")
    print(f"Already registered: {len(all_results['registered'])}")
    print(f"Not registered: {len(all_results['not_registered'])}")
    print(f"Unknown status: {len(all_results['unknown'])}")
    print(f"Failed to process: {len(all_results['failed'])}")
    
    # Save results to separate files (only if backup is enabled)
    try:
        if config['files'].get('save_results', True) and config['files'].get('output_file'):
            print(f"All results have been saved to {config['files']['output_file']} in real-time")
        
        # Only create backup files if create_backup is enabled
        if config['files'].get('create_backup', False):
            # Ensure results directory exists
            results_dir = os.path.join(BASE_PATH, 'results')
            os.makedirs(results_dir, exist_ok=True)
            
            with open(os.path.join(results_dir, 'registered_numbers.txt'), 'w', encoding='utf-8') as f:
                for num in all_results['registered']:
                    f.write(f"{num}\n")
            print(f"Saved {len(all_results['registered'])} registered numbers to results/registered_numbers.txt")
            
            with open(os.path.join(results_dir, 'not_registered_numbers.txt'), 'w', encoding='utf-8') as f:
                for num in all_results['not_registered']:
                    f.write(f"{num}\n")
            print(f"Saved {len(all_results['not_registered'])} not registered numbers to results/not_registered_numbers.txt")
            
            with open(os.path.join(results_dir, 'unknown_numbers.txt'), 'w', encoding='utf-8') as f:
                for num in all_results['unknown']:
                    f.write(f"{num}\n")
            print(f"Saved {len(all_results['unknown'])} unknown status numbers to results/unknown_numbers.txt")
            
            with open(os.path.join(results_dir, 'failed_numbers.txt'), 'w', encoding='utf-8') as f:
                for num in all_results['failed']:
                    f.write(f"{num}\n")
            print(f"Saved {len(all_results['failed'])} failed numbers to results/failed_numbers.txt")
        else:
            print("Backup files creation is disabled in configuration")
        
    except Exception as e:
        print(f"Error saving results to files: {e}")
    
    # Clean up any remaining proxy extension directories
    print(f"\n🧹 Cleaning up proxy extension directories...")
    try:
        import shutil
        import glob
        
        # Clean up proxy extension directories in the proxy_files folder
        proxy_files_dir = os.path.join(BASE_PATH, "proxy_files")
        if os.path.exists(proxy_files_dir):
            extension_dirs = glob.glob(os.path.join(proxy_files_dir, "proxy_auth_extension_worker_*"))
            for ext_dir in extension_dirs:
                try:
                    shutil.rmtree(ext_dir)
                    print(f"   Cleaned up: {os.path.basename(ext_dir)}")
                except Exception as e:
                    print(f"   Could not clean up {os.path.basename(ext_dir)}: {e}")
            
            # Remove proxy_files directory if empty
            try:
                if not os.listdir(proxy_files_dir):
                    os.rmdir(proxy_files_dir)
                    print(f"   Removed empty proxy_files directory")
            except:
                pass
            
            if not extension_dirs:
                print("   No proxy extension directories to clean up")
        else:
            print("   No proxy_files directory found")
    except Exception as e:
        print(f"   Error during cleanup: {e}")

if __name__ == "__main__":
    main()
