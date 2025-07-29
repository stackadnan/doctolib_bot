"""
Simple Redis installation and startup for Windows
"""
import subprocess
import time
import requests
import zipfile
import os

def download_redis():
    """Download Redis for Windows"""
    print("📥 Downloading Redis for Windows...")
    redis_url = "https://github.com/microsoftarchive/redis/releases/download/win-3.0.504/Redis-x64-3.0.504.zip"
    
    try:
        response = requests.get(redis_url)
        with open("redis.zip", "wb") as f:
            f.write(response.content)
        
        # Extract Redis
        with zipfile.ZipFile("redis.zip", 'r') as zip_ref:
            zip_ref.extractall("redis")
        
        print("✅ Redis downloaded and extracted!")
        return True
    except Exception as e:
        print(f"❌ Error downloading Redis: {e}")
        return False

def start_redis():
    """Start Redis server"""
    redis_exe = os.path.join("redis", "redis-server.exe")
    if os.path.exists(redis_exe):
        print("🚀 Starting Redis server...")
        subprocess.Popen([redis_exe], creationflags=subprocess.CREATE_NEW_CONSOLE)
        time.sleep(3)
        print("✅ Redis server started!")
        return True
    else:
        print("❌ Redis executable not found")
        return False

def start_workers(num_workers=10):
    """Start Celery workers"""
    python_exe = "C:/Users/muham/AppData/Local/Programs/Python/Python310/python.exe"
    
    print(f"🚀 Starting {num_workers} Celery workers...")
    for i in range(1, num_workers + 1):
        cmd = [
            python_exe, "-m", "celery", "-A", "celery_tasks", 
            "worker", "--loglevel=info", "--concurrency=1", 
            f"--hostname=worker{i}@%h"
        ]
        subprocess.Popen(cmd, creationflags=subprocess.CREATE_NEW_CONSOLE)
        time.sleep(1)
    
    print(f"✅ {num_workers} workers started!")

if __name__ == "__main__":
    print("🚀 ULTRA-FAST DOCTOLIB BOT SETUP")
    print("================================")
    
    # Step 1: Download and start Redis
    if download_redis():
        if start_redis():
            # Step 2: Start workers
            start_workers(10)
            
            print("\n✅ SYSTEM READY!")
            print("🎯 10 ultra-fast workers active")
            print("📱 Ready for 2-3 minute processing")
            print("\nNext: Run 'python telegram_bot.py'")
        else:
            print("❌ Failed to start Redis")
    else:
        print("❌ Failed to download Redis")
        print("💡 Alternative: Install Redis manually or use Docker")
