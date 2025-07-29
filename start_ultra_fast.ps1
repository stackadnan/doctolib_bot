# Ultra-Fast Doctolib Bot Startup Script for Windows
# 100 workers for maximum parallel processing

Write-Host "🚀 ULTRA-FAST MODE: Starting 100 Celery workers" -ForegroundColor Green
Write-Host "================================================"
Write-Host "⚡ Target: 31 phones = 31 workers = 2-3 minutes"
Write-Host "📊 Configuration: 100 workers × 1 concurrency = 100 total capacity"
Write-Host ""

# Check if Redis is available
Write-Host "🔍 Checking Redis..." -ForegroundColor Yellow
try {
    $redisCheck = redis-cli ping 2>$null
    if ($redisCheck -eq "PONG") {
        Write-Host "✅ Redis is running" -ForegroundColor Green
    } else {
        Write-Host "⚠️  Redis not responding, please start Redis manually" -ForegroundColor Yellow
    }
} catch {
    Write-Host "⚠️  Redis-cli not found, please ensure Redis is installed and running" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "🚀 Starting 100 ultra-fast workers..." -ForegroundColor Green

# Start the workers using bash script
if (Test-Path "run_celery.sh") {
    bash ./run_celery.sh workers 100 1
} else {
    Write-Host "❌ run_celery.sh not found in current directory" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "✅ Ultra-fast system ready!" -ForegroundColor Green
Write-Host "📱 For 31 phones: All will be processed simultaneously"
Write-Host "⏱️  Expected time: 2-3 minutes"
Write-Host ""
Write-Host "🔍 Monitor progress with:"
Write-Host "   Get-ChildItem results\downloadable_*.txt | Sort LastWriteTime -Descending | Select Name, Length, LastWriteTime"
Write-Host ""
Write-Host "🎯 Start your bot and send phone numbers!" -ForegroundColor Cyan
