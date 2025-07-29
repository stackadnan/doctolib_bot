# Celery Configuration
import os

# Broker settings (using Redis as message broker)
broker_url = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
result_backend = os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')

# Task settings
task_serializer = 'json'
result_serializer = 'json'
accept_content = ['json']
timezone = 'UTC'
enable_utc = True

# Worker settings
worker_concurrency = 4  # Number of concurrent tasks per worker
worker_prefetch_multiplier = 1  # Prevent workers from hoarding tasks
worker_max_tasks_per_child = 1000  # Restart worker after 1000 tasks to prevent memory leaks

# Task routing
task_routes = {
    'celery_tasks.check_phone_registration': {'queue': 'phone_checker'},
    'celery_tasks.process_phone_batch': {'queue': 'batch_processor'},
}

# Rate limiting
task_annotations = {
    'celery_tasks.check_phone_registration': {
        'rate_limit': '10/m',  # 10 tasks per minute to avoid detection
    }
}

# Task execution settings
task_always_eager = False  # Set to True for testing without broker
task_store_eager_result = True
task_track_started = True
task_reject_on_worker_lost = True

# Result settings
result_expires = 3600  # Results expire after 1 hour

# Retry settings
task_acks_late = True
worker_disable_rate_limits = False
