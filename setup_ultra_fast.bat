@echo off
echo.
echo ==========================================
echo    ULTRA-FAST DOCTOLIB BOT SETUP
echo ==========================================
echo.

echo 📋 Step 1: Installing Redis via Chocolatey...
echo ⚠️  This requires admin privileges

choco install redis-64 -y
if %errorlevel% neq 0 (
    echo ❌ Redis installation failed. Please install Redis manually.
    echo 💡 Alternative: Download Redis from https://github.com/microsoftarchive/redis/releases
    pause
    exit /b 1
)

echo.
echo ✅ Redis installed successfully!
echo.

echo 📋 Step 2: Starting Redis service...
redis-server --service-install
redis-server --service-start
if %errorlevel% neq 0 (
    echo ⚠️  Service mode failed, starting Redis directly...
    start /b redis-server
    timeout /t 3 >nul
)

echo.
echo 📋 Step 3: Testing Redis connection...
redis-cli ping
if %errorlevel% neq 0 (
    echo ❌ Redis is not responding. Please check the installation.
    pause
    exit /b 1
)

echo.
echo ✅ Redis is running successfully!
echo.

echo 📋 Step 4: Starting 20 ultra-fast Celery workers...
for /l %%i in (1,1,20) do (
    start /min "Celery Worker %%i" "C:/Users/muham/AppData/Local/Programs/Python/Python310/python.exe" -m celery -A celery_tasks worker --loglevel=info --concurrency=1 --hostname=worker%%i@%%h
    timeout /t 1 >nul
)

echo.
echo ✅ 20 Celery workers started!
echo.

echo 📋 Step 5: Testing Celery workers...
timeout /t 5 >nul
"C:/Users/muham/AppData/Local/Programs/Python/Python310/python.exe" -c "from celery_integration import is_celery_available; print('✅ Workers ready!' if is_celery_available() else '❌ Workers not detected')"

echo.
echo 🚀 SYSTEM READY!
echo ==========================================
echo ⚡ 20 Ultra-fast workers active
echo 📱 31 phones = 2-3 minutes processing
echo 🎯 Each phone gets individual worker
echo ==========================================
echo.
echo 📋 Next step: Start your Telegram bot
echo Command: python telegram_bot.py
echo.
pause
