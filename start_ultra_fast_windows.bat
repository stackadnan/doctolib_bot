@echo off
echo.
echo ===============================================
echo    ULTRA-FAST DOCTOLIB BOT - WINDOWS VERSION
echo ===============================================
echo.

set PYTHON_EXE=C:\Users\muham\AppData\Local\Programs\Python\Python310\python.exe

echo 📋 Step 1: Testing Python and packages...
"%PYTHON_EXE%" -c "import celery, redis, requests; print('✅ All packages available')"
if %errorlevel% neq 0 (
    echo ❌ Packages missing. Installing...
    "%PYTHON_EXE%" -m pip install celery redis requests python-telegram-bot
)

echo.
echo 📋 Step 2: Testing Celery integration...
"%PYTHON_EXE%" -c "from celery_integration import is_celery_available; print('✅ Celery integration OK')"
if %errorlevel% neq 0 (
    echo ❌ Celery integration has issues. Please check Redis.
    echo 💡 Install Redis: https://github.com/microsoftarchive/redis/releases
    pause
    exit /b 1
)

echo.
echo 📋 Step 3: Starting 10 ultra-fast workers...
for /l %%i in (1,1,10) do (
    echo Starting worker %%i...
    start /min "Worker-%%i" "%PYTHON_EXE%" -m celery -A celery_tasks worker --loglevel=info --concurrency=1 --hostname=worker%%i
    timeout /t 1 >nul
)

echo.
echo ✅ 10 workers started!
echo.
echo 📋 Step 4: Testing worker availability...
timeout /t 5 >nul
"%PYTHON_EXE%" -c "from celery_integration import is_celery_available; print('✅ Workers ready!' if is_celery_available() else '⚠️ Workers still starting...')"

echo.
echo 🤖 Step 5: Starting Telegram bot...
echo Press Ctrl+C to stop the bot
echo.
"%PYTHON_EXE%" telegram_bot.py

echo.
echo 👋 Bot stopped. Workers are still running in background.
echo Use Task Manager to close worker windows if needed.
pause
