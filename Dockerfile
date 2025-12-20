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
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -u 1000 -s /bin/bash podcast && \
    mkdir -p /app /data/podcasts /data/cache && \
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

# Switch to non-root user
USER podcast

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MEDIA_EMBED_BASE_DIRECTORY=/data/podcasts

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import sys; sys.exit(0)"

# Default command (can be overridden in docker-compose)
CMD ["python", "src/scheduler.py"]
