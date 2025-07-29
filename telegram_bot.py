import os,json,time,threading,tempfile,platform,signal,sys
from datetime import datetime
from telegram import Update, Document
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode
import tempfile
import shutil
from main import main as run_doctolib_bot, load_config, get_base_path, calculate_optimal_workers_and_batch_size, calculate_dynamic_delays

# Import virtual display manager if available
try:
    from virtual_display import VirtualDisplayManager
    VIRTUAL_DISPLAY_AVAILABLE = True
except ImportError:
    VIRTUAL_DISPLAY_AVAILABLE = False
    print("⚠️ Virtual display manager not available. Running without virtual display support.")

# Import shared locks from main.py to avoid conflicts
try:
    from main import file_lock as shared_file_lock
except ImportError:
    shared_file_lock = threading.Lock()

config_file_lock = shared_file_lock
active_jobs = {}
job_counter = 0
job_lock = threading.Lock()

# Virtual display management
virtual_display_manager = None
virtual_display_lock = threading.Lock()

# Process termination support
job_termination_flags = {}  # job_id -> threading.Event()
job_processes = {}  # job_id -> list of process objects or browser instances

# Job cleanup configuration
MAX_ACTIVE_JOBS = 50  # Maximum number of jobs to keep in memory
JOB_CLEANUP_INTERVAL = 300  # 5 minutes
JOB_EXPIRY_TIME = 1800  # 30 minutes

def cleanup_old_jobs():
    """Clean up old completed jobs from memory"""
    with job_lock:
        current_time = datetime.now()
        jobs_to_remove = []
        
        for job_id, job in active_jobs.items():
            # Remove jobs older than 30 minutes or completed jobs older than 5 minutes
            job_age = (current_time - job.get('created_time', current_time)).total_seconds()
            
            if job['status'] in ['completed', 'failed']:
                completion_time = job.get('end_time', job.get('created_time', current_time))
                time_since_completion = (current_time - completion_time).total_seconds()
                if time_since_completion > JOB_CLEANUP_INTERVAL:
                    jobs_to_remove.append(job_id)
            elif job_age > JOB_EXPIRY_TIME:
                jobs_to_remove.append(job_id)
        
        # If we still have too many jobs, remove the oldest completed ones
        if len(active_jobs) > MAX_ACTIVE_JOBS:
            completed_jobs = [(job_id, job) for job_id, job in active_jobs.items() 
                            if job['status'] in ['completed', 'failed']]
            completed_jobs.sort(key=lambda x: x[1].get('end_time', x[1].get('created_time', datetime.now())))
            
            excess_count = len(active_jobs) - MAX_ACTIVE_JOBS
            for job_id, _ in completed_jobs[:excess_count]:
                if job_id not in jobs_to_remove:
                    jobs_to_remove.append(job_id)
        
        # Remove the jobs
        for job_id in jobs_to_remove:
            del active_jobs[job_id]
            print(f"Cleaned up job {job_id} from memory")
        
        if jobs_to_remove:
            print(f"Memory cleanup: Removed {len(jobs_to_remove)} old jobs. Active jobs: {len(active_jobs)}")

def schedule_job_cleanup():
    """Schedule periodic job cleanup"""
    def run_cleanup():
        while True:
            time.sleep(JOB_CLEANUP_INTERVAL)
            try:
                cleanup_old_jobs()
            except Exception as e:
                print(f"Error during job cleanup: {e}")
    
    cleanup_thread = threading.Thread(target=run_cleanup, daemon=True)
    cleanup_thread.start()
    print("Job cleanup scheduler started")

BASE_PATH = get_base_path()

# Bot instance management
BOT_LOCKFILE = os.path.join(BASE_PATH, '.bot_instance.lock')
bot_application_instance = None

def create_bot_lockfile():
    """Create a lockfile to prevent multiple bot instances"""
    try:
        if os.path.exists(BOT_LOCKFILE):
            # Check if the process in the lockfile is still running
            try:
                with open(BOT_LOCKFILE, 'r') as f:
                    old_pid = int(f.read().strip())
                
                # Check if process is still running
                try:
                    if platform.system() == "Windows":
                        import subprocess
                        result = subprocess.run(['tasklist', '/FI', f'PID eq {old_pid}'], 
                                              capture_output=True, text=True)
                        if str(old_pid) not in result.stdout:
                            # Process is dead, remove stale lockfile
                            os.remove(BOT_LOCKFILE)
                            print(f"🧹 Removed stale lockfile for dead process {old_pid}")
                        else:
                            print(f"❌ Another bot instance is already running (PID: {old_pid})")
                            print("Please stop the other instance before starting this one.")
                            return False
                    else:
                        # Unix-like systems
                        os.kill(old_pid, 0)  # This will raise an exception if process doesn't exist
                        print(f"❌ Another bot instance is already running (PID: {old_pid})")
                        print("Please stop the other instance before starting this one.")
                        return False
                except (subprocess.CalledProcessError, ProcessLookupError, OSError):
                    # Process is dead, remove stale lockfile
                    os.remove(BOT_LOCKFILE)
                    print(f"🧹 Removed stale lockfile for dead process {old_pid}")
            except (ValueError, FileNotFoundError):
                # Invalid lockfile, remove it
                if os.path.exists(BOT_LOCKFILE):
                    os.remove(BOT_LOCKFILE)
                print("🧹 Removed invalid lockfile")
        
        # Create new lockfile with current PID
        with open(BOT_LOCKFILE, 'w') as f:
            f.write(str(os.getpid()))
        print(f"📁 Created bot instance lockfile (PID: {os.getpid()})")
        return True
        
    except Exception as e:
        print(f"⚠️ Warning: Could not create bot lockfile: {e}")
        return True  # Continue anyway

def remove_bot_lockfile():
    """Remove the bot lockfile on shutdown"""
    try:
        if os.path.exists(BOT_LOCKFILE):
            with open(BOT_LOCKFILE, 'r') as f:
                lockfile_pid = int(f.read().strip())
            
            # Only remove if it's our lockfile
            if lockfile_pid == os.getpid():
                os.remove(BOT_LOCKFILE)
                print(f"🧹 Removed bot instance lockfile")
            else:
                print(f"⚠️ Lockfile belongs to different process ({lockfile_pid}), not removing")
    except Exception as e:
        print(f"⚠️ Warning: Could not remove bot lockfile: {e}")

def signal_handler(signum, frame):
    """Handle shutdown signals gracefully"""
    print(f"\n🛑 Received signal {signum}, shutting down gracefully...")
    
    # Stop the bot application if it exists
    global bot_application_instance
    if bot_application_instance:
        print("🔄 Stopping bot application...")
        try:
            bot_application_instance.stop()
            print("✅ Bot application stopped")
        except Exception as e:
            print(f"⚠️ Error stopping bot application: {e}")
    
    # Terminate any active jobs
    print("🛑 Terminating active jobs...")
    global active_jobs, job_termination_flags
    for job_id in list(active_jobs.keys()):
        if job_id in job_termination_flags:
            job_termination_flags[job_id].set()
        terminate_job_processes(job_id)
    
    # Clean up virtual display
    cleanup_virtual_display()
    
    # Clean up resources
    cleanup_proxy_files_on_startup()
    remove_bot_lockfile()
    
    print("👋 Bot shutdown completed")
    sys.exit(0)

def ensure_virtual_display():
    """Ensure virtual display is running for non-headless mode on Linux"""
    global virtual_display_manager
    
    if not VIRTUAL_DISPLAY_AVAILABLE:
        return True  # No virtual display support, assume headless or Windows
    
    if platform.system() != "Linux":
        return True  # Not Linux, no virtual display needed
    
    with virtual_display_lock:
        # Check if we already have a display manager
        if virtual_display_manager is None:
            virtual_display_manager = VirtualDisplayManager()
        
        # Check if display is already running
        if virtual_display_manager.is_display_running():
            print("✅ Virtual display is already running")
            return True
        
        # Start virtual display
        print("🖥️ Starting virtual display for Telegram bot jobs...")
        if virtual_display_manager.start_display():
            print("✅ Virtual display started successfully for Telegram bot")
            return True
        else:
            print("❌ Failed to start virtual display")
            return False

def cleanup_virtual_display():
    """Clean up virtual display on shutdown"""
    global virtual_display_manager
    
    if virtual_display_manager and VIRTUAL_DISPLAY_AVAILABLE:
        print("🧹 Cleaning up virtual display...")
        virtual_display_manager.stop_display()
        virtual_display_manager = None

def check_virtual_display_requirements(config):
    """Check if virtual display is needed and available"""
    if platform.system() != "Linux":
        return True, "Not running on Linux - virtual display not needed"
    
    if config.get('browser', {}).get('headless', True):
        return True, "Headless mode enabled - virtual display not needed"
    
    if not VIRTUAL_DISPLAY_AVAILABLE:
        return False, "Virtual display module not available. Install requirements or enable headless mode."
    
    # Check if Xvfb is installed
    try:
        import subprocess
        result = subprocess.run(['which', 'Xvfb'], capture_output=True)
        if result.returncode != 0:
            return False, "Xvfb not installed. Run setup script or install with: sudo apt install xvfb"
    except Exception:
        return False, "Cannot check Xvfb installation"
    
    return True, "Virtual display requirements met"

def ensure_proxy_config_compatibility(config):
    """Ensure proxy configuration has all required fields for main.py compatibility"""
    if 'proxy' not in config:
        config['proxy'] = {}
    
    # Set default proxy configuration if missing
    proxy_defaults = {
        'use_rotating_proxies': False,
        'proxy_file': 'proxies.txt',
        'rotation': {
            'min_requests': 20,
            'max_requests': 30,
            'per_worker': True
        },
        'username': '',
        'password': '',
        'host': '',
        'port': ''
    }
    
    for key, value in proxy_defaults.items():
        if key not in config['proxy']:
            config['proxy'][key] = value
    
    # Ensure rotation sub-config exists
    if 'rotation' not in config['proxy']:
        config['proxy']['rotation'] = proxy_defaults['rotation']
    
    return config

def load_telegram_config():
    """Load Telegram bot configuration"""
    config_path = os.path.join(BASE_PATH, 'config.json')
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        if 'telegram' not in config:
            print("No Telegram configuration found in config.json. Please add telegram section with bot_token.")
            return None
        
        return config['telegram']
    except Exception as e:
        print(f"Error loading Telegram config: {e}")
        return None

def create_job_id():
    """Create a unique job ID"""
    global job_counter
    with job_lock:
        job_counter += 1
        return f"job_{job_counter}_{int(time.time())}"

def send_simple_message(chat_id, text, bot_application):
    """Send a simple message using direct HTTP request to avoid event loop issues"""
    try:
        import requests
        bot_token = bot_application.bot.token
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        data = {
            'chat_id': chat_id,
            'text': text
        }
        response = requests.post(url, data=data, timeout=10)
        if response.status_code == 200:
            print(f"Message sent successfully to chat {chat_id}")
        else:
            print(f"Failed to send message: {response.status_code}")
    except Exception as e:
        print(f"Error sending message: {e}")

def send_partial_results_message_sync(chat_id, job_id, output_file, bot_application):
    """Send partial results message when job is stopped"""
    try:
        import requests
        
        # Read statistics from output file
        with open(output_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        if not lines:
            send_simple_message(chat_id, f"🛑 Job {job_id} was stopped but no results were processed yet.", bot_application)
            return
        
        # Parse and categorize phone numbers
        registered_numbers = []
        not_registered_numbers = []
        failed_numbers = []
        unknown_numbers = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # Extract phone number from the line (before the first space or dash)
            parts = line.split(' - ')
            if len(parts) >= 2:
                phone_number = parts[0].strip()
                status = parts[1].strip().lower()
                
                if "registered" in status and "not registered" not in status:
                    registered_numbers.append(phone_number)
                elif "not registered" in status:
                    not_registered_numbers.append(phone_number)
                elif "failed to process" in status:
                    failed_numbers.append(phone_number)
                else:
                    unknown_numbers.append(phone_number)
            else:
                # If format is unexpected, try to extract just the phone number
                phone_number = line.split()[0] if line.split() else line
                unknown_numbers.append(phone_number)
        
        # Calculate processing info
        total_requested = len(active_jobs[job_id]['phone_numbers']) if job_id in active_jobs else 0
        processed_count = len(lines)
        progress = (processed_count / total_requested * 100) if total_requested > 0 else 0
        
        duration = "Unknown"
        if job_id in active_jobs and 'start_time' in active_jobs[job_id] and 'end_time' in active_jobs[job_id]:
            duration_seconds = (active_jobs[job_id]['end_time'] - active_jobs[job_id]['start_time']).total_seconds()
            duration = f"{duration_seconds:.1f} seconds"
        
        summary_text = (
            f"🛑 Job {job_id} Stopped!\n\n"
            f"📊 Partial Results Summary:\n"
            f"📈 Progress: {processed_count}/{total_requested} ({progress:.1f}%)\n\n"
            f"📱 Processed Numbers:\n"
            f"• Already Registered: {len(registered_numbers)}\n"
            f"• Not Registered: {len(not_registered_numbers)}\n"
            f"• Failed to Process: {len(failed_numbers)}\n"
            f"• Unknown Status: {len(unknown_numbers)}\n\n"
            f"⏱ Processing Time: {duration}\n"
            f"🔄 All Chrome instances have been closed\n\n"
            # f"📎 Download your partial results below:"
        )
        
        # Send summary message
        bot_token = bot_application.bot.token
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        data = {
            'chat_id': chat_id,
            'text': summary_text
        }
        response = requests.post(url, data=data, timeout=10)
        
        # Send the partial results file
        url = f"https://api.telegram.org/bot{bot_token}/sendDocument"
        with open(output_file, 'rb') as f:
            files = {'document': f}
            data = {
                'chat_id': chat_id,
                'caption': f"🛑 Partial results for stopped job {job_id} ({processed_count}/{total_requested} processed)"
            }
            requests.post(url, files=files, data=data, timeout=30)
            
        print(f"Partial results sent successfully for stopped job {job_id}")
            
    except Exception as e:
        print(f"Error sending partial results message for job {job_id}: {e}")
        send_simple_message(chat_id, f"🛑 Job {job_id} was stopped, but there was an error sending the partial results.", bot_application)

def send_completion_message_sync(chat_id, job_id, output_file, bot_application):
    """Send completion message with file using direct HTTP requests"""
    try:
        import requests
        
        # Read statistics from output file
        with open(output_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # Parse and categorize phone numbers
        registered_numbers = []
        not_registered_numbers = []
        failed_numbers = []
        unknown_numbers = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # Extract phone number from the line (before the first space or dash)
            parts = line.split(' - ')
            if len(parts) >= 2:
                phone_number = parts[0].strip()
                status = parts[1].strip().lower()
                
                if "registered" in status and "not registered" not in status:
                    registered_numbers.append(phone_number)
                elif "not registered" in status:
                    not_registered_numbers.append(phone_number)
                elif "failed to process" in status:
                    failed_numbers.append(phone_number)
                else:
                    unknown_numbers.append(phone_number)
            else:
                # If format is unexpected, try to extract just the phone number
                phone_number = line.split()[0] if line.split() else line
                unknown_numbers.append(phone_number)
        
        duration = "Unknown"
        if job_id in active_jobs and 'start_time' in active_jobs[job_id] and 'end_time' in active_jobs[job_id]:
            duration_seconds = (active_jobs[job_id]['end_time'] - active_jobs[job_id]['start_time']).total_seconds()
            duration = f"{duration_seconds:.1f} seconds"
        
        summary_text = (
            f"✅ Job {job_id} Completed!\n\n"
            f"📊 Results Summary:\n"
            f"• Already Registered: {len(registered_numbers)}\n"
            f"• Not Registered: {len(not_registered_numbers)}\n"
            f"• Failed to Process: {len(failed_numbers)}\n"
            f"• Unknown Status: {len(unknown_numbers)}\n"
            f"• Total Processed: {len(lines)}\n\n"
            f"⏱ Processing Time: {duration}\n\n"
            # f"📎 Download your results below:"
        )
        
        # Send summary message
        bot_token = bot_application.bot.token
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        data = {
            'chat_id': chat_id,
            'text': summary_text
        }
        response = requests.post(url, data=data, timeout=10)
        
        # Create and send separate files for each category
        base_path = os.path.join(BASE_PATH, "results")
        
        # Send registered numbers file if any
        if registered_numbers:
            registered_file = os.path.join(base_path, f"registered_{job_id}.txt")
            with open(registered_file, 'w', encoding='utf-8') as f:
                for number in registered_numbers:
                    f.write(f"{number}\n")
            
            # Send registered file
            url = f"https://api.telegram.org/bot{bot_token}/sendDocument"
            with open(registered_file, 'rb') as f:
                files = {'document': f}
                data = {
                    'chat_id': chat_id,
                    'caption': f"� {len(registered_numbers)} Registered numbers"
                }
                requests.post(url, files=files, data=data, timeout=30)
            
            # Clean up temp file
            try:
                os.remove(registered_file)
            except:
                pass
        
        # Send not registered numbers file if any
        if not_registered_numbers:
            not_registered_file = os.path.join(base_path, f"not_registered_{job_id}.txt")
            with open(not_registered_file, 'w', encoding='utf-8') as f:
                for number in not_registered_numbers:
                    f.write(f"{number}\n")
            
            # Send not registered file
            url = f"https://api.telegram.org/bot{bot_token}/sendDocument"
            with open(not_registered_file, 'rb') as f:
                files = {'document': f}
                data = {
                    'chat_id': chat_id,
                    'caption': f"📱 {len(not_registered_numbers)} Not Registered numbers"
                }
                requests.post(url, files=files, data=data, timeout=30)
            
            # Clean up temp file
            try:
                os.remove(not_registered_file)
            except:
                pass
            
        print(f"Result files sent successfully for job {job_id}")
            
    except Exception as e:
        print(f"Error sending completion message for job {job_id}: {e}")
        send_simple_message(chat_id, f"✅ Job {job_id} completed, but there was an error sending the results file.", bot_application)

def validate_main_dependencies():
    """Validate that all required functions from main.py are available"""
    try:
        from main import process_phone_batch, save_result_to_file, file_lock
        return True
    except ImportError as e:
        print(f"❌ Error importing required functions from main.py: {e}")
        return False

def process_phone_batch_with_termination(phone_batch, worker_id, config, job_id, delays):
    """Process a batch of phone numbers with termination support and dynamic delays"""
    try:
        # Import the function from main.py but with termination checking
        import concurrent.futures
        import time
        
        print(f"[Worker {worker_id}] Starting batch processing for job {job_id}")
        
        # Check if termination was requested before starting
        if job_id in job_termination_flags and job_termination_flags[job_id].is_set():
            print(f"[Worker {worker_id}] Job {job_id} termination requested before starting")
            return []
        
        # Use the original function but with periodic termination checks
        from main import process_phone_batch
        
        # We'll need to modify this to support termination
        # For now, let's create a simple version that processes one phone at a time
        # and checks for termination between each phone
        
        results = []
        for i, phone in enumerate(phone_batch):
            # Check for termination before processing each phone
            if job_id in job_termination_flags and job_termination_flags[job_id].is_set():
                print(f"[Worker {worker_id}] Job {job_id} termination requested, stopping at phone {i+1}/{len(phone_batch)}")
                break
            
            # Process single phone (we'll need to modify main.py to support this)
            try:
                # For now, call the batch function with single phone
                single_result = process_phone_batch([phone], worker_id, config, delays)
                results.extend(single_result)
                
                # Small delay and termination check
                time.sleep(0.1)
                if job_id in job_termination_flags and job_termination_flags[job_id].is_set():
                    print(f"[Worker {worker_id}] Job {job_id} termination requested after processing phone {i+1}")
                    break
                    
            except Exception as e:
                print(f"[Worker {worker_id}] Error processing phone {phone}: {e}")
                # Add failed result
                results.append({
                    'phone_number': phone,
                    'success': False,
                    'status': None,
                    'worker_id': worker_id,
                    'index': i
                })
        
        print(f"[Worker {worker_id}] Completed batch processing for job {job_id} - processed {len(results)} phones")
        return results
        
    except Exception as e:
        print(f"[Worker {worker_id}] Error in terminable batch processing: {e}")
        return []

def terminate_job_processes(job_id):
    """Terminate all processes/browsers for a specific job"""
    try:
        print(f"🛑 Terminating processes for job {job_id}")
        
        # Set termination flag
        if job_id in job_termination_flags:
            job_termination_flags[job_id].set()
        
        # Kill any browser processes (this is a fallback - browsers should close gracefully)
        try:
            import psutil
            import subprocess
            
            # Kill Chrome processes that might be stuck
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    if proc.info['name'] and 'chrome' in proc.info['name'].lower():
                        # Check if it's related to our worker
                        if proc.info['cmdline']:
                            cmdline = ' '.join(proc.info['cmdline'])
                            if f'proxy_auth_extension_worker_' in cmdline:
                                print(f"🔍 Found Chrome process: {proc.info['pid']}")
                                proc.terminate()
                                proc.wait(timeout=3)
                                print(f"✅ Terminated Chrome process: {proc.info['pid']}")
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired):
                    pass
        except ImportError:
            print("⚠️ psutil not available - cannot force-kill Chrome processes")
            # Fallback: use taskkill on Windows
            try:
                import subprocess
                subprocess.run(["taskkill", "/f", "/im", "chrome.exe"], capture_output=True)
                print("🔧 Used taskkill as fallback to close Chrome")
            except:
                print("⚠️ Could not force-close Chrome processes")
        
        # Clean up proxy files for this job
        try:
            import shutil
            proxy_files_dir = os.path.join(BASE_PATH, "proxy_files")
            if os.path.exists(proxy_files_dir):
                for item in os.listdir(proxy_files_dir):
                    if f"worker_" in item:
                        item_path = os.path.join(proxy_files_dir, item)
                        if os.path.isdir(item_path):
                            shutil.rmtree(item_path)
                            print(f"🧹 Cleaned up proxy extension: {item}")
        except Exception as e:
            print(f"⚠️ Error cleaning proxy files: {e}")
        
        print(f"✅ Process termination completed for job {job_id}")
        
    except Exception as e:
        print(f"❌ Error terminating job processes: {e}")

def process_doctolib_job_with_config(phone_batch, worker_id, config, job_id):
    """Process a batch of phone numbers with custom config - wrapper for main.py function"""
    # Import the process_phone_batch function from main.py
    from main import process_phone_batch
    return process_phone_batch(phone_batch, worker_id, config)

def process_doctolib_job(job_id, user_id, phone_numbers_file, chat_id, bot_application):
    """Run the Doctolib bot processing in a separate thread"""
    try:
        print(f"Starting job {job_id} for user {user_id}")
        
        # Validate main.py dependencies first
        if not validate_main_dependencies():
            raise Exception("Required dependencies from main.py are not available")
        
        # Load base config to check display requirements
        config = load_config()
        
        # Check virtual display requirements before starting job
        display_ok, display_msg = check_virtual_display_requirements(config)
        print(f"🖥️ Virtual display check: {display_msg}")
        
        if not display_ok:
            error_msg = f"❌ Virtual display setup failed: {display_msg}"
            print(error_msg)
            
            # Update job status
            active_jobs[job_id]['status'] = 'failed'
            active_jobs[job_id]['error'] = display_msg
            active_jobs[job_id]['end_time'] = datetime.now()
            
            # Send error message to user
            send_simple_message(chat_id, f"❌ Job {job_id} failed to start:\n{display_msg}\n\n"
                                        f"💡 Solutions:\n"
                                        f"1. Run setup script: ./setup_virtual_display.sh\n"
                                        f"2. Enable headless mode in config\n"
                                        f"3. Install Xvfb: sudo apt install xvfb", bot_application)
            return
        
        # Ensure virtual display is running if needed
        if platform.system() == "Linux" and not config.get('browser', {}).get('headless', True):
            if not ensure_virtual_display():
                error_msg = "Failed to start virtual display"
                print(f"❌ {error_msg}")
                
                # Update job status
                active_jobs[job_id]['status'] = 'failed'
                active_jobs[job_id]['error'] = error_msg
                active_jobs[job_id]['end_time'] = datetime.now()
                
                send_simple_message(chat_id, f"❌ Job {job_id} failed: {error_msg}\n"
                                            f"💡 Try enabling headless mode or run setup script", bot_application)
                return
        
        # Create termination flag for this job
        job_termination_flags[job_id] = threading.Event()
        job_processes[job_id] = []
        
        # Update job status
        active_jobs[job_id]['status'] = 'processing'
        active_jobs[job_id]['start_time'] = datetime.now()
        
        # Send processing started message using a simple approach
        def send_start_message():
            try:
                import requests
                # Use direct HTTP request to avoid event loop issues
                bot_token = bot_application.bot.token
                url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
                data = {
                    'chat_id': chat_id,
                    'text': f"🔄 Processing started for job {job_id}\n"
                           f"📱 Processing {len(active_jobs[job_id]['phone_numbers'])} phone numbers...\n"
                           f"⏰ This may take several minutes depending on the number of phones."
                }
                response = requests.post(url, data=data, timeout=10)
                if response.status_code == 200:
                    print(f"Start message sent successfully for job {job_id}")
                else:
                    print(f"Failed to send start message: {response.status_code}")
            except Exception as e:
                print(f"Error sending start message: {e}")
        
        send_start_message()
        
        # Load base config without modifying the global config file
        config = load_config()
        
        # Ensure proxy configuration compatibility
        config = ensure_proxy_config_compatibility(config)
        
        # Print multiprocessing configuration that will be used
        phone_count = len(active_jobs[job_id]['phone_numbers'])
        if config['multiprocessing']['enabled']:
            max_workers = config['multiprocessing']['max_workers']
            phones_per_worker = config['multiprocessing']['phones_per_worker']
            estimated_batches = (phone_count + phones_per_worker - 1) // phones_per_worker
            actual_workers = min(max_workers, estimated_batches)
            
            print(f"Job {job_id} multiprocessing configuration:")
            print(f"  📱 Total phones: {phone_count}")
            print(f"  🔧 Max workers: {max_workers}")
            print(f"  📦 Phones per worker: {phones_per_worker}")
            print(f"  🎯 Estimated batches: {estimated_batches}")
            print(f"  ⚡ Actual workers to use: {actual_workers}")
        else:
            print(f"Job {job_id} will run in single-process mode (multiprocessing disabled)")
        
        # Ensure results directory exists
        results_dir = os.path.join(BASE_PATH, 'results')
        os.makedirs(results_dir, exist_ok=True)
        
        # Create job-specific filenames
        job_phone_file = os.path.join(BASE_PATH, "results", f"phone_numbers_{job_id}.txt")
        job_output_file = os.path.join(BASE_PATH, "results", f"downloadable_{job_id}.txt")
        
        # Copy user's phone numbers to job-specific file
        shutil.copy2(phone_numbers_file, job_phone_file)
        
        # Get phone numbers for this job
        phone_numbers = active_jobs[job_id]['phone_numbers']
        
        # Create job-specific config without modifying global config
        job_config = config.copy()
        job_config['files']['phone_numbers_file'] = f"results/phone_numbers_{job_id}.txt"
        job_config['files']['output_file'] = f"results/downloadable_{job_id}.txt"
        
        # Apply intelligent scaling for this job
        total_phones = len(phone_numbers)
        print(f"🧠 Applying intelligent scaling for {total_phones:,} phone numbers...")
        
        if job_config['multiprocessing'].get('auto_scale', True):
            optimal_workers, optimal_phones_per_worker = calculate_optimal_workers_and_batch_size(total_phones)
            
            # Apply safety limits
            max_worker_limit = job_config['multiprocessing'].get('max_worker_limit', 130)
            optimal_workers = min(optimal_workers, max_worker_limit)
            
            # Override config with optimal values
            job_config['multiprocessing']['max_workers'] = optimal_workers
            job_config['multiprocessing']['phones_per_worker'] = optimal_phones_per_worker
            
            print(f"✅ Auto-scaling applied:")
            print(f"   🤖 Workers: {optimal_workers} (limit: {max_worker_limit})")
            print(f"   📱 Phones per worker: {optimal_phones_per_worker}")
            
            # Update active job info
            active_jobs[job_id]['auto_scaled'] = True
            active_jobs[job_id]['optimal_workers'] = optimal_workers
            active_jobs[job_id]['optimal_phones_per_worker'] = optimal_phones_per_worker
        
        # Calculate dynamic delays based on dataset size
        delays = calculate_dynamic_delays(total_phones)
        active_jobs[job_id]['delays'] = delays
        
        # Debug: Print the full paths being used
        print(f"🔍 Debug - Job {job_id} file paths:")
        print(f"   Phone file: {job_phone_file}")
        print(f"   Output file: {job_output_file}")
        print(f"   Config output: {job_config['files']['output_file']}")
        print(f"   Full output path: {os.path.join(BASE_PATH, job_config['files']['output_file'])}")
        
        # Process using the same logic as main.py but with isolated config and termination support
        if job_config['multiprocessing']['enabled']:
            import concurrent.futures
            
            # Split phone numbers into batches
            phones_per_worker = job_config['multiprocessing']['phones_per_worker']
            phone_batches = [phone_numbers[i:i+phones_per_worker] for i in range(0, len(phone_numbers), phones_per_worker)]
            
            print(f"📦 Split {len(phone_numbers)} phone numbers into {len(phone_batches)} batches")
            
            # Clear the output file at the start
            with shared_file_lock:
                try:
                    with open(job_output_file, 'w', encoding='utf-8') as f:
                        f.write("")  # Clear the file
                    print(f"Cleared {job_output_file} for fresh start")
                except Exception as e:
                    print(f"Could not clear {job_output_file}: {e}")
            
            # Process batches using ThreadPoolExecutor with termination support
            with concurrent.futures.ThreadPoolExecutor(max_workers=job_config['multiprocessing']['max_workers']) as executor:
                # Submit all batches with termination support
                future_to_batch = {
                    executor.submit(process_phone_batch_with_termination, batch, i, job_config, job_id, delays): i 
                    for i, batch in enumerate(phone_batches)
                }
                
                # Process completed futures and save results
                completed_batches = 0
                total_batches = len(phone_batches)
                
                for future in concurrent.futures.as_completed(future_to_batch):
                    batch_id = future_to_batch[future]
                    
                    # Check if termination was requested
                    if job_id in job_termination_flags and job_termination_flags[job_id].is_set():
                        print(f"🛑 Job {job_id} termination detected, canceling remaining batches")
                        # Cancel remaining futures
                        for f in future_to_batch:
                            if not f.done():
                                f.cancel()
                        break
                    
                    try:
                        worker_results = future.result(timeout=5)  # 5 second timeout for getting results
                        completed_batches += 1
                        print(f"✅ Batch {batch_id + 1}/{total_batches} completed with {len(worker_results)} results")
                        
                        # Save results to job-specific file using direct file writing
                        for result in worker_results:
                            # Use direct file writing instead of save_result_to_file to ensure it goes to the right place
                            phone_number = result['phone_number']
                            success = result['success']
                            status = result['status']
                            worker_id = result['worker_id']
                            
                            with shared_file_lock:  # Use the shared file lock
                                try:
                                    with open(job_output_file, 'a', encoding='utf-8') as f:
                                        if success:
                                            if status == 'registered':
                                                f.write(f"{phone_number} - Registered (Worker {worker_id})\n")
                                                print(f"[Job {job_id}][Worker {worker_id}] ✓ REGISTERED: {phone_number}")
                                            elif status == 'not_registered':
                                                f.write(f"{phone_number} - Not Registered (Worker {worker_id})\n")
                                                print(f"[Job {job_id}][Worker {worker_id}] ✗ NOT REGISTERED: {phone_number}")
                                            else:
                                                f.write(f"{phone_number} - Unknown Status (Worker {worker_id})\n")
                                                print(f"[Job {job_id}][Worker {worker_id}] ? UNKNOWN STATUS: {phone_number}")
                                        else:
                                            f.write(f"{phone_number} - Failed to Process (Worker {worker_id})\n")
                                            print(f"[Job {job_id}][Worker {worker_id}] ✗ FAILED to process {phone_number}")
                                except Exception as e:
                                    print(f"[Job {job_id}][Worker {worker_id}] Error saving result for {phone_number}: {e}")
                            
                    except concurrent.futures.TimeoutError:
                        print(f"⏰ Batch {batch_id + 1} timed out")
                    except Exception as exc:
                        print(f"❌ Batch {batch_id + 1} generated an exception: {exc}")
                
                # Check if job was terminated
                was_terminated = job_id in job_termination_flags and job_termination_flags[job_id].is_set()
                if was_terminated:
                    print(f"🛑 Job {job_id} was terminated by user. Processed {completed_batches}/{total_batches} batches")
                    active_jobs[job_id]['status'] = 'stopped'
                    active_jobs[job_id]['error'] = f'Stopped by user - processed {completed_batches}/{total_batches} batches'
                else:
                    print(f"✅ Job {job_id} completed normally. Processed {completed_batches}/{total_batches} batches")
        else:
            print("Single-process mode not implemented in this version. Please enable multiprocessing in config.json")
            raise Exception("Single-process mode not supported")
        
        # Update job status based on completion or termination
        was_terminated = job_id in job_termination_flags and job_termination_flags[job_id].is_set()
        
        if not was_terminated and job_id in active_jobs and active_jobs[job_id]['status'] != 'stopped':
            active_jobs[job_id]['status'] = 'completed'
        
        active_jobs[job_id]['end_time'] = datetime.now()
        active_jobs[job_id]['output_file'] = job_output_file
        
        # Terminate any remaining processes
        terminate_job_processes(job_id)
        
        # Check if output file was created and send appropriate message
        if os.path.exists(job_output_file):
            if was_terminated or active_jobs[job_id]['status'] == 'stopped':
                # Send partial results message
                send_partial_results_message_sync(chat_id, job_id, job_output_file, bot_application)
            else:
                # Send completion message with file
                send_completion_message_sync(chat_id, job_id, job_output_file, bot_application)
        else:
            # Send error message
            send_simple_message(chat_id, f"❌ Job {job_id} completed but no output file was generated.\n"
                                       f"This might indicate an error during processing.", bot_application)
        
        # Cleanup temporary files
        cleanup_job_files(job_id)
        
    except Exception as e:
        print(f"Error in job {job_id}: {e}")
        
        # Terminate processes in case of error
        terminate_job_processes(job_id)
        
        # Check if it was a user termination or actual error
        was_terminated = job_id in job_termination_flags and job_termination_flags[job_id].is_set()
        
        if was_terminated:
            # Don't mark as failed if user requested termination
            if job_id in active_jobs:
                active_jobs[job_id]['status'] = 'stopped'
                active_jobs[job_id]['error'] = 'Stopped by user request'
        else:
            # Actual error occurred
            if job_id in active_jobs:
                active_jobs[job_id]['status'] = 'failed'
                active_jobs[job_id]['error'] = str(e)
            
            # Send error message
            send_simple_message(chat_id, f"❌ Job {job_id} failed with error:\n{str(e)}", bot_application)
        
        # Cleanup temporary files
        cleanup_job_files(job_id)
    
    finally:
        # Always clean up termination flags and process references
        if job_id in job_termination_flags:
            del job_termination_flags[job_id]
        if job_id in job_processes:
            del job_processes[job_id]

async def send_completion_message(chat_id, job_id, output_file, bot_application):
    """Send completion message with the result file"""
    try:
        # Read some statistics from the output file
        with open(output_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        registered_count = sum(1 for line in lines if "Registered" in line and "Not Registered" not in line)
        not_registered_count = sum(1 for line in lines if "Not Registered" in line)
        failed_count = sum(1 for line in lines if "Failed to Process" in line)
        unknown_count = sum(1 for line in lines if "Unknown Status" in line)
        
        duration = "Unknown"
        if job_id in active_jobs and 'start_time' in active_jobs[job_id] and 'end_time' in active_jobs[job_id]:
            duration_seconds = (active_jobs[job_id]['end_time'] - active_jobs[job_id]['start_time']).total_seconds()
            duration = f"{duration_seconds:.1f} seconds"
        
        summary_text = (
            f"✅ *Job {job_id} Completed!*\n\n"
            f"📊 *Results Summary:*\n"
            f"• Already Registered: {registered_count}\n"
            f"• Not Registered: {not_registered_count}\n"
            f"• Failed to Process: {failed_count}\n"
            f"• Unknown Status: {unknown_count}\n"
            f"• Total Processed: {len(lines)}\n\n"
            f"⏱ *Processing Time:* {duration}\n\n"
            # f"📎 *Download your results below:*"
        )
        
        # Send summary message
        await bot_application.bot.send_message(
            chat_id=chat_id,
            text=summary_text,
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Send the file
        with open(output_file, 'rb') as f:
            await bot_application.bot.send_document(
                chat_id=chat_id,
                document=f,
                filename=f"doctolib_results_{job_id}.txt",
                caption=f"📄 Doctolib processing results for job {job_id}"
            )
        
    except Exception as e:
        print(f"Error sending completion message for job {job_id}: {e}")
        await bot_application.bot.send_message(
            chat_id=chat_id,
            text=f"✅ Job {job_id} completed, but there was an error sending the results file. Please contact support."
        )

def cleanup_job_files(job_id):
    """Clean up temporary files for a completed job"""
    try:
        files_to_cleanup = [
            os.path.join(BASE_PATH, "results", f"phone_numbers_{job_id}.txt"),
            os.path.join(BASE_PATH, "results", f"downloadable_{job_id}.txt")
            # Removed config backup files since we no longer use unsafe config manipulation
        ]
        
        for file_path in files_to_cleanup:
            if os.path.exists(file_path):
                os.remove(file_path)
                print(f"Cleaned up: {file_path}")
        
        # Mark job for cleanup - the scheduled cleanup will remove it from memory
        if job_id in active_jobs:
            active_jobs[job_id]['cleaned_files'] = True
        
    except Exception as e:
        print(f"Error cleaning up files for job {job_id}: {e}")

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /start command"""
    welcome_message = (
        "🤖 *Welcome to Doctolib Phone Number Checker Bot!*\n\n"
        "This bot helps you check if phone numbers are registered with Doctolib.\n\n"
        "📋 *How to use:*\n"
        "1. Send me a text file named `phone_numbers.txt`\n"
        "2. The file should contain one phone number per line\n"
        "3. I'll process all numbers and send you the results\n\n"
        "📁 *Commands:*\n"
        "• /start - Show this welcome message\n"
        "• /status - Check current job status\n"
        # "• /download - Download current/partial results\n"
        "• /stop - Stop running job process\n"
        "• /help - Get detailed help\n\n"
        "📤 *Ready to start? Send me your phone_numbers.txt file!*"
    )
    
    await update.message.reply_text(welcome_message, parse_mode=ParseMode.MARKDOWN)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /help command"""
    # Check if we're on Linux to show display commands
    display_commands = ""
    if platform.system() == "Linux" and VIRTUAL_DISPLAY_AVAILABLE:
        display_commands = (
            "\n*Virtual Display (Linux only):*\n"
            "• `/display` - Show virtual display status\n"
            "• `/display start` - Start virtual display\n"
            "• `/display stop` - Stop virtual display\n"
            "• `/display restart` - Restart virtual display\n"
        )
    
    help_message = (
        "📖 *Detailed Help - Doctolib Phone Checker*\n\n"
        "*File Format:*\n"
        "• Upload a `.txt` file with phone numbers\n"
        "• One phone number per line\n"
        "• Supported formats: +49..., 0049..., etc.\n\n"
        "*Example file content:*\n"
        "```\n"
        "+4917612345678\n"
        "+4915987654321\n"
        "+4916123456789\n"
        "```\n\n"
        "*Processing:*\n"
        "• The bot will check each number with Doctolib\n"
        "• Processing time depends on the number of phones\n"
        "• You'll receive updates during processing\n\n"
        "*Results:*\n"
        "• You'll get a downloadable.txt file with results\n"
        "• Each number will be marked as:\n"
        "  - ✅ Registered\n"
        "  - ❌ Not Registered\n"
        "  - ❓ Unknown Status\n"
        "  - ⚠️ Failed to Process\n\n"
        "*Limits:*\n"
        "• Maximum 20000000 phone numbers per request\n"
        "• One job at a time per user\n\n"
        "*Commands:*\n"
        "• `/start` - Show welcome message\n"
        "• `/status` - Check job status and progress\n"
        # "• `/download` - Get current results (even if job is still running)\n"
        "• `/stop` - Stop your running job and get partial results\n"
        "• `/help` - Show this help message\n"
        f"{display_commands}\n"
        "Need more help? Contact support."
    )
    
    await update.message.reply_text(help_message, parse_mode=ParseMode.MARKDOWN)

async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /stop command"""
    user_id = update.effective_user.id
    
    # Find user's active jobs
    user_active_jobs = [job for job_id, job in active_jobs.items() 
                       if job['user_id'] == user_id and job['status'] in ['waiting', 'processing']]
    
    if not user_active_jobs:
        await update.message.reply_text("📭 You have no active jobs to stop.")
        return
    
    stopped_jobs = []
    for job in user_active_jobs:
        job_id = job['job_id']
        
        # Set termination flag
        if job_id in job_termination_flags:
            job_termination_flags[job_id].set()
            print(f"🛑 Termination requested for job {job_id}")
        
        # Mark job as failed with stop reason
        active_jobs[job_id]['status'] = 'stopped'
        active_jobs[job_id]['end_time'] = datetime.now()
        active_jobs[job_id]['error'] = 'Stopped by user request'
        
        stopped_jobs.append(job_id)
    
    if len(stopped_jobs) == 1:
        await update.message.reply_text(
            f"🛑 *Job {stopped_jobs[0]} Stop Requested*\n\n"
            "⏳ The job is being terminated...\n"
            "🔄 Chrome instances are being closed...\n"
            "📁 You'll receive any partial results shortly.",
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        job_list = '\n'.join([f"• {job_id}" for job_id in stopped_jobs])
        await update.message.reply_text(
            f"🛑 *Stop Requested for {len(stopped_jobs)} Jobs*\n\n"
            f"{job_list}\n\n"
            "⏳ All jobs are being terminated...\n"
            "🔄 Chrome instances are being closed...\n"
            "📁 You'll receive any partial results shortly.",
            parse_mode=ParseMode.MARKDOWN
        )

async def download_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /download command to get partial results"""
    user_id = update.effective_user.id
    
    # Find user's jobs (including active ones)
    user_jobs = [job for job_id, job in active_jobs.items() if job['user_id'] == user_id]
    
    if not user_jobs:
        await update.message.reply_text("📭 You have no jobs to download results from.")
        return
    
    # Find the most recent job
    recent_job = max(user_jobs, key=lambda x: x.get('created_time', datetime.min))
    job_id = recent_job['job_id']
    
    # Check if there's a partial or complete output file
    job_output_file = os.path.join(BASE_PATH, "results", f"downloadable_{job_id}.txt")
    
    # Debug: Print file information
    print(f"🔍 Debug - Download command for job {job_id}:")
    print(f"   Looking for file: {job_output_file}")
    print(f"   File exists: {os.path.exists(job_output_file)}")
    if os.path.exists(job_output_file):
        file_size = os.path.getsize(job_output_file)
        print(f"   File size: {file_size} bytes")
    
    if not os.path.exists(job_output_file):
        await update.message.reply_text(
            f"📄 No results file found for job {job_id}.\n"
            f"Expected location: {job_output_file}\n"
            "The processing may not have started yet or no results have been generated."
        )
        return
    
    try:
        # Read the current results
        with open(job_output_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        if not lines:
            await update.message.reply_text(
                f"📄 Results file for job {job_id} is empty.\n"
                "Processing may have just started."
            )
            return
        
        # Parse results for summary
        registered_count = sum(1 for line in lines if "registered" in line.lower() and "not registered" not in line.lower())
        not_registered_count = sum(1 for line in lines if "not registered" in line.lower())
        failed_count = sum(1 for line in lines if "failed to process" in line.lower())
        
        status = recent_job['status']
        if status == 'processing':
            status_text = "🔄 In Progress"
        elif status == 'completed':
            status_text = "✅ Completed"
        elif status == 'stopped':
            status_text = "🛑 Stopped"
        elif status == 'failed':
            status_text = "❌ Failed"
        else:
            status_text = f"❓ {status.title()}"
        
        total_phones = len(recent_job['phone_numbers'])
        processed_count = len(lines)
        progress = (processed_count / total_phones * 100) if total_phones > 0 else 0
        
        summary_text = (
            f"📊 *Download Results - Job {job_id}*\n\n"
            f"🎯 *Status:* {status_text}\n"
            f"📈 *Progress:* {processed_count}/{total_phones} ({progress:.1f}%)\n\n"
            f"📊 *Current Results:*\n"
            f"• ✅ Registered: {registered_count}\n"
            f"• ❌ Not Registered: {not_registered_count}\n"
            f"• ⚠️ Failed: {failed_count}\n\n"
            f"📎 *Downloading current results...*"
        )
        
        # Send summary
        await update.message.reply_text(summary_text, parse_mode=ParseMode.MARKDOWN)
        
        # Send the file
        with open(job_output_file, 'rb') as f:
            filename = f"doctolib_partial_{job_id}.txt" if status == 'processing' else f"doctolib_results_{job_id}.txt"
            await update.message.reply_document(
                document=f,
                filename=filename,
                caption=f"📄 Results for job {job_id} ({status_text})"
            )
        
    except Exception as e:
        print(f"Error in download command: {e}")
        await update.message.reply_text(
            f"❌ Error downloading results: {str(e)}",
            parse_mode=ParseMode.MARKDOWN
        )

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /status command"""
    user_id = update.effective_user.id
    
    # Find user's active jobs
    user_jobs = [job for job_id, job in active_jobs.items() if job['user_id'] == user_id]
    
    if not user_jobs:
        await update.message.reply_text("📭 You have no active jobs.")
        return
    
    status_message = "📊 *Your Active Jobs:*\n\n"
    
    for job in user_jobs:
        job_id = job['job_id']
        status = job['status']
        phone_count = len(job['phone_numbers'])
        
        if status == 'waiting':
            status_emoji = "⏳"
            status_text = "Waiting to start"
        elif status == 'processing':
            status_emoji = "🔄"
            if 'start_time' in job:
                elapsed = (datetime.now() - job['start_time']).total_seconds()
                status_text = f"Processing ({elapsed:.0f}s elapsed)"
            else:
                status_text = "Processing"
        elif status == 'completed':
            status_emoji = "✅"
            status_text = "Completed"
        elif status == 'failed':
            status_emoji = "❌"
            error = job.get('error', 'Unknown error')
            status_text = f"Failed: {error}"
        else:
            status_emoji = "❓"
            status_text = f"Unknown: {status}"
        
        status_message += (
            f"{status_emoji} *Job {job_id}*\n"
            f"• Status: {status_text}\n"
            f"• Phone Numbers: {phone_count}\n\n"
        )
    
    await update.message.reply_text(status_message, parse_mode=ParseMode.MARKDOWN)

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle uploaded documents"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    # Check if user already has an active job
    user_active_jobs = [job for job in active_jobs.values() if job['user_id'] == user_id and job['status'] in ['waiting', 'processing']]
    if user_active_jobs:
        await update.message.reply_text(
            "⚠️ You already have an active job running. Please wait for it to complete before starting a new one.\n"
            "Use /status to check your current job status."
        )
        return
    
    document: Document = update.message.document
    
    # Check file type and name
    if not document.file_name.endswith('.txt'):
        await update.message.reply_text(
            "❌ Please upload a .txt file containing phone numbers.\n"
            "The file should contain one phone number per line."
        )
        return
    
    # Check file size (limit to 10MB)
    if document.file_size > 10 * 1024 * 1024:
        await update.message.reply_text(
            "❌ File too large. Please upload a file smaller than 10MB."
        )
        return
    
    try:
        # Download the file
        await update.message.reply_text("📥 Downloading your file...")
        
        file = await context.bot.get_file(document.file_id)
        
        # Create temporary file
        with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.txt') as temp_file:
            await file.download_to_drive(temp_file.name)
            temp_file_path = temp_file.name
        
        # Read and validate phone numbers
        with open(temp_file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # Clean and validate phone numbers
        phone_numbers = []
        for i, line in enumerate(lines):
            phone = line.strip()
            if phone:  # Skip empty lines
                phone_numbers.append(phone)
        
        if not phone_numbers:
            await update.message.reply_text(
                "❌ No valid phone numbers found in the file.\n"
                "Please make sure the file contains one phone number per line."
            )
            os.unlink(temp_file_path)
            return
        
        # Check phone number limit
        if len(phone_numbers) > 20000000:
            await update.message.reply_text(
                f"❌ Too many phone numbers ({len(phone_numbers)}). Maximum allowed is 20000000 per request.\n"
                "Please split your file into smaller batches."
            )
            os.unlink(temp_file_path)
            return
        
        # Create job
        job_id = create_job_id()
        
        # Get multiprocessing info for confirmation
        config = load_config()
        processing_info = ""
        if config['multiprocessing']['enabled']:
            max_workers = config['multiprocessing']['max_workers']
            phones_per_worker = config['multiprocessing']['phones_per_worker']
            estimated_batches = (len(phone_numbers) + phones_per_worker - 1) // phones_per_worker
            actual_workers = min(max_workers, estimated_batches)
            processing_info = f"⚡ *Workers:* {actual_workers} parallel workers\n📦 *Batch size:* {phones_per_worker} phones per worker\n"
        else:
            processing_info = f"🔧 *Processing:* Single-process mode\n"
        
        active_jobs[job_id] = {
            'job_id': job_id,
            'user_id': user_id,
            'chat_id': chat_id,
            'phone_numbers': phone_numbers,
            'status': 'waiting',
            'created_time': datetime.now()
        }
        
        # Send confirmation
        confirmation_message = (
            f"✅ *File received and validated!*\n\n"
            f"📱 *Phone Numbers:* {len(phone_numbers)}\n"
            f"🆔 *Job ID:* {job_id}\n"
            f"{processing_info}"
            f"🚀 Starting processing now...\n"
            # f"⏰ Estimated time: {len(phone_numbers) * 5 // 60 + 1} minutes\n\n"
            f"I'll notify you when the processing is complete!"
        )
        
        await update.message.reply_text(confirmation_message, parse_mode=ParseMode.MARKDOWN)
        
        # Start processing in a separate thread
        processing_thread = threading.Thread(
            target=process_doctolib_job,
            args=(job_id, user_id, temp_file_path, chat_id, context.application),
            daemon=True
        )
        processing_thread.start()
        
    except Exception as e:
        print(f"Error handling document: {e}")
        await update.message.reply_text(
            f"❌ An error occurred while processing your file:\n`{str(e)}`",
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Cleanup
        try:
            os.unlink(temp_file_path)
        except:
            pass

async def display_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle display management command"""
    user_id = update.effective_user.id
    
    if not VIRTUAL_DISPLAY_AVAILABLE:
        await update.message.reply_text(
            "❌ Virtual display management is not available.\n"
            "This feature is only available on Linux servers."
        )
        return
    
    if platform.system() != "Linux":
        await update.message.reply_text(
            "ℹ️ Virtual display is only needed on Linux servers.\n"
            "You're running on Windows/Mac where browsers can display normally."
        )
        return
    
    # Parse command arguments
    args = context.args
    if not args:
        # Show status
        global virtual_display_manager
        if virtual_display_manager is None:
            virtual_display_manager = VirtualDisplayManager()
        
        is_running = virtual_display_manager.is_display_running()
        display_env = os.environ.get('DISPLAY', 'Not set')
        
        status_msg = (
            f"🖥️ *Virtual Display Status*\n\n"
            f"🔍 *Status:* {'✅ Running' if is_running else '❌ Not running'}\n"
            f"📺 *Display:* {virtual_display_manager.display_env}\n"
            f"🔧 *Environment:* {display_env}\n\n"
            f"*Commands:*\n"
            f"• `/display start` - Start virtual display\n"
            f"• `/display stop` - Stop virtual display\n"
            f"• `/display restart` - Restart virtual display\n"
            f"• `/display status` - Show this status"
        )
        
        await update.message.reply_text(status_msg, parse_mode=ParseMode.MARKDOWN)
        return
    
    command = args[0].lower()
    
    if command == "start":
        if ensure_virtual_display():
            await update.message.reply_text("✅ Virtual display started successfully!")
        else:
            await update.message.reply_text(
                "❌ Failed to start virtual display.\n"
                "Make sure Xvfb is installed: `sudo apt install xvfb`"
            )
    
    elif command == "stop":
        cleanup_virtual_display()
        await update.message.reply_text("🛑 Virtual display stopped.")
    
    elif command == "restart":
        cleanup_virtual_display()
        time.sleep(1)
        if ensure_virtual_display():
            await update.message.reply_text("🔄 Virtual display restarted successfully!")
        else:
            await update.message.reply_text("❌ Failed to restart virtual display.")
    
    elif command == "status":
        # Same as no arguments
        await display_command(update, context)
    
    else:
        await update.message.reply_text(
            f"❌ Unknown display command: {command}\n\n"
            f"Available commands:\n"
            f"• start, stop, restart, status"
        )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle text messages"""
    text = update.message.text.lower()
    
    if any(greeting in text for greeting in ['hello', 'hi', 'hey', 'start']):
        await start_command(update, context)
    elif any(help_word in text for help_word in ['help', 'how', 'what']):
        await help_command(update, context)
    elif 'status' in text:
        await status_command(update, context)
    else:
        await update.message.reply_text(
            "🤔 I'm not sure what you mean.\n\n"
            "📎 To get started, please upload a .txt file with phone numbers.\n"
            "💡 Use /help for detailed instructions or /start for a quick overview."
        )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle errors that occur during bot operation"""
    print(f"Update {update} caused error {context.error}")
    
    # Try to send an error message to the user if possible
    if update and update.effective_chat:
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❌ Sorry, an error occurred while processing your request. Please try again."
            )
        except Exception:
            pass  # If we can't send the error message, just continue

def cleanup_proxy_files_on_startup():
    """Clean up any leftover proxy extension files from previous runs"""
    try:
        import shutil
        proxy_files_dir = os.path.join(BASE_PATH, "proxy_files")
        if os.path.exists(proxy_files_dir):
            shutil.rmtree(proxy_files_dir)
            print(f"🧹 Cleaned up leftover proxy_files directory from previous run")
        os.makedirs(proxy_files_dir, exist_ok=True)
        print(f"📁 Created fresh proxy_files directory for bot operations")
        
        # Also clean up any leftover termination flags and process references
        global job_termination_flags, job_processes
        job_termination_flags.clear()
        job_processes.clear()
        print(f"🧹 Cleared leftover job termination flags and process references")
        
    except Exception as e:
        print(f"⚠️ Warning: Could not clean up proxy_files directory: {e}")

def main():
    """Main function to run the Telegram bot"""
    # Validate dependencies first
    if not validate_main_dependencies():
        print("❌ Cannot start Telegram bot - required dependencies missing")
        return
    
    # Clean up any leftover proxy files from previous runs
    cleanup_proxy_files_on_startup()
    
    # Load Telegram configuration
    telegram_config = load_telegram_config()
    if not telegram_config or 'bot_token' not in telegram_config:
        print("Error: Telegram bot token not found in config.json")
        print("Please add the following to your config.json:")
        print("""
{
    "telegram": {
        "bot_token": "YOUR_BOT_TOKEN_HERE"
    }
}
        """)
        return
    
    print("🤖 Starting Telegram Bot...")
    print(f"📂 Base path: {BASE_PATH}")
    print("✅ All dependencies validated successfully")
    
    # Start job cleanup scheduler
    schedule_job_cleanup()
    
    # Create application
    application = ApplicationBuilder().token(telegram_config['bot_token']).build()
    
    # Add error handler
    application.add_error_handler(error_handler)
    
    # Add handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("download", download_command))
    application.add_handler(CommandHandler("stop", stop_command))
    application.add_handler(CommandHandler("display", display_command))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    print("✅ Telegram bot is ready!")
    print("Send /start to your bot to begin.")
    
    # Run the bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
