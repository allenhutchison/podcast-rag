# CLAUDE.md - AI Assistant Context for Podcast RAG System

This document provides context for AI assistants working with this codebase.

## Project Overview

**Podcast RAG System** is a Python-based Retrieval-Augmented Generation (RAG) application that enables intelligent search and question-answering over podcast libraries.

**Core Functionality:**
- Transcribes audio using OpenAI Whisper
- Extracts structured metadata using AI (Gemini)
- Stores transcriptions in vector databases for semantic search
- Answers natural language queries with source citations via CLI

**Tech Stack:** Python 3.11, PostgreSQL + pgvector, ChromaDB, Whisper, Gemini

## Architecture

### High-Level RAG Pipeline

```
User Query → Vector Search → Context Retrieval → Prompt Formatting → AI Model → Sourced Answer
```

### Key Components

1. **RAG Manager** (`src/rag.py`) - Orchestrates query processing pipeline
2. **File Manager** (`src/file_manager.py`) - Central processor for transcription → metadata → indexing
3. **Background Services:**
   - `src/transcription_service.py` - Processes audio files with Whisper
   - `src/scheduler.py` - Scheduled transcription processing
4. **Database Layer:**
   - PostgreSQL (primary) - Episodes, transcripts, embeddings (pgvector)
   - ChromaDB - Vector similarity search
   - SQLite (legacy) - Metadata fallback
5. **MCP Server** (`src/mcp_server.py`) - Claude integration protocol

### Project Structure

```
/home/user/podcast-rag/
├── src/                    # Core application code
│   ├── rag.py              # RAG pipeline orchestrator
│   ├── config.py           # Configuration management
│   ├── schemas.py          # Pydantic models for validation
│   ├── file_manager.py     # Processing orchestrator
│   ├── scheduler.py        # Scheduled processing
│   ├── transcription_service.py  # Background transcription
│   │
│   ├── db/
│   │   ├── models.py       # SQLAlchemy ORM (PostgreSQL)
│   │   ├── database.py     # DB connection management
│   │   └── gemini_file_search.py  # Gemini File Search interface
│
├── scripts/
│   └── init_db.py          # Database initialization
│
├── prompts/                # AI prompt templates
│   ├── archive_question.txt      # RAG answer generation
│   ├── podcast_snippet.txt       # Context formatting
│   └── metadata_extraction.txt   # Metadata extraction
│
├── tests/                  # pytest test suite
└── requirements.txt        # Python dependencies
```

## Key Files Reference

| File | Purpose | When to Modify |
|------|---------|----------------|
| `src/config.py` | Environment variables, paths, settings | Adding new config options |
| `src/rag.py` | Query processing, AI inference | Changing RAG logic |
| `src/db/models.py` | Database schema (SQLAlchemy) | Modifying data structure |
| `src/file_manager.py` | Transcription + metadata pipeline | Processing workflow changes |
| `src/chroma_search.py` | Vector similarity search | Search algorithm tuning |
| `src/metadata_extractor.py` | AI-powered metadata parsing | Changing metadata fields |
| `prompts/archive_question.txt` | RAG system prompt | Improving answer quality |
| `requirements.txt` | Python dependencies | Adding/updating packages |

## Development Workflow

### Setup

```bash
# 1. Virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env with database credentials, API keys

# 4. System dependencies
# Requires: ffmpeg, PostgreSQL
```

### Common Tasks

**Process Existing Podcasts:**
```bash
# Process all podcasts in media directory
python src/file_manager.py

# Scheduled processing (runs every hour)
python src/scheduler.py
```

**Search & Query:**
```bash
# Vector search
python src/chroma_search.py --query "your search query"

# Full RAG query
python src/rag.py --query "your question" --ai-system gemini
```

**Database Operations:**
```bash
# Initialize database
python scripts/init_db.py --yes
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
- **Classes:** PascalCase (`TranscriptionManager`, `PodcastDB`)
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

### Database Conventions
- Use SQLAlchemy ORM for PostgreSQL operations
- Define relationships explicitly in models
- Use migrations for schema changes (consider adding Alembic)
- Index frequently queried fields (podcast_id, episode_id)

## Important Context

### Dependencies & Integrations

**External APIs:**
- **Gemini API:** Requires `GEMINI_API_KEY` environment variable
  - Model: `gemini-2.0-flash-exp` (configurable via `GEMINI_MODEL`)
  - Used for: RAG queries, metadata extraction

**Vector Database:**
- ChromaDB stores transcript embeddings
- Persisted in `MEDIA_EMBED_BASE_DIRECTORY`
- Collection name: "transcripts"

### Known Constraints

1. **Whisper Model:** Large-v3 model requires significant RAM (~10GB VRAM for GPU)
2. **Transcription Speed:** Real-time factor varies (1-3x on CPU, faster on GPU)
3. **PostgreSQL:** pgvector extension required - initialized by `scripts/init_db.py`
4. **ffmpeg:** System dependency required for audio processing

### Environment Variables

**Required:**
- `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` - Database credentials
- `POSTGRES_HOST`, `POSTGRES_PORT` - Database connection
- `MEDIA_EMBED_BASE_DIRECTORY` - Base path for podcast audio files

**Optional:**
- `GEMINI_API_KEY` - For Gemini-based RAG

## Testing Guidelines

### Test Structure
- Tests located in `/home/user/podcast-rag/tests/`
- Use pytest fixtures for setup/teardown
- Test files mirror source structure (`test_*.py`)

### Coverage Areas
- File processing pipeline (`test_file_manager.py`)
- Database operations (`test_metadatadb.py`)
- Transcription workflow (`test_transcribe_podcasts.py`)

### Writing New Tests
```python
import pytest

@pytest.fixture
def temp_db():
    """Create temporary database for testing"""
    db_path = "test_temp.db"
    db = PodcastDB(db_path)
    yield db
    if os.path.exists(db_path):
        os.remove(db_path)

def test_feature(temp_db):
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

### Vector Search Returns No Results
- Verify ChromaDB collection exists
- Check embeddings were generated during indexing
- Confirm `MEDIA_EMBED_BASE_DIRECTORY` is correct

### Database Connection Errors
- Ensure PostgreSQL is running
- Check credentials in `.env` match database
- Verify pgvector extension: `python scripts/init_db.py --yes`

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
5. Update `requirements.txt` if new dependencies
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
