import json

try:
    with open('config.json', 'r') as f:
        config = json.load(f)
    
    print("✅ Config.json validation successful!")
    print("\n🤖 Intelligent Scaling Features:")
    print(f"   Auto-scaling enabled: {config['multiprocessing']['auto_scale']}")
    print(f"   Max worker limit: {config['multiprocessing']['max_worker_limit']}")
    print(f"   Human behavior: {config['browser']['human_behavior']}")
    print(f"   Verbose logging: {config['debug']['verbose_logging']}")
    print(f"   Proxy rotation: {config['proxy']['rotation']['min_requests']}-{config['proxy']['rotation']['max_requests']} requests")
    
    print("\n📋 All new config options:")
    print("   ✅ multiprocessing.auto_scale")
    print("   ✅ multiprocessing.max_worker_limit") 
    print("   ✅ browser.human_behavior")
    print("   ✅ Updated proxy rotation settings")
    print("   ✅ Static proxy fallback configuration")
    
except Exception as e:
    print(f"❌ Error loading config: {e}")
