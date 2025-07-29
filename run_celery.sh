#!/bin/bash

# Celery Doctolib Checker Setup and Run Script
# This script sets up and runs the Celery-based phone checker with Telegram bot

echo "🚀 Setting up Celery-based Doctolib Phone Checker with Telegram Bot"
echo "====================================================================="

# Script configuration
CELERY_WORKERS=100        # Increased to 100 workers for maximum speed
CELERY_CONCURRENCY=1      # 1 concurrent task per worker = 100 total capacity  
CELERY_LOG_LEVEL=info
BOT_LOG_FILE="logs/telegram_bot.log"
CELERY_LOG_FILE="logs/celery.log"
REDIS_URL="redis://localhost:6379/0"

# Define Python and Celery binary paths
# Check if we're in WSL and can use Windows Python
WINDOWS_PYTHON="/mnt/c/Users/muham/AppData/Local/Programs/Python/Python310/python.exe"

if [ -f "$WINDOWS_PYTHON" ] && command -v "$WINDOWS_PYTHON" > /dev/null 2>&1; then
    echo "🔍 Detected WSL environment with Windows Python available"
    PYTHON_BIN="$WINDOWS_PYTHON"
elif command -v python3 > /dev/null 2>&1; then
    PYTHON_BIN="python3"
elif command -v python > /dev/null 2>&1; then
    PYTHON_BIN="python"
else
    echo "❌ No Python interpreter found (tried Windows Python, python3 and python)"
    exit 1
fi

echo "🐍 Using Python: $PYTHON_BIN"

if command -v celery > /dev/null 2>&1; then
    CELERY_BIN="celery"
else
    CELERY_BIN="$PYTHON_BIN -m celery"
fi

# Create PID directory
mkdir -p pids

# Function to show usage
show_usage() {
    echo "Usage: $0 [COMMAND] [OPTIONS]"
    echo ""
    echo "Commands:"
    echo "  workers [N] [C] - Start N workers with C concurrency each (default: 100 workers, 1 concurrency)"
    echo "  bot            - Start Telegram bot only"
    echo "  all [N] [C]    - Start both Celery workers and Telegram bot"
    echo "  status         - Check status of running processes"
    echo "  stop           - Stop all processes"
    echo "  logs           - Show logs"
    echo "  setup          - Setup dependencies and directories"
    echo ""
    echo "Examples:"
    echo "  $0 setup                # First-time setup"
    echo "  $0 all                  # Start everything (8 workers, 8 concurrency = 64 capacity)"
    echo "  $0 all 12               # Start with 12 workers, 8 concurrency = 96 capacity"
    echo "  $0 all 8 16             # Start with 8 workers, 16 concurrency = 128 capacity"
    echo "  $0 workers 16 12        # Start 16 workers with 12 concurrency = 192 capacity"
    echo "  $0 status               # Check what's running"
    echo "  $0 stop                 # Stop everything"
}

# Function to check Redis
check_redis() {
    echo "🔍 Checking Redis connection..."
    if ! redis-cli -u $REDIS_URL ping > /dev/null 2>&1; then
        echo "❌ Redis is not running or not accessible at $REDIS_URL"
        echo "Please start Redis first:"
        echo "   Ubuntu/Debian: sudo systemctl start redis-server"
        echo "   CentOS/RHEL: sudo systemctl start redis"
        echo "   Docker: docker run -d -p 6379:6379 redis:alpine"
        return 1
    fi
    echo "✅ Redis is running and accessible"
    return 0
}

# Function to setup environment
setup_environment() {
    echo "📦 Setting up environment..."
    
    # Install Python dependencies
    echo "📦 Installing Python dependencies..."
    $PYTHON_BIN -m pip install 'celery[redis]' flower requests urllib3 python-telegram-bot
    
    # Create necessary directories
    echo "📁 Creating directories..."
    mkdir -p results
    mkdir -p logs
    mkdir -p proxy_files
    mkdir -p pids
    
    # Check configuration file
    if [ ! -f "config.json" ]; then
        echo "⚠️ config.json not found, creating from template..."
        if [ -f "config_updated_with_celery.json" ]; then
            cp config_updated_with_celery.json config.json
            echo "✅ Created config.json from template"
        else
            echo "❌ No configuration template found"
            echo "Please create config.json with your settings"
            return 1
        fi
    else
        echo "✅ Configuration file found"
    fi
    
    # Check if proxies file exists (optional)
    if [ ! -f "proxies.txt" ]; then
        echo "⚠️ Proxies file not found: proxies.txt"
        echo "Creating empty proxies.txt - running without proxies"
        touch proxies.txt
    else
        echo "✅ Proxies file found"
    fi
    
    # Test Celery import
    echo "🧪 Testing Celery integration..."
    if $PYTHON_BIN -c "from celery_integration import celery_app; print('Celery app imported successfully')" 2>/dev/null; then
        echo "✅ Celery integration working"
    else
        echo "❌ Celery integration has issues"
        echo "Testing import manually:"
        $PYTHON_BIN -c "from celery_integration import celery_app"
        return 1
    fi
    
    echo "✅ Environment setup complete"
    
    # Additional debug information
    echo ""
    echo "🔍 Environment Debug Info:"
    echo "   Working directory: $(pwd)"
    echo "   Python version: $($PYTHON_BIN --version)"
    echo "   Results directory: $(pwd)/results"
    echo "   Results dir exists: $([ -d results ] && echo 'YES' || echo 'NO')"
    echo "   Results dir permissions: $(ls -ld results 2>/dev/null || echo 'NOT FOUND')"
    
    return 0
}

# Function to start Celery worker
start_celery_workers() {
    local num_workers=${1:-100}  # Default to 100 workers for maximum speed
    local concurrency=${2:-$CELERY_CONCURRENCY}
    local total_capacity=$((num_workers * concurrency))
    
    echo "🚀 Starting $num_workers Celery workers with concurrency $concurrency each..."
    echo "📊 Total processing capacity: $total_capacity concurrent tasks"
    
    # Test if Celery can be imported first
    echo "🧪 Testing Celery app before starting workers..."
    if ! $PYTHON_BIN -c "from celery_integration import celery_app; print('OK')" 2>/dev/null; then
        echo "❌ Cannot import celery_integration.celery_app"
        echo "Please check celery_integration.py file"
        return 1
    fi
    
    # Start Celery flower monitoring (optional web UI)
    echo "🌸 Starting Celery Flower monitoring..."
    if command -v flower > /dev/null 2>&1; then
        nohup flower --broker=$REDIS_URL --port=5555 > logs/flower.log 2>&1 &
        echo $! > pids/flower.pid
        echo "✅ Flower started on port 5555"
    else
        echo "⚠️ Flower not available, skipping web UI"
    fi
    
    # Start the workers
    for ((i=1; i<=num_workers; i++)); do
        echo "Starting worker-$i with concurrency $concurrency..."
        nohup $CELERY_BIN -A celery_tasks worker \
            --loglevel=info \
            --hostname=worker-$i@%h \
            --concurrency=$concurrency \
            --max-tasks-per-child=1000 \
            --time-limit=300 \
            --soft-time-limit=240 \
            --uid=nobody \
            --gid=nogroup \
            > logs/worker-$i.log 2>&1 &
        
        echo $! > pids/worker-$i.pid
        sleep 1
    done
    
    echo "✅ Started $num_workers workers. Check status with: $0 status"
    echo "� Monitor at: http://localhost:5555 (Flower UI)"
    echo "📈 Processing capacity: $total_capacity concurrent phone numbers"
}

# Function to start Telegram bot
start_telegram_bot() {
    echo "🤖 Starting Telegram bot..."
    
    # Kill existing bot processes
    pkill -f "$PYTHON_BIN.*telegram_bot.py" 2>/dev/null || true
    sleep 2
    
    # Start Telegram bot in background
    nohup $PYTHON_BIN telegram_bot.py > $BOT_LOG_FILE 2>&1 &
    
    sleep 3
    
    if pgrep -f "$PYTHON_BIN.*telegram_bot.py" > /dev/null; then
        echo "✅ Telegram bot started successfully (PID: $(pgrep -f "$PYTHON_BIN.*telegram_bot.py"))"
        echo "📄 Logs: $BOT_LOG_FILE"
    else
        echo "❌ Failed to start Telegram bot"
        return 1
    fi
}

# Function to check status
check_status() {
    echo "📊 Service Status:"
    echo "=================="
    
    # Check Redis
    if redis-cli -u $REDIS_URL ping > /dev/null 2>&1; then
        echo "✅ Redis: Running"
    else
        echo "❌ Redis: Not running"
    fi
    
    # Check Celery workers
    if pgrep -f "celery.*worker" > /dev/null; then
        local worker_count=$(pgrep -f "celery.*worker" | wc -l)
        echo "✅ Celery Workers: $worker_count running"
        echo "   PIDs: $(pgrep -f 'celery.*worker' | tr '\n' ' ')"
    else
        echo "❌ Celery Workers: Not running"
    fi
    
    # Check Telegram bot
    if pgrep -f "$PYTHON_BIN.*telegram_bot.py" > /dev/null; then
        echo "✅ Telegram Bot: Running (PID: $(pgrep -f "$PYTHON_BIN.*telegram_bot.py"))"
    else
        echo "❌ Telegram Bot: Not running"
    fi
    
    echo ""
    echo "📁 Log Files:"
    echo "   Celery: $CELERY_LOG_FILE"
    echo "   Bot: $BOT_LOG_FILE"
}

# Function to stop all processes
stop_all() {
    echo "🛑 Stopping all processes..."
    
    # Stop Telegram bot
    if pgrep -f "$PYTHON_BIN.*telegram_bot.py" > /dev/null; then
        echo "🤖 Stopping Telegram bot..."
        pkill -f "$PYTHON_BIN.*telegram_bot.py"
        sleep 2
    fi
    
    # Stop Celery workers
    if pgrep -f "celery.*worker" > /dev/null; then
        echo "⚙️ Stopping Celery workers..."
        pkill -f "celery.*worker"
        sleep 3
        
        # Force kill if still running
        if pgrep -f "celery.*worker" > /dev/null; then
            pkill -9 -f "celery.*worker"
        fi
    fi
    
    # Clean up PID files
    rm -f logs/celery.pid
    
    echo "✅ All processes stopped"
}

# Function to show logs
show_logs() {
    echo "📄 Recent logs:"
    echo "==============="
    
    if [ -f "$CELERY_LOG_FILE" ]; then
        echo "🔧 Celery logs (last 20 lines):"
        tail -20 "$CELERY_LOG_FILE"
        echo ""
    fi
    
    if [ -f "$BOT_LOG_FILE" ]; then
        echo "🤖 Bot logs (last 20 lines):"
        tail -20 "$BOT_LOG_FILE"
        echo ""
    fi
    
    echo "💡 To follow logs in real-time:"
    echo "   tail -f $CELERY_LOG_FILE"
    echo "   tail -f $BOT_LOG_FILE"
}

# Main script logic
case "${1:-help}" in
    "setup")
        setup_environment
        ;;
    "workers")
        echo "🚀 Starting Celery workers only..."
        check_redis || exit 1
        setup_environment || exit 1
        start_celery_workers "${2:-$CELERY_WORKERS}" "${3:-$CELERY_CONCURRENCY}" || exit 1
        echo "✅ Workers started! Use '$0 status' to check status"
        ;;
    "bot")
        echo "🤖 Starting Telegram bot only..."
        setup_environment || exit 1
        start_telegram_bot || exit 1
        ;;
    "all")
        echo "🚀 Starting complete Doctolib Checker system..."
        check_redis || exit 1
        setup_environment || exit 1
        start_celery_workers "${2:-$CELERY_WORKERS}" "${3:-$CELERY_CONCURRENCY}" || exit 1
        start_telegram_bot || exit 1
        echo ""
        echo "🎉 System started successfully!"
        echo "📊 Use '$0 status' to check status"
        echo "📄 Use '$0 logs' to view logs"
        echo "🛑 Use '$0 stop' to stop everything"
        ;;
    "status")
        check_status
        ;;
    "stop")
        stop_all
        ;;
    "logs")
        show_logs
        ;;
    "help"|*)
        show_usage
        ;;
esac
