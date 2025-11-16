# Podcast RAG System

A Python-based Retrieval-Augmented Generation (RAG) system for intelligent search and question-answering over podcast libraries. The system transcribes audio using Whisper, extracts metadata with AI, and enables semantic search with automatic citations.

## Features
- Automatic transcription of MP3 files using OpenAI Whisper
- AI-powered metadata extraction (titles, hosts, guests, summaries, keywords)
- Vector embeddings and semantic search using Gemini File Search
- Natural language queries with source citations
- PostgreSQL database for metadata storage
- Scheduled batch processing
- Dry-run mode and comprehensive logging

## Installation
To use this tool, you'll need to set up a Python environment with the required dependencies and install Whisper for transcription.

### Prerequisites
1. Python 3.8+
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
# PostgreSQL database
POSTGRES_USER=podcast_rag_user
POSTGRES_PASSWORD=your_password
POSTGRES_DB=podcast_rag_db
POSTGRES_HOST=localhost
POSTGRES_PORT=5432

# Media directory
MEDIA_EMBED_BASE_DIRECTORY=/path/to/your/podcasts

# Gemini API (for metadata extraction and RAG)
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.5-flash

# Gemini File Search
GEMINI_FILE_SEARCH_STORE_NAME=podcast-transcripts
```

4. Initialize the database:
```bash
python scripts/init_db.py --yes
```

5. Run the transcription tool in dry-run mode:
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
python src/rag.py --query "your question here"
```

## Logging
The tool uses Python's built-in logging for tracking progress and errors. By default, logs are displayed in the console, but this can be easily modified to output to a file.

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

