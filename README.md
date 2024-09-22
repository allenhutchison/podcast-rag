
# Podcast Transcription using Whisper

This project provides a Python-based tool to automate the transcription of podcasts using the Whisper model. The tool processes directories of podcast MP3 files, transcribes them, and outputs the results in a text format.

## Features
- Batch transcription of MP3 files
- Dry-run mode to preview files without performing transcription
- Logging for detailed process tracking
- Support for environment configuration using `.env`

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
git clone https://github.com/yourusername/podcast-transcription
cd podcast-transcription
```

2. Set up the environment variables by creating a `.env` file, or export them directly:

```bash
export MEDIA_EMBED_BASE_DIRECTORY="/path/to/your/podcasts"
export MEDIA_EMBED_WHISPER_PATH="/path/to/whisper"
```

3. Run the transcription tool in dry-run mode:
```bash
python transcribe_podcasts.py --dry-run
```

## Configuration
The configuration is managed via environment variables:

- `MEDIA_EMBED_BASE_DIRECTORY`: Base directory containing podcast subdirectories.
- `MEDIA_EMBED_WHISPER_PATH`: Path to the Whisper binary.

The default values can be found in the `config.py` file.

## Usage
You can run the tool with or without the dry-run option:

### To perform a dry run:
```bash
python transcribe_podcasts.py --dry-run
```

### To transcribe podcasts:
```bash
python transcribe_podcasts.py
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

