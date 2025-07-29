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
        
        # ALWAYS process individually for maximum speed - one worker per phone
        batch_size = 1
        print(f"🚀 Maximum speed mode: 1 worker per phone number")
        
        # Each phone gets its own task for parallel processing
        phone_batches = [
            [phone] for phone in phone_numbers  # Each "batch" contains exactly 1 phone
        ]
        
        print(f"⚡ Creating {len(phone_batches)} individual tasks for {len(phone_numbers)} phones")
        print(f"🎯 Target: {len(phone_numbers)} workers processing simultaneously")
        
        # Prepare results file
        results_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'results')
        os.makedirs(results_dir, exist_ok=True)
        job_output_file = os.path.join(results_dir, f"downloadable_{job_id}.txt")
        
        # Configure output file in config for tasks to use
        config['files'] = config.get('files', {})
        config['files']['output_file'] = f"results/downloadable_{job_id}.txt"
        
        # Clear the output file
        with open(job_output_file, 'w', encoding='utf-8') as f:
            f.write("")
        
        print(f"📝 Results will be written to: {job_output_file}")
        print(f"🔍 Config output file: {config['files']['output_file']}")
        
        # Create individual Celery tasks - one per phone number
        batch_tasks = []
        for phone_idx, phone_batch in enumerate(phone_batches):
            # Each batch contains exactly 1 phone
            phone = phone_batch[0]
            task = check_phone_registration.s(
                phone_number=phone,
                proxy_info=None,  # Add proxy support later
                config=config     # Pass the full config with output file
            )
            batch_tasks.append(task)
        
        # Execute ALL tasks in parallel using Celery group
        print(f"⚡ Submitting {len(batch_tasks)} individual tasks to 100 Celery workers...")
        print(f"🎯 Each phone gets its own worker for maximum parallel processing")
        print(f"🔍 Debug: Total tasks created: {len(batch_tasks)}")
        print(f"🔍 Debug: Celery app: {celery_app}")
        print(f"🔍 Debug: Target completion time: 2-3 minutes")
        
        task_group = group(batch_tasks)
        group_result = task_group.apply_async()
        
        print(f"✅ Task group submitted successfully. Group ID: {group_result.id}")
        print(f"📋 Individual task IDs: {[r.id for r in group_result.results[:3]]}{'...' if len(group_result.results) > 3 else ''}")
        
        # Monitor progress and collect results
        total_tasks = len(batch_tasks)
        completed_tasks = 0
        failed_tasks = 0
        
        # Wait for all tasks to complete with progress monitoring
        start_time = time.time()
        last_check_time = start_time
        
        while not group_result.ready():
            # Count completed tasks
            current_completed = sum(1 for result in group_result.results if result.ready())
            
            if current_completed != completed_tasks:
                completed_tasks = current_completed
                progress = (completed_tasks / total_tasks) * 100
                elapsed = time.time() - start_time
                rate = completed_tasks / elapsed if elapsed > 0 else 0
                eta = (total_tasks - completed_tasks) / rate if rate > 0 else 0
                
                print(f"⚡ ULTRA-FAST: {completed_tasks}/{total_tasks} ({progress:.1f}%) - {rate:.1f}/s - ETA: {eta:.0f}s")
                
                # Check if new results are being written to file
                if os.path.exists(job_output_file):
                    with open(job_output_file, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                    print(f"📄 Results file: {len(lines)} phones completed")
                
                # Send progress update to user every 5 completions for real-time feedback
                if completed_tasks % 5 == 0:
                    send_progress_update(chat_id, job_id, completed_tasks, total_tasks, bot_application)
            
            time.sleep(1)  # Check every 1 second for ultra-fast updates
        
        # Collect all results (this will wait for completion)
        print("📋 All tasks completed! Collecting final results...")
        group_result.get()  # Wait for all tasks to complete
        
        # Read final results from file (since tasks write directly to file)
        registered_count = 0
        not_registered_count = 0
        failed_count = 0
        total_processed = 0
        
        if os.path.exists(job_output_file):
            with open(job_output_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                total_processed = len(lines)
                
                for line in lines:
                    line = line.strip().lower()
                    if 'registered' in line and 'not registered' not in line:
                        registered_count += 1
                    elif 'not registered' in line:
                        not_registered_count += 1
                    else:
                        failed_count += 1
        
        print(f"📊 Final Results: {total_processed} processed, {registered_count} registered, {not_registered_count} not registered, {failed_count} failed")
        
        # Return results summary
        return {
            'success': True,
            'total_processed': total_processed,
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
