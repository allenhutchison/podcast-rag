# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Python-based Retrieval-Augmented Generation (RAG) system for a podcast library. The system downloads podcasts from RSS feeds, transcribes them using OpenAI's Whisper, extracts metadata using AI models (Gemini or Ollama), stores embeddings in ChromaDB, and provides a web interface for semantic search and question answering.

## Architecture

### Data Flow Pipeline
1. **Download** (`podcast_downloader.py`) → Fetches episodes from RSS feeds/OPML files
2. **Transcribe** (`transcribe_podcasts.py`) → Converts audio to text using Whisper
3. **Extract Metadata** (`metadata_extractor.py`) → Uses AI to extract structured data (title, hosts, guests, keywords) from transcripts and MP3 tags
4. **Index** (`db/chroma_vectordb.py`) → Chunks transcripts and stores embeddings in ChromaDB
5. **Query** (`rag.py`, `chroma_search.py`) → Retrieves relevant chunks and generates AI-powered answers

### Key Components

**Orchestration Layer:**
- `file_manager.py` - Central coordinator that runs transcription → metadata extraction → indexing for all podcasts in a directory
- `download_and_transcribe.py` - End-to-end pipeline for downloading and processing podcasts
- `scheduler.py` - APScheduler-based background job that runs `file_manager.py` every hour to process new episodes

**Data Storage:**
- `db/chroma_vectordb.py` - Manages ChromaDB vector database (stores transcript chunks with embeddings)
- `db/metadatadb.py` - SQLAlchemy-based SQLite database for podcast/episode metadata (titles, feed URLs, descriptions)
- Transcripts are stored as `{episode_name}_transcription.txt` files alongside MP3s

**RAG Implementation:**
- `rag.py` - `RagManager` class orchestrates the RAG pipeline: query → vector search → prompt formatting → AI generation
- `chroma_search.py` - Handles ChromaDB queries and returns relevant transcript chunks with metadata
- `prompt_manager.py` - Loads and formats prompts from `/prompts` directory using template substitution
- Prompts in `/prompts` use placeholders like `{query}`, `{context}`, `{podcast}`, etc.

**AI Integration:**
- Supports two AI backends: Ollama (local) or Gemini (cloud)
- Metadata extraction uses Pydantic schemas (`schemas.py`) with Gemini's structured output API
- RAG queries can use either backend based on `--ai-system` argument

**Web Interface:**
- `app.py` - Flask application entry point (imports from `src/app.py`)
- Web UI provides search interface and podcast management

**MCP Server:**
- `mcp_server.py` - Model Context Protocol server for podcast search integration with AI assistants

## Common Development Commands

### Installation
```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Linux/macOS

# Install dependencies (project uses uv for fast installation)
uv pip install -r requirements.txt
# OR standard pip:
pip install -r requirements.txt
```

### Running the Application
```bash
# Start web interface (runs on default Flask port 5000)
python3 app.py

# Run scheduler for automatic processing (checks every hour)
python3 src/scheduler.py --env-file .env
```

### Processing Podcasts
```bash
# Download and process podcasts from a feed
python src/download_and_transcribe.py --feed https://feeds.megaphone.fm/darknetdiaries --limit 5

# Download from OPML file (list of feeds)
python src/download_and_transcribe.py --feed-file podcast_feeds.txt

# Process existing downloaded podcasts (transcribe + index)
python src/file_manager.py

# Transcribe a single episode
python src/transcribe_podcasts.py --episode-path /path/to/episode.mp3

# Dry run mode (preview without processing)
python src/download_and_transcribe.py --feed-file podcast_feeds.txt --dry-run
```

### Querying
```bash
# Search vector database only
python src/chroma_search.py --query "your search query"

# Full RAG pipeline with AI answer generation
python src/rag.py --query "your question" --ai-system gemini
python src/rag.py --query "your question" --ai-system ollama
```

### Testing
```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_file_manager.py

# Run with verbose output
pytest -v
```

## Configuration

**Environment Variables** (create `.env` from `.env.example`):
- `MEDIA_EMBED_BASE_DIRECTORY` - Root directory containing podcast subdirectories
- `CHROMA_DB_HOST`, `CHROMA_DB_PORT` - ChromaDB connection settings
- `GEMINI_API_KEY`, `GEMINI_MODEL` - Gemini API configuration
- `OLLAMA_HOST`, `OLLAMA_MODEL` - Ollama configuration

All scripts support `--env-file` argument to specify a custom `.env` file location.

## File Organization

Podcasts are organized as:
```
MEDIA_EMBED_BASE_DIRECTORY/
  ├── Podcast Name 1/
  │   ├── episode1.mp3
  │   ├── episode1_transcription.txt
  │   ├── episode2.mp3
  │   └── episode2_transcription.txt
  └── Podcast Name 2/
      └── ...
```

The system automatically:
- Creates temp files (`.transcription_in_progress`, `.index_in_progress`) to track processing
- Skips already-processed files (checks for existence of `_transcription.txt` and `_index.txt` marker files)

## Important Implementation Details

**Transcript Chunking:**
- `VectorDbManager.split_transcript_into_chunks()` uses sentence tokenization with overlap
- Default: 500 words per chunk, 50 word overlap
- Chunks are indexed with metadata (podcast name, episode title, hosts, guests, keywords, timestamps)

**Metadata Extraction:**
- Extracts both AI-generated metadata (from transcripts) and technical metadata (from MP3 ID3 tags)
- Uses Pydantic schemas for structured output validation
- Metadata is stored in both SQLite (searchable) and ChromaDB (alongside embeddings)

**Error Handling:**
- Components gracefully degrade if ChromaDB is unavailable (use `--skip-vectordb` to suppress warnings)
- Failed transcriptions leave temp files for manual inspection
- Scheduler logs to `scheduler.log` for debugging background jobs

**Resource Management:**
- Whisper model is loaded once and reused across all transcriptions in a batch
- `TranscriptionManager.release_model()` explicitly frees memory after processing
- File descriptors are properly closed after each operation to prevent leaks
