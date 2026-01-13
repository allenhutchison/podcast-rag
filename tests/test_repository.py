"""Tests for the podcast repository."""

import pytest

from src.db.factory import create_repository
from src.db.repository import _escape_like_pattern


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

    def test_get_episode_by_file_search_display_name(self, repository, sample_podcast):
        """Test getting an episode by File Search display name."""
        episode = repository.create_episode(
            podcast_id=sample_podcast.id,
            guid="episode-1",
            title="Episode 1",
            enclosure_url="https://example.com/episode1.mp3",
            enclosure_type="audio/mpeg",
        )

        # Update the episode with a file_search_display_name
        repository.update_episode(episode.id, file_search_display_name="episode_1_transcription.txt")

        # Test retrieval
        retrieved = repository.get_episode_by_file_search_display_name("episode_1_transcription.txt")

        assert retrieved is not None
        assert retrieved.guid == "episode-1"
        assert retrieved.file_search_display_name == "episode_1_transcription.txt"
        assert retrieved.podcast is not None  # Eager loaded
        assert retrieved.podcast.title == "Test Podcast"

    def test_get_episode_by_file_search_display_name_not_found(self, repository):
        """Test getting a non-existent episode by File Search display name."""
        retrieved = repository.get_episode_by_file_search_display_name("nonexistent.txt")
        assert retrieved is None

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
        repository.create_episode(
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



class TestTranscriptTextStorage:
    """Tests for transcript text database storage functionality."""

    def test_mark_transcript_complete_with_text(self, repository, sample_podcast):
        """Test storing transcript text directly in database."""
        episode = repository.create_episode(
            podcast_id=sample_podcast.id,
            guid="episode-1",
            title="Episode 1",
            enclosure_url="https://example.com/episode1.mp3",
            enclosure_type="audio/mpeg",
        )

        transcript_text = "This is the full transcript text content."
        repository.mark_transcript_complete(
            episode.id,
            transcript_text=transcript_text,
        )

        episode = repository.get_episode(episode.id)
        assert episode.transcript_status == "completed"
        assert episode.transcript_text == transcript_text
        assert episode.transcribed_at is not None

    def test_mark_transcript_complete_with_text_and_path(self, repository, sample_podcast):
        """Test storing both transcript text and legacy path."""
        episode = repository.create_episode(
            podcast_id=sample_podcast.id,
            guid="episode-1",
            title="Episode 1",
            enclosure_url="https://example.com/episode1.mp3",
            enclosure_type="audio/mpeg",
        )

        transcript_text = "This is the full transcript text content."
        transcript_path = "/path/to/transcript.txt"
        repository.mark_transcript_complete(
            episode.id,
            transcript_text=transcript_text,
            transcript_path=transcript_path,
        )

        episode = repository.get_episode(episode.id)
        assert episode.transcript_text == transcript_text
        assert episode.transcript_path == transcript_path

    def test_get_transcript_text_from_database(self, repository, sample_podcast):
        """Test retrieving transcript text from database."""
        episode = repository.create_episode(
            podcast_id=sample_podcast.id,
            guid="episode-1",
            title="Episode 1",
            enclosure_url="https://example.com/episode1.mp3",
            enclosure_type="audio/mpeg",
        )

        transcript_text = "This is the full transcript text content."
        repository.mark_transcript_complete(
            episode.id,
            transcript_text=transcript_text,
        )

        retrieved_text = repository.get_transcript_text(episode.id)
        assert retrieved_text == transcript_text

    def test_get_transcript_text_from_file(self, repository, sample_podcast, tmp_path):
        """Test retrieving transcript text from legacy file."""
        episode = repository.create_episode(
            podcast_id=sample_podcast.id,
            guid="episode-1",
            title="Episode 1",
            enclosure_url="https://example.com/episode1.mp3",
            enclosure_type="audio/mpeg",
        )

        # Create a legacy transcript file
        transcript_file = tmp_path / "transcript.txt"
        transcript_text = "Legacy transcript from file."
        transcript_file.write_text(transcript_text, encoding="utf-8")

        # Update episode with only transcript_path (legacy mode)
        repository.update_episode(
            episode.id,
            transcript_path=str(transcript_file),
            transcript_status="completed",
        )

        retrieved_text = repository.get_transcript_text(episode.id)
        assert retrieved_text == transcript_text

    def test_get_transcript_text_prefers_database(self, repository, sample_podcast, tmp_path):
        """Test that database text is preferred over file."""
        episode = repository.create_episode(
            podcast_id=sample_podcast.id,
            guid="episode-1",
            title="Episode 1",
            enclosure_url="https://example.com/episode1.mp3",
            enclosure_type="audio/mpeg",
        )

        # Create a file with different content
        transcript_file = tmp_path / "transcript.txt"
        transcript_file.write_text("File content", encoding="utf-8")

        # Store different content in database
        db_text = "Database content"
        repository.mark_transcript_complete(
            episode.id,
            transcript_text=db_text,
            transcript_path=str(transcript_file),
        )

        # Should return database content, not file content
        retrieved_text = repository.get_transcript_text(episode.id)
        assert retrieved_text == db_text

    def test_get_transcript_text_nonexistent_episode(self, repository):
        """Test getting transcript for non-existent episode."""
        result = repository.get_transcript_text("nonexistent-id")
        assert result is None

    def test_get_transcript_text_no_transcript(self, repository, sample_podcast):
        """Test getting transcript when episode has no transcript."""
        episode = repository.create_episode(
            podcast_id=sample_podcast.id,
            guid="episode-1",
            title="Episode 1",
            enclosure_url="https://example.com/episode1.mp3",
            enclosure_type="audio/mpeg",
        )

        result = repository.get_transcript_text(episode.id)
        assert result is None

    def test_get_transcript_text_file_not_found(self, repository, sample_podcast):
        """Test handling missing transcript file."""
        episode = repository.create_episode(
            podcast_id=sample_podcast.id,
            guid="episode-1",
            title="Episode 1",
            enclosure_url="https://example.com/episode1.mp3",
            enclosure_type="audio/mpeg",
        )

        # Set transcript_path to non-existent file
        repository.update_episode(
            episode.id,
            transcript_path="/nonexistent/transcript.txt",
            transcript_status="completed",
        )

        result = repository.get_transcript_text(episode.id)
        assert result is None

    def test_get_transcript_text_unicode_content(self, repository, sample_podcast):
        """Test handling Unicode content in transcript."""
        episode = repository.create_episode(
            podcast_id=sample_podcast.id,
            guid="episode-1",
            title="Episode 1",
            enclosure_url="https://example.com/episode1.mp3",
            enclosure_type="audio/mpeg",
        )

        transcript_text = "Transcript with émojis 🎙️ and spëcial çharacters"
        repository.mark_transcript_complete(
            episode.id,
            transcript_text=transcript_text,
        )

        retrieved_text = repository.get_transcript_text(episode.id)
        assert retrieved_text == transcript_text

    def test_get_transcript_text_empty_string(self, repository, sample_podcast):
        """Test handling empty transcript text."""
        episode = repository.create_episode(
            podcast_id=sample_podcast.id,
            guid="episode-1",
            title="Episode 1",
            enclosure_url="https://example.com/episode1.mp3",
            enclosure_type="audio/mpeg",
        )

        repository.mark_transcript_complete(
            episode.id,
            transcript_text="",
        )

        # Empty string should still be returned
        retrieved_text = repository.get_transcript_text(episode.id)
        assert retrieved_text == ""


class TestMP3Metadata:
    """Tests for MP3 metadata storage functionality."""

    def test_mark_metadata_complete_with_mp3_tags(self, repository, sample_podcast):
        """Test storing MP3 metadata tags."""
        episode = repository.create_episode(
            podcast_id=sample_podcast.id,
            guid="episode-1",
            title="Episode 1",
            enclosure_url="https://example.com/episode1.mp3",
            enclosure_type="audio/mpeg",
        )

        repository.mark_metadata_complete(
            episode_id=episode.id,
            summary="Episode summary",
            keywords=["tech", "podcast"],
            hosts=["Host 1", "Host 2"],
            guests=["Guest 1"],
            mp3_artist="Podcast Artist",
            mp3_album="Podcast Album",
        )

        episode = repository.get_episode(episode.id)
        assert episode.metadata_status == "completed"
        assert episode.mp3_artist == "Podcast Artist"
        assert episode.mp3_album == "Podcast Album"
        assert episode.ai_summary == "Episode summary"
        assert episode.ai_keywords == ["tech", "podcast"]
        assert episode.ai_hosts == ["Host 1", "Host 2"]
        assert episode.ai_guests == ["Guest 1"]

    def test_mark_metadata_complete_without_mp3_tags(self, repository, sample_podcast):
        """Test metadata completion without MP3 tags."""
        episode = repository.create_episode(
            podcast_id=sample_podcast.id,
            guid="episode-1",
            title="Episode 1",
            enclosure_url="https://example.com/episode1.mp3",
            enclosure_type="audio/mpeg",
        )

        repository.mark_metadata_complete(
            episode_id=episode.id,
            summary="Episode summary",
            keywords=["tech"],
        )

        episode = repository.get_episode(episode.id)
        assert episode.metadata_status == "completed"
        assert episode.mp3_artist is None
        assert episode.mp3_album is None
        assert episode.ai_summary == "Episode summary"

    def test_mark_metadata_complete_only_mp3_tags(self, repository, sample_podcast):
        """Test storing only MP3 tags without AI metadata."""
        episode = repository.create_episode(
            podcast_id=sample_podcast.id,
            guid="episode-1",
            title="Episode 1",
            enclosure_url="https://example.com/episode1.mp3",
            enclosure_type="audio/mpeg",
        )

        repository.mark_metadata_complete(
            episode_id=episode.id,
            mp3_artist="Podcast Artist",
            mp3_album="Podcast Album",
        )

        episode = repository.get_episode(episode.id)
        assert episode.mp3_artist == "Podcast Artist"
        assert episode.mp3_album == "Podcast Album"
        assert episode.ai_summary is None

    def test_update_episode_mp3_metadata(self, repository, sample_podcast):
        """Test updating MP3 metadata on existing episode."""
        episode = repository.create_episode(
            podcast_id=sample_podcast.id,
            guid="episode-1",
            title="Episode 1",
            enclosure_url="https://example.com/episode1.mp3",
            enclosure_type="audio/mpeg",
        )

        repository.update_episode(
            episode.id,
            mp3_artist="New Artist",
            mp3_album="New Album",
        )

        episode = repository.get_episode(episode.id)
        assert episode.mp3_artist == "New Artist"
        assert episode.mp3_album == "New Album"

    def test_mp3_metadata_unicode_characters(self, repository, sample_podcast):
        """Test MP3 metadata with Unicode characters."""
        episode = repository.create_episode(
            podcast_id=sample_podcast.id,
            guid="episode-1",
            title="Episode 1",
            enclosure_url="https://example.com/episode1.mp3",
            enclosure_type="audio/mpeg",
        )

        repository.mark_metadata_complete(
            episode_id=episode.id,
            mp3_artist="Artiste Français",
            mp3_album="Álbum Español",
        )

        episode = repository.get_episode(episode.id)
        assert episode.mp3_artist == "Artiste Français"
        assert episode.mp3_album == "Álbum Español"

    def test_mp3_metadata_long_strings(self, repository, sample_podcast):
        """Test MP3 metadata with long strings."""
        episode = repository.create_episode(
            podcast_id=sample_podcast.id,
            guid="episode-1",
            title="Episode 1",
            enclosure_url="https://example.com/episode1.mp3",
            enclosure_type="audio/mpeg",
        )

        long_artist = "A" * 500  # Within 512 char limit
        long_album = "B" * 500
        repository.mark_metadata_complete(
            episode_id=episode.id,
            mp3_artist=long_artist,
            mp3_album=long_album,
        )

        episode = repository.get_episode(episode.id)
        assert episode.mp3_artist == long_artist
        assert episode.mp3_album == long_album


class TestPendingEpisodesWithTranscriptText:
    """Tests for pending episode queries with transcript text support."""

    def test_get_episodes_pending_metadata_with_transcript_text(self, repository, sample_podcast):
        """Test that episodes with transcript_text are returned for metadata."""
        episode = repository.create_episode(
            podcast_id=sample_podcast.id,
            guid="episode-1",
            title="Episode 1",
            enclosure_url="https://example.com/episode1.mp3",
            enclosure_type="audio/mpeg",
        )

        # Mark transcript complete with text in database
        repository.mark_transcript_complete(
            episode.id,
            transcript_text="Transcript content",
        )

        pending = repository.get_episodes_pending_metadata()
        assert len(pending) == 1
        assert pending[0].id == episode.id

    def test_get_episodes_pending_metadata_with_transcript_path(self, repository, sample_podcast, tmp_path):
        """Test that legacy episodes with transcript_path are still returned."""
        episode = repository.create_episode(
            podcast_id=sample_podcast.id,
            guid="episode-1",
            title="Episode 1",
            enclosure_url="https://example.com/episode1.mp3",
            enclosure_type="audio/mpeg",
        )

        # Create legacy transcript file
        transcript_file = tmp_path / "transcript.txt"
        transcript_file.write_text("Legacy transcript", encoding="utf-8")

        # Mark complete with only path (legacy mode)
        repository.update_episode(
            episode.id,
            transcript_status="completed",
            transcript_path=str(transcript_file),
        )

        pending = repository.get_episodes_pending_metadata()
        assert len(pending) == 1
        assert pending[0].id == episode.id

    def test_get_episodes_pending_metadata_without_transcript(self, repository, sample_podcast):
        """Test that episodes without transcript are not returned."""
        episode = repository.create_episode(
            podcast_id=sample_podcast.id,
            guid="episode-1",
            title="Episode 1",
            enclosure_url="https://example.com/episode1.mp3",
            enclosure_type="audio/mpeg",
        )

        # Mark transcript complete but without text or path
        repository.update_episode(
            episode.id,
            transcript_status="completed",
        )

        pending = repository.get_episodes_pending_metadata()
        assert len(pending) == 0

    def test_get_episodes_pending_indexing_with_transcript_text(self, repository, sample_podcast):
        """Test that episodes with transcript_text are returned for indexing."""
        episode = repository.create_episode(
            podcast_id=sample_podcast.id,
            guid="episode-1",
            title="Episode 1",
            enclosure_url="https://example.com/episode1.mp3",
            enclosure_type="audio/mpeg",
        )

        # Complete transcript and metadata
        repository.mark_transcript_complete(
            episode.id,
            transcript_text="Transcript content",
        )
        repository.mark_metadata_complete(
            episode_id=episode.id,
            summary="Summary",
        )

        pending = repository.get_episodes_pending_indexing()
        assert len(pending) == 1
        assert pending[0].id == episode.id

    def test_get_episodes_pending_indexing_with_transcript_path(self, repository, sample_podcast, tmp_path):
        """Test that legacy episodes are returned for indexing."""
        episode = repository.create_episode(
            podcast_id=sample_podcast.id,
            guid="episode-1",
            title="Episode 1",
            enclosure_url="https://example.com/episode1.mp3",
            enclosure_type="audio/mpeg",
        )

        # Create legacy transcript file
        transcript_file = tmp_path / "transcript.txt"
        transcript_file.write_text("Legacy transcript", encoding="utf-8")

        # Complete with legacy path
        repository.update_episode(
            episode.id,
            transcript_status="completed",
            transcript_path=str(transcript_file),
            metadata_status="completed",
        )

        pending = repository.get_episodes_pending_indexing()
        assert len(pending) == 1
        assert pending[0].id == episode.id

    def test_get_episodes_pending_indexing_without_transcript(self, repository, sample_podcast):
        """Test that episodes without transcript are not returned for indexing."""
        episode = repository.create_episode(
            podcast_id=sample_podcast.id,
            guid="episode-1",
            title="Episode 1",
            enclosure_url="https://example.com/episode1.mp3",
            enclosure_type="audio/mpeg",
        )

        # Complete metadata but no transcript
        repository.update_episode(
            episode.id,
            transcript_status="completed",
            metadata_status="completed",
        )

        pending = repository.get_episodes_pending_indexing()
        assert len(pending) == 0

    def test_get_episodes_pending_metadata_respects_limit(self, repository, sample_podcast):
        """Test that pending metadata query respects limit."""
        # Create multiple episodes
        for i in range(5):
            episode = repository.create_episode(
                podcast_id=sample_podcast.id,
                guid=f"episode-{i}",
                title=f"Episode {i}",
                enclosure_url=f"https://example.com/episode{i}.mp3",
                enclosure_type="audio/mpeg",
            )
            repository.mark_transcript_complete(
                episode.id,
                transcript_text=f"Transcript {i}",
            )

        pending = repository.get_episodes_pending_metadata(limit=3)
        assert len(pending) == 3

    def test_get_episodes_pending_indexing_respects_limit(self, repository, sample_podcast):
        """Test that pending indexing query respects limit."""
        # Create multiple episodes
        for i in range(5):
            episode = repository.create_episode(
                podcast_id=sample_podcast.id,
                guid=f"episode-{i}",
                title=f"Episode {i}",
                enclosure_url=f"https://example.com/episode{i}.mp3",
                enclosure_type="audio/mpeg",
            )
            repository.mark_transcript_complete(
                episode.id,
                transcript_text=f"Transcript {i}",
            )
            repository.mark_metadata_complete(
                episode_id=episode.id,
                summary=f"Summary {i}",
            )

        pending = repository.get_episodes_pending_indexing(limit=3)
        assert len(pending) == 3

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


class TestEscapeLikePattern:
    """Tests for LIKE pattern escaping to prevent injection."""

    def test_escape_normal_string(self):
        """Test that normal strings pass through unchanged."""
        assert _escape_like_pattern("John Smith") == "John Smith"
        assert _escape_like_pattern("AI Technology") == "AI Technology"

    def test_escape_percent(self):
        """Test that percent signs are escaped."""
        assert _escape_like_pattern("100%") == "100\\%"
        assert _escape_like_pattern("%wildcard%") == "\\%wildcard\\%"

    def test_escape_underscore(self):
        """Test that underscores are escaped."""
        assert _escape_like_pattern("some_name") == "some\\_name"
        assert _escape_like_pattern("_prefix") == "\\_prefix"

    def test_escape_backslash(self):
        """Test that backslashes are escaped."""
        assert _escape_like_pattern("path\\to") == "path\\\\to"
        assert _escape_like_pattern("\\start") == "\\\\start"

    def test_escape_double_quote(self):
        """Test that double quotes are escaped."""
        assert _escape_like_pattern('say "hello"') == 'say \\"hello\\"'

    def test_escape_combined(self):
        """Test escaping multiple special characters together."""
        # Backslash must be escaped first to avoid double-escaping
        result = _escape_like_pattern('100% of "users_data"\\path')
        assert result == '100\\% of \\"users\\_data\\"\\\\path'

    def test_escape_empty_string(self):
        """Test that empty string returns empty."""
        assert _escape_like_pattern("") == ""


# Additional test classes added for database storage migration:
# - TestTranscriptTextStorage: Tests for storing transcript text directly in database
# - TestMP3Metadata: Tests for MP3 ID3 tag metadata storage
# - TestPendingEpisodesWithTranscriptText: Tests for pending episode queries with new storage


class TestPipelineModeMethods:
    """Tests for pipeline mode processing methods."""

    def test_get_download_buffer_count(self, repository, sample_podcast):
        """Test counting episodes ready for transcription."""
        # Create episodes with different statuses
        for i in range(3):
            episode = repository.create_episode(
                podcast_id=sample_podcast.id,
                guid=f"episode-{i}",
                title=f"Episode {i}",
                enclosure_url=f"https://example.com/episode{i}.mp3",
                enclosure_type="audio/mpeg",
            )
            repository.mark_download_complete(episode.id, f"/path/ep{i}.mp3", 1000, "hash")

        count = repository.get_download_buffer_count()
        assert count == 3

    def test_get_next_for_transcription(self, repository, sample_podcast):
        """Test getting next episode for transcription."""
        from datetime import datetime, UTC

        # Create episodes with different dates
        ep1 = repository.create_episode(
            podcast_id=sample_podcast.id,
            guid="episode-1",
            title="Older Episode",
            enclosure_url="https://example.com/episode1.mp3",
            enclosure_type="audio/mpeg",
            published_date=datetime(2024, 1, 1, tzinfo=UTC),
        )
        repository.mark_download_complete(ep1.id, "/path/ep1.mp3", 1000, "hash1")

        ep2 = repository.create_episode(
            podcast_id=sample_podcast.id,
            guid="episode-2",
            title="Newer Episode",
            enclosure_url="https://example.com/episode2.mp3",
            enclosure_type="audio/mpeg",
            published_date=datetime(2024, 6, 1, tzinfo=UTC),
        )
        repository.mark_download_complete(ep2.id, "/path/ep2.mp3", 1000, "hash2")

        # Should get newer episode first
        next_ep = repository.get_next_for_transcription()
        assert next_ep is not None
        assert next_ep.id == ep2.id

    def test_get_next_for_transcription_none_available(self, repository):
        """Test getting next episode when none available."""
        next_ep = repository.get_next_for_transcription()
        assert next_ep is None

    def test_get_next_pending_post_processing_metadata(self, repository, sample_podcast):
        """Test getting next episode for metadata extraction."""
        episode = repository.create_episode(
            podcast_id=sample_podcast.id,
            guid="episode-1",
            title="Episode 1",
            enclosure_url="https://example.com/episode1.mp3",
            enclosure_type="audio/mpeg",
        )
        repository.mark_transcript_complete(episode.id, transcript_text="Transcript")

        next_ep = repository.get_next_pending_post_processing()
        assert next_ep is not None
        assert next_ep.id == episode.id

    def test_get_next_pending_post_processing_indexing(self, repository, sample_podcast):
        """Test getting next episode for indexing."""
        episode = repository.create_episode(
            podcast_id=sample_podcast.id,
            guid="episode-1",
            title="Episode 1",
            enclosure_url="https://example.com/episode1.mp3",
            enclosure_type="audio/mpeg",
        )
        repository.mark_transcript_complete(episode.id, transcript_text="Transcript")
        repository.mark_metadata_complete(episode.id, summary="Summary")

        next_ep = repository.get_next_pending_post_processing()
        assert next_ep is not None
        assert next_ep.id == episode.id

    def test_get_next_pending_post_processing_none(self, repository):
        """Test getting next episode when none need post-processing."""
        next_ep = repository.get_next_pending_post_processing()
        assert next_ep is None

    def test_increment_retry_count(self, repository, sample_podcast):
        """Test incrementing retry counts for different stages."""
        episode = repository.create_episode(
            podcast_id=sample_podcast.id,
            guid="episode-1",
            title="Episode 1",
            enclosure_url="https://example.com/episode1.mp3",
            enclosure_type="audio/mpeg",
        )

        # Test transcript retry
        count = repository.increment_retry_count(episode.id, "transcript")
        assert count == 1
        count = repository.increment_retry_count(episode.id, "transcript")
        assert count == 2

        # Test metadata retry
        count = repository.increment_retry_count(episode.id, "metadata")
        assert count == 1

        # Test indexing retry
        count = repository.increment_retry_count(episode.id, "indexing")
        assert count == 1

    def test_increment_retry_count_invalid_stage(self, repository, sample_podcast):
        """Test increment_retry_count with invalid stage."""
        episode = repository.create_episode(
            podcast_id=sample_podcast.id,
            guid="episode-1",
            title="Episode 1",
            enclosure_url="https://example.com/episode1.mp3",
            enclosure_type="audio/mpeg",
        )

        with pytest.raises(ValueError, match="Invalid stage"):
            repository.increment_retry_count(episode.id, "invalid")

    def test_increment_retry_count_nonexistent_episode(self, repository):
        """Test increment_retry_count for nonexistent episode."""
        with pytest.raises(ValueError, match="Episode not found"):
            repository.increment_retry_count("nonexistent", "transcript")

    def test_mark_permanently_failed(self, repository, sample_podcast):
        """Test marking episode as permanently failed."""
        episode = repository.create_episode(
            podcast_id=sample_podcast.id,
            guid="episode-1",
            title="Episode 1",
            enclosure_url="https://example.com/episode1.mp3",
            enclosure_type="audio/mpeg",
        )

        repository.mark_permanently_failed(episode.id, "transcript", "Max retries exceeded")
        episode = repository.get_episode(episode.id)
        assert episode.transcript_status == "permanently_failed"
        assert episode.transcript_error == "Max retries exceeded"

    def test_mark_permanently_failed_metadata(self, repository, sample_podcast):
        """Test marking episode as permanently failed for metadata."""
        episode = repository.create_episode(
            podcast_id=sample_podcast.id,
            guid="episode-1",
            title="Episode 1",
            enclosure_url="https://example.com/episode1.mp3",
            enclosure_type="audio/mpeg",
        )

        repository.mark_permanently_failed(episode.id, "metadata", "API error")
        episode = repository.get_episode(episode.id)
        assert episode.metadata_status == "permanently_failed"

    def test_mark_permanently_failed_indexing(self, repository, sample_podcast):
        """Test marking episode as permanently failed for indexing."""
        episode = repository.create_episode(
            podcast_id=sample_podcast.id,
            guid="episode-1",
            title="Episode 1",
            enclosure_url="https://example.com/episode1.mp3",
            enclosure_type="audio/mpeg",
        )

        repository.mark_permanently_failed(episode.id, "indexing", "Upload failed")
        episode = repository.get_episode(episode.id)
        assert episode.file_search_status == "permanently_failed"

    def test_mark_permanently_failed_invalid_stage(self, repository, sample_podcast):
        """Test mark_permanently_failed with invalid stage."""
        episode = repository.create_episode(
            podcast_id=sample_podcast.id,
            guid="episode-1",
            title="Episode 1",
            enclosure_url="https://example.com/episode1.mp3",
            enclosure_type="audio/mpeg",
        )

        with pytest.raises(ValueError, match="Invalid stage"):
            repository.mark_permanently_failed(episode.id, "invalid", "Error")

    def test_reset_episode_for_retry(self, repository, sample_podcast):
        """Test resetting episode status for retry."""
        episode = repository.create_episode(
            podcast_id=sample_podcast.id,
            guid="episode-1",
            title="Episode 1",
            enclosure_url="https://example.com/episode1.mp3",
            enclosure_type="audio/mpeg",
        )

        # Mark as failed first
        repository.mark_transcript_failed(episode.id, "Some error")
        episode = repository.get_episode(episode.id)
        assert episode.transcript_status == "failed"

        # Reset for retry
        repository.reset_episode_for_retry(episode.id, "transcript")
        episode = repository.get_episode(episode.id)
        assert episode.transcript_status == "pending"
        assert episode.transcript_error is None

    def test_reset_episode_for_retry_download(self, repository, sample_podcast):
        """Test resetting download status for retry."""
        episode = repository.create_episode(
            podcast_id=sample_podcast.id,
            guid="episode-1",
            title="Episode 1",
            enclosure_url="https://example.com/episode1.mp3",
            enclosure_type="audio/mpeg",
        )

        repository.mark_download_failed(episode.id, "Download error")
        repository.reset_episode_for_retry(episode.id, "download")
        episode = repository.get_episode(episode.id)
        assert episode.download_status == "pending"

    def test_reset_episode_for_retry_invalid_stage(self, repository, sample_podcast):
        """Test reset_episode_for_retry with invalid stage."""
        episode = repository.create_episode(
            podcast_id=sample_podcast.id,
            guid="episode-1",
            title="Episode 1",
            enclosure_url="https://example.com/episode1.mp3",
            enclosure_type="audio/mpeg",
        )

        with pytest.raises(ValueError, match="Invalid stage"):
            repository.reset_episode_for_retry(episode.id, "invalid")


class TestUserOperations:
    """Tests for user CRUD operations."""

    def test_create_user(self, repository):
        """Test creating a user."""
        user = repository.create_user(
            google_id="google123",
            email="test@example.com",
            name="Test User",
            picture_url="https://example.com/pic.jpg",
        )

        assert user.id is not None
        assert user.google_id == "google123"
        assert user.email == "test@example.com"
        assert user.name == "Test User"
        assert user.picture_url == "https://example.com/pic.jpg"

    def test_create_user_duplicate_returns_existing(self, repository):
        """Test creating duplicate user returns existing."""
        user1 = repository.create_user(
            google_id="google123",
            email="test@example.com",
        )
        user2 = repository.create_user(
            google_id="google123",
            email="test@example.com",
        )

        assert user1.id == user2.id

    def test_get_user(self, repository):
        """Test getting a user by ID."""
        user = repository.create_user(
            google_id="google123",
            email="test@example.com",
        )

        retrieved = repository.get_user(user.id)
        assert retrieved is not None
        assert retrieved.id == user.id

    def test_get_user_nonexistent(self, repository):
        """Test getting nonexistent user returns None."""
        retrieved = repository.get_user("nonexistent")
        assert retrieved is None

    def test_get_user_by_google_id(self, repository):
        """Test getting user by Google ID."""
        user = repository.create_user(
            google_id="google123",
            email="test@example.com",
        )

        retrieved = repository.get_user_by_google_id("google123")
        assert retrieved is not None
        assert retrieved.id == user.id

    def test_get_user_by_google_id_not_found(self, repository):
        """Test getting user by nonexistent Google ID."""
        retrieved = repository.get_user_by_google_id("nonexistent")
        assert retrieved is None

    def test_get_user_by_email(self, repository):
        """Test getting user by email."""
        user = repository.create_user(
            google_id="google123",
            email="test@example.com",
        )

        retrieved = repository.get_user_by_email("test@example.com")
        assert retrieved is not None
        assert retrieved.id == user.id

    def test_get_user_by_email_not_found(self, repository):
        """Test getting user by nonexistent email."""
        retrieved = repository.get_user_by_email("nonexistent@example.com")
        assert retrieved is None

    def test_update_user(self, repository):
        """Test updating a user."""
        user = repository.create_user(
            google_id="google123",
            email="test@example.com",
            name="Original Name",
        )

        updated = repository.update_user(user.id, name="Updated Name")
        assert updated is not None
        assert updated.name == "Updated Name"

    def test_update_user_nonexistent(self, repository):
        """Test updating nonexistent user returns None."""
        updated = repository.update_user("nonexistent", name="New Name")
        assert updated is None

    def test_list_users(self, repository):
        """Test listing users."""
        repository.create_user(google_id="google1", email="user1@example.com")
        repository.create_user(google_id="google2", email="user2@example.com")
        repository.create_user(google_id="google3", email="user3@example.com")

        users = repository.list_users()
        assert len(users) == 3

    def test_list_users_with_limit(self, repository):
        """Test listing users with limit."""
        for i in range(5):
            repository.create_user(google_id=f"google{i}", email=f"user{i}@example.com")

        users = repository.list_users(limit=3)
        assert len(users) == 3

    def test_list_users_filter_admin(self, repository):
        """Test listing only admin users."""
        user1 = repository.create_user(google_id="google1", email="user1@example.com")
        repository.create_user(google_id="google2", email="user2@example.com")

        repository.set_user_admin_status(user1.id, True)

        admins = repository.list_users(is_admin=True)
        assert len(admins) == 1
        assert admins[0].id == user1.id

    def test_list_users_filter_active(self, repository):
        """Test listing active users."""
        user1 = repository.create_user(google_id="google1", email="user1@example.com")
        user2 = repository.create_user(google_id="google2", email="user2@example.com")

        repository.update_user(user2.id, is_active=False)

        active_users = repository.list_users(is_active=True)
        assert len(active_users) == 1
        assert active_users[0].id == user1.id

    def test_list_users_with_offset(self, repository):
        """Test listing users with offset."""
        for i in range(5):
            repository.create_user(google_id=f"google{i}", email=f"user{i}@example.com")

        users = repository.list_users(offset=2, limit=2)
        assert len(users) == 2

    def test_set_user_admin_status(self, repository):
        """Test setting user admin status."""
        user = repository.create_user(google_id="google1", email="user@example.com")
        assert user.is_admin is False

        updated = repository.set_user_admin_status(user.id, True)
        assert updated.is_admin is True

        updated = repository.set_user_admin_status(user.id, False)
        assert updated.is_admin is False

    def test_get_user_count(self, repository):
        """Test getting user count."""
        for i in range(3):
            repository.create_user(google_id=f"google{i}", email=f"user{i}@example.com")

        count = repository.get_user_count()
        assert count == 3

    def test_get_user_count_admin_filter(self, repository):
        """Test getting admin user count."""
        user1 = repository.create_user(google_id="google1", email="user1@example.com")
        repository.create_user(google_id="google2", email="user2@example.com")

        repository.set_user_admin_status(user1.id, True)

        admin_count = repository.get_user_count(is_admin=True)
        assert admin_count == 1

        non_admin_count = repository.get_user_count(is_admin=False)
        assert non_admin_count == 1


class TestSubscriptionOperations:
    """Tests for user subscription operations."""

    @pytest.fixture
    def user(self, repository):
        """Create a test user."""
        return repository.create_user(
            google_id="google123",
            email="test@example.com",
        )

    def test_subscribe_user_to_podcast(self, repository, sample_podcast, user):
        """Test subscribing user to podcast."""
        subscription = repository.subscribe_user_to_podcast(user.id, sample_podcast.id)

        assert subscription is not None
        assert subscription.user_id == user.id
        assert subscription.podcast_id == sample_podcast.id

    def test_subscribe_user_already_subscribed(self, repository, sample_podcast, user):
        """Test subscribing when already subscribed returns existing."""
        sub1 = repository.subscribe_user_to_podcast(user.id, sample_podcast.id)
        sub2 = repository.subscribe_user_to_podcast(user.id, sample_podcast.id)

        assert sub1.id == sub2.id

    def test_unsubscribe_user_from_podcast(self, repository, sample_podcast, user):
        """Test unsubscribing user from podcast."""
        repository.subscribe_user_to_podcast(user.id, sample_podcast.id)

        result = repository.unsubscribe_user_from_podcast(user.id, sample_podcast.id)
        assert result is True

        # Verify unsubscribed
        is_subscribed = repository.is_user_subscribed(user.id, sample_podcast.id)
        assert is_subscribed is False

    def test_unsubscribe_user_not_subscribed(self, repository, sample_podcast, user):
        """Test unsubscribing when not subscribed returns False."""
        result = repository.unsubscribe_user_from_podcast(user.id, sample_podcast.id)
        assert result is False

    def test_is_user_subscribed(self, repository, sample_podcast, user):
        """Test checking if user is subscribed."""
        assert repository.is_user_subscribed(user.id, sample_podcast.id) is False

        repository.subscribe_user_to_podcast(user.id, sample_podcast.id)

        assert repository.is_user_subscribed(user.id, sample_podcast.id) is True

    def test_get_user_subscriptions(self, repository, user):
        """Test getting user subscriptions."""
        podcast1 = repository.create_podcast(
            feed_url="https://example.com/feed1.xml",
            title="Podcast 1",
        )
        podcast2 = repository.create_podcast(
            feed_url="https://example.com/feed2.xml",
            title="Podcast 2",
        )

        repository.subscribe_user_to_podcast(user.id, podcast1.id)
        repository.subscribe_user_to_podcast(user.id, podcast2.id)

        subscriptions = repository.get_user_subscriptions(user.id)
        assert len(subscriptions) == 2

    def test_get_user_subscriptions_sorted_alphabetical(self, repository, user):
        """Test getting user subscriptions sorted alphabetically."""
        podcast1 = repository.create_podcast(
            feed_url="https://example.com/feed1.xml",
            title="Zebra Podcast",
        )
        podcast2 = repository.create_podcast(
            feed_url="https://example.com/feed2.xml",
            title="Alpha Podcast",
        )

        repository.subscribe_user_to_podcast(user.id, podcast1.id)
        repository.subscribe_user_to_podcast(user.id, podcast2.id)

        subscriptions = repository.get_user_subscriptions(user.id, sort_by="alphabetical", sort_order="asc")
        assert len(subscriptions) == 2
        assert subscriptions[0].title == "Alpha Podcast"
        assert subscriptions[1].title == "Zebra Podcast"

    def test_list_podcasts_for_user(self, repository, user):
        """Test listing podcasts for user."""
        podcast1 = repository.create_podcast(
            feed_url="https://example.com/feed1.xml",
            title="Podcast 1",
        )
        podcast2 = repository.create_podcast(
            feed_url="https://example.com/feed2.xml",
            title="Podcast 2",
        )

        repository.subscribe_user_to_podcast(user.id, podcast1.id)
        repository.subscribe_user_to_podcast(user.id, podcast2.id)

        podcasts = repository.list_podcasts_for_user(user.id)
        assert len(podcasts) == 2

    def test_list_podcasts_for_user_with_limit(self, repository, user):
        """Test listing podcasts for user with limit."""
        for i in range(5):
            podcast = repository.create_podcast(
                feed_url=f"https://example.com/feed{i}.xml",
                title=f"Podcast {i}",
            )
            repository.subscribe_user_to_podcast(user.id, podcast.id)

        podcasts = repository.list_podcasts_for_user(user.id, limit=3)
        assert len(podcasts) == 3


class TestEmailDigestOperations:
    """Tests for email digest operations."""

    @pytest.fixture
    def user_with_digest(self, repository):
        """Create a user with email digest enabled."""
        user = repository.create_user(
            google_id="google123",
            email="test@example.com",
        )
        return repository.update_user(user.id, email_digest_enabled=True)

    def test_get_users_for_email_digest(self, repository, user_with_digest):
        """Test getting users eligible for email digest."""
        users = repository.get_users_for_email_digest()
        assert len(users) == 1
        assert users[0].id == user_with_digest.id

    def test_get_users_for_email_digest_inactive_excluded(self, repository):
        """Test that inactive users are excluded."""
        user = repository.create_user(
            google_id="google123",
            email="test@example.com",
        )
        repository.update_user(user.id, email_digest_enabled=True, is_active=False)

        users = repository.get_users_for_email_digest()
        assert len(users) == 0

    def test_get_users_for_email_digest_disabled_excluded(self, repository):
        """Test that users with digest disabled are excluded."""
        repository.create_user(
            google_id="google123",
            email="test@example.com",
        )
        # email_digest_enabled defaults to False

        users = repository.get_users_for_email_digest()
        assert len(users) == 0

    def test_mark_email_digest_sent(self, repository, user_with_digest):
        """Test marking email digest as sent."""
        repository.mark_email_digest_sent(user_with_digest.id)

        user = repository.get_user(user_with_digest.id)
        assert user.last_email_digest_sent is not None

    def test_get_new_episodes_for_user_since(self, repository, sample_podcast):
        """Test getting new episodes for user since a date."""
        from datetime import datetime, timedelta, UTC

        user = repository.create_user(google_id="google123", email="test@example.com")
        repository.subscribe_user_to_podcast(user.id, sample_podcast.id)

        # Create an episode with metadata
        episode = repository.create_episode(
            podcast_id=sample_podcast.id,
            guid="episode-1",
            title="Episode 1",
            enclosure_url="https://example.com/episode1.mp3",
            enclosure_type="audio/mpeg",
            published_date=datetime.now(UTC),
        )
        repository.mark_metadata_complete(episode.id, summary="Episode summary")

        since = datetime.now(UTC) - timedelta(hours=1)
        episodes = repository.get_new_episodes_for_user_since(user.id, since)
        assert len(episodes) == 1

    def test_get_recent_processed_episodes(self, repository, sample_podcast):
        """Test getting recent processed episodes."""
        episode = repository.create_episode(
            podcast_id=sample_podcast.id,
            guid="episode-1",
            title="Episode 1",
            enclosure_url="https://example.com/episode1.mp3",
            enclosure_type="audio/mpeg",
        )
        repository.mark_metadata_complete(episode.id, summary="Episode summary")

        episodes = repository.get_recent_processed_episodes(limit=5)
        assert len(episodes) == 1
        assert episodes[0].id == episode.id


class TestConversationOperations:
    """Tests for conversation and chat message operations."""

    @pytest.fixture
    def user(self, repository):
        """Create a test user."""
        return repository.create_user(
            google_id="google123",
            email="test@example.com",
        )

    def test_create_conversation(self, repository, user):
        """Test creating a conversation."""
        conversation = repository.create_conversation(
            user_id=user.id,
            scope="global",
            title="Test Conversation",
        )

        assert conversation.id is not None
        assert conversation.user_id == user.id
        assert conversation.scope == "global"
        assert conversation.title == "Test Conversation"

    def test_create_conversation_with_podcast(self, repository, user, sample_podcast):
        """Test creating a conversation scoped to a podcast."""
        conversation = repository.create_conversation(
            user_id=user.id,
            scope="podcast",
            podcast_id=sample_podcast.id,
        )

        assert conversation.podcast_id == sample_podcast.id

    def test_get_conversation(self, repository, user):
        """Test getting a conversation by ID."""
        conversation = repository.create_conversation(
            user_id=user.id,
            scope="global",
        )

        retrieved = repository.get_conversation(conversation.id)
        assert retrieved is not None
        assert retrieved.id == conversation.id

    def test_get_conversation_nonexistent(self, repository):
        """Test getting nonexistent conversation returns None."""
        retrieved = repository.get_conversation("nonexistent")
        assert retrieved is None

    def test_list_conversations(self, repository, user):
        """Test listing conversations for a user."""
        for i in range(3):
            repository.create_conversation(
                user_id=user.id,
                scope="global",
                title=f"Conversation {i}",
            )

        conversations = repository.list_conversations(user.id)
        assert len(conversations) == 3

    def test_list_conversations_with_limit(self, repository, user):
        """Test listing conversations with limit and offset."""
        for i in range(5):
            repository.create_conversation(
                user_id=user.id,
                scope="global",
                title=f"Conversation {i}",
            )

        conversations = repository.list_conversations(user.id, limit=2, offset=1)
        assert len(conversations) == 2

    def test_update_conversation(self, repository, user):
        """Test updating a conversation."""
        conversation = repository.create_conversation(
            user_id=user.id,
            scope="global",
            title="Original Title",
        )

        updated = repository.update_conversation(conversation.id, title="Updated Title")
        assert updated is not None
        assert updated.title == "Updated Title"

    def test_update_conversation_nonexistent(self, repository):
        """Test updating nonexistent conversation returns None."""
        updated = repository.update_conversation("nonexistent", title="New Title")
        assert updated is None

    def test_delete_conversation(self, repository, user):
        """Test deleting a conversation."""
        conversation = repository.create_conversation(
            user_id=user.id,
            scope="global",
        )

        result = repository.delete_conversation(conversation.id)
        assert result is True

        retrieved = repository.get_conversation(conversation.id)
        assert retrieved is None

    def test_delete_conversation_nonexistent(self, repository):
        """Test deleting nonexistent conversation returns False."""
        result = repository.delete_conversation("nonexistent")
        assert result is False

    def test_add_message(self, repository, user):
        """Test adding a message to a conversation."""
        conversation = repository.create_conversation(
            user_id=user.id,
            scope="global",
        )

        message = repository.add_message(
            conversation_id=conversation.id,
            role="user",
            content="Hello, world!",
        )

        assert message.id is not None
        assert message.role == "user"
        assert message.content == "Hello, world!"

    def test_add_message_with_citations(self, repository, user):
        """Test adding a message with citations."""
        conversation = repository.create_conversation(
            user_id=user.id,
            scope="global",
        )

        citations = [{"source": "Episode 1", "text": "Quote"}]
        message = repository.add_message(
            conversation_id=conversation.id,
            role="assistant",
            content="Response with citation",
            citations=citations,
        )

        assert message.citations == citations

    def test_add_message_updates_conversation(self, repository, user):
        """Test that adding a message updates conversation timestamp and count."""
        conversation = repository.create_conversation(
            user_id=user.id,
            scope="global",
        )
        original_updated_at = conversation.updated_at

        import time
        time.sleep(0.1)

        repository.add_message(
            conversation_id=conversation.id,
            role="user",
            content="Test message",
        )

        updated_conversation = repository.get_conversation(conversation.id)
        assert updated_conversation.message_count == 1
        assert updated_conversation.updated_at > original_updated_at

    def test_get_messages(self, repository, user):
        """Test getting messages for a conversation."""
        conversation = repository.create_conversation(
            user_id=user.id,
            scope="global",
        )

        for i in range(3):
            repository.add_message(
                conversation_id=conversation.id,
                role="user" if i % 2 == 0 else "assistant",
                content=f"Message {i}",
            )

        messages = repository.get_messages(conversation.id)
        assert len(messages) == 3

    def test_get_messages_with_limit(self, repository, user):
        """Test getting messages with limit and offset."""
        conversation = repository.create_conversation(
            user_id=user.id,
            scope="global",
        )

        for i in range(5):
            repository.add_message(
                conversation_id=conversation.id,
                role="user",
                content=f"Message {i}",
            )

        messages = repository.get_messages(conversation.id, limit=2, offset=1)
        assert len(messages) == 2

    def test_count_conversations(self, repository, user):
        """Test counting conversations for a user."""
        for i in range(3):
            repository.create_conversation(
                user_id=user.id,
                scope="global",
            )

        count = repository.count_conversations(user.id)
        assert count == 3

    def test_count_conversations_empty(self, repository, user):
        """Test counting conversations when user has none."""
        count = repository.count_conversations(user.id)
        assert count == 0
