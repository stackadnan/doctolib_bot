#!/bin/bash

echo "🚀 Doctolib Bot Launcher with Virtual Display"
echo "=============================================="

# Set the display
export DISPLAY=:99

# Check if virtual display is running
if ! xdpyinfo -display :99 >/dev/null 2>&1; then
    echo "🖥️ Virtual display not running, starting it..."
    
    # Kill any existing Xvfb on display :99
    pkill -f "Xvfb :99" 2>/dev/null
    
    # Start Xvfb with high resolution and 24-bit color depth
    Xvfb :99 -screen 0 1920x1080x24 -ac -nolisten tcp -dpi 96 &
    
    # Wait for display to start
    sleep 3
    
    # Verify display is working
    if xdpyinfo -display :99 >/dev/null 2>&1; then
        echo "✅ Virtual display started successfully"
    else
        echo "❌ Failed to start virtual display"
        exit 1
    fi
else
    echo "✅ Virtual display is already running"
fi

# Update config to use non-headless mode
echo "🔧 Updating config for virtual display..."
python3 -c "
import json
import os

config_file = 'config.json'
if os.path.exists(config_file):
    with open(config_file, 'r') as f:
        config = json.load(f)
    
    if 'browser' not in config:
        config['browser'] = {}
    config['browser']['headless'] = False
    
    with open(config_file, 'w') as f:
        json.dump(config, f, indent=4)
    
    print('✅ Config updated for virtual display')
else:
    print('⚠️ config.json not found, using defaults')
"

echo ""
echo "🎯 Starting Doctolib Bot with Virtual Display..."
echo "📺 Display: $DISPLAY"
echo "🖥️ Resolution: 1920x1080x24"
echo ""

# Check what to run
if [ -f "telegram_bot.py" ]; then
    echo "🤖 Starting Telegram Bot..."
    python3 telegram_bot.py
elif [ -f "main.py" ]; then
    echo "🔄 Starting Main Bot..."
    python3 main.py
else
    echo "❌ No bot script found (telegram_bot.py or main.py)"
    exit 1
fi
