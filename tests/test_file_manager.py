import pytest
import sys
import os
from unittest.mock import patch

from src.config import Config
from src.transcribe_podcasts import TranscriptionManager
from src.file_manager import FileManager

# Test for process_directory with a dry-run mode (mocked transcription process)
def test_process_podcasts_dry_run(monkeypatch, tmpdir):
    config = Config()
    config.BASE_DIRECTORY = str(tmpdir.mkdir("podcasts"))

    # Mock the BASE_DIRECTORY and whisper path in the TranscriptionManager
    mock_podcast_dir = os.path.join(config.BASE_DIRECTORY, "SamplePodcast")
    os.makedirs(mock_podcast_dir)
    mock_podcast_file = os.path.join(mock_podcast_dir, "episode1.mp3")
    with open(mock_podcast_file, 'w') as f:
        f.write("Fake MP3 content")

    # Instantiate FileManager with dry_run=True
    manager = FileManager(config=config, dry_run=True)
    
    # Mock the TranscriptionManager's handle_transcription method
    with patch.object(manager.transcription_manager, 'handle_transcription') as mock_transcribe:
        manager.process_directory()
        # Check that handle_transcription was called
        mock_transcribe.assert_called()
