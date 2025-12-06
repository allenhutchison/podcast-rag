# CLAUDE.md - AI Assistant Context for Podcast RAG System

This document provides context for AI assistants working with this codebase.

## Project Overview

**Podcast RAG System** is a Python-based Retrieval-Augmented Generation (RAG) application that enables intelligent search and question-answering over podcast libraries.

**Core Functionality:**
- Transcribes audio using OpenAI Whisper
- Extracts structured metadata using AI (Gemini)
- Stores transcriptions in vector databases for semantic search
- Answers natural language queries with source citations via CLI

**Tech Stack:** Python 3.11, Gemini File Search, Whisper, Gemini API

## Architecture

### High-Level RAG Pipeline

```
User Query → Vector Search → Context Retrieval → Prompt Formatting → AI Model → Sourced Answer
```

### Key Components

1. **RAG Manager** (`src/rag.py`) - Orchestrates query processing pipeline
2. **File Manager** (`src/file_manager.py`) - Central processor for transcription → metadata → indexing
3. **Transcription Manager** (`src/transcribe_podcasts.py`) - Processes audio files with Whisper
4. **Background Services:**
   - `src/scheduler.py` - Scheduled transcription processing
5. **Search & Storage:**
   - Gemini File Search - Semantic search with automatic chunking and embeddings
   - Local metadata cache - Fast lookups without API calls
6. **MCP Server** (`src/mcp_server.py`) - Claude integration protocol

### Project Structure

```
/home/user/podcast-rag/
├── src/                    # Core application code
│   ├── rag.py              # RAG pipeline orchestrator
│   ├── config.py           # Configuration management
│   ├── schemas.py          # Pydantic models for validation
│   ├── file_manager.py     # Processing orchestrator
│   ├── transcribe_podcasts.py  # Whisper transcription manager
│   ├── scheduler.py        # Scheduled processing
│   │
│   ├── db/
│   │   └── gemini_file_search.py  # Gemini File Search interface
│
├── scripts/
│   ├── file_search_utils.py      # File Search management utilities
│   └── rebuild_cache.py          # Cache rebuilding tool
│
├── prompts/                # AI prompt templates
│   └── metadata_extraction.txt   # Metadata extraction
│
├── tests/                  # pytest test suite
├── pyproject.toml          # Project config and dependencies (uv)
└── uv.lock                 # Locked dependencies
```

## Key Files Reference

| File | Purpose | When to Modify |
|------|---------|----------------|
| `src/config.py` | Environment variables, paths, settings | Adding new config options |
| `src/rag.py` | Query processing, AI inference | Changing RAG logic |
| `src/db/gemini_file_search.py` | Gemini File Search interface | File Search integration changes |
| `src/file_manager.py` | Transcription + metadata pipeline | Processing workflow changes |
| `src/gemini_search.py` | Search manager using Gemini File Search | Search logic modifications |
| `src/metadata_extractor.py` | AI-powered metadata parsing | Changing metadata fields |
| `prompts/metadata_extraction.txt` | Metadata extraction prompt | Improving metadata quality |
| `pyproject.toml` | Python dependencies (uv) | Adding/updating packages |

## Development Workflow

### Setup

This project uses [uv](https://docs.astral.sh/uv/) for dependency management.

```bash
# 1. Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh
# Or on macOS: brew install uv

# 2. Install dependencies and create virtual environment
uv sync

# 3. Activate virtual environment (optional if using 'uv run')
source .venv/bin/activate

# 4. Configure environment
cp .env.example .env
# Edit .env with database credentials, API keys

# 5. Initialize the database
alembic upgrade head

# 6. System dependencies
# Requires: ffmpeg
```

### Common Tasks

**Process Existing Podcasts:**
```bash
# Process all podcasts in media directory
python src/file_manager.py

# Scheduled processing (runs every hour)
python src/scheduler.py
```

**Query & Search:**
```bash
# RAG query with Gemini File Search
python -m src.rag --query "your question"

# Manage File Search store (list, find duplicates, delete)
python scripts/file_search_utils.py --action list

# Rebuild cache with metadata
python scripts/rebuild_cache.py
```

**Testing:**
```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_file_manager.py

# Verbose output
pytest -v

# With coverage
pytest --cov=src tests/
```

## Coding Conventions

### Style Guide
- **Classes:** PascalCase (`TranscriptionManager`, `GeminiFileSearchManager`)
- **Functions/Methods:** snake_case (`handle_transcription`, `search_vector_db`)
- **Constants:** UPPER_SNAKE_CASE (`TRANSCRIPTION_OUTPUT_SUFFIX`)
- **Private methods:** Leading underscore (`_parse_response`)

### Patterns Used
- **Singleton:** Config class for app-wide settings
- **Factory:** Model loading (Whisper, AI clients)
- **Service Layer:** Separation of business logic from routes
- **Repository:** Database access abstraction

### Error Handling
- Use try/except with specific exception types
- Log errors with context (logger.error with traceback)
- Retry logic with exponential backoff for network operations
- Validate inputs with Pydantic schemas

## Important Context

### Dependencies & Integrations

**External APIs:**
- **Gemini API:** Requires `GEMINI_API_KEY` environment variable
  - Model: `gemini-2.0-flash-exp` (configurable via `GEMINI_MODEL`)
  - Used for: RAG queries, metadata extraction

**Gemini File Search:**
- Google-hosted semantic search solution
- Automatic chunking and embedding
- Local metadata cache (`.file_search_cache.json`) for instant lookups

### Known Constraints

1. **Whisper Model:** Large-v3 model requires significant RAM (~10GB VRAM for GPU)
2. **Transcription Speed:** Real-time factor varies (1-3x on CPU, faster on GPU)
3. **ffmpeg:** System dependency required for audio processing

### Environment Variables

**Required:**
- `MEDIA_EMBED_BASE_DIRECTORY` - Base path for podcast audio files
- `GEMINI_API_KEY` - For metadata extraction and RAG queries
- `GEMINI_MODEL` - Gemini model to use (e.g., gemini-2.5-flash)

**Optional:**
- `GEMINI_FILE_SEARCH_STORE_NAME` - Name of File Search store (default: podcast-transcripts)

## Testing Guidelines

### Test Structure
- Tests located in `/home/user/podcast-rag/tests/`
- Use pytest fixtures for setup/teardown
- Test files mirror source structure (`test_*.py`)

### Coverage Areas
- File processing pipeline (`test_file_manager.py`)
- Gemini File Search integration (`test_gemini_file_search.py`)
- Metadata utilities (`test_metadata_utils.py`)
- RAG query processing (`test_rag.py`)
- Transcription workflow (`test_transcribe_podcasts.py`)

### Writing New Tests
```python
import pytest
from unittest.mock import Mock, patch

@pytest.fixture
def mock_config():
    """Create mock config for testing"""
    config = Mock()
    config.BASE_DIRECTORY = "/tmp/test_podcasts"
    config.GEMINI_API_KEY = "test_key"
    return config

def test_feature(mock_config):
    # Test implementation
    pass
```

## Git Workflow

### Branch Strategy
- Feature branches: `feat/feature-name`
- Bug fixes: `fix/bug-name`
- Deploy fixes: `fix(deploy)/description`

### Commit Message Format
Follow conventional commits:
- `feat(module): Add new feature`
- `fix(module): Fix bug description`
- `refactor(module): Restructure code`
- `docs(module): Update documentation`
- `test(module): Add tests`

### Current Branch
Working on: `claude/generate-claude-md-011CV2TtD4R9Z11NP64p6u5F`

## Common Issues & Solutions

### Transcription Fails
- Check ffmpeg installation: `which ffmpeg`
- Verify audio file format is supported
- Ensure sufficient RAM for Whisper model

### File Search Returns No Results
- Verify files are uploaded to File Search store (`python scripts/file_search_utils.py --action list`)
- Check if store name matches config (`GEMINI_FILE_SEARCH_STORE_NAME`)
- Ensure cache is up to date (`python scripts/rebuild_cache.py`)

### AI Query Failures
- Gemini: Verify `GEMINI_API_KEY` is valid
- Check network connectivity for API calls

## Resources

- **Primary Docs:** `/home/user/podcast-rag/README.md`
- **Technical Guide:** `/home/user/podcast-rag/GEMINI.md`
- **License:** Apache 2.0 (`/home/user/podcast-rag/LICENSE`)

## Code Modification Guidelines

### When Adding Features
1. Update `src/config.py` if new settings needed
2. Add database models in `src/db/models.py` if schema changes
3. Update Pydantic schemas in `src/schemas.py` for validation
4. Add tests in `tests/test_*.py`
5. Add new dependencies with `uv add <package>` (updates pyproject.toml and uv.lock)
6. Document in README.md or GEMINI.md

### When Fixing Bugs
1. Write failing test first (TDD approach)
2. Fix code to pass test
3. Run full test suite: `pytest`
4. Check for regressions in related components
5. Update documentation if behavior changes

### When Refactoring
1. Ensure tests pass before refactoring
2. Refactor incrementally with tests passing at each step
3. Use descriptive commit messages
4. Consider backward compatibility
5. Update docstrings and type hints

---

**Last Updated:** 2025-11-11
**Project Version:** See `git log -1` for latest commit
**Python Version:** 3.11+
**License:** Apache 2.0
