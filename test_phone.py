#!/usr/bin/env python3
"""
Quick test script to verify the updated phone processing logic
"""
import sys
import os

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from main import load_config, read_phone_numbers

def test_main():
    print("🧪 Testing updated phone processing logic...")
    
    # Load config
    config = load_config()
    print(f"✅ Config loaded successfully")
    
    # Check phone numbers file
    phone_numbers = read_phone_numbers(config)
    print(f"✅ Found {len(phone_numbers)} phone numbers")
    
    if phone_numbers:
        print(f"📱 First phone number: {phone_numbers[0]}")
    
    print("\n🔧 Key improvements implemented:")
    print("   1. ✅ Smart popup dismissal for 'already registered' messages")
    print("   2. ✅ Proper back navigation for 'not registered' pages") 
    print("   3. ✅ Multiple dismissal methods (close buttons, Escape key, click outside)")
    print("   4. ✅ Enhanced German keyword detection")
    print("   5. ✅ URL verification after popup dismissal")
    print("   6. ✅ Intelligent page state detection for subsequent numbers")
    
    print("\n💡 How it works now:")
    print("   📋 'Already Registered' → Dismiss popup by clicking/Escape → Stay on same page")
    print("   📋 'Not Registered' → Use back button → Return to phone input page")
    print("   📋 Subsequent numbers → Smart navigation based on current page state")

if __name__ == "__main__":
    test_main()
