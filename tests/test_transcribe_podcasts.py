
import pytest
import sys
import os
from unittest.mock import patch

# Add the src directory to sys.path so that Config and TranscriptionManager can be imported
sys.path.append(os.path.join(os.path.dirname(__file__), '../src'))

from config import Config
from transcribe_podcasts import TranscriptionManager

# Test for is_mp3_file using a real temporary file
def test_is_mp3_file(tmpdir):
    config = Config()
    manager = TranscriptionManager(config=config, dry_run=True)
    
    # Create a temporary MP3 file
    mp3_file = tmpdir.join("testfile.mp3")
    mp3_file.write("Fake MP3 content")
    
    # Create a temporary non-MP3 file
    txt_file = tmpdir.join("testfile.txt")
    txt_file.write("Fake TXT content")
    
    assert manager.is_mp3_file(str(mp3_file)) == True
    assert manager.is_mp3_file(str(txt_file)) == False

# Test for transcription_exists (mocking)
def test_transcription_exists(monkeypatch, tmpdir):
    config = Config()
    manager = TranscriptionManager(config=config, dry_run=True)
    
    # Create a mock transcription file in tmpdir
    transcription_file = tmpdir.join("episode_transcription.txt")
    transcription_file.write("Fake transcription content")
    
    # Mocking os.path.exists and os.path.getsize to simulate file existence and size
    def mock_exists(path):
        return str(path) == str(transcription_file)
    
    def mock_getsize(path):
        return 100 if str(path) == str(transcription_file) else 0

    monkeypatch.setattr(os.path, "exists", mock_exists)
    monkeypatch.setattr(os.path, "getsize", mock_getsize)

    # Existing transcription file (mocked as existing)
    assert manager.transcription_exists(str(transcription_file)) == True

    # Non-existent transcription file (mocked as not existing)
    assert manager.transcription_exists("/path/to/episode_no_transcription.txt") == False

# Test for process_directory with a dry-run mode (mocked transcription process)
def test_transcribe_podcasts_dry_run(monkeypatch, tmpdir):
    config = Config()
    config.BASE_DIRECTORY = str(tmpdir.mkdir("podcasts"))

    # Mock the BASE_DIRECTORY and whisper path in the TranscriptionManager
    mock_podcast_dir = os.path.join(config.BASE_DIRECTORY, "SamplePodcast")
    os.makedirs(mock_podcast_dir)
    mock_podcast_file = os.path.join(mock_podcast_dir, "episode1.mp3")
    with open(mock_podcast_file, 'w') as f:
        f.write("Fake MP3 content")

    # Instantiate TranscriptionManager
    manager = TranscriptionManager(config=config, dry_run=True)
    
    # Mock start_transcription method so that it doesn't actually run
    with patch.object(manager, 'start_transcription') as mock_transcribe:
        manager.process_directory()

        # Check that start_transcription was not called in dry-run mode
        mock_transcribe.assert_not_called()
