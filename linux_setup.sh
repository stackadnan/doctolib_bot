#!/bin/bash
# Linux Server Setup Script for Doctolib Bot

# Update system
sudo apt update && sudo apt upgrade -y

# Install Python and pip
sudo apt install python3 python3-pip -y

# Install Chrome dependencies
sudo apt install -y wget gnupg2 software-properties-common apt-transport-https ca-certificates

# Add Google Chrome repository
wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | sudo apt-key add -
echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" | sudo tee /etc/apt/sources.list.d/google-chrome.list

# Install Google Chrome
sudo apt update
sudo apt install google-chrome-stable -y

# Install additional dependencies for headless Chrome
sudo apt install -y libnss3 libatk-bridge2.0-0 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxrandr2 libgbm1 libxss1 libasound2

# Install Python packages
pip3 install DrissionPage

# Create project directory
mkdir -p /home/ubuntu/doctolib_bot

echo "Linux setup complete!"
echo "Remember to:"
echo "1. Copy your phone_numbers.txt file to /home/ubuntu/doctolib_bot/"
echo "2. Update the BASE_PATH in main.py if you want a different directory"
echo "3. Run the bot with: python3 main.py"
