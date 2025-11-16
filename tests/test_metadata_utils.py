"""
Tests for metadata utility functions.
"""

import pytest
import sys
import os
import json
import tempfile

# Add the src directory to sys.path
sys.path.append(os.path.join(os.path.dirname(__file__), '../src'))

from utils.metadata_utils import (
    flatten_episode_metadata,
    load_metadata_from_file,
    load_and_flatten_metadata
)


def test_flatten_nested_metadata():
    """Test flattening of nested EpisodeMetadata structure."""
    nested = {
        'transcript_metadata': {
            'podcast_title': 'Test Podcast',
            'episode_title': 'Episode 1',
            'hosts': ['Host1'],
            'co_hosts': ['CoHost1'],
            'guests': ['Guest1', 'Guest2'],
            'date': '2024-01-01',  # Note: uses 'date', not 'release_date'
            'keywords': ['AI', 'Tech'],
            'summary': 'Test summary'
        },
        'mp3_metadata': {
            'hosts': ['Host2'],  # Should be combined with transcript hosts
            'release_date': '2024-01-02'  # Should prefer transcript date
        }
    }

    result = flatten_episode_metadata(nested)

    assert result['podcast'] == 'Test Podcast'
    assert result['episode'] == 'Episode 1'
    assert 'Host1' in result['hosts']
    assert 'CoHost1' in result['hosts']
    assert 'Host2' in result['hosts']
    assert result['release_date'] == '2024-01-01'  # Prefer transcript date
    assert result['guests'] == ['Guest1', 'Guest2']
    assert result['keywords'] == ['AI', 'Tech']
    assert result['summary'] == 'Test summary'


def test_flatten_already_flat_metadata():
    """Test that already-flat metadata passes through unchanged."""
    flat = {
        'podcast': 'Test Podcast',
        'episode': 'Episode 1',
        'hosts': ['Host1'],
        'release_date': '2024-01-01'
    }

    result = flatten_episode_metadata(flat)

    assert result == flat


def test_flatten_empty_metadata():
    """Test flattening of empty metadata."""
    result = flatten_episode_metadata({})
    assert result == {}

    result = flatten_episode_metadata(None)
    assert result == {}


def test_flatten_partial_metadata():
    """Test flattening when only some fields are present."""
    partial = {
        'transcript_metadata': {
            'podcast_title': 'Test Podcast',
            # Missing episode_title, hosts, etc.
        }
    }

    result = flatten_episode_metadata(partial)

    assert result['podcast'] == 'Test Podcast'
    assert 'episode' not in result or result['episode'] is None
    assert 'hosts' not in result or result['hosts'] == []


def test_flatten_pydantic_model():
    """Test flattening of Pydantic model with model_dump method."""
    # Create a mock Pydantic model
    class MockModel:
        def model_dump(self):
            return {
                'transcript_metadata': {
                    'podcast_title': 'Pydantic Podcast',
                    'episode_title': 'Pydantic Episode'
                }
            }

    model = MockModel()
    result = flatten_episode_metadata(model)

    assert result['podcast'] == 'Pydantic Podcast'
    assert result['episode'] == 'Pydantic Episode'


def test_load_metadata_from_file(tmpdir):
    """Test loading metadata from a JSON file."""
    # Create a test metadata file
    metadata_file = tmpdir.join("test_metadata.json")
    metadata = {
        'transcript_metadata': {
            'podcast_title': 'File Podcast',
            'episode_title': 'File Episode'
        }
    }
    metadata_file.write(json.dumps(metadata))

    result = load_metadata_from_file(str(metadata_file))

    assert result is not None
    assert result['transcript_metadata']['podcast_title'] == 'File Podcast'


def test_load_metadata_from_missing_file():
    """Test loading metadata from a non-existent file returns None."""
    result = load_metadata_from_file("/nonexistent/metadata.json")
    assert result is None


def test_load_metadata_from_invalid_json(tmpdir):
    """Test loading metadata from invalid JSON file returns None."""
    invalid_file = tmpdir.join("invalid.json")
    invalid_file.write("{ invalid json content")

    result = load_metadata_from_file(str(invalid_file))
    assert result is None


def test_load_and_flatten_metadata(tmpdir):
    """Test combined load and flatten operation."""
    # Create transcript file
    transcript_file = tmpdir.join("episode_transcription.txt")
    transcript_file.write("Test transcript")

    # Create corresponding metadata file
    metadata_file = tmpdir.join("episode_metadata.json")
    metadata = {
        'transcript_metadata': {
            'podcast_title': 'Combined Podcast',
            'episode_title': 'Combined Episode',
            'hosts': ['Host1']
        }
    }
    metadata_file.write(json.dumps(metadata))

    result = load_and_flatten_metadata(
        transcript_path=str(transcript_file),
        transcription_suffix="_transcription.txt"
    )

    assert result is not None
    assert result['podcast'] == 'Combined Podcast'
    assert result['episode'] == 'Combined Episode'
    assert result['hosts'] == ['Host1']


def test_load_and_flatten_no_metadata_file(tmpdir):
    """Test load and flatten when metadata file doesn't exist."""
    transcript_file = tmpdir.join("episode_transcription.txt")
    transcript_file.write("Test transcript")

    result = load_and_flatten_metadata(
        transcript_path=str(transcript_file),
        transcription_suffix="_transcription.txt"
    )

    # Should return None or empty dict when no metadata file exists
    assert result is None or result == {}


def test_flatten_hosts_deduplication():
    """Test that hosts are deduplicated when combining transcript and mp3 metadata."""
    nested = {
        'transcript_metadata': {
            'hosts': ['Host1', 'Host2'],
            'co_hosts': ['Host2', 'Host3']  # Host2 is duplicate
        },
        'mp3_metadata': {
            'hosts': ['Host1', 'Host4']  # Host1 is duplicate
        }
    }

    result = flatten_episode_metadata(nested)

    # Should have all unique hosts
    hosts_set = set(result.get('hosts', []))
    assert len(hosts_set) == 4  # Host1, Host2, Host3, Host4
    assert 'Host1' in hosts_set
    assert 'Host2' in hosts_set
    assert 'Host3' in hosts_set
    assert 'Host4' in hosts_set
