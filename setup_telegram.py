#!/usr/bin/env python3
"""
Telegram Bot Setup and Configuration Script
This script helps you set up the Doctolib Telegram Bot
"""

import json
import os
import sys

def load_config():
    """Load current configuration"""
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print("❌ config.json not found!")
        return None
    except Exception as e:
        print(f"❌ Error loading config.json: {e}")
        return None

def save_config(config):
    """Save configuration to file"""
    try:
        with open('config.json', 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4)
        return True
    except Exception as e:
        print(f"❌ Error saving config.json: {e}")
        return False

def setup_telegram_bot():
    """Interactive setup for Telegram bot"""
    print("🤖 Telegram Bot Setup")
    print("=" * 40)
    
    # Load existing config
    config = load_config()
    if not config:
        return False
    
    # Check if telegram section exists
    if 'telegram' not in config:
        config['telegram'] = {}
    
    print("\n📝 You need to create a Telegram bot first:")
    print("1. Open Telegram and search for @BotFather")
    print("2. Send /newbot command")
    print("3. Follow instructions to create your bot")
    print("4. Copy the bot token you receive\n")
    
    # Get bot token
    current_token = config['telegram'].get('bot_token', 'YOUR_BOT_TOKEN_HERE')
    if current_token == 'YOUR_BOT_TOKEN_HERE':
        print("🔑 Enter your Telegram bot token:")
    else:
        print(f"🔑 Current bot token: {current_token[:10]}...")
        print("🔑 Enter new bot token (or press Enter to keep current):")
    
    new_token = input("Bot Token: ").strip()
    
    if new_token:
        config['telegram']['bot_token'] = new_token
        print("✅ Bot token updated!")
    elif current_token == 'YOUR_BOT_TOKEN_HERE':
        print("❌ Bot token is required!")
        return False
    else:
        print("✅ Keeping current bot token")
    
    # Configure limits
    print("\n⚙️ Configure Bot Limits:")
    
    max_file_size = input(f"Maximum file size in MB [{config['telegram'].get('max_file_size_mb', 10)}]: ").strip()
    if max_file_size:
        try:
            config['telegram']['max_file_size_mb'] = int(max_file_size)
        except ValueError:
            print("⚠️ Invalid number, using default (10)")
            config['telegram']['max_file_size_mb'] = 10
    else:
        config['telegram']['max_file_size_mb'] = config['telegram'].get('max_file_size_mb', 10)
    
    max_phones = input(f"Maximum phone numbers per request [{config['telegram'].get('max_phone_numbers', 100)}]: ").strip()
    if max_phones:
        try:
            config['telegram']['max_phone_numbers'] = int(max_phones)
        except ValueError:
            print("⚠️ Invalid number, using default (100)")
            config['telegram']['max_phone_numbers'] = 100
    else:
        config['telegram']['max_phone_numbers'] = config['telegram'].get('max_phone_numbers', 100)
    
    # Save configuration
    if save_config(config):
        print("\n✅ Configuration saved successfully!")
        return True
    else:
        print("\n❌ Failed to save configuration!")
        return False

def verify_setup():
    """Verify the setup is complete"""
    print("\n🔍 Verifying Setup...")
    print("=" * 30)
    
    # Check config
    config = load_config()
    if not config:
        return False
    
    # Check telegram config
    if 'telegram' not in config:
        print("❌ Telegram configuration missing")
        return False
    
    bot_token = config['telegram'].get('bot_token', '')
    if not bot_token or bot_token == 'YOUR_BOT_TOKEN_HERE':
        print("❌ Bot token not configured")
        return False
    
    print("✅ Configuration looks good!")
    
    # Check files
    required_files = ['main.py', 'telegram_bot.py', 'requirements.txt']
    for file in required_files:
        if os.path.exists(file):
            print(f"✅ {file} found")
        else:
            print(f"❌ {file} missing")
            return False
    
    print("\n✅ All files present!")
    return True

def show_next_steps():
    """Show next steps to user"""
    print("\n🚀 Setup Complete! Next Steps:")
    print("=" * 35)
    print("1. Start the bot: python telegram_bot.py")
    print("2. Open Telegram and find your bot")
    print("3. Send /start to your bot")
    print("4. Upload a phone_numbers.txt file")
    print("5. Wait for processing and receive results!")
    
    print(f"\n📱 Test with sample file: sample_phone_numbers.txt")
    print(f"🔧 Start with batch file: start_telegram_bot.bat")
    
    print(f"\n📖 For detailed help, see: README_TELEGRAM.md")

def main():
    """Main setup function"""
    print("🎯 Doctolib Telegram Bot Setup")
    print("=" * 50)
    print("This script will help you configure your Telegram bot.\n")
    
    # Check if we're in the right directory
    if not os.path.exists('main.py'):
        print("❌ Please run this script from the bot directory (where main.py is located)")
        return
    
    try:
        # Setup telegram bot
        if not setup_telegram_bot():
            print("\n❌ Setup failed!")
            return
        
        # Verify setup
        if not verify_setup():
            print("\n❌ Verification failed!")
            return
        
        # Show next steps
        show_next_steps()
        
        print(f"\n🎉 Setup completed successfully!")
        
    except KeyboardInterrupt:
        print("\n\n👋 Setup cancelled by user.")
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")

if __name__ == "__main__":
    main()
