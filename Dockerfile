"""
Docker setup for Celery-based Doctolib phone checker
This provides a complete containerized environment
"""

# Multi-stage Dockerfile for production deployment
FROM python:3.11-slim as base

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV CELERY_BROKER_URL=redis://redis:6379/0
ENV CELERY_RESULT_BACKEND=redis://redis:6379/0

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements_celery.txt .
RUN pip install --no-cache-dir -r requirements_celery.txt

# Copy application code
COPY celery_tasks.py celeryconfig.py celery_main.py ./
COPY config.json ./

# Create necessary directories
RUN mkdir -p results logs

# Production stage
FROM base as production

# Copy data files
COPY proxies.txt ./
COPY results/phone_numbers.txt ./results/

# Expose Flower monitoring port
EXPOSE 5555

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD celery -A celery_tasks inspect ping || exit 1

# Default command (can be overridden)
CMD ["celery", "-A", "celery_tasks", "worker", "--loglevel=info"]
