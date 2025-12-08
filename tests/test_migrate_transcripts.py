"""Tests for transcript migration script."""

import json
import os
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from src.db.factory import create_repository
from src.db.models import Episode

# Import migration functions
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.migrate_transcripts_to_db import (
    get_metadata_path,
    read_transcript_file,
    read_metadata_file,
    migrate_transcripts,
)


@pytest.fixture
def repository(tmp_path):
    """Create a temporary SQLite-backed repository for tests."""
    db_path = tmp_path / "test.db"
    repo = create_repository(f"sqlite:///{db_path}", create_tables=True)
    yield repo
    repo.close()


@pytest.fixture
def sample_podcast(repository):
    """Create a sample podcast for testing."""
    return repository.create_podcast(
        feed_url="https://example.com/feed.xml",
        title="Test Podcast",
        description="A test podcast",
    )


class TestMigrationHelpers:
    """Tests for migration helper functions."""

    def test_get_metadata_path_standard(self):
        """Test building metadata path from standard transcript path."""
        transcript_path = "/path/to/episode_transcription.txt"
        metadata_path = get_metadata_path(transcript_path)
        assert metadata_path == "/path/to/episode_metadata.json"

    def test_get_metadata_path_no_suffix(self):
        """Test building metadata path from transcript without suffix."""
        transcript_path = "/path/to/episode.txt"
        metadata_path = get_metadata_path(transcript_path)
        assert metadata_path == "/path/to/episode_metadata.json"

    def test_get_metadata_path_nested(self):
        """Test building metadata path with nested directories."""
        transcript_path = "/data/podcasts/show/ep1_transcription.txt"
        metadata_path = get_metadata_path(transcript_path)
        assert metadata_path == "/data/podcasts/show/ep1_metadata.json"

    def test_read_transcript_file_success(self, tmp_path):
        """Test reading a valid transcript file."""
        transcript_file = tmp_path / "transcript.txt"
        transcript_content = "This is a test transcript."
        transcript_file.write_text(transcript_content, encoding="utf-8")

        result = read_transcript_file(str(transcript_file))
        assert result == transcript_content

    def test_read_transcript_file_unicode(self, tmp_path):
        """Test reading transcript with Unicode characters."""
        transcript_file = tmp_path / "transcript.txt"
        transcript_content = "Transcript with émojis 🎙️ and spëcial çharacters"
        transcript_file.write_text(transcript_content, encoding="utf-8")

        result = read_transcript_file(str(transcript_file))
        assert result == transcript_content

    def test_read_transcript_file_not_found(self):
        """Test reading non-existent transcript file."""
        result = read_transcript_file("/nonexistent/transcript.txt")
        assert result is None

    def test_read_transcript_file_large(self, tmp_path):
        """Test reading large transcript file."""
        transcript_file = tmp_path / "transcript.txt"
        transcript_content = "Large transcript. " * 10000  # ~170KB
        transcript_file.write_text(transcript_content, encoding="utf-8")

        result = read_transcript_file(str(transcript_file))
        assert result == transcript_content

    def test_read_metadata_file_success(self, tmp_path):
        """Test reading valid metadata file."""
        metadata_file = tmp_path / "metadata.json"
        metadata = {
            "feed_metadata": {"title": "Episode"},
            "mp3_metadata": {
                "artist": "Test Artist",
                "album": "Test Album",
            },
            "ai_metadata": {"summary": "Summary"},
        }
        metadata_file.write_text(json.dumps(metadata), encoding="utf-8")

        result = read_metadata_file(str(metadata_file))
        assert result is not None
        assert result["mp3_artist"] == "Test Artist"
        assert result["mp3_album"] == "Test Album"

    def test_read_metadata_file_missing_mp3(self, tmp_path):
        """Test reading metadata without MP3 data."""
        metadata_file = tmp_path / "metadata.json"
        metadata = {
            "feed_metadata": {"title": "Episode"},
            "ai_metadata": {"summary": "Summary"},
        }
        metadata_file.write_text(json.dumps(metadata), encoding="utf-8")

        result = read_metadata_file(str(metadata_file))
        assert result is not None
        assert result["mp3_artist"] is None
        assert result["mp3_album"] is None

    def test_read_metadata_file_not_found(self):
        """Test reading non-existent metadata file."""
        result = read_metadata_file("/nonexistent/metadata.json")
        assert result is None

    def test_read_metadata_file_invalid_json(self, tmp_path):
        """Test reading invalid JSON metadata file."""
        metadata_file = tmp_path / "metadata.json"
        metadata_file.write_text("invalid json{", encoding="utf-8")

        result = read_metadata_file(str(metadata_file))
        assert result is None

    def test_read_metadata_file_partial_mp3_data(self, tmp_path):
        """Test reading metadata with partial MP3 data."""
        metadata_file = tmp_path / "metadata.json"
        metadata = {
            "mp3_metadata": {
                "artist": "Test Artist",
                # album is missing
            },
        }
        metadata_file.write_text(json.dumps(metadata), encoding="utf-8")

        result = read_metadata_file(str(metadata_file))
        assert result is not None
        assert result["mp3_artist"] == "Test Artist"
        assert result["mp3_album"] is None


class TestMigrationLogic:
    """Tests for the main migration logic."""

    def test_migrate_no_episodes(self, repository):
        """Test migration with no episodes to migrate."""
        migrated, skipped, errors = migrate_transcripts(repository)
        assert migrated == 0
        assert skipped == 0
        assert errors == 0

    def test_migrate_single_episode(self, repository, sample_podcast, tmp_path):
        """Test migrating a single episode."""
        # Create episode with transcript file
        transcript_file = tmp_path / "transcript.txt"
        transcript_content = "Test transcript content."
        transcript_file.write_text(transcript_content, encoding="utf-8")

        episode = repository.create_episode(
            podcast_id=sample_podcast.id,
            guid="episode-1",
            title="Episode 1",
            enclosure_url="https://example.com/episode1.mp3",
            enclosure_type="audio/mpeg",
        )
        repository.update_episode(
            episode.id,
            transcript_path=str(transcript_file),
            transcript_status="completed",
        )

        # Run migration
        migrated, skipped, errors = migrate_transcripts(repository)

        assert migrated == 1
        assert errors == 0

        # Verify transcript was stored in database
        updated_episode = repository.get_episode(episode.id)
        assert updated_episode.transcript_text == transcript_content

    def test_migrate_with_metadata(self, repository, sample_podcast, tmp_path):
        """Test migrating episode with metadata file."""
        # Create transcript file
        transcript_file = tmp_path / "episode_transcription.txt"
        transcript_content = "Test transcript."
        transcript_file.write_text(transcript_content, encoding="utf-8")

        # Create metadata file
        metadata_file = tmp_path / "episode_metadata.json"
        metadata = {
            "mp3_metadata": {
                "artist": "Test Artist",
                "album": "Test Album",
            }
        }
        metadata_file.write_text(json.dumps(metadata), encoding="utf-8")

        episode = repository.create_episode(
            podcast_id=sample_podcast.id,
            guid="episode-1",
            title="Episode 1",
            enclosure_url="https://example.com/episode1.mp3",
            enclosure_type="audio/mpeg",
        )
        repository.update_episode(
            episode.id,
            transcript_path=str(transcript_file),
            transcript_status="completed",
        )

        # Run migration
        migrated, skipped, errors = migrate_transcripts(repository)

        assert migrated == 1
        assert errors == 0

        # Verify both transcript and metadata were stored
        updated_episode = repository.get_episode(episode.id)
        assert updated_episode.transcript_text == transcript_content
        assert updated_episode.mp3_artist == "Test Artist"
        assert updated_episode.mp3_album == "Test Album"

    def test_migrate_multiple_episodes(self, repository, sample_podcast, tmp_path):
        """Test migrating multiple episodes."""
        episodes = []
        for i in range(3):
            transcript_file = tmp_path / f"transcript_{i}.txt"
            transcript_file.write_text(f"Transcript {i}", encoding="utf-8")

            episode = repository.create_episode(
                podcast_id=sample_podcast.id,
                guid=f"episode-{i}",
                title=f"Episode {i}",
                enclosure_url=f"https://example.com/episode{i}.mp3",
                enclosure_type="audio/mpeg",
            )
            repository.update_episode(
                episode.id,
                transcript_path=str(transcript_file),
                transcript_status="completed",
            )
            episodes.append(episode)

        # Run migration
        migrated, skipped, errors = migrate_transcripts(repository)

        assert migrated == 3
        assert errors == 0

        # Verify all episodes were migrated
        for i, episode in enumerate(episodes):
            updated_episode = repository.get_episode(episode.id)
            assert updated_episode.transcript_text == f"Transcript {i}"

    def test_migrate_dry_run(self, repository, sample_podcast, tmp_path):
        """Test migration in dry-run mode."""
        transcript_file = tmp_path / "transcript.txt"
        transcript_file.write_text("Test transcript", encoding="utf-8")

        episode = repository.create_episode(
            podcast_id=sample_podcast.id,
            guid="episode-1",
            title="Episode 1",
            enclosure_url="https://example.com/episode1.mp3",
            enclosure_type="audio/mpeg",
        )
        repository.update_episode(
            episode.id,
            transcript_path=str(transcript_file),
            transcript_status="completed",
        )

        # Run in dry-run mode
        migrated, skipped, errors = migrate_transcripts(repository, dry_run=True)

        assert migrated == 1
        assert errors == 0

        # Verify database was NOT updated
        updated_episode = repository.get_episode(episode.id)
        assert updated_episode.transcript_text is None

    def test_migrate_verify_only(self, repository, sample_podcast, tmp_path):
        """Test migration in verify-only mode."""
        transcript_file = tmp_path / "transcript.txt"
        transcript_file.write_text("Test transcript", encoding="utf-8")

        episode = repository.create_episode(
            podcast_id=sample_podcast.id,
            guid="episode-1",
            title="Episode 1",
            enclosure_url="https://example.com/episode1.mp3",
            enclosure_type="audio/mpeg",
        )
        repository.update_episode(
            episode.id,
            transcript_path=str(transcript_file),
            transcript_status="completed",
        )

        # Run in verify mode
        migrated, skipped, errors = migrate_transcripts(repository, verify_only=True)

        assert migrated == 0
        assert skipped == 1
        assert errors == 0

    def test_migrate_missing_file(self, repository, sample_podcast):
        """Test migration with missing transcript file."""
        episode = repository.create_episode(
            podcast_id=sample_podcast.id,
            guid="episode-1",
            title="Episode 1",
            enclosure_url="https://example.com/episode1.mp3",
            enclosure_type="audio/mpeg",
        )
        repository.update_episode(
            episode.id,
            transcript_path="/nonexistent/transcript.txt",
            transcript_status="completed",
        )

        # Run migration
        migrated, skipped, errors = migrate_transcripts(repository)

        assert migrated == 0
        assert errors == 1

    def test_migrate_skips_already_migrated(self, repository, sample_podcast, tmp_path):
        """Test that already migrated episodes are skipped."""
        transcript_file = tmp_path / "transcript.txt"
        transcript_file.write_text("Test transcript", encoding="utf-8")

        episode = repository.create_episode(
            podcast_id=sample_podcast.id,
            guid="episode-1",
            title="Episode 1",
            enclosure_url="https://example.com/episode1.mp3",
            enclosure_type="audio/mpeg",
        )
        # Set both transcript_text and transcript_path
        repository.update_episode(
            episode.id,
            transcript_path=str(transcript_file),
            transcript_text="Already migrated",
            transcript_status="completed",
        )

        # Run migration - should skip
        migrated, skipped, errors = migrate_transcripts(repository)

        assert migrated == 0
        assert errors == 0

    def test_migrate_with_unicode_content(self, repository, sample_podcast, tmp_path):
        """Test migrating transcript with Unicode characters."""
        transcript_file = tmp_path / "transcript.txt"
        transcript_content = "Transcript avec des caractères spéciaux: émojis 🎙️"
        transcript_file.write_text(transcript_content, encoding="utf-8")

        episode = repository.create_episode(
            podcast_id=sample_podcast.id,
            guid="episode-1",
            title="Episode 1",
            enclosure_url="https://example.com/episode1.mp3",
            enclosure_type="audio/mpeg",
        )
        repository.update_episode(
            episode.id,
            transcript_path=str(transcript_file),
            transcript_status="completed",
        )

        # Run migration
        migrated, skipped, errors = migrate_transcripts(repository)

        assert migrated == 1
        assert errors == 0

        # Verify Unicode content preserved
        updated_episode = repository.get_episode(episode.id)
        assert updated_episode.transcript_text == transcript_content

    def test_migrate_large_transcript(self, repository, sample_podcast, tmp_path):
        """Test migrating a large transcript file."""
        transcript_file = tmp_path / "transcript.txt"
        # Create ~500KB transcript
        transcript_content = "Large transcript content. " * 20000
        transcript_file.write_text(transcript_content, encoding="utf-8")

        episode = repository.create_episode(
            podcast_id=sample_podcast.id,
            guid="episode-1",
            title="Episode 1",
            enclosure_url="https://example.com/episode1.mp3",
            enclosure_type="audio/mpeg",
        )
        repository.update_episode(
            episode.id,
            transcript_path=str(transcript_file),
            transcript_status="completed",
        )

        # Run migration
        migrated, skipped, errors = migrate_transcripts(repository)

        assert migrated == 1
        assert errors == 0

        # Verify large content stored correctly
        updated_episode = repository.get_episode(episode.id)
        assert len(updated_episode.transcript_text) == len(transcript_content)