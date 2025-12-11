![CodeRabbit Pull Request Reviews](https://img.shields.io/coderabbit/prs/github/allenhutchison/podcast-rag?utm_source=oss&utm_medium=github&utm_campaign=allenhutchison%2Fpodcast-rag&labelColor=171717&color=FF570A&link=https%3A%2F%2Fcoderabbit.ai&label=CodeRabbit+Reviews)

# Podcast RAG System

A Python-based Retrieval-Augmented Generation (RAG) system for intelligent search and question-answering over podcast libraries. The system transcribes audio using Whisper, extracts metadata with AI, and enables semantic search with automatic citations.

## Features
- Automatic transcription of MP3 files using OpenAI Whisper
- AI-powered metadata extraction (titles, hosts, guests, summaries, keywords)
- Vector embeddings and semantic search using Gemini File Search
- Natural language queries with source citations
- Local metadata cache for instant lookups
- Scheduled batch processing
- Dry-run mode and comprehensive logging

## Installation

This project uses [uv](https://docs.astral.sh/uv/) for fast, reliable dependency management. You can also use traditional pip if preferred.

### Prerequisites
1. Python 3.11+ (recommended)
2. Install `ffmpeg`:
   - **Linux:**
     ```bash
     sudo apt-get install ffmpeg
     ```
   - **macOS (using Homebrew):**
     ```bash
     brew install ffmpeg
     ```
   - **Windows:**
     - Download and install `ffmpeg` from [https://ffmpeg.org/download.html](https://ffmpeg.org/download.html).

3. Install `uv` (recommended):
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   # Or on macOS:
   brew install uv
   ```

### Install

```bash
# Clone and enter the repository
git clone https://github.com/allenhutchison/podcast-rag
cd podcast-rag

# Install all dependencies (creates .venv automatically)
uv sync

# Optional: Activate the virtual environment
# (not required if using 'uv run' commands)
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

## Configuration

The configuration is managed via environment variables loaded from a `.env` file.

1. Create your `.env` file from the example:

```bash
cp .env.example .env
# Edit .env with your configuration
```

2. Configure required environment variables (see `.env.example` for all options):

```bash
# Media directory
MEDIA_EMBED_BASE_DIRECTORY=/path/to/your/podcasts

# Gemini API (for metadata extraction and RAG)
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.5-flash

# Gemini File Search
GEMINI_FILE_SEARCH_STORE_NAME=podcast-transcripts
```

3. Test the installation by checking status:
```bash
uv run python -m src.cli podcast status
```

See `src/config.py` for implementation details.

## Docker Deployment

Pre-built Docker images are available on Docker Hub for easy deployment:
- **`allenhutchison/podcast-rag`** - Encoding backend (transcription + metadata extraction)
- **`allenhutchison/podcast-rag-web`** - Web interface for querying podcasts

### Homelab Deployment (Recommended)

Run both the encoding backend and web service together using docker-compose:

1. **Create `.env` file** with required environment variables:
   ```bash
   cp .env.example .env
   # Edit .env with your API keys and paths
   ```

2. **Configure environment** (in your shell or `.env` file):
   ```bash
   export PODCAST_DIR=/path/to/your/podcasts  # Local podcast directory
   export CACHE_DIR=.                         # Directory for cache file
   ```

3. **Start services**:
   ```bash
   # Pull latest images
   docker-compose pull

   # Start both services in background
   docker-compose up -d

   # View logs
   docker-compose logs -f

   # Stop services
   docker-compose down
   ```

4. **Access web interface**:
   - Open http://localhost:8080 in your browser
   - Start querying your podcast library!

**What's running:**
- **podcast-rag**: Processes new podcasts every hour, updates metadata cache
- **podcast-rag-web**: Serves web UI for real-time queries with streaming responses

**Shared resources:**
- `.file_search_cache.json`: Metadata cache (both services read/write)
- Podcast directory: Source audio files (read-only)

### Cloud Run Deployment (Web Service Only)

Deploy the web interface to Google Cloud Run for public access:

1. **Build and push web image** (or use pre-built from Docker Hub):
   ```bash
   gcloud builds submit --tag gcr.io/YOUR_PROJECT/podcast-rag-web
   ```

2. **Deploy to Cloud Run**:
   ```bash
   gcloud run deploy podcast-rag-web \
     --image gcr.io/YOUR_PROJECT/podcast-rag-web \
     --platform managed \
     --region us-central1 \
     --allow-unauthenticated \
     --set-env-vars GEMINI_API_KEY=your_key,GEMINI_FILE_SEARCH_STORE_NAME=podcast-transcripts
   ```

3. **Access your deployment**:
   - Cloud Run provides a public URL
   - Web service connects to your Gemini File Search store

**Note**: Cloud Run deployment uses `Dockerfile.web` which excludes ffmpeg (~100MB) for faster startup. The homelab encoding backend must run separately to process podcasts.

### Building Images Yourself

Images are automatically built via GitHub Actions when you create a release:

```bash
# Create and push a tag
git tag v1.0.0
git push origin v1.0.0

# Or create release via GitHub UI
# This triggers builds for both images
```

**Manual build**:
```bash
# Build encoding backend
docker build -t podcast-rag -f Dockerfile .

# Build web service
docker build -t podcast-rag-web -f Dockerfile.web .
```

### Image Details

| Image | Base | Size | Contains | Use Case |
|-------|------|------|----------|----------|
| `podcast-rag` | python:3.12-slim | ~1.5GB | ffmpeg, whisper, all dependencies | Homelab encoding backend |
| `podcast-rag-web` | python:3.12-slim | ~500MB | Web server, no ffmpeg | Cloud Run or homelab web UI |

Both images:
- Use multi-stage builds for smaller size
- Run as non-root user (UID 1000)
- Include health checks
- Support automatic cache rebuilding

## Usage

All commands can be run with `uv run` or directly if you've activated the virtual environment.

### Run the processing pipeline:
```bash
# Run the pipeline (continuous processing optimized for GPU)
uv run python src/scheduler.py

# Or using the CLI
uv run python -m src.cli podcast pipeline
```

### Check status:
```bash
uv run python -m src.cli podcast status
```

### Query the RAG system:
```bash
uv run python -m src.rag --query "your question here"
```

### Manage File Search store:
```bash
# List all documents in the store
python scripts/file_search_utils.py --action list

# Find duplicate files
python scripts/file_search_utils.py --action find-duplicates

# Delete duplicates (keeps oldest by default)
python scripts/file_search_utils.py --action delete-duplicates

# Delete all files (with confirmation)
python scripts/file_search_utils.py --action delete-all
```

### Rebuild metadata cache:
```bash
# Rebuild cache from remote File Search store
python scripts/rebuild_cache.py
```

This fetches all document metadata from the remote File Search store and saves it to a local cache file for instant lookups during RAG queries.

## Logging
The tool uses Python's built-in logging for tracking progress and errors. By default, logs are displayed in the console at INFO level.

### Set log level:
```bash
# Available levels: DEBUG, INFO, WARNING, ERROR
python src/scheduler.py --log-level DEBUG
python -m src.rag --query "your question" --log-level ERROR
```

## Error Reporting
When processing fails for any episodes, the pipeline will log detailed error information showing:
- Episodes that failed to transcribe
- Episodes that failed metadata extraction
- Episodes that failed indexing

Use `python -m src.cli podcast status` to view current processing status and any failures.

## Testing
Unit tests can be run using `pytest`. To install `pytest`:

```bash
pip install pytest
```

To run the tests:
```bash
pytest
```

## Contributing
Contributions are welcome! Please submit a pull request with any improvements or bug fixes. Ensure all tests pass before submitting your PR.

## License
This project is licensed under the Apache 2.0 License. See the `LICENSE` file for details.

