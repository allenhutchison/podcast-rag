import pytest
import sys
import os
from unittest.mock import patch

from src.config import Config
from src.transcribe_podcasts import TranscriptionManager

# Test for is_mp3_file using a real temporary file
def test_is_mp3_file(tmpdir):
    config = Config()
    
    # Create a temporary MP3 file
    mp3_file = tmpdir.join("testfile.mp3")
    mp3_file.write("Fake MP3 content")
    
    # Create a temporary non-MP3 file
    txt_file = tmpdir.join("testfile.txt")
    txt_file.write("Fake TXT content")
    
    assert config.is_mp3_file(str(mp3_file)) == True
    assert config.is_mp3_file(str(txt_file)) == False

# Test for transcription_exists (mocking)
def test_transcription_exists(monkeypatch, tmpdir):
    config = Config()
    
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
    assert config.transcription_exists(str(transcription_file)) == True

    # Non-existent transcription file (mocked as not existing)
    assert config.transcription_exists("/path/to/episode_no_transcription.txt") == False
