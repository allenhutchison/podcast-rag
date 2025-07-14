# Gemini Project Guidance

This document provides guidance for the Gemini AI agent to effectively understand and interact with this project.

## Project Overview

This project is a Python-based tool for managing and processing podcasts. It allows users to download podcast episodes from RSS feeds, transcribe them using OpenAI's Whisper model, and then use the transcriptions for Retrieval-Augmented Generation (RAG). The project includes a web interface for searching and interacting with the transcribed podcast data.

## Key Technologies

- **Backend:** Python, Flask, Gunicorn
- **Frontend:** HTML, CSS, JavaScript
- **Transcription:** `openai-whisper`
- **Vector Database:** ChromaDB
- **Metadata Database:** SQLAlchemy (SQLite)
- **Scheduling:** APScheduler
- **Dependencies:**
  - `pytest` for testing
  - `python-dotenv` for environment variable management
  - `nltk` for natural language processing
  - `markdown` for text processing
  - `flask-cors` for handling Cross-Origin Resource Sharing
  - `google-generativeai` and `google-genai` for generative AI functionalities
  - `ollama` for running local large language models
  - `eyed3` for handling audio metadata (ID3 tags)
  - `pydantic` for data validation
  - `feedparser` and `listparser` for parsing RSS/OPML feeds
  - `requests` for making HTTP requests

## File Structure

- `app.py`: The main Flask application entry point.
- `src/`: Contains the core source code for the application.
  - `download_and_transcribe.py`: Script to download and transcribe podcasts.
  - `transcribe_podcasts.py`: Script to transcribe existing podcast files.
  - `podcast_downloader.py`: Script to download podcasts from RSS feeds.
  - `rag.py`: Module for Retrieval-Augmented Generation.
  - `chroma_search.py`: Module for searching the ChromaDB vector database.
  - `db/`: Contains database-related modules.
    - `chroma_vectordb.py`: Manages the ChromaDB vector database.
    - `metadatadb.py`: Manages the metadata database using SQLAlchemy.
  - `static/`: Contains static assets for the web interface (CSS, JavaScript).
  - `templates/`: Contains HTML templates for the Flask application.
- `tests/`: Contains unit tests for the project.
- `requirements.txt`: A list of Python dependencies for the project.
- `Dockerfile` and `docker-compose.yml`: For containerizing the application.
- `.env.example`: An example file for setting up environment variables.

## Common Commands

### Installation

```bash
uv pip install -r requirements.txt
```

### Running the Application

To run the web application:

```bash
python3 app.py
```

### Downloading and Transcribing

To download and transcribe podcasts from a single RSS feed:

```bash
python src/download_and_transcribe.py --feed https://feeds.megaphone.fm/darknetdiaries
```

To download and transcribe from a list of feeds in a file:

```bash
python src/download_and_transcribe.py --feed-file test_podcasts.opml
```

### Testing

To run the unit tests:

```bash
pytest
```

## Development Notes

- The application uses a `.env` file for configuration. You can copy `.env.example` to `.env` and customize the variables.
- The `config.py` file contains default configuration values.
- The project is set up to use both a metadata database (for podcast and episode information) and a vector database (for transcriptions).
- The `scheduler.py` module is used to schedule recurring tasks, such as checking for new podcast episodes.
- The web interface is a simple Flask application that allows users to search the transcribed podcasts.
- The project is containerized using Docker, which can be useful for deployment.
