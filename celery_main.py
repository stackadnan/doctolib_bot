#!/usr/bin/env python3
"""
Main controller for Celery-based Doctolib phone checker
This replaces the browser automation with distributed HTTP requests
"""

import json
import os
import time
from celery import group
from celery_tasks import app, check_phone_registration, process_phone_batch

def load_config():
    """Load configuration from config.json"""
    config_path = os.path.join(os.path.dirname(__file__), 'config.json')
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return get_default_config()

def get_default_config():
    """Default configuration for Celery-based approach"""
    return {
        "celery": {
            "workers": 4,
            "batch_size": 50,
            "rate_limit": "10/m"  # 10 requests per minute per worker
        },
        "proxy": {
            "use_rotating_proxies": True,
            "proxy_file": "proxies.txt"
        },
        "files": {
            "phone_numbers_file": "results/phone_numbers.txt",
            "output_file": "results/downloadable.txt"
        }
    }

def load_proxies(config):
    """Load proxies from file"""
    if not config['proxy'].get('use_rotating_proxies', False):
        return []
    
    proxy_file = os.path.join(os.path.dirname(__file__), config['proxy']['proxy_file'])
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
        
        print(f"📁 Loaded {len(proxies)} proxies from {proxy_file}")
        return proxies
        
    except FileNotFoundError:
        print(f"❌ Proxy file not found: {proxy_file}")
        return []
    except Exception as e:
        print(f"❌ Error loading proxies: {e}")
        return []

def load_phone_numbers(config):
    """Load phone numbers from file"""
    file_path = os.path.join(os.path.dirname(__file__), config['files']['phone_numbers_file'])
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            phone_numbers = [line.strip() for line in f if line.strip()]
        print(f"📱 Loaded {len(phone_numbers)} phone numbers from {file_path}")
        return phone_numbers
    except FileNotFoundError:
        print(f"❌ Phone numbers file not found: {file_path}")
        return []
    except Exception as e:
        print(f"❌ Error reading phone numbers: {e}")
        return []

def create_batches(phone_numbers, batch_size):
    """Split phone numbers into batches"""
    batches = []
    for i in range(0, len(phone_numbers), batch_size):
        batches.append(phone_numbers[i:i + batch_size])
    return batches

def main():
    """Main function to orchestrate Celery-based phone checking"""
    print("🚀 Starting Celery-based Doctolib Phone Checker")
    print("=" * 60)
    
    # Load configuration
    config = load_config()
    
    # Load phone numbers
    phone_numbers = load_phone_numbers(config)
    if not phone_numbers:
        print("❌ No phone numbers loaded. Exiting...")
        return
    
    # Load proxies
    proxies = load_proxies(config)
    if proxies:
        print(f"🌐 Using {len(proxies)} proxies for requests")
    else:
        print("⚠️ No proxies configured - using direct connections")
    
    # Configuration summary
    batch_size = config['celery']['batch_size']
    total_phones = len(phone_numbers)
    
    print(f"\n📊 Processing Configuration:")
    print(f"   📱 Total phone numbers: {total_phones:,}")
    print(f"   📦 Batch size: {batch_size}")
    print(f"   🌐 Proxies available: {len(proxies)}")
    print(f"   ⚡ Rate limit: {config['celery']['rate_limit']}")
    
    # Clear output file
    output_file = os.path.join(os.path.dirname(__file__), config['files']['output_file'])
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("")  # Clear file
        print(f"📝 Cleared output file: {config['files']['output_file']}")
    except Exception as e:
        print(f"⚠️ Could not clear output file: {e}")
    
    # Create batches
    phone_batches = create_batches(phone_numbers, batch_size)
    print(f"\n📦 Created {len(phone_batches)} batches:")
    for i, batch in enumerate(phone_batches[:5]):  # Show first 5 batches
        print(f"   Batch {i+1}: {len(batch)} phones")
    if len(phone_batches) > 5:
        print(f"   ... and {len(phone_batches) - 5} more batches")
    
    print(f"\n🔄 Submitting tasks to Celery workers...")
    
    # Submit tasks to Celery
    submitted_tasks = []
    
    for i, batch in enumerate(phone_batches):
        print(f"📤 Submitting batch {i+1}/{len(phone_batches)} ({len(batch)} phones)")
        
        # Create individual tasks for each phone number with proxy rotation
        batch_tasks = []
        for j, phone_number in enumerate(batch):
            # Assign proxy (round-robin)
            proxy_info = None
            if proxies:
                proxy_index = (i * batch_size + j) % len(proxies)
                proxy_info = proxies[proxy_index]
            
            # Submit task
            task = check_phone_registration.delay(phone_number, proxy_info)
            batch_tasks.append(task)
        
        submitted_tasks.extend(batch_tasks)
        
        # Small delay between batch submissions to avoid overwhelming
        if i < len(phone_batches) - 1:
            time.sleep(1)
    
    print(f"\n✅ Submitted {len(submitted_tasks)} tasks to Celery")
    print(f"🔍 Task IDs: {[task.id[:8] + '...' for task in submitted_tasks[:5]]}")
    if len(submitted_tasks) > 5:
        print(f"   ... and {len(submitted_tasks) - 5} more tasks")
    
    # Monitor progress
    print(f"\n⏳ Monitoring task progress...")
    print("=" * 60)
    
    completed = 0
    failed = 0
    start_time = time.time()
    
    # Wait for all tasks to complete
    while completed + failed < len(submitted_tasks):
        time.sleep(10)  # Check every 10 seconds
        
        current_completed = 0
        current_failed = 0
        
        for task in submitted_tasks:
            if task.ready():
                if task.successful():
                    current_completed += 1
                else:
                    current_failed += 1
        
        if current_completed != completed or current_failed != failed:
            completed = current_completed
            failed = current_failed
            
            elapsed = time.time() - start_time
            remaining = len(submitted_tasks) - completed - failed
            
            if completed > 0:
                avg_time = elapsed / completed
                eta = avg_time * remaining
                eta_str = f"{eta/60:.1f}m" if eta > 60 else f"{eta:.0f}s"
            else:
                eta_str = "calculating..."
            
            print(f"📊 Progress: {completed}/{len(submitted_tasks)} completed, "
                  f"{failed} failed, {remaining} remaining (ETA: {eta_str})")
    
    # Final summary
    elapsed_total = time.time() - start_time
    print(f"\n{'='*60}")
    print("🎉 PROCESSING COMPLETE!")
    print(f"{'='*60}")
    print(f"📊 Final Results:")
    print(f"   ✅ Completed: {completed}")
    print(f"   ❌ Failed: {failed}")
    print(f"   ⏱️ Total time: {elapsed_total/60:.1f} minutes")
    print(f"   📈 Average rate: {completed/(elapsed_total/60):.1f} phones/minute")
    print(f"   📝 Results saved to: {config['files']['output_file']}")
    
    # Collect detailed results
    print(f"\n📋 Collecting detailed results...")
    results_summary = {
        'registered': 0,
        'not_registered': 0,
        'unknown': 0,
        'failed': 0
    }
    
    for task in submitted_tasks:
        if task.ready() and task.successful():
            try:
                result = task.result
                status = result.get('status', 'unknown')
                if status in results_summary:
                    results_summary[status] += 1
                else:
                    results_summary['unknown'] += 1
            except:
                results_summary['failed'] += 1
        else:
            results_summary['failed'] += 1
    
    print(f"\n📊 DETAILED RESULTS:")
    print(f"   📱 Total processed: {sum(results_summary.values())}")
    print(f"   ✅ Already registered: {results_summary['registered']}")
    print(f"   ❌ Not registered: {results_summary['not_registered']}")
    print(f"   ❓ Unknown status: {results_summary['unknown']}")
    print(f"   💥 Failed: {results_summary['failed']}")
    
    print(f"\n🚀 All tasks completed! Check the output file for detailed results.")

if __name__ == "__main__":
    main()
