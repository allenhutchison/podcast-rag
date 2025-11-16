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


def test_sanitize_display_name_unicode():
    """Test unicode character replacement in display names."""
    config = Config()
    manager = GeminiFileSearchManager(config=config, dry_run=True)

    # Test curly quotes
    result = manager._sanitize_display_name("Test's Episode")
    assert result == "Test's Episode"
    result.encode('ascii')  # Should not raise

    # Test en-dash
    result = manager._sanitize_display_name("Episode–Title")
    assert result == "Episode-Title"
    result.encode('ascii')  # Should not raise

    # Test em-dash
    result = manager._sanitize_display_name("Episode—Title")
    assert result == "Episode--Title"
    result.encode('ascii')  # Should not raise

    # Test ellipsis
    result = manager._sanitize_display_name("Episode…")
    assert result == "Episode..."
    result.encode('ascii')  # Should not raise

    # Test combined
    result = manager._sanitize_display_name("Test's—Episode…")
    assert result == "Test's--Episode..."
    result.encode('ascii')  # Should not raise


def test_sanitize_display_name_already_ascii():
    """Test that ASCII-safe names pass through unchanged."""
    config = Config()
    manager = GeminiFileSearchManager(config=config, dry_run=True)

    ascii_name = "Episode_Title_123.txt"
    result = manager._sanitize_display_name(ascii_name)
    assert result == ascii_name


def test_metadata_truncation():
    """Test metadata values are truncated to 255 chars."""
    config = Config()
    manager = GeminiFileSearchManager(config=config, dry_run=True)

    # Create metadata with a very long summary (use nested format)
    long_value = 'x' * 300
    metadata = {
        'transcript_metadata': {
            'summary': long_value
        }
    }

    result = manager._prepare_metadata(metadata)

    # Should have one metadata entry
    assert len(result) == 1
    assert result[0]['key'] == 'summary'

    # Value should be truncated to 255 chars
    assert len(result[0]['string_value']) == 255
    assert result[0]['string_value'].endswith('...')


def test_metadata_truncation_preserves_short_values():
    """Test that short metadata values are not truncated."""
    config = Config()
    manager = GeminiFileSearchManager(config=config, dry_run=True)

    metadata = {
        'transcript_metadata': {
            'summary': 'Short summary'
        }
    }

    result = manager._prepare_metadata(metadata)

    assert len(result) == 1
    assert result[0]['string_value'] == 'Short summary'


def test_metadata_list_conversion():
    """Test that list metadata is converted to comma-separated strings."""
    config = Config()
    manager = GeminiFileSearchManager(config=config, dry_run=True)

    metadata = {
        'transcript_metadata': {
            'hosts': ['Host1', 'Host2', 'Host3'],
            'keywords': ['AI', 'Tech', 'Science']
        }
    }

    result = manager._prepare_metadata(metadata)

    # Find hosts and keywords in result
    hosts_meta = next((m for m in result if m['key'] == 'hosts'), None)
    keywords_meta = next((m for m in result if m['key'] == 'keywords'), None)

    assert hosts_meta is not None
    assert hosts_meta['string_value'] == 'Host1, Host2, Host3'

    assert keywords_meta is not None
    assert keywords_meta['string_value'] == 'AI, Tech, Science'


def test_idempotent_upload_skips_existing(tmpdir):
    """Test that upload skips files that already exist."""
    config = Config()
    manager = GeminiFileSearchManager(config=config, dry_run=True)

    # Create a test transcript file
    transcript_file = tmpdir.join("episode_transcription.txt")
    transcript_file.write("Test transcript")

    # Create existing files dict
    existing_files = {
        'episode_transcription.txt': 'fileSearchStores/store123/documents/doc123'
    }

    # Try to upload - should skip
    result = manager.upload_transcript(
        transcript_path=str(transcript_file),
        metadata={'podcast': 'Test'},
        existing_files=existing_files,
        skip_existing=True
    )

    # Should return None when skipped
    assert result is None


def test_idempotent_upload_allows_new_files(tmpdir):
    """Test that upload proceeds for new files."""
    config = Config()
    manager = GeminiFileSearchManager(config=config, dry_run=True)

    # Create a test transcript file
    transcript_file = tmpdir.join("new_episode_transcription.txt")
    transcript_file.write("Test transcript")

    # Create existing files dict with a different file
    existing_files = {
        'old_episode_transcription.txt': 'fileSearchStores/store123/documents/doc123'
    }

    # Try to upload - should proceed
    result = manager.upload_transcript(
        transcript_path=str(transcript_file),
        metadata={'podcast': 'Test'},
        existing_files=existing_files,
        skip_existing=True
    )

    # Should return a file name (dry-run name in this case)
    assert result is not None
    assert 'dry-run' in result


def test_upload_unicode_filename(tmpdir):
    """Test uploading file with unicode characters in filename."""
    config = Config()
    manager = GeminiFileSearchManager(config=config, dry_run=True)

    # Create file with unicode in name
    # Note: tmpdir handles unicode filenames
    transcript_file = tmpdir.join("episode's—test_transcription.txt")
    transcript_file.write("Test transcript")

    # Upload should handle unicode gracefully
    result = manager.upload_transcript(
        transcript_path=str(transcript_file),
        metadata={'podcast': 'Test'}
    )

    # Should successfully return a result
    assert result is not None
    assert 'dry-run' in result


def test_poll_operation_timeout():
    """Test that _poll_operation() raises TimeoutError after timeout."""
    config = Config()
    manager = GeminiFileSearchManager(config=config, dry_run=False)

    # Create a mock operation that never completes
    mock_operation = MagicMock()
    mock_operation.done = False
    mock_operation.error = None  # No error, just doesn't complete
    mock_operation.name = "operations/test123"

    # Mock the client.operations.get to return the same operation (never completes)
    with patch.object(manager.client.operations, 'get', return_value=mock_operation):
        # Should timeout after the specified duration
        with pytest.raises(TimeoutError, match="Operation timed out"):
            manager._poll_operation(mock_operation, timeout=1)  # 1 second timeout


def test_poll_operation_error():
    """Test that _poll_operation() raises RuntimeError when operation fails."""
    config = Config()
    manager = GeminiFileSearchManager(config=config, dry_run=False)

    # Create a mock operation with an error
    mock_error = MagicMock()
    mock_error.__str__ = lambda self: "Upload failed: Invalid file"

    mock_operation = MagicMock()
    mock_operation.done = False
    mock_operation.error = mock_error
    mock_operation.name = "operations/test123"

    # Mock the client.operations.get to return the same operation
    with patch.object(manager.client.operations, 'get', return_value=mock_operation):
        with pytest.raises(RuntimeError, match="Operation failed"):
            manager._poll_operation(mock_operation, timeout=5)


def test_poll_operation_success():
    """Test that _poll_operation() completes successfully."""
    config = Config()
    manager = GeminiFileSearchManager(config=config, dry_run=False)

    # Create a mock operation that completes immediately
    mock_operation = MagicMock()
    mock_operation.done = True
    mock_operation.error = None

    # Should complete without error
    manager._poll_operation(mock_operation)
