"""
Tests for Gemini File Search functionality.

These tests run in dry_run mode to avoid requiring API credentials.
"""

import pytest
import sys
import os
import json
from unittest.mock import patch, MagicMock

# Add the src directory to sys.path
sys.path.append(os.path.join(os.path.dirname(__file__), '../src'))

from config import Config
from db.gemini_file_search import GeminiFileSearchManager


def test_file_search_manager_init_dry_run():
    """Test that FileSearchManager initializes properly in dry_run mode."""
    config = Config()
    manager = GeminiFileSearchManager(config=config, dry_run=True)

    assert manager.config == config
    assert manager.dry_run is True
    assert manager.client is not None


def test_create_store_dry_run(tmpdir):
    """Test store creation in dry_run mode."""
    config = Config()
    config.GEMINI_FILE_SEARCH_STORE_NAME = "test-store"

    manager = GeminiFileSearchManager(config=config, dry_run=True)
    store_name = manager.create_or_get_store()

    # In dry_run mode, should return a mock store name
    assert "dry-run" in store_name
    assert "test-store" in store_name


def test_upload_transcript_dry_run(tmpdir):
    """Test transcript upload in dry_run mode."""
    config = Config()
    manager = GeminiFileSearchManager(config=config, dry_run=True)

    # Create a fake transcript file
    transcript_file = tmpdir.join("episode_transcription.txt")
    transcript_file.write("This is a test transcript.")

    # Upload in dry_run mode
    metadata = {
        'podcast': 'Test Podcast',
        'episode': 'Episode 1',
        'hosts': ['Host 1', 'Host 2'],
        'guests': ['Guest 1']
    }

    file_name = manager.upload_transcript(
        transcript_path=str(transcript_file),
        metadata=metadata
    )

    # Should return a dry-run file name
    assert "dry-run" in file_name
    assert "episode_transcription.txt" in file_name


def test_upload_transcript_text_dry_run():
    """Test direct text upload in dry_run mode."""
    config = Config()
    manager = GeminiFileSearchManager(config=config, dry_run=True)

    text = "This is a test transcript."
    metadata = {
        'podcast': 'Test Podcast',
        'episode': 'Episode 1'
    }

    file_name = manager.upload_transcript_text(
        text=text,
        display_name="test_episode.txt",
        metadata=metadata
    )

    assert "dry-run" in file_name


def test_batch_upload_directory_dry_run(tmpdir):
    """Test batch upload in dry_run mode."""
    config = Config()
    config.BASE_DIRECTORY = str(tmpdir)

    # Create some fake transcript files
    podcast_dir = tmpdir.mkdir("TestPodcast")

    for i in range(3):
        transcript = podcast_dir.join(f"episode{i}_transcription.txt")
        transcript.write(f"Transcript {i}")

        metadata = podcast_dir.join(f"episode{i}_metadata.json")
        metadata.write(json.dumps({
            'podcast': 'Test Podcast',
            'episode': f'Episode {i}'
        }))

    manager = GeminiFileSearchManager(config=config, dry_run=True)
    uploaded = manager.batch_upload_directory(
        directory_path=str(tmpdir),
        pattern="*_transcription.txt"
    )

    # Should have found and "uploaded" 3 files in dry_run
    assert len(uploaded) == 3


def test_metadata_conversion():
    """Test that metadata is properly converted for File Search."""
    config = Config()
    manager = GeminiFileSearchManager(config=config, dry_run=True)

    # Test metadata with various types
    metadata = {
        'podcast': 'Test Podcast',
        'episode': 'Episode 1',
        'hosts': ['Host 1', 'Host 2'],  # List
        'guests': ['Guest'],  # List
        'keywords': ['AI', 'Tech'],  # List
        'release_date': '2024-01-01',  # String
        'summary': 'Test summary'  # String
    }

    # The upload_transcript_text method should handle list conversion
    # We can't easily test internal behavior, but we can verify it doesn't crash
    file_name = manager.upload_transcript_text(
        text="Test",
        display_name="test.txt",
        metadata=metadata
    )

    assert file_name is not None


def test_file_not_found_error(tmpdir):
    """Test that FileNotFoundError is raised for missing files."""
    config = Config()
    manager = GeminiFileSearchManager(config=config, dry_run=False)

    # Try to upload a non-existent file
    with pytest.raises(FileNotFoundError):
        manager.upload_transcript(
            transcript_path="/nonexistent/path/file.txt",
            metadata={}
        )


def test_get_store_info_dry_run():
    """Test get_store_info in dry_run mode."""
    config = Config()
    manager = GeminiFileSearchManager(config=config, dry_run=True)

    store_info = manager.get_store_info()

    assert 'name' in store_info
    assert 'display_name' in store_info
    assert store_info['file_count'] == 0
    assert store_info['storage_bytes'] == 0


def test_list_files_dry_run():
    """Test list_files in dry_run mode."""
    config = Config()
    manager = GeminiFileSearchManager(config=config, dry_run=True)

    files = manager.list_files()

    # In dry_run mode, should return empty list
    assert isinstance(files, list)
    assert len(files) == 0
