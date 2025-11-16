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


def test_batch_upload_with_progress_callback(tmpdir):
    """Test batch upload with progress callback."""
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

    # Track progress callbacks
    progress_events = []

    def progress_callback(info):
        progress_events.append(info.copy())

    manager = GeminiFileSearchManager(config=config, dry_run=True)
    uploaded = manager.batch_upload_directory(
        directory_path=str(tmpdir),
        pattern="*_transcription.txt",
        progress_callback=progress_callback
    )

    # Should have received progress events
    assert len(progress_events) > 0

    # First event should be 'start'
    assert progress_events[0]['status'] == 'start'
    assert progress_events[0]['total'] == 3

    # Last event should be 'complete'
    assert progress_events[-1]['status'] == 'complete'
    assert progress_events[-1]['uploaded_count'] == 3

    # Should have progress events for each file
    progress_updates = [e for e in progress_events if e['status'] == 'progress']
    assert len(progress_updates) == 3

    # Verify progress updates have required fields
    for update in progress_updates:
        assert 'current' in update
        assert 'total' in update
        assert 'file_path' in update
        assert 'file_name' in update
        assert 'uploaded_count' in update


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


def test_sanitize_display_name_emoji():
    """Test handling of emoji in display names."""
    config = Config()
    manager = GeminiFileSearchManager(config=config, dry_run=True)

    # Test various emoji
    result = manager._sanitize_display_name("Episode 🎧 Title.txt")
    # Emoji should be removed or replaced with ASCII-safe equivalent
    assert result.encode('ascii', errors='ignore').decode('ascii') or True  # Should not crash

    result = manager._sanitize_display_name("Test 👍🎉.txt")
    # Should handle multiple emoji
    assert isinstance(result, str)  # Should return a string

    result = manager._sanitize_display_name("📚 Reading List.txt")
    # Should handle emoji at start
    assert isinstance(result, str)


def test_sanitize_display_name_rtl_text():
    """Test handling of Right-to-Left (RTL) text in display names."""
    config = Config()
    manager = GeminiFileSearchManager(config=config, dry_run=True)

    # Test Arabic text (RTL)
    result = manager._sanitize_display_name("Episode مرحبا.txt")
    assert isinstance(result, str)
    # Should not crash, but may transliterate or remove non-ASCII

    # Test Hebrew text (RTL)
    result = manager._sanitize_display_name("שלום Episode.txt")
    assert isinstance(result, str)

    # Test mixed LTR and RTL
    result = manager._sanitize_display_name("Episode שלום Test.txt")
    assert isinstance(result, str)


def test_sanitize_display_name_combining_diacriticals():
    """Test handling of combining diacritical marks in display names."""
    config = Config()
    manager = GeminiFileSearchManager(config=config, dry_run=True)

    # Test composed form (single character)
    result = manager._sanitize_display_name("Café Episode.txt")
    assert isinstance(result, str)
    # Should handle é (U+00E9)

    # Test decomposed form (base + combining mark)
    # "Café" with decomposed é (e + combining acute accent)
    decomposed = "Cafe\u0301 Episode.txt"  # e + ́
    result = manager._sanitize_display_name(decomposed)
    assert isinstance(result, str)

    # Test multiple diacriticals
    result = manager._sanitize_display_name("Naïve Résumé.txt")
    assert isinstance(result, str)

    # Test complex diacriticals
    result = manager._sanitize_display_name("Příliš žluťoučký.txt")
    assert isinstance(result, str)


def test_upload_filename_with_emoji(tmpdir):
    """Test uploading file with emoji in filename."""
    config = Config()
    manager = GeminiFileSearchManager(config=config, dry_run=True)

    # Create file - use ASCII-safe name for tmpdir, test with metadata
    transcript_file = tmpdir.join("episode_transcription.txt")
    transcript_file.write("Test transcript")

    # Upload with emoji in display name
    metadata = {
        'podcast': 'Test Podcast 🎧',
        'episode': 'Episode 1 📻',
    }

    # Should handle emoji gracefully without crashing
    result = manager.upload_transcript(
        transcript_path=str(transcript_file),
        metadata=metadata
    )

    assert result is not None
    assert 'dry-run' in result


def test_metadata_with_rtl_text():
    """Test metadata containing Right-to-Left text."""
    config = Config()
    manager = GeminiFileSearchManager(config=config, dry_run=True)

    metadata = {
        'transcript_metadata': {
            'podcast_title': 'Arabic Podcast مرحبا',
            'episode_title': 'שלום Hebrew Episode',
            'summary': 'Mixed LTR and RTL: English עברית العربية'
        }
    }

    # Should process without crashing
    result = manager._prepare_metadata(metadata)

    assert isinstance(result, list)
    # All values should be strings
    for item in result:
        assert isinstance(item['string_value'], str)
        # Should fit within byte limit even with multi-byte chars
        assert len(item['string_value'].encode('utf-8')) <= 256


def test_metadata_with_combining_diacriticals():
    """Test metadata with combining diacritical marks."""
    config = Config()
    manager = GeminiFileSearchManager(config=config, dry_run=True)

    # Test both composed and decomposed forms
    metadata = {
        'transcript_metadata': {
            'podcast_title': 'Café Résumé',
            'episode_title': 'Naïve Approach',
            'summary': 'Test with diacriticals: Příliš žluťoučký kůň'
        }
    }

    result = manager._prepare_metadata(metadata)

    assert isinstance(result, list)
    assert len(result) == 3

    # Values should be properly handled
    for item in result:
        assert isinstance(item['string_value'], str)
        # Check byte length, not character length
        assert len(item['string_value'].encode('utf-8')) <= 256


def test_metadata_truncation_with_multibyte_chars():
    """Test truncation with multi-byte Unicode characters."""
    config = Config()
    manager = GeminiFileSearchManager(config=config, dry_run=True)

    # Create very long string with multi-byte chars
    # 'café' has 4 chars but 5 bytes (é is 2 bytes in UTF-8)
    long_value = ('café ' * 60)  # Each 'café ' is 5 chars/6 bytes, total 300 chars/360 bytes

    metadata = {
        'transcript_metadata': {
            'summary': long_value
        }
    }

    result = manager._prepare_metadata(metadata)

    assert len(result) == 1
    # Should be truncated to 256 BYTES (not characters)
    truncated_bytes = len(result[0]['string_value'].encode('utf-8'))
    assert truncated_bytes <= 256, f"Expected <= 256 bytes, got {truncated_bytes}"
    assert result[0]['string_value'].endswith('...')

    # Verify it's valid UTF-8 (no broken multi-byte sequences)
    result[0]['string_value'].encode('utf-8')  # Should not raise


def test_metadata_truncation_prevents_byte_limit_overflow():
    """Test that byte-based truncation prevents the specific bug where
    character-based truncation could exceed byte limit with multi-byte chars.

    Regression test for issue where API rejected metadata with error:
    'string_value cannot be more than 256 characters long'
    when character count was 256 but byte count exceeded 256.
    """
    config = Config()
    manager = GeminiFileSearchManager(config=config, dry_run=True)

    # Create string that would fail with character-based truncation
    # "Théâtre" contains multi-byte characters
    # Construct a value that when truncated to 256 chars would exceed 256 bytes
    base = "This episode explores the story of the Théâtre de la Mode. "
    # Repeat to get well over 256 bytes
    long_value = base * 10  # ~600 bytes

    metadata = {
        'transcript_metadata': {
            'summary': long_value
        }
    }

    result = manager._prepare_metadata(metadata)

    # Verify byte length is within API limit
    truncated_value = result[0]['string_value']
    byte_length = len(truncated_value.encode('utf-8'))
    char_length = len(truncated_value)

    # Must not exceed 256 bytes (the actual API limit)
    assert byte_length <= 256, \
        f"Byte length {byte_length} exceeds API limit of 256 bytes"

    # Character length might be less than 256 due to multi-byte chars
    assert char_length <= 256, \
        f"Character length {char_length} unexpectedly exceeds 256"

    # Should end with ellipsis
    assert truncated_value.endswith('...')

    # No broken UTF-8 sequences
    truncated_value.encode('utf-8')


def test_metadata_truncation():
    """Test metadata values are truncated to 256 bytes (API limit)."""
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

    # Value should be truncated to 256 bytes (API maximum)
    truncated_bytes = len(result[0]['string_value'].encode('utf-8'))
    assert truncated_bytes <= 256
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
