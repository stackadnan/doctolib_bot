#!/bin/bash

echo "🖥️ Setting up Virtual Display for Doctolib Bot on Linux Server (Root Version)"
echo "=============================================================================="

# Check if running as root (this version is designed for root)
if [ "$EUID" -ne 0 ]; then
    echo "⚠️ This script must be run as root. Use: sudo ./setup_virtual_display_root.sh"
    exit 1
fi

# Get the actual user who invoked sudo (if any)
ACTUAL_USER=${SUDO_USER:-$(logname 2>/dev/null || echo "root")}
ACTUAL_HOME=$(eval echo "~$ACTUAL_USER")

echo "🔍 Running as root for user: $ACTUAL_USER"
echo "📁 User home directory: $ACTUAL_HOME"

# Update package list
echo "📦 Updating package list..."
apt update

# Install Xvfb (X Virtual Framebuffer)
echo "🖥️ Installing Xvfb and dependencies..."
apt install -y xvfb xfonts-base xfonts-75dpi xfonts-100dpi xfonts-cyrillic

# Install additional useful packages
echo "📦 Installing additional display packages..."
apt install -y x11-utils x11-xserver-utils

# Install Chrome dependencies if not already installed
echo "🌐 Installing Chrome dependencies..."
apt install -y wget gnupg2 software-properties-common apt-transport-https ca-certificates

# Download and install Google Chrome if not already installed
if ! command -v google-chrome &> /dev/null; then
    echo "🌐 Installing Google Chrome..."
    wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add -
    echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" | tee /etc/apt/sources.list.d/google-chrome.list
    apt update
    apt install -y google-chrome-stable
else
    echo "✅ Google Chrome is already installed"
fi

# Install Python packages that might be needed
echo "🐍 Installing Python packages for virtual display..."
pip3 install psutil 2>/dev/null || echo "⚠️ Could not install psutil via pip3"

# Determine the correct directory for scripts (where this script is located)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "📁 Script directory: $SCRIPT_DIR"

# Create virtual display startup script
echo "📝 Creating virtual display startup script..."
cat > "$SCRIPT_DIR/start_virtual_display.sh" << 'EOF'
#!/bin/bash

# Start Virtual Display for Doctolib Bot
echo "🖥️ Starting virtual display on :99..."

# Kill any existing Xvfb on display :99
pkill -f "Xvfb :99" 2>/dev/null

# Start Xvfb with high resolution and 24-bit color depth
Xvfb :99 -screen 0 1920x1080x24 -ac -nolisten tcp -dpi 96 &

# Wait a moment for display to start
sleep 2

# Set DISPLAY environment variable
export DISPLAY=:99

# Verify display is working
if xdpyinfo -display :99 >/dev/null 2>&1; then
    echo "✅ Virtual display :99 is running successfully"
    echo "📊 Display info:"
    xdpyinfo -display :99 | grep dimensions
else
    echo "❌ Failed to start virtual display"
    exit 1
fi

echo "🎯 Virtual display is ready! You can now run your bot with headless=False"
echo "💡 To run your bot: export DISPLAY=:99 && python main.py"
EOF

# Make the startup script executable
chmod +x "$SCRIPT_DIR/start_virtual_display.sh"

# Create systemd service for auto-start (optional)
echo "📝 Creating systemd service for auto-start..."
cat > /etc/systemd/system/virtual-display.service << EOF
[Unit]
Description=Virtual Display for Doctolib Bot
After=network.target

[Service]
Type=forking
User=root
Group=root
ExecStart=$SCRIPT_DIR/start_virtual_display.sh
ExecStop=/usr/bin/pkill -f "Xvfb :99"
Restart=always
RestartSec=3
Environment=DISPLAY=:99

[Install]
WantedBy=multi-user.target
EOF

# Create stop script
echo "📝 Creating stop script..."
cat > "$SCRIPT_DIR/stop_virtual_display.sh" << 'EOF'
#!/bin/bash
echo "🛑 Stopping virtual display..."
pkill -f "Xvfb :99"
echo "✅ Virtual display stopped"
EOF

chmod +x "$SCRIPT_DIR/stop_virtual_display.sh"

# Create config update script
echo "📝 Creating config updater..."
cat > "$SCRIPT_DIR/update_config_for_virtual_display.py" << 'EOF'
#!/usr/bin/env python3
import json
import os

config_file = 'config.json'

if os.path.exists(config_file):
    with open(config_file, 'r') as f:
        config = json.load(f)
    
    # Update browser settings for virtual display
    if 'browser' not in config:
        config['browser'] = {}
    config['browser']['headless'] = False
    
    with open(config_file, 'w') as f:
        json.dump(config, f, indent=4)
    
    print("✅ Updated config.json to use virtual display (headless=False)")
else:
    print("⚠️ config.json not found. The bot will use default settings.")
EOF

chmod +x "$SCRIPT_DIR/update_config_for_virtual_display.py"

# Set proper ownership if we know the actual user
if [ "$ACTUAL_USER" != "root" ]; then
    echo "🔧 Setting proper ownership for scripts..."
    chown "$ACTUAL_USER:$ACTUAL_USER" "$SCRIPT_DIR"/*.sh 2>/dev/null || true
    chown "$ACTUAL_USER:$ACTUAL_USER" "$SCRIPT_DIR"/*.py 2>/dev/null || true
fi

# Reload systemd daemon
systemctl daemon-reload

echo ""
echo "🎉 Setup completed successfully!"
echo ""
echo "📋 Next Steps:"
echo "1. Start virtual display: $SCRIPT_DIR/start_virtual_display.sh"
echo "2. Update config: cd $SCRIPT_DIR && python3 update_config_for_virtual_display.py"
echo "3. Run your bot: cd $SCRIPT_DIR && python3 main.py"
echo ""
echo "🔧 Optional - Enable auto-start on boot:"
echo "   systemctl enable virtual-display.service"
echo "   systemctl start virtual-display.service"
echo ""
echo "🛑 To stop virtual display: $SCRIPT_DIR/stop_virtual_display.sh"
echo ""
echo "🔍 To check virtual display status:"
echo "   systemctl status virtual-display.service"
echo ""
echo "💡 Tips:"
echo "   - Virtual display runs on :99"
echo "   - Browser will open normally but invisible to you"
echo "   - Much more realistic than headless mode"
echo "   - Better for avoiding detection"
echo "   - All scripts are in: $SCRIPT_DIR"
echo ""
echo "⚠️ Important: When running your bot, make sure to set DISPLAY=:99"
echo "   Example: export DISPLAY=:99 && python3 main.py"
