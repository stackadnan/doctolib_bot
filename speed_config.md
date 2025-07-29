# ⚡ Speed Optimization Guide

## Performance Improvements Made

### 1. Reduced Delays
- **Base delay**: 2.0s → 0.5s (4x faster)
- **Randomization**: 1.0s → 0.3s (3x faster)
- **Retry delay**: 5.0s → 2.0s (2.5x faster)

### 2. Increased Workers & Concurrency
- **Workers**: 4 → 8 (double the workers)
- **Concurrency**: 4 → 8 per worker (double the parallel tasks)
- **Total capacity**: 16 → 64 concurrent tasks (4x capacity)

### 3. Optimized Timeouts & Retries
- **API timeout**: 30s → 10s (3x faster failure detection)
- **Max retries**: 3 → 2 (faster failure handling)
- **Backoff factor**: 1s → 0.5s (faster retry attempts)

### 4. Smart Batching
- **Large jobs**: 50 phone batch → 10 phone batch
- **Small jobs** (<100 phones): Individual processing for maximum speed
- **Immediate task distribution**: No waiting for batches to complete

## Expected Performance

### Before Optimization:
- 31 phones in 19 minutes = ~37 seconds per phone
- Processing capacity: 16 concurrent tasks

### After Optimization:
- 31 phones should complete in ~2-3 minutes = ~4-6 seconds per phone
- Processing capacity: 64 concurrent tasks
- **~8-10x speed improvement**

## Commands for Maximum Speed

```bash
# For maximum performance (will use ~192 concurrent tasks!)
./run_celery.sh all 16 12

# For balanced performance (64 concurrent tasks)
./run_celery.sh all

# Monitor performance
./run_celery.sh status
```

## Speed Test Results

After restarting with optimizations:
- Test with 31 phones should complete in 2-3 minutes
- Each phone should process in 4-6 seconds
- Total system capacity: 64-192 concurrent phone checks

If still slow, check:
1. Internet connection speed
2. Doctolib server response times
3. Proxy performance (if using proxies)
