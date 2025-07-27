import os
import json
import time
import threading
import tempfile
import platform
from datetime import datetime
from telegram import Update, Document
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode
import tempfile
import shutil
from main import main as run_doctolib_bot, load_config, get_base_path

# Global file lock for config operations
config_file_lock = threading.Lock()

def safe_config_operation(job_id, config, operation_func):
    """Safely perform config file operations with proper locking"""
    config_file_path = os.path.join(BASE_PATH, 'config.json')
    backup_file_path = os.path.join(BASE_PATH, f'config_backup_{job_id}.json')
    temp_config_path = os.path.join(BASE_PATH, f'config_temp_{job_id}.json')
    
    with config_file_lock:
        try:
            # Create backup of original config
            shutil.copy2(config_file_path, backup_file_path)
            
            # Create temporary config for this job
            with open(temp_config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4)
            
            # Atomically replace the config file
            if platform.system() == "Windows":
                # On Windows, we need to remove the target file first
                if os.path.exists(config_file_path):
                    os.remove(config_file_path)
                shutil.move(temp_config_path, config_file_path)
            else:
                # On Unix systems, move is atomic
                shutil.move(temp_config_path, config_file_path)
            
            try:
                # Run the operation
                result = operation_func()
                return result
            finally:
                # Always restore the original config
                if os.path.exists(backup_file_path):
                    if platform.system() == "Windows":
                        if os.path.exists(config_file_path):
                            os.remove(config_file_path)
                        shutil.move(backup_file_path, config_file_path)
                    else:
                        shutil.move(backup_file_path, config_file_path)
                
        except Exception as e:
            # Restore backup if something went wrong
            try:
                if os.path.exists(backup_file_path):
                    if platform.system() == "Windows":
                        if os.path.exists(config_file_path):
                            os.remove(config_file_path)
                        shutil.move(backup_file_path, config_file_path)
                    else:
                        shutil.move(backup_file_path, config_file_path)
            except:
                pass
            raise e
        finally:
            # Clean up temporary files
            for temp_file in [temp_config_path, backup_file_path]:
                try:
                    if os.path.exists(temp_file):
                        os.remove(temp_file)
                except:
                    pass

# Global variables for job tracking
active_jobs = {}
job_counter = 0
job_lock = threading.Lock()

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
            f"📎 Download your results below:"
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

def process_doctolib_job(job_id, user_id, phone_numbers_file, chat_id, bot_application):
    """Run the Doctolib bot processing in a separate thread"""
    try:
        print(f"Starting job {job_id} for user {user_id}")
        
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
        
        # Temporarily replace the phone numbers file
        config = load_config()
        
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
        
        # Update config to use job-specific files
        job_config = config.copy()
        job_config['files']['phone_numbers_file'] = f"results/phone_numbers_{job_id}.txt"
        job_config['files']['output_file'] = f"results/downloadable_{job_id}.txt"
        
        # Use safe config operation
        def run_bot():
            return run_doctolib_bot()
        
        safe_config_operation(job_id, job_config, run_bot)
        
        # Update job status
        active_jobs[job_id]['status'] = 'completed'
        active_jobs[job_id]['end_time'] = datetime.now()
        active_jobs[job_id]['output_file'] = job_output_file
        
        # Check if output file was created
        if os.path.exists(job_output_file):
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
        active_jobs[job_id]['status'] = 'failed'
        active_jobs[job_id]['error'] = str(e)
        
        # Send error message
        send_simple_message(chat_id, f"❌ Job {job_id} failed with error:\n{str(e)}", bot_application)
        
        # Cleanup temporary files
        cleanup_job_files(job_id)

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
            f"📎 *Download your results below:*"
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
            os.path.join(BASE_PATH, "results", f"downloadable_{job_id}.txt"),
            os.path.join(BASE_PATH, f"config_backup_{job_id}.json"),
            os.path.join(BASE_PATH, f"config_temp_{job_id}.json")
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
        "• /help - Get detailed help\n\n"
        "📤 *Ready to start? Send me your phone_numbers.txt file!*"
    )
    
    await update.message.reply_text(welcome_message, parse_mode=ParseMode.MARKDOWN)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /help command"""
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
        "• Maximum 100 phone numbers per request\n"
        "• One job at a time per user\n\n"
        "Need more help? Contact support."
    )
    
    await update.message.reply_text(help_message, parse_mode=ParseMode.MARKDOWN)

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

def main():
    """Main function to run the Telegram bot"""
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
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    print("✅ Telegram bot is ready!")
    print("Send /start to your bot to begin.")
    
    # Run the bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
