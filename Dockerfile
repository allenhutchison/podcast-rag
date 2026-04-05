# Multi-stage build for smaller final image
FROM python:3.12-slim AS builder

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install all dependencies (encoding + web, no dev)
RUN uv sync --frozen --no-dev --group encoding --group web --no-install-project

# Final stage
FROM python:3.12-slim

# Install system dependencies
# - ffmpeg: Required for Whisper audio processing
# - curl: For health checks
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    apt-transport-https \
    ca-certificates \
    gnupg \
    && curl -sLf --retry 3 --tlsv1.2 --proto "=https" \
    'https://packages.doppler.com/public/cli/gpg.DE2A7741A397C129.key' | gpg --dearmor -o /usr/share/keyrings/doppler-archive-keyring.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/doppler-archive-keyring.gpg] https://packages.doppler.com/public/cli/deb/debian any-version main" | tee /etc/apt/sources.list.d/doppler-cli.list \
    && apt-get update && apt-get -y install doppler \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -u 1000 -s /bin/bash podcast && \
    mkdir -p /app /data/podcasts && \
    chown -R podcast:podcast /app /data

# Set working directory
WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder --chown=podcast:podcast /app/.venv /app/.venv

# Copy application code
COPY --chown=podcast:podcast . .

# Install the project itself
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/
RUN /bin/uv sync --frozen --no-dev --group encoding --group web

# Copy entrypoint script
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod 755 /usr/local/bin/docker-entrypoint.sh

# Switch to non-root user
USER podcast

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PODCAST_DOWNLOAD_DIRECTORY=/data/podcasts \
    LD_LIBRARY_PATH="/app/.venv/lib/python3.12/site-packages/nvidia/cublas/lib:/app/.venv/lib/python3.12/site-packages/nvidia/cudnn/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import sys; sys.exit(0)"

# Entrypoint wraps CMD with doppler when DOPPLER_TOKEN is set
ENTRYPOINT ["docker-entrypoint.sh"]

# Default command (can be overridden in docker-compose)
CMD ["python", "src/scheduler.py"]
