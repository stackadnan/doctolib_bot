#!/usr/bin/env python3
"""
Linux Deployment Setup Script
This script configures the bot for production deployment on Linux servers
"""

import os
import json
import sys
import subprocess

def install_dependencies():
    """Install required system dependencies"""
    print("🔧 Installing system dependencies...")
    
    commands = [
        "sudo apt update",
        "sudo apt install -y python3 python3-pip python3-venv",
        "sudo apt install -y wget gnupg2 software-properties-common",
        "wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | sudo apt-key add -",
        'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" | sudo tee /etc/apt/sources.list.d/google-chrome.list',
        "sudo apt update",
        "sudo apt install -y google-chrome-stable",
        "sudo apt install -y libnss3 libatk-bridge2.0-0 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxrandr2 libgbm1 libxss1 libasound2"
    ]
    
    for cmd in commands:
        print(f"Running: {cmd}")
        result = os.system(cmd)
        if result != 0:
            print(f"⚠️ Warning: Command failed: {cmd}")

def setup_python_environment():
    """Setup Python virtual environment"""
    print("🐍 Setting up Python environment...")
    
    # Create virtual environment
    os.system("python3 -m venv venv")
    
    # Install Python packages
    os.system("source venv/bin/activate && pip install -r requirements.txt")
    
    print("✅ Python environment setup complete")

def configure_for_production():
    """Configure bot for production environment"""
    print("⚙️ Configuring for production...")
    
    # Create directories
    os.makedirs("results", exist_ok=True)
    os.makedirs("logs", exist_ok=True)
    
    # Update config for production
    config = {
        "multiprocessing": {
            "enabled": True,
            "max_workers": 4,
            "phones_per_worker": 50
        },
        "browser": {
            "headless": True,
            "timeout": 30,
            "delay_between_phones": 2
        },
        "proxy": {
            "use_rotating_proxies": True,
            "proxy_file": "proxies.txt",
            "rotation": {
                "min_requests": 20,
                "max_requests": 30,
                "per_worker": True
            }
        },
        "files": {
            "phone_numbers_file": "results/phone_numbers.txt",
            "output_file": "results/downloadable.txt",
            "create_backup": True,
            "save_results": True
        },
        "debug": {
            "enable_screenshots": False,
            "verbose_logging": False
        },
        "telegram": {
            "bot_token": "YOUR_BOT_TOKEN_HERE",
            "max_file_size_mb": 10,
            "max_phone_numbers": 10000
        }
    }
    
    with open('config.json', 'w') as f:
        json.dump(config, f, indent=4)
    
    print("✅ Production configuration complete")

def create_systemd_service():
    """Create systemd service for auto-start"""
    print("🔄 Creating systemd service...")
    
    current_dir = os.getcwd()
    service_content = f"""[Unit]
Description=Doctolib Telegram Bot
After=network.target

[Service]
Type=simple
User={os.getenv('USER', 'ubuntu')}
WorkingDirectory={current_dir}
Environment=PATH={current_dir}/venv/bin
ExecStart={current_dir}/venv/bin/python telegram_bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
"""
    
    # Write service file (requires sudo)
    print("Creating service file (requires sudo)...")
    with open('/tmp/doctolib-bot.service', 'w') as f:
        f.write(service_content)
    
    os.system("sudo mv /tmp/doctolib-bot.service /etc/systemd/system/")
    os.system("sudo systemctl daemon-reload")
    os.system("sudo systemctl enable doctolib-bot")
    
    print("✅ Systemd service created")
    print("To start: sudo systemctl start doctolib-bot")
    print("To check status: sudo systemctl status doctolib-bot")

def create_startup_scripts():
    """Create convenient startup scripts"""
    print("📝 Creating startup scripts...")
    
    # Start script
    start_script = """#!/bin/bash
cd "$(dirname "$0")"
source venv/bin/activate
python telegram_bot.py
"""
    
    with open('start_bot.sh', 'w') as f:
        f.write(start_script)
    os.chmod('start_bot.sh', 0o755)
    
    # Test script
    test_script = """#!/bin/bash
cd "$(dirname "$0")"
source venv/bin/activate
python -c "import DrissionPage; print('✅ DrissionPage OK')"
python -c "import telegram; print('✅ python-telegram-bot OK')"
python -c "from main import load_config; print('✅ Config loading OK')"
echo "✅ All tests passed!"
"""
    
    with open('test_setup.sh', 'w') as f:
        f.write(test_script)
    os.chmod('test_setup.sh', 0o755)
    
    print("✅ Startup scripts created")

def main():
    """Main deployment setup"""
    print("🚀 Doctolib Bot - Linux Deployment Setup")
    print("=" * 50)
    
    if os.name != 'posix':
        print("❌ This script is for Linux systems only!")
        sys.exit(1)
    
    try:
        print("1. Installing system dependencies...")
        install_dependencies()
        
        print("\n2. Setting up Python environment...")
        setup_python_environment()
        
        print("\n3. Configuring for production...")
        configure_for_production()
        
        print("\n4. Creating startup scripts...")
        create_startup_scripts()
        
        print("\n5. Creating systemd service...")
        create_systemd_service()
        
        print("\n🎉 Deployment setup complete!")
        print("\n📋 Next Steps:")
        print("1. Edit config.json and add your bot token")
        print("2. Upload your phone numbers to results/phone_numbers.txt")
        print("3. Test setup: ./test_setup.sh")
        print("4. Start bot: ./start_bot.sh")
        print("5. Or use systemd: sudo systemctl start doctolib-bot")
        
    except Exception as e:
        print(f"❌ Setup failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
