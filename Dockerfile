# Use lightweight Python 3.12 slim base
FROM python:3.12-slim

# Prevent Python from writing .pyc files and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Set working directory
WORKDIR /app

# Install system dependencies if required (sqlite3 is bundled with python)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python packages
COPY service/requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && \
    pip install -r /app/requirements.txt

# Copy service code
COPY service/ /app/service/

# Create data directory for SQLite database storage and non-root user
RUN mkdir -p /data && \
    useradd -u 1000 -m appuser && \
    chown -R appuser:appuser /app /data

USER appuser

# Default runtime configuration
ENV MQTT_BROKER=mqtt-broker \
    MQTT_PORT=1883 \
    MQTT_TOPIC=home/room1/env \
    TEMP_THRESHOLD=30.0 \
    DB_PATH=/data/env_data.db \
    LOG_LEVEL=INFO

# Run subscriber service
CMD ["python", "-m", "service.monitor"]
