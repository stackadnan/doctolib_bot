#!/bin/bash

# Ultra-Fast Doctolib Bot Startup Script
# 100 workers for maximum parallel processing

echo "🚀 ULTRA-FAST MODE: Starting 100 Celery workers"
echo "================================================"
echo "⚡ Target: 31 phones = 31 workers = 2-3 minutes"
echo "📊 Configuration: 100 workers × 1 concurrency = 100 total capacity"
echo ""

# Start Redis if not running
echo "🔍 Checking Redis..."
if ! pgrep -x "redis-server" > /dev/null; then
    echo "⚡ Starting Redis server..."
    redis-server --daemonize yes
    sleep 2
fi

# Start 100 Celery workers with ultra-fast settings
echo "🚀 Starting 100 ultra-fast workers..."
./run_celery.sh workers 100 1

echo ""
echo "✅ Ultra-fast system ready!"
echo "📱 For 31 phones: All will be processed simultaneously"
echo "⏱️  Expected time: 2-3 minutes"
echo ""
echo "🔍 Monitor with:"
echo "   watch -n 1 'ls -la results/downloadable_*.txt'"
echo ""
echo "🎯 Start your bot and send phone numbers!"
