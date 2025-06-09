# Dockerfile for Service Quality Oracle

# Use Python 3.9 slim as the base image for a lightweight container
FROM python:3.9-slim

# Add metadata labels
LABEL description="Service Quality Oracle" \
      version="0.1.0"

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    TZ=UTC

# Install minimal system dependencies
RUN apt-get update && apt-get install -y \
    tini \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file first to leverage Docker caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Create necessary directories for persistent data
RUN mkdir -p /app/data/output /app/logs

# Copy the application code
COPY src/ ./src/
COPY scripts/ ./scripts/
COPY contracts/ ./contracts/

# Copy marker files for project root detection
COPY .gitignore ./
COPY pyproject.toml ./

# Copy the scheduler to the root directory
COPY src/models/scheduler.py ./

# Create healthcheck file
RUN touch /app/healthcheck

# Use Tini as entrypoint for proper signal handling
ENTRYPOINT ["/usr/bin/tini", "--"]

# Add healthcheck to verify the service is running
HEALTHCHECK --interval=5m --timeout=30s --start-period=1m --retries=3 \
  CMD python -c "import os, time; assert os.path.exists('/app/healthcheck') and time.time() - os.path.getmtime('/app/healthcheck') < 3600, 'Healthcheck failed'" || exit 1

# Run the scheduler
CMD ["python", "scheduler.py"]
