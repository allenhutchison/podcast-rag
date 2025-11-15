# Gemini Project Guidance

This document provides guidance for the Gemini AI agent to effectively understand and interact with this project.

## Project Overview

This project is a comprehensive Python-based tool for building a Retrieval-Augmented Generation (RAG) system over a library of podcasts. It allows users to:
1.  **Download**: Fetch podcast episodes from multiple RSS feeds or an OPML file.
2.  **Transcribe**: Use OpenAI's Whisper model to generate text transcriptions of the audio files.
3.  **Extract Metadata**: Employ a Gemini-based AI model to extract structured metadata (titles, hosts, guests, summaries, keywords) from the transcriptions. It also extracts technical metadata from the MP3 files.
4.  **Store**: Save the transcriptions and their embeddings in a ChromaDB vector database and the associated metadata in a local SQLite database.
5.  **Query**: Use a Flask-based web interface or command-line scripts to ask questions. The system retrieves relevant transcript snippets from ChromaDB and uses Gemini to generate a coherent answer with source citations.

The project includes a web UI for search, a podcast management interface, and various command-line scripts for batch processing and maintenance.

## Key Technologies

- **Backend:** Python, Flask
- **Frontend:** HTML, CSS, JavaScript
- **Transcription:** `openai-whisper`
- **Vector Database:** ChromaDB
- **Metadata Database:** SQLAlchemy (with SQLite)
- **AI/RAG:** `google-generativeai` (Gemini)
- **Scheduling:** APScheduler for recurring jobs.
- **Data Parsing/Handling:** `feedparser` and `listparser` for RSS/OPML, `pydantic` for data validation, `eyed3` for audio metadata.
- **Development & Testing:** `pytest` for testing, `python-dotenv` for environment variables.

## File Structure

- `app.py`: The main Flask application entry point for the web interface.
- `src/`: Contains the core source code for the application.
  - `download_and_transcribe.py`: The main script for orchestrating the download and transcription pipeline.
  - `file_manager.py`: A key orchestrator that coordinates transcription, metadata extraction, and vector indexing for podcast files.
  - `podcast_downloader.py`: Handles downloading podcast episodes from RSS feeds.
  - `transcribe_podcasts.py`: Manages the transcription process using `whisper`.
  - `metadata_extractor.py`: Extracts structured metadata from transcripts using an AI model and from MP3 files.
  - `rag.py`: Implements the core RAG logic, preparing prompts and querying AI models.
  - `chroma_search.py`: Module for querying the ChromaDB vector database.
  - `db/`:
    - `chroma_vectordb.py`: Manages the connection to and indexing of data within ChromaDB.
    - `metadatadb.py`: Manages the podcast metadata database (SQLite) using SQLAlchemy.
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
# Search the vector database
python src/chroma_search.py --query "your search query"

# Use the full RAG pipeline
python src/rag.py --query "your question for the AI" --ai-system gemini
```

### Testing

To run the unit tests:

```bash
pytest
```

## Development Notes

- **Configuration:** The application uses a `.env` file for configuration (copy `.env.example` to `.env`). Key variables include API keys and paths.
- **Workflow:** The typical workflow is to run `download_and_transcribe.py` to populate the databases. The `file_manager.py` script is the central point for processing a directory of podcasts, handling transcription, metadata extraction, and indexing.
- **Metadata:** The `metadata_extractor.py` is crucial. It uses a Gemini model with a JSON response schema (`schemas.py`) to create structured data from unstructured transcripts. This structured data is then used in prompts and for filtering.
- **RAG Pipeline:** When a query is made via the UI or `rag.py`, the `RagManager` class takes over. It searches ChromaDB for relevant text chunks, combines them with the user's query into a detailed prompt (using templates from `prompt_manager.py`), and sends it to Gemini for a final answer.
- **Database:** The system uses two databases: SQLite (`metadatadb.py`) for structured podcast/episode metadata (title, feed URL, etc.) and ChromaDB (`chroma_vectordb.py`) for storing vector embeddings of transcript chunks.