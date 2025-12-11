# Docker Deployment Guide

This guide covers deploying podcast-rag in Docker to run the scheduler for automated podcast processing.

## Quick Start

### 1. Prerequisites

- Docker and Docker Compose installed
- Podcast files accessible on the host
- Gemini API key

### 2. Configuration

Create a `.env` file in the project root:

```bash
cp .env.example .env
```

Edit `.env` with your settings:

```bash
# Required
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.5-flash
GEMINI_FILE_SEARCH_STORE_NAME=podcast-transcripts

# Optional - override in docker-compose.yml
MEDIA_EMBED_BASE_DIRECTORY=/data/podcasts
```

### 3. Set Environment Variables

Create a `.env.docker` file or set these in your shell:

```bash
# Path to your podcast directory on the host
export PODCAST_DIR=/opt/podcasts

# Path to store the cache file (default: current directory)
export CACHE_DIR=/path/to/persistent/storage
```

### 4. Build and Run

```bash
# Build the image
docker compose build

# Start the scheduler (runs continuously)
docker compose up -d

# View logs
docker compose logs -f

# Stop the service
docker compose down
```

## Service Details

### Main Service: `podcast-rag`

- **Purpose**: Runs `scheduler.py` continuously
- **Schedule**: Processes podcasts every hour (configurable in scheduler.py)
- **Auto-restart**: Enabled (`unless-stopped`)
- **Resources**:
  - Limit: 2 CPU cores, 4GB RAM
  - Reserved: 0.5 CPU cores, 1GB RAM

### Volume Mounts

1. **Podcast Directory**: `/data/podcasts` (read-only)
   - Maps to `$PODCAST_DIR` on host (default: `/opt/podcasts`)
   - Contains your MP3 files organized by podcast name

2. **Cache File**: `.file_search_cache.json`
   - Stores metadata for fast lookups
   - Persisted to `$CACHE_DIR` on host

## Usage Examples

### Running One-Time Processing

```bash
# Run the processing pipeline
docker compose run --rm podcast-rag python src/scheduler.py

# Or using the CLI
docker compose run --rm podcast-rag python -m src.cli podcast pipeline
```

### Running a RAG Query

```bash
# Interactive query
docker compose run --rm podcast-rag \
  python -m src.rag --query "What topics are discussed?"
```

### Rebuilding Cache

```bash
docker compose run --rm podcast-rag \
  python scripts/rebuild_cache.py
```

### Managing File Search

```bash
# List files in store
docker compose run --rm podcast-rag \
  python scripts/file_search_utils.py --action list

# Find duplicates
docker compose run --rm podcast-rag \
  python scripts/file_search_utils.py --action find-duplicates
```

## Homelab Integration

### Typical Homelab Setup

```yaml
# docker-compose.yml additions for homelab
version: '3.8'

services:
  podcast-rag:
    # ... existing config ...

    # Network configuration
    networks:
      - homelab

    # Labels for reverse proxy (Traefik example)
    labels:
      - "traefik.enable=false"  # No web interface

    # Restart policy
    restart: unless-stopped

networks:
  homelab:
    external: true
```

### Environment Variables in Homelab

If you're using something like Portainer or a dotfiles system:

```bash
# Set these in your homelab environment
PODCAST_DIR=/mnt/media/podcasts
CACHE_DIR=/mnt/data/podcast-rag
GEMINI_API_KEY=<from-secrets-manager>
```

## Monitoring

### Health Checks

The container includes a health check. View status:

```bash
docker compose ps
```

Healthy output:
```
NAME          STATUS                    PORTS
podcast-rag   Up 5 minutes (healthy)
```

### Logs

```bash
# Follow logs
docker compose logs -f

# Last 100 lines
docker compose logs --tail=100

# Specific timestamp
docker compose logs --since 2h
```

### Log Levels

Adjust log verbosity by modifying the CMD in docker-compose.yml:

```yaml
command: ["python", "src/scheduler.py", "--log-level", "DEBUG"]
```

## Troubleshooting

### Container Won't Start

```bash
# Check logs
docker compose logs

# Check environment
docker compose config

# Verify volumes
docker compose run --rm podcast-rag ls -la /data/podcasts
```

### Permission Issues

The container runs as user `podcast` (UID 1000). Ensure your podcast files are readable:

```bash
# On host
chmod -R a+r /opt/podcasts
```

Or build with custom UID:

```dockerfile
# In Dockerfile, change:
RUN useradd -m -u 1000 ...
# To your UID:
RUN useradd -m -u $(id -u) ...
```

### FFmpeg Not Found

If you see "ffmpeg not found" errors:

```bash
# Rebuild the image
docker compose build --no-cache
```

### Out of Memory

Increase memory limits in docker-compose.yml:

```yaml
deploy:
  resources:
    limits:
      memory: 8G  # Increase from 4G
```

## Updating

```bash
# Pull latest code
git pull

# Rebuild and restart
docker compose down
docker compose build
docker compose up -d
```

## Resource Usage

Expected resource consumption:

- **Idle**: ~100MB RAM, minimal CPU
- **Transcribing**: 1-2GB RAM, 50-100% CPU (per core)
- **Metadata Extraction**: ~500MB RAM, 20% CPU
- **Disk**: Minimal (cache file ~14MB for 17k files)

## Production Recommendations

1. **Persistent Storage**: Store cache file on persistent volume
2. **Monitoring**: Set up log aggregation (e.g., Loki, ELK)
3. **Secrets**: Use Docker secrets for GEMINI_API_KEY
4. **Backups**: Backup `.file_search_cache.json` regularly
5. **Resource Limits**: Adjust based on your homelab capacity
6. **Auto-updates**: Consider Watchtower for automatic updates

## Example Homelab Stack

```yaml
# Full example for homelab deployment
version: '3.8'

services:
  podcast-rag:
    build: .
    container_name: podcast-rag
    restart: unless-stopped

    environment:
      - GEMINI_API_KEY=${GEMINI_API_KEY}
      - GEMINI_MODEL=gemini-2.5-flash
      - MEDIA_EMBED_BASE_DIRECTORY=/data/podcasts

    volumes:
      - /mnt/media/podcasts:/data/podcasts:ro
      - podcast-rag-cache:/app

    networks:
      - homelab

    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 4G

    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

volumes:
  podcast-rag-cache:
    driver: local

networks:
  homelab:
    external: true
```
