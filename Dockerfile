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

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    tini \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user to run the application
RUN groupadd -g 1000 oracle && \
    useradd -u 1000 -g oracle -s /bin/bash -m oracle

# Create necessary directories for persistent data with proper permissions
RUN mkdir -p /app/data/output /app/logs && \
    chown -R oracle:oracle /app && \
    chmod -R 750 /app

# Copy requirements file separately to leverage Docker caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY --chown=oracle:oracle src/ ./src/
COPY --chown=oracle:oracle scripts/ ./scripts/
COPY --chown=oracle:oracle contracts/ ./contracts/

# Copy marker files for project root detection
COPY --chown=oracle:oracle .gitignore ./
COPY --chown=oracle:oracle pyproject.toml ./

# Copy the scheduler to the root directory
COPY --chown=oracle:oracle src/models/scheduler.py ./

# Create healthcheck file
RUN touch /app/healthcheck && chown oracle:oracle /app/healthcheck

# Switch to non-root user
USER oracle

# Use Tini as entrypoint
ENTRYPOINT ["/usr/bin/tini", "--"]

# Add healthcheck to verify the service is running
HEALTHCHECK --interval=5m --timeout=30s --start-period=1m --retries=3 \
  CMD python -c "import os, time; assert os.path.exists('/app/healthcheck') and time.time() - os.path.getmtime('/app/healthcheck') < 3600, 'Healthcheck failed: file missing or too old'" || exit 1

# Run the scheduler
CMD ["python", "scheduler.py"]
