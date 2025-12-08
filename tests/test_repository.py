"""Tests for the podcast repository."""

import os
import pytest
from datetime import datetime

from src.db.factory import create_repository
from src.db.models import Podcast, Episode
from src.db.repository import SQLAlchemyPodcastRepository


@pytest.fixture
def repository(tmp_path):
    """
    Create a temporary SQLite-backed repository for tests.

    Yields a repository instance configured to use a SQLite file under the provided temporary path and closes the repository when the fixture is torn down.
    """
    db_path = tmp_path / "test.db"
    repo = create_repository(f"sqlite:///{db_path}", create_tables=True)
    yield repo
    repo.close()


@pytest.fixture
def sample_podcast(repository):
    """
    Create and persist a sample podcast used by tests.
    
    Returns:
        podcast: The created podcast object with an assigned `id` and the provided fields (feed_url, title, description, author, language).
    """
    return repository.create_podcast(
        feed_url="https://example.com/feed.xml",
        title="Test Podcast",
        description="A test podcast",
        author="Test Author",
        language="en",
    )


class TestPodcastOperations:
    """Tests for podcast CRUD operations."""

    def test_create_podcast(self, repository):
        """Test creating a podcast."""
        podcast = repository.create_podcast(
            feed_url="https://example.com/feed.xml",
            title="Test Podcast",
            description="A test podcast",
        )

        assert podcast.id is not None
        assert podcast.feed_url == "https://example.com/feed.xml"
        assert podcast.title == "Test Podcast"
        assert podcast.is_subscribed is True

    def test_get_podcast(self, repository, sample_podcast):
        """Test getting a podcast by ID."""
        retrieved = repository.get_podcast(sample_podcast.id)

        assert retrieved is not None
        assert retrieved.id == sample_podcast.id
        assert retrieved.title == sample_podcast.title

    def test_get_podcast_by_feed_url(self, repository, sample_podcast):
        """Test getting a podcast by feed URL."""
        retrieved = repository.get_podcast_by_feed_url("https://example.com/feed.xml")

        assert retrieved is not None
        assert retrieved.id == sample_podcast.id

    def test_get_nonexistent_podcast(self, repository):
        """Test getting a podcast that doesn't exist."""
        retrieved = repository.get_podcast("nonexistent-id")
        assert retrieved is None

    def test_list_podcasts(self, repository):
        """Test listing podcasts."""
        repository.create_podcast(
            feed_url="https://example.com/feed1.xml",
            title="Podcast 1",
        )
        repository.create_podcast(
            feed_url="https://example.com/feed2.xml",
            title="Podcast 2",
        )

        podcasts = repository.list_podcasts()
        assert len(podcasts) == 2

    def test_list_podcasts_subscribed_only(self, repository):
        """Test listing only subscribed podcasts."""
        repository.create_podcast(
            feed_url="https://example.com/feed1.xml",
            title="Podcast 1",
            is_subscribed=True,
        )
        repository.create_podcast(
            feed_url="https://example.com/feed2.xml",
            title="Podcast 2",
            is_subscribed=False,
        )

        subscribed = repository.list_podcasts(subscribed_only=True)
        all_podcasts = repository.list_podcasts(subscribed_only=False)

        assert len(subscribed) == 1
        assert len(all_podcasts) == 2

    def test_update_podcast(self, repository, sample_podcast):
        """Test updating a podcast."""
        updated = repository.update_podcast(
            sample_podcast.id,
            title="Updated Title",
            description="Updated description",
        )

        assert updated.title == "Updated Title"
        assert updated.description == "Updated description"

    def test_delete_podcast(self, repository, sample_podcast):
        """Test deleting a podcast."""
        result = repository.delete_podcast(sample_podcast.id)
        assert result is True

        retrieved = repository.get_podcast(sample_podcast.id)
        assert retrieved is None


class TestEpisodeOperations:
    """Tests for episode CRUD operations."""

    def test_create_episode(self, repository, sample_podcast):
        """Test creating an episode."""
        episode = repository.create_episode(
            podcast_id=sample_podcast.id,
            guid="episode-1",
            title="Episode 1",
            enclosure_url="https://example.com/episode1.mp3",
            enclosure_type="audio/mpeg",
        )

        assert episode.id is not None
        assert episode.guid == "episode-1"
        assert episode.title == "Episode 1"
        assert episode.download_status == "pending"

    def test_get_episode(self, repository, sample_podcast):
        """Test getting an episode by ID."""
        episode = repository.create_episode(
            podcast_id=sample_podcast.id,
            guid="episode-1",
            title="Episode 1",
            enclosure_url="https://example.com/episode1.mp3",
            enclosure_type="audio/mpeg",
        )

        retrieved = repository.get_episode(episode.id)

        assert retrieved is not None
        assert retrieved.id == episode.id

    def test_get_episode_by_guid(self, repository, sample_podcast):
        """Test getting an episode by GUID."""
        repository.create_episode(
            podcast_id=sample_podcast.id,
            guid="episode-1",
            title="Episode 1",
            enclosure_url="https://example.com/episode1.mp3",
            enclosure_type="audio/mpeg",
        )

        retrieved = repository.get_episode_by_guid(sample_podcast.id, "episode-1")

        assert retrieved is not None
        assert retrieved.guid == "episode-1"

    def test_list_episodes(self, repository, sample_podcast):
        """Test listing episodes."""
        for i in range(3):
            repository.create_episode(
                podcast_id=sample_podcast.id,
                guid=f"episode-{i}",
                title=f"Episode {i}",
                enclosure_url=f"https://example.com/episode{i}.mp3",
                enclosure_type="audio/mpeg",
            )

        episodes = repository.list_episodes(podcast_id=sample_podcast.id)
        assert len(episodes) == 3

    def test_list_episodes_by_status(self, repository, sample_podcast):
        """Test filtering episodes by status."""
        episode1 = repository.create_episode(
            podcast_id=sample_podcast.id,
            guid="episode-1",
            title="Episode 1",
            enclosure_url="https://example.com/episode1.mp3",
            enclosure_type="audio/mpeg",
        )
        episode2 = repository.create_episode(
            podcast_id=sample_podcast.id,
            guid="episode-2",
            title="Episode 2",
            enclosure_url="https://example.com/episode2.mp3",
            enclosure_type="audio/mpeg",
        )

        # Mark one as completed
        repository.mark_download_complete(episode1.id, "/path/to/file.mp3", 1000, "abc123")

        pending = repository.list_episodes(download_status="pending")
        completed = repository.list_episodes(download_status="completed")

        assert len(pending) == 1
        assert len(completed) == 1

    def test_get_or_create_episode(self, repository, sample_podcast):
        """Test get_or_create_episode."""
        # First call creates
        episode1, created1 = repository.get_or_create_episode(
            podcast_id=sample_podcast.id,
            guid="episode-1",
            title="Episode 1",
            enclosure_url="https://example.com/episode1.mp3",
            enclosure_type="audio/mpeg",
        )
        assert created1 is True

        # Second call gets existing
        episode2, created2 = repository.get_or_create_episode(
            podcast_id=sample_podcast.id,
            guid="episode-1",
            title="Episode 1",
            enclosure_url="https://example.com/episode1.mp3",
            enclosure_type="audio/mpeg",
        )
        assert created2 is False
        assert episode2.id == episode1.id

    def test_update_episode(self, repository, sample_podcast):
        """Test updating an episode."""
        episode = repository.create_episode(
            podcast_id=sample_podcast.id,
            guid="episode-1",
            title="Episode 1",
            enclosure_url="https://example.com/episode1.mp3",
            enclosure_type="audio/mpeg",
        )

        updated = repository.update_episode(
            episode.id,
            title="Updated Episode 1",
            description="New description",
        )

        assert updated.title == "Updated Episode 1"
        assert updated.description == "New description"

    def test_delete_episode(self, repository, sample_podcast):
        """Test deleting an episode."""
        episode = repository.create_episode(
            podcast_id=sample_podcast.id,
            guid="episode-1",
            title="Episode 1",
            enclosure_url="https://example.com/episode1.mp3",
            enclosure_type="audio/mpeg",
        )

        result = repository.delete_episode(episode.id)
        assert result is True

        retrieved = repository.get_episode(episode.id)
        assert retrieved is None


class TestStatusUpdates:
    """Tests for status update methods."""

    def test_download_status_flow(self, repository, sample_podcast):
        """Test download status transitions."""
        episode = repository.create_episode(
            podcast_id=sample_podcast.id,
            guid="episode-1",
            title="Episode 1",
            enclosure_url="https://example.com/episode1.mp3",
            enclosure_type="audio/mpeg",
        )

        # Initial status
        assert episode.download_status == "pending"

        # Mark as downloading
        repository.mark_download_started(episode.id)
        episode = repository.get_episode(episode.id)
        assert episode.download_status == "downloading"

        # Mark as complete
        repository.mark_download_complete(episode.id, "/path/to/file.mp3", 1000, "abc123")
        episode = repository.get_episode(episode.id)
        assert episode.download_status == "completed"
        assert episode.local_file_path == "/path/to/file.mp3"
        assert episode.file_size_bytes == 1000
        assert episode.file_hash == "abc123"

    def test_download_failure(self, repository, sample_podcast):
        """Test marking download as failed."""
        episode = repository.create_episode(
            podcast_id=sample_podcast.id,
            guid="episode-1",
            title="Episode 1",
            enclosure_url="https://example.com/episode1.mp3",
            enclosure_type="audio/mpeg",
        )

        repository.mark_download_started(episode.id)
        repository.mark_download_failed(episode.id, "Connection timeout")

        episode = repository.get_episode(episode.id)
        assert episode.download_status == "failed"
        assert episode.download_error == "Connection timeout"

    def test_transcript_status_flow(self, repository, sample_podcast):
        """
        Verify that an episode's transcript status progresses from "processing" to "completed"
        and that the transcript text is stored when transcription completes.
        """
        episode = repository.create_episode(
            podcast_id=sample_podcast.id,
            guid="episode-1",
            title="Episode 1",
            enclosure_url="https://example.com/episode1.mp3",
            enclosure_type="audio/mpeg",
        )

        repository.mark_transcript_started(episode.id)
        episode = repository.get_episode(episode.id)
        assert episode.transcript_status == "processing"

        transcript_text = "This is the full transcript content for the episode."
        repository.mark_transcript_complete(episode.id, transcript_text=transcript_text)
        episode = repository.get_episode(episode.id)
        assert episode.transcript_status == "completed"
        assert episode.transcript_text == transcript_text

    def test_indexing_status_flow(self, repository, sample_podcast):
        """Test File Search indexing status transitions."""
        episode = repository.create_episode(
            podcast_id=sample_podcast.id,
            guid="episode-1",
            title="Episode 1",
            enclosure_url="https://example.com/episode1.mp3",
            enclosure_type="audio/mpeg",
        )

        repository.mark_indexing_started(episode.id)
        episode = repository.get_episode(episode.id)
        assert episode.file_search_status == "uploading"

        repository.mark_indexing_complete(
            episode.id,
            "corpora/abc/documents/xyz",
            "Episode_1.txt",
        )
        episode = repository.get_episode(episode.id)
        assert episode.file_search_status == "indexed"
        assert episode.file_search_resource_name == "corpora/abc/documents/xyz"


class TestBatchOperations:
    """Tests for batch query operations."""

    def test_get_episodes_pending_download(self, repository, sample_podcast):
        """Test getting episodes pending download."""
        for i in range(5):
            repository.create_episode(
                podcast_id=sample_podcast.id,
                guid=f"episode-{i}",
                title=f"Episode {i}",
                enclosure_url=f"https://example.com/episode{i}.mp3",
                enclosure_type="audio/mpeg",
            )

        pending = repository.get_episodes_pending_download(limit=3)
        assert len(pending) == 3

    def test_get_episodes_pending_transcription(self, repository, sample_podcast):
        """Test getting episodes pending transcription."""
        episode = repository.create_episode(
            podcast_id=sample_podcast.id,
            guid="episode-1",
            title="Episode 1",
            enclosure_url="https://example.com/episode1.mp3",
            enclosure_type="audio/mpeg",
        )

        # Not ready yet (not downloaded)
        pending = repository.get_episodes_pending_transcription()
        assert len(pending) == 0

        # Mark as downloaded
        repository.mark_download_complete(episode.id, "/path/to/file.mp3", 1000, "abc123")

        # Now should be pending transcription
        pending = repository.get_episodes_pending_transcription()
        assert len(pending) == 1


class TestStatistics:
    """Tests for statistics methods."""

    def test_get_podcast_stats(self, repository, sample_podcast):
        """Test getting podcast statistics."""
        for i in range(3):
            repository.create_episode(
                podcast_id=sample_podcast.id,
                guid=f"episode-{i}",
                title=f"Episode {i}",
                enclosure_url=f"https://example.com/episode{i}.mp3",
                enclosure_type="audio/mpeg",
            )

        stats = repository.get_podcast_stats(sample_podcast.id)

        assert stats["total_episodes"] == 3
        assert stats["pending_download"] == 3
        assert stats["downloaded"] == 0

    def test_get_overall_stats(self, repository):
        """Test getting overall statistics."""
        for i in range(2):
            podcast = repository.create_podcast(
                feed_url=f"https://example.com/feed{i}.xml",
                title=f"Podcast {i}",
            )
            repository.create_episode(
                podcast_id=podcast.id,
                guid="episode-1",
                title="Episode 1",
                enclosure_url="https://example.com/episode1.mp3",
                enclosure_type="audio/mpeg",
            )

        stats = repository.get_overall_stats()

        assert stats["total_podcasts"] == 2
        assert stats["total_episodes"] == 2