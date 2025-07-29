"""
Celery integration for telegram_bot.py
This allows the bot to use either threading-based browser automation or Celery-based HTTP requests
"""

import os
import json
import time
import requests
from datetime import datetime
from celery import group
from celery_tasks import check_phone_registration, app as celery_app

def process_phones_with_celery(phone_numbers, job_id, config, chat_id, bot_application):
    """
    Process phone numbers using Celery instead of threading
    This replaces the ThreadPoolExecutor approach with distributed Celery workers
    """
    try:
        print(f"🚀 Starting Celery-based processing for job {job_id}")
        print(f"📱 Processing {len(phone_numbers)} phone numbers with distributed workers")
        
        # Load Celery configuration  
        celery_config = config.get('celery', {})
        batch_size = celery_config.get('batch_size', 10)  # Reduced from 50 to 10 for faster individual processing
        
        # For small jobs (< 100 phones), process individually for maximum speed
        if len(phone_numbers) < 100:
            batch_size = 1
            print(f"🚀 Small job detected - processing individually for maximum speed")
        
        # Split phone numbers into batches for better performance
        phone_batches = [
            phone_numbers[i:i + batch_size] 
            for i in range(0, len(phone_numbers), batch_size)
        ]
        
        print(f"📦 Split into {len(phone_batches)} batches of ~{batch_size} phones each")
        
        # Prepare results file
        results_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'results')
        os.makedirs(results_dir, exist_ok=True)
        job_output_file = os.path.join(results_dir, f"downloadable_{job_id}.txt")
        
        # Clear the output file
        with open(job_output_file, 'w', encoding='utf-8') as f:
            f.write("")
        
        # Create Celery group for parallel execution
        batch_tasks = []
        for batch_idx, phone_batch in enumerate(phone_batches):
            # Create individual tasks for each phone in the batch
            for phone_idx, phone in enumerate(phone_batch):
                task = check_phone_registration.s(
                    phone_number=phone,
                    worker_id=f"celery_{batch_idx}_{phone_idx}",
                    config=config
                )
                batch_tasks.append(task)
        
        # Execute tasks in parallel using Celery group
        print(f"⚡ Submitting {len(batch_tasks)} tasks to Celery workers...")
        task_group = group(batch_tasks)
        group_result = task_group.apply_async()
        
        # Monitor progress and collect results
        total_tasks = len(batch_tasks)
        completed_tasks = 0
        failed_tasks = 0
        
        # Wait for all tasks to complete with progress monitoring
        while not group_result.ready():
            # Count completed tasks
            current_completed = sum(1 for result in group_result.results if result.ready())
            
            if current_completed != completed_tasks:
                completed_tasks = current_completed
                progress = (completed_tasks / total_tasks) * 100
                print(f"📊 Progress: {completed_tasks}/{total_tasks} ({progress:.1f}%)")
                
                # Send progress update to user every 10%
                if completed_tasks % max(1, total_tasks // 10) == 0:
                    send_progress_update(chat_id, job_id, completed_tasks, total_tasks, bot_application)
            
            time.sleep(5)  # Check every 5 seconds
        
        # Collect all results
        print("📋 Collecting results from all workers...")
        results = group_result.get()  # This blocks until all tasks complete
        
        # Process and save results
        registered_count = 0
        not_registered_count = 0
        failed_count = 0
        
        with open(job_output_file, 'w', encoding='utf-8') as f:
            for result in results:
                phone = result['phone_number']
                success = result['success']
                status = result.get('status')
                worker_id = result.get('worker_id', 'unknown')
                
                if success:
                    if status == 'registered':
                        f.write(f"{phone} - Registered (Worker {worker_id})\n")
                        registered_count += 1
                        print(f"[{worker_id}] ✓ REGISTERED: {phone}")
                    elif status == 'not_registered':
                        f.write(f"{phone} - Not Registered (Worker {worker_id})\n")
                        not_registered_count += 1
                        print(f"[{worker_id}] ✗ NOT REGISTERED: {phone}")
                    else:
                        f.write(f"{phone} - Unknown Status (Worker {worker_id})\n")
                        failed_count += 1
                        print(f"[{worker_id}] ? UNKNOWN: {phone}")
                else:
                    f.write(f"{phone} - Failed to Process (Worker {worker_id})\n")
                    failed_count += 1
                    print(f"[{worker_id}] ✗ FAILED: {phone}")
        
        # Return results summary
        return {
            'success': True,
            'total_processed': len(results),
            'registered': registered_count,
            'not_registered': not_registered_count,
            'failed': failed_count,
            'output_file': job_output_file
        }
        
    except Exception as e:
        print(f"❌ Error in Celery processing: {e}")
        return {
            'success': False,
            'error': str(e),
            'output_file': None
        }

def send_progress_update(chat_id, job_id, completed, total, bot_application):
    """Send progress update to user"""
    try:
        progress = (completed / total) * 100
        message = f"🔄 Job {job_id} Progress: {completed}/{total} ({progress:.1f}%)"
        
        # Use direct HTTP request to avoid event loop issues
        bot_token = bot_application.bot.token
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        data = {
            'chat_id': chat_id,
            'text': message
        }
        requests.post(url, data=data, timeout=10)
        
    except Exception as e:
        print(f"Error sending progress update: {e}")

def is_celery_available():
    """Check if Celery workers are available"""
    try:
        from celery_tasks import app
        
        # Check if any workers are active
        inspect = app.control.inspect()
        active_workers = inspect.active()
        
        if active_workers:
            worker_count = len(active_workers)
            print(f"✅ Found {worker_count} active Celery workers")
            return True
        else:
            print("⚠️ No active Celery workers found")
            return False
            
    except Exception as e:
        print(f"❌ Celery not available: {e}")
        return False

def get_processing_mode(config):
    """Determine which processing mode to use based on configuration and availability"""
    
    # Check user preference in config
    processing_mode = config.get('processing_mode', 'auto')
    
    if processing_mode == 'celery':
        if is_celery_available():
            return 'celery'
        else:
            print("⚠️ Celery requested but not available, falling back to threading")
            return 'threading'
    
    elif processing_mode == 'threading':
        return 'threading'
    
    else:  # auto mode
        if is_celery_available():
            print("🚀 Auto-detected: Using Celery for better performance")
            return 'celery'
        else:
            print("🔄 Auto-detected: Using threading (browser automation)")
            return 'threading'
