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
To use this tool, you'll need to set up a Python environment with the required dependencies and install Whisper for transcription.

### Prerequisites
1. Python 3.11+ (recommended)
2. [Whisper](https://github.com/openai/whisper)
3. Install `ffmpeg`:
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

4. Install dependencies:

```bash
pip install -r requirements.txt
```

### Setup
1. Clone the repository:
```bash
git clone https://github.com/allenhutchison/podcast-rag
cd podcast-rag
```

2. Set up the environment variables by creating a `.env` file from the example:

```bash
cp .env.example .env
# Edit .env with your configuration
```

3. Configure required environment variables (see `.env.example` for all options):

```bash
# Media directory
MEDIA_EMBED_BASE_DIRECTORY=/path/to/your/podcasts

# Gemini API (for metadata extraction and RAG)
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.5-flash

# Gemini File Search
GEMINI_FILE_SEARCH_STORE_NAME=podcast-transcripts
```

4. Run the transcription tool in dry-run mode:
```bash
python src/file_manager.py --dry-run
```

## Configuration
The configuration is managed via environment variables loaded from a `.env` file. See `.env.example` for all available options and `src/config.py` for implementation details.

## Usage

### Process all podcasts in media directory:
```bash
python src/file_manager.py
```

### Run scheduled processing (every hour):
```bash
python src/scheduler.py
```

### Perform a dry run:
```bash
python src/file_manager.py --dry-run
```

### Skip vector database operations:
```bash
python src/file_manager.py --skip-vectordb
```

### Query the RAG system:
```bash
python -m src.rag --query "your question here"
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
python src/file_manager.py --log-level DEBUG
python -m src.rag --query "your question" --log-level ERROR
```

## Error Reporting
When processing fails for any files, the file_manager will print a detailed error report at the end showing:
- Files that failed to transcribe (with file paths)
- Files that failed metadata extraction (categorized by error type)
- Recommended actions to resolve each type of error

This makes it easy to identify and fix problematic files.

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

