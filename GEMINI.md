# Gemini Project Guidance

This document provides guidance for the Gemini AI agent to effectively understand and interact with this project.

## Project Overview

This project is a comprehensive Python-based tool for building a Retrieval-Augmented Generation (RAG) system over a library of podcasts. It allows users to:
1.  **Download**: Fetch podcast episodes from multiple RSS feeds or an OPML file.
2.  **Transcribe**: Use OpenAI's Whisper model to generate text transcriptions of the audio files.
3.  **Extract Metadata**: Employ a Gemini-based AI model to extract structured metadata (titles, hosts, guests, summaries, keywords) from the transcriptions. It also extracts technical metadata from the MP3 files.
4.  **Store**: Upload transcriptions to Google's Gemini File Search for automatic embedding and indexing. Metadata is stored in a PostgreSQL database.
5.  **Query**: Use a Flask-based web interface or command-line scripts to ask questions. The system uses Gemini File Search to retrieve relevant transcript chunks and generates answers with automatic citations.

The project includes a web UI for search, a podcast management interface, and various command-line scripts for batch processing and maintenance.

## Key Technologies

- **Backend:** Python, Flask
- **Frontend:** HTML, CSS, JavaScript
- **Transcription:** `openai-whisper`
- **RAG/Vector Search:** Google Gemini File Search (hosted embedding and retrieval)
- **Metadata Database:** SQLAlchemy with PostgreSQL
- **AI:** `google-genai` SDK (Gemini 2.5)
- **Scheduling:** APScheduler for recurring jobs
- **Data Parsing/Handling:** `feedparser` and `listparser` for RSS/OPML, `pydantic` for data validation, `eyed3` for audio metadata
- **Development & Testing:** `pytest` for testing, `python-dotenv` for environment variables

## File Structure

- `app.py`: The main Flask application entry point for the web interface.
- `src/`: Contains the core source code for the application.
  - `download_and_transcribe.py`: The main script for orchestrating the download and transcription pipeline.
  - `file_manager.py`: A key orchestrator that coordinates transcription, metadata extraction, and vector indexing for podcast files.
  - `podcast_downloader.py`: Handles downloading podcast episodes from RSS feeds.
  - `transcribe_podcasts.py`: Manages the transcription process using `whisper`.
  - `metadata_extractor.py`: Extracts structured metadata from transcripts using an AI model and from MP3 files.
  - `rag.py`: Implements the core RAG logic using Gemini File Search for retrieval and generation.
  - `gemini_search.py`: Module for querying transcripts using Gemini File Search (replaces ChromaDB).
  - `db/`:
    - `gemini_file_search.py`: Manages File Search store creation, transcript uploads, and batch migrations.
    - `metadatadb.py`: Manages the podcast metadata database (PostgreSQL) using SQLAlchemy.
  - `schemas.py`: Defines the Pydantic data models for structured metadata.
  - `prompt_manager.py`: Loads and formats prompts from the `/prompts` directory.
  - `scheduler.py`: Runs background jobs, such as periodically checking for new podcast episodes.
  - `util/opml_importer.py`: Logic for importing podcast feeds from an OPML file.
  - `static/` & `templates/`: Contain the assets and templates for the Flask web UI.
- `tests/`: Contains unit and integration tests for the project.
- `requirements.txt`: A list of Python dependencies.
- `Dockerfile` & `docker-compose.yml`: For containerizing the application.
- `.env.example`: An example file for setting up environment variables.

## Common Commands

### Installation

This project uses `uv` for fast dependency management. Create a virtual environment and install the required packages:

```bash
# Create a virtual environment
python3 -m venv .venv
# Activate it (macOS/Linux)
source .venv/bin/activate
# Install dependencies with uv
uv pip install -r requirements.txt
```

### Running the Application

To run the web application:

```bash
python3 app.py
```

### Command-Line Scripts

The project includes several scripts for processing data.

**Download and Transcribe (All-in-One):**
```bash
# Download and transcribe the 5 latest episodes from a single feed
python src/download_and_transcribe.py --feed https://feeds.megaphone.fm/darknetdiaries --limit 5

# Download and transcribe from a list of feeds in a file
python src/download_and_transcribe.py --feed-file test_podcasts.opml
```

**Transcribe Only:**
```bash
# Transcribe a single, already downloaded episode
python src/transcribe_podcasts.py --episode-path /path/to/your/episode.mp3
```

**Search from the CLI:**
```bash
# Search using Gemini File Search
python src/gemini_search.py --query "your search query"

# Use the full RAG pipeline with File Search
python src/rag.py --query "your question for the AI"
```

**Migrate Existing Transcripts:**
```bash
# Upload all existing transcripts to Gemini File Search
python scripts/migrate_to_file_search.py

# Dry run to see what would be uploaded
python scripts/migrate_to_file_search.py --dry-run

# Limit migration for testing
python scripts/migrate_to_file_search.py --limit 10
```

### Testing

To run the unit tests:

```bash
pytest
```

## Development Notes

- **Configuration:** The application uses a `.env` file for configuration (copy `.env.example` to `.env`). Key variables include:
  - `GEMINI_API_KEY`: Your Google Gemini API key (required)
  - `GEMINI_MODEL`: Model to use (default: `gemini-2.5-flash`)
  - `GEMINI_FILE_SEARCH_STORE_NAME`: Name for the File Search store (default: `podcast-transcripts`)
  - `POSTGRES_*`: Database credentials for metadata storage
- **Workflow:** The typical workflow is to run `download_and_transcribe.py` to download episodes, transcribe them, and automatically upload to File Search. The `file_manager.py` script is the central orchestrator, handling transcription, metadata extraction, and File Search indexing.
- **Metadata:** The `metadata_extractor.py` uses a Gemini model with a JSON response schema (`schemas.py`) to create structured data from unstructured transcripts. This metadata is attached to each File Search upload and stored in PostgreSQL for querying.
- **RAG Pipeline:** When a query is made via the UI or `rag.py`, the `RagManager` class uses Gemini File Search as a tool. File Search automatically:
  - Retrieves relevant transcript chunks based on semantic similarity
  - Provides grounding metadata with file IDs and chunk indices
  - Enables Gemini to generate answers with automatic citations
  No manual prompt construction or chunking is required - Google's hosted service handles all embedding and retrieval.
- **File Search Store:** Transcripts are uploaded to a Google-hosted File Search store (`gemini_file_search.py`). The store handles:
  - Automatic chunking and embedding
  - Semantic search across all transcripts
  - Metadata filtering capabilities
  - Citation/grounding support
- **Database:** The system uses PostgreSQL (`metadatadb.py`) for structured podcast/episode metadata (title, feed URL, release date, etc.). Vector search is handled entirely by Gemini File Search.