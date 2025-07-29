#!/usr/bin/env python3
"""
Virtual Display Manager for Doctolib Bot
Manages Xvfb virtual display for running browsers on headless Linux servers
"""

import os
import sys
import subprocess
import time
import signal
import psutil

class VirtualDisplayManager:
    def __init__(self, display_num=99, resolution="1920x1080", color_depth=24):
        self.display_num = display_num
        self.resolution = resolution
        self.color_depth = color_depth
        self.display_env = f":{display_num}"
        self.xvfb_process = None
    
    def is_display_running(self):
        """Check if Xvfb is already running on the display"""
        try:
            result = subprocess.run(
                ['xdpyinfo', '-display', self.display_env],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
    
    def kill_existing_display(self):
        """Kill any existing Xvfb processes on this display"""
        try:
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                if proc.info['name'] == 'Xvfb':
                    cmdline = ' '.join(proc.info['cmdline'] or [])
                    if f":{self.display_num}" in cmdline:
                        print(f"🛑 Killing existing Xvfb process (PID: {proc.info['pid']})")
                        proc.kill()
                        proc.wait(timeout=3)
        except Exception as e:
            print(f"⚠️ Warning: Could not kill existing processes: {e}")
    
    def start_display(self):
        """Start the virtual display"""
        print(f"🖥️ Starting virtual display {self.display_env} with resolution {self.resolution}x{self.color_depth}")
        
        # Kill any existing display first
        self.kill_existing_display()
        time.sleep(1)
        
        # Start Xvfb
        cmd = [
            'Xvfb', self.display_env,
            '-screen', '0', f"{self.resolution}x{self.color_depth}",
            '-ac',  # Disable access control
            '-nolisten', 'tcp',  # Don't listen on TCP
            '-dpi', '96',  # Set DPI
            '+extension', 'GLX',  # Enable OpenGL
            '+extension', 'RANDR',  # Enable screen resolution extension
            '-noreset'  # Don't reset after last client disconnects
        ]
        
        try:
            self.xvfb_process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            
            # Wait for display to start
            for i in range(10):
                time.sleep(0.5)
                if self.is_display_running():
                    print(f"✅ Virtual display {self.display_env} started successfully")
                    
                    # Set environment variable
                    os.environ['DISPLAY'] = self.display_env
                    print(f"🔧 Set DISPLAY environment variable to {self.display_env}")
                    
                    # Show display info
                    self.show_display_info()
                    return True
            
            print(f"❌ Failed to start virtual display after 5 seconds")
            return False
            
        except FileNotFoundError:
            print("❌ Error: Xvfb not found. Please install it with: sudo apt install xvfb")
            return False
        except Exception as e:
            print(f"❌ Error starting virtual display: {e}")
            return False
    
    def show_display_info(self):
        """Show information about the running display"""
        try:
            result = subprocess.run(
                ['xdpyinfo', '-display', self.display_env],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                lines = result.stdout.split('\n')
                for line in lines:
                    if 'dimensions:' in line:
                        print(f"📊 Display dimensions: {line.strip()}")
                        break
            else:
                print("⚠️ Could not get display info")
                
        except Exception as e:
            print(f"⚠️ Error getting display info: {e}")
    
    def stop_display(self):
        """Stop the virtual display"""
        print(f"🛑 Stopping virtual display {self.display_env}")
        
        if self.xvfb_process:
            try:
                self.xvfb_process.terminate()
                self.xvfb_process.wait(timeout=5)
                print("✅ Xvfb process terminated")
            except subprocess.TimeoutExpired:
                self.xvfb_process.kill()
                print("🔨 Xvfb process killed")
            except Exception as e:
                print(f"⚠️ Error stopping Xvfb process: {e}")
        
        # Also kill any remaining processes
        self.kill_existing_display()
        
        # Clean up environment
        if os.environ.get('DISPLAY') == self.display_env:
            del os.environ['DISPLAY']
            print("🔧 Removed DISPLAY environment variable")
    
    def status(self):
        """Check and display status of virtual display"""
        if self.is_display_running():
            print(f"✅ Virtual display {self.display_env} is running")
            self.show_display_info()
            
            # Check environment variable
            current_display = os.environ.get('DISPLAY')
            if current_display == self.display_env:
                print(f"✅ DISPLAY environment variable is set correctly: {current_display}")
            else:
                print(f"⚠️ DISPLAY environment variable mismatch. Expected: {self.display_env}, Current: {current_display}")
            
            return True
        else:
            print(f"❌ Virtual display {self.display_env} is not running")
            return False

def signal_handler(signum, frame):
    """Handle Ctrl+C gracefully"""
    print("\n🛑 Received interrupt signal. Stopping virtual display...")
    manager.stop_display()
    sys.exit(0)

if __name__ == "__main__":
    manager = VirtualDisplayManager()
    
    # Set up signal handler for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    if len(sys.argv) < 2:
        print("🖥️ Virtual Display Manager for Doctolib Bot")
        print("Usage:")
        print("  python virtual_display.py start   - Start virtual display")
        print("  python virtual_display.py stop    - Stop virtual display") 
        print("  python virtual_display.py status  - Check display status")
        print("  python virtual_display.py restart - Restart virtual display")
        sys.exit(1)
    
    command = sys.argv[1].lower()
    
    if command == "start":
        if manager.status():
            print("ℹ️ Virtual display is already running")
        else:
            if manager.start_display():
                print("\n🎉 Virtual display started successfully!")
                print("💡 You can now run your bot with headless=False")
                print("🔧 Press Ctrl+C to stop the virtual display")
                
                # Keep the script running
                try:
                    while True:
                        time.sleep(60)
                        if not manager.is_display_running():
                            print("❌ Virtual display stopped unexpectedly")
                            break
                except KeyboardInterrupt:
                    pass
                finally:
                    manager.stop_display()
            else:
                sys.exit(1)
    
    elif command == "stop":
        manager.stop_display()
    
    elif command == "status":
        manager.status()
    
    elif command == "restart":
        manager.stop_display()
        time.sleep(2)
        if manager.start_display():
            print("🎉 Virtual display restarted successfully!")
        else:
            sys.exit(1)
    
    else:
        print(f"❌ Unknown command: {command}")
        sys.exit(1)
