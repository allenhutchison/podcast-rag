import pytest
import sys
import os
from unittest.mock import patch

# Add the src directory to sys.path so that Config and TranscriptionManager can be imported
sys.path.append(os.path.join(os.path.dirname(__file__), '../src'))

from config import Config
from transcribe_podcasts import TranscriptionManager
from file_manager import FileManager

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

    transcription_manager = TranscriptionManager(config=config, dry_run=True)

    # Instantiate TranscriptionManager
    manager = FileManager(config=config, dry_run=True, transcription_manager=transcription_manager)
    
    # Mock start_transcription method so that it doesn't actually run
    with patch.object(transcription_manager, 'handle_transcription') as mock_transcribe:
        manager.process_directory()

        # Check that start_transcription was not called in dry-run mode
        mock_transcribe.assert_called()
