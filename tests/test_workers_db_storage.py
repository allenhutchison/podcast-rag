"""Tests for worker database storage functionality.

Tests the changes to transcription, metadata, and indexing workers
to use database storage instead of file-based storage.
"""

import os
import pytest
from unittest.mock import Mock, MagicMock, patch, call
from pathlib import Path

from src.db.factory import create_repository
from src.db.models import Episode
from src.workflow.workers.base import WorkerResult


@pytest.fixture
def repository(tmp_path):
    """Create a temporary SQLite-backed repository for tests."""
    db_path = tmp_path / "test.db"
    repo = create_repository(f"sqlite:///{db_path}", create_tables=True)
    yield repo
    repo.close()


@pytest.fixture
def mock_config():
    """Create a mock config for testing."""
    config = Mock()
    config.DATABASE_URL = "sqlite:///:memory:"
    config.PODCAST_DOWNLOAD_DIRECTORY = "/tmp/podcasts"
    config.TRANSCRIPTION_OUTPUT_SUFFIX = "_transcription.txt"
    config.GEMINI_API_KEY = "test_key"
    config.GEMINI_MODEL = "gemini-2.5-flash"
    config.GEMINI_CORPUS_ID = "test-corpus"
    return config


@pytest.fixture
def sample_podcast(repository):
    """Create a sample podcast for testing."""
    return repository.create_podcast(
        feed_url="https://example.com/feed.xml",
        title="Test Podcast",
        description="A test podcast",
    )


@pytest.fixture
def sample_episode_with_audio(repository, sample_podcast, tmp_path):
    """Create a sample episode with audio file."""
    # Create a mock audio file
    audio_file = tmp_path / "episode.mp3"
    audio_file.write_bytes(b"fake audio data")
    
    episode = repository.create_episode(
        podcast_id=sample_podcast.id,
        guid="test-episode",
        title="Test Episode",
        enclosure_url="https://example.com/episode.mp3",
        enclosure_type="audio/mpeg",
    )
    repository.mark_download_complete(
        episode.id,
        str(audio_file),
        len(b"fake audio data"),
        "abc123"
    )
    return episode


class TestTranscriptionWorkerDatabaseStorage:
    """Tests for TranscriptionWorker database storage."""

    def test_transcribe_stores_text_in_database(
        self, mock_config, repository, sample_episode_with_audio
    ):
        """Test that transcription stores text directly in database."""
        from src.workflow.workers.transcription import TranscriptionWorker

        worker = TranscriptionWorker(config=mock_config, repository=repository)
        
        # Mock the Whisper model
        mock_model = MagicMock()
        mock_segment = MagicMock()
        mock_segment.text = "Test transcript segment."
        mock_model.transcribe.return_value = ([mock_segment], None)
        worker._model = mock_model

        # Transcribe the episode
        transcript_text = worker._transcribe_episode(sample_episode_with_audio)

        # Verify transcript text is returned
        assert transcript_text == "Test transcript segment."
        assert isinstance(transcript_text, str)

    def test_transcribe_single_updates_database(
        self, mock_config, repository, sample_episode_with_audio
    ):
        """Test that transcribe_single updates database with text."""
        from src.workflow.workers.transcription import TranscriptionWorker

        worker = TranscriptionWorker(config=mock_config, repository=repository)
        
        # Mock the transcription
        mock_model = MagicMock()
        mock_segment = MagicMock()
        mock_segment.text = "Full transcript text."
        mock_model.transcribe.return_value = ([mock_segment], None)
        worker._model = mock_model

        # Transcribe
        result = worker.transcribe_single(sample_episode_with_audio)

        # Verify result is text
        assert result == "Full transcript text."
        
        # Verify database was updated
        episode = repository.get_episode(sample_episode_with_audio.id)
        assert episode.transcript_status == "completed"
        assert episode.transcript_text == "Full transcript text."
        assert episode.transcribed_at is not None

    def test_transcribe_handles_existing_transcript_text(
        self, mock_config, repository, sample_episode_with_audio
    ):
        """Test that existing transcript text is returned without re-transcription."""
        from src.workflow.workers.transcription import TranscriptionWorker

        # Set existing transcript text
        existing_text = "Already transcribed content"
        repository.mark_transcript_complete(
            sample_episode_with_audio.id,
            transcript_text=existing_text,
        )

        worker = TranscriptionWorker(config=mock_config, repository=repository)
        
        # Mock should not be called
        mock_model = MagicMock()
        worker._model = mock_model

        # Try to transcribe
        result = worker._transcribe_episode(sample_episode_with_audio)

        # Should return existing text without calling model
        assert result == existing_text
        mock_model.transcribe.assert_not_called()

    def test_transcribe_handles_legacy_file(
        self, mock_config, repository, sample_episode_with_audio, tmp_path
    ):
        """Test handling of existing legacy transcript file."""
        from src.workflow.workers.transcription import TranscriptionWorker

        # Create legacy transcript file
        transcript_file = tmp_path / "episode_transcription.txt"
        legacy_text = "Legacy transcript from file"
        transcript_file.write_text(legacy_text, encoding="utf-8")

        # Update episode with transcript_path
        repository.update_episode(
            sample_episode_with_audio.id,
            transcript_path=str(transcript_file),
            transcript_status="completed",
        )

        worker = TranscriptionWorker(config=mock_config, repository=repository)
        mock_model = MagicMock()
        worker._model = mock_model

        # Try to transcribe - should read from file
        result = worker._transcribe_episode(sample_episode_with_audio)

        # Should return file content
        assert result == legacy_text
        mock_model.transcribe.assert_not_called()

    def test_process_batch_stores_all_transcripts(
        self, mock_config, repository, sample_podcast, tmp_path
    ):
        """Test that batch processing stores all transcripts in database."""
        from src.workflow.workers.transcription import TranscriptionWorker

        # Create multiple episodes with audio files
        episodes = []
        for i in range(3):
            audio_file = tmp_path / f"episode_{i}.mp3"
            audio_file.write_bytes(b"fake audio")
            
            episode = repository.create_episode(
                podcast_id=sample_podcast.id,
                guid=f"episode-{i}",
                title=f"Episode {i}",
                enclosure_url=f"https://example.com/episode{i}.mp3",
                enclosure_type="audio/mpeg",
            )
            repository.mark_download_complete(
                episode.id, str(audio_file), len(b"fake audio"), f"hash{i}"
            )
            episodes.append(episode)

        worker = TranscriptionWorker(config=mock_config, repository=repository)
        
        # Mock transcription
        mock_model = MagicMock()
        def mock_transcribe(audio_path, *args, **kwargs):
            idx = int(Path(audio_path).stem.split('_')[1])
            mock_segment = MagicMock()
            mock_segment.text = f"Transcript {idx}"
            return ([mock_segment], None)
        
        mock_model.transcribe.side_effect = mock_transcribe
        worker._model = mock_model

        # Process batch
        result = worker.process_batch(limit=10)

        assert result.processed == 3
        assert result.failed == 0

        # Verify all transcripts stored in database
        for i, episode in enumerate(episodes):
            updated = repository.get_episode(episode.id)
            assert updated.transcript_text == f"Transcript {i}"
            assert updated.transcript_status == "completed"

    def test_transcribe_handles_unicode(
        self, mock_config, repository, sample_episode_with_audio
    ):
        """Test handling Unicode characters in transcript."""
        from src.workflow.workers.transcription import TranscriptionWorker

        worker = TranscriptionWorker(config=mock_config, repository=repository)
        
        # Mock with Unicode content
        mock_model = MagicMock()
        mock_segment = MagicMock()
        mock_segment.text = "Transcript avec émojis 🎙️ et caractères spéciaux"
        mock_model.transcribe.return_value = ([mock_segment], None)
        worker._model = mock_model

        # Transcribe
        result = worker.transcribe_single(sample_episode_with_audio)

        # Verify Unicode preserved
        assert "émojis 🎙️" in result
        
        episode = repository.get_episode(sample_episode_with_audio.id)
        assert "émojis 🎙️" in episode.transcript_text


class TestMetadataWorkerDatabaseStorage:
    """Tests for MetadataWorker database storage."""

    def test_process_episode_uses_database_transcript(
        self, mock_config, repository, sample_podcast
    ):
        """Test that metadata worker reads transcript from database."""
        from src.workflow.workers.metadata import MetadataWorker

        episode = repository.create_episode(
            podcast_id=sample_podcast.id,
            guid="episode-1",
            title="Episode 1",
            enclosure_url="https://example.com/episode.mp3",
            enclosure_type="audio/mpeg",
        )
        
        # Store transcript in database
        transcript_text = "This is the transcript for metadata extraction."
        repository.mark_transcript_complete(
            episode.id,
            transcript_text=transcript_text,
        )

        worker = MetadataWorker(config=mock_config, repository=repository)
        
        # Mock AI extraction
        with patch.object(worker, '_extract_ai_metadata') as mock_extract:
            mock_extract.return_value = {
                "summary": "Test summary",
                "keywords": ["test"],
                "hosts": [],
                "guests": [],
            }
            
            # Process episode
            merged = worker._process_episode(episode)

        # Verify AI extraction was called with database transcript
        mock_extract.assert_called_once()
        call_args = mock_extract.call_args[0]
        assert call_args[0] == transcript_text

    def test_process_episode_reads_legacy_transcript_file(
        self, mock_config, repository, sample_podcast, tmp_path
    ):
        """Test that metadata worker can still read legacy transcript files."""
        from src.workflow.workers.metadata import MetadataWorker

        episode = repository.create_episode(
            podcast_id=sample_podcast.id,
            guid="episode-1",
            title="Episode 1",
            enclosure_url="https://example.com/episode.mp3",
            enclosure_type="audio/mpeg",
        )
        
        # Create legacy transcript file
        transcript_file = tmp_path / "transcript.txt"
        legacy_text = "Legacy transcript from file."
        transcript_file.write_text(legacy_text, encoding="utf-8")
        
        repository.update_episode(
            episode.id,
            transcript_path=str(transcript_file),
            transcript_status="completed",
        )

        worker = MetadataWorker(config=mock_config, repository=repository)
        
        # Mock AI extraction
        with patch.object(worker, '_extract_ai_metadata') as mock_extract:
            mock_extract.return_value = {
                "summary": "Test summary",
                "keywords": [],
                "hosts": [],
                "guests": [],
            }
            
            # Process episode
            merged = worker._process_episode(episode)

        # Verify legacy file content was used
        call_args = mock_extract.call_args[0]
        assert call_args[0] == legacy_text

    def test_process_episode_stores_mp3_metadata(
        self, mock_config, repository, sample_podcast, tmp_path
    ):
        """Test that MP3 metadata is stored in database."""
        from src.workflow.workers.metadata import MetadataWorker

        # Create episode with audio file
        audio_file = tmp_path / "episode.mp3"
        audio_file.write_bytes(b"fake audio")
        
        episode = repository.create_episode(
            podcast_id=sample_podcast.id,
            guid="episode-1",
            title="Episode 1",
            enclosure_url="https://example.com/episode.mp3",
            enclosure_type="audio/mpeg",
        )
        repository.mark_download_complete(
            episode.id, str(audio_file), len(b"fake audio"), "hash"
        )
        repository.mark_transcript_complete(
            episode.id,
            transcript_text="Transcript content",
        )

        worker = MetadataWorker(config=mock_config, repository=repository)
        
        # Mock MP3 tag reading
        with patch.object(worker, '_read_mp3_tags') as mock_read_tags:
            mock_read_tags.return_value = {
                "artist": "Test Artist",
                "album": "Test Album",
            }
            
            with patch.object(worker, '_extract_ai_metadata') as mock_extract:
                mock_extract.return_value = {
                    "summary": "Summary",
                    "keywords": ["test"],
                    "hosts": [],
                    "guests": [],
                }
                
                # Process episode
                merged = worker._process_episode(episode)

        # Verify MP3 metadata in merged result
        assert merged.mp3_artist == "Test Artist"
        assert merged.mp3_album == "Test Album"

    def test_process_episode_raises_on_missing_transcript(
        self, mock_config, repository, sample_podcast
    ):
        """Test that processing fails gracefully without transcript."""
        from src.workflow.workers.metadata import MetadataWorker

        episode = repository.create_episode(
            podcast_id=sample_podcast.id,
            guid="episode-1",
            title="Episode 1",
            enclosure_url="https://example.com/episode.mp3",
            enclosure_type="audio/mpeg",
        )
        
        # No transcript set

        worker = MetadataWorker(config=mock_config, repository=repository)
        
        # Should raise ValueError
        with pytest.raises(ValueError, match="no transcript content"):
            worker._process_episode(episode)

    def test_process_batch_stores_all_metadata(
        self, mock_config, repository, sample_podcast
    ):
        """Test that batch processing stores all metadata in database."""
        from src.workflow.workers.metadata import MetadataWorker

        # Create episodes with transcripts
        for i in range(3):
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

        worker = MetadataWorker(config=mock_config, repository=repository)
        
        # Mock AI extraction
        with patch.object(worker, '_extract_ai_metadata') as mock_extract:
            def side_effect(transcript, filename):
                idx = transcript.split()[-1]
                return {
                    "summary": f"Summary {idx}",
                    "keywords": [f"keyword{idx}"],
                    "hosts": [],
                    "guests": [],
                }
            mock_extract.side_effect = side_effect
            
            # Process batch
            result = worker.process_batch(limit=10)

        assert result.processed == 3
        assert result.failed == 0

        # Verify all metadata stored
        for i in range(3):
            episodes = repository.list_episodes(podcast_id=sample_podcast.id)
            episode = [e for e in episodes if e.guid == f"episode-{i}"][0]
            assert episode.metadata_status == "completed"
            assert episode.ai_summary == f"Summary {i}"


class TestIndexingWorkerDatabaseStorage:
    """Tests for IndexingWorker database storage."""

    def test_build_display_name_from_title(
        self, mock_config, repository, sample_podcast
    ):
        """Test building display name from episode title."""
        from src.workflow.workers.indexing import IndexingWorker

        episode = repository.create_episode(
            podcast_id=sample_podcast.id,
            guid="episode-1",
            title="Test Episode Title",
            enclosure_url="https://example.com/episode.mp3",
            enclosure_type="audio/mpeg",
        )
        repository.mark_transcript_complete(
            episode.id,
            transcript_text="Transcript content",
        )

        worker = IndexingWorker(config=mock_config, repository=repository)
        display_name = worker._build_display_name(episode)

        assert "Test_Episode_Title" in display_name
        assert display_name.endswith("_transcription.txt")

    def test_build_display_name_from_transcript_path(
        self, mock_config, repository, sample_podcast
    ):
        """Test building display name from legacy transcript path."""
        from src.workflow.workers.indexing import IndexingWorker

        episode = repository.create_episode(
            podcast_id=sample_podcast.id,
            guid="episode-1",
            title="Episode",
            enclosure_url="https://example.com/episode.mp3",
            enclosure_type="audio/mpeg",
        )
        repository.update_episode(
            episode.id,
            transcript_path="/path/to/episode_123_transcription.txt",
            transcript_status="completed",
        )

        worker = IndexingWorker(config=mock_config, repository=repository)
        display_name = worker._build_display_name(episode)

        assert display_name == "episode_123_transcription.txt"

    def test_index_episode_uses_database_transcript(
        self, mock_config, repository, sample_podcast
    ):
        """Test that indexing uses transcript text from database."""
        from src.workflow.workers.indexing import IndexingWorker

        episode = repository.create_episode(
            podcast_id=sample_podcast.id,
            guid="episode-1",
            title="Episode 1",
            enclosure_url="https://example.com/episode.mp3",
            enclosure_type="audio/mpeg",
        )
        
        transcript_text = "Transcript content for indexing."
        repository.mark_transcript_complete(
            episode.id,
            transcript_text=transcript_text,
        )
        repository.mark_metadata_complete(
            episode_id=episode.id,
            summary="Summary",
        )

        worker = IndexingWorker(config=mock_config, repository=repository)
        
        # Mock file search manager
        mock_manager = MagicMock()
        mock_manager.upload_transcript_text.return_value = "corpus/doc/123"
        worker.file_search_manager = mock_manager
        worker._existing_files = {}

        # Index episode
        resource_name, display_name = worker._index_episode(episode)

        # Verify upload was called with database text
        mock_manager.upload_transcript_text.assert_called_once()
        call_kwargs = mock_manager.upload_transcript_text.call_args[1]
        assert call_kwargs['text'] == transcript_text
        assert resource_name == "corpus/doc/123"

    def test_index_episode_raises_on_missing_transcript(
        self, mock_config, repository, sample_podcast
    ):
        """Test that indexing fails without transcript."""
        from src.workflow.workers.indexing import IndexingWorker

        episode = repository.create_episode(
            podcast_id=sample_podcast.id,
            guid="episode-1",
            title="Episode 1",
            enclosure_url="https://example.com/episode.mp3",
            enclosure_type="audio/mpeg",
        )
        repository.mark_metadata_complete(
            episode_id=episode.id,
            summary="Summary",
        )

        worker = IndexingWorker(config=mock_config, repository=repository)
        
        # Should raise ValueError
        with pytest.raises(ValueError, match="no transcript content"):
            worker._index_episode(episode)

    def test_process_batch_indexes_all_episodes(
        self, mock_config, repository, sample_podcast
    ):
        """Test that batch indexing processes all episodes."""
        from src.workflow.workers.indexing import IndexingWorker

        # Create episodes with transcripts and metadata
        for i in range(3):
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

        worker = IndexingWorker(config=mock_config, repository=repository)
        
        # Mock file search
        mock_manager = MagicMock()
        mock_manager.upload_transcript_text.return_value = "corpus/doc/123"
        worker.file_search_manager = mock_manager
        worker._existing_files = {}

        # Process batch
        result = worker.process_batch(limit=10)

        assert result.processed == 3
        assert result.failed == 0
        assert mock_manager.upload_transcript_text.call_count == 3

    def test_index_episode_handles_unicode(
        self, mock_config, repository, sample_podcast
    ):
        """Test indexing with Unicode transcript content."""
        from src.workflow.workers.indexing import IndexingWorker

        episode = repository.create_episode(
            podcast_id=sample_podcast.id,
            guid="episode-1",
            title="Épisode en Français",
            enclosure_url="https://example.com/episode.mp3",
            enclosure_type="audio/mpeg",
        )
        
        transcript_text = "Transcription avec caractères spéciaux: émojis 🎙️"
        repository.mark_transcript_complete(
            episode.id,
            transcript_text=transcript_text,
        )
        repository.mark_metadata_complete(
            episode_id=episode.id,
            summary="Résumé",
        )

        worker = IndexingWorker(config=mock_config, repository=repository)
        
        mock_manager = MagicMock()
        mock_manager.upload_transcript_text.return_value = "corpus/doc/123"
        worker.file_search_manager = mock_manager
        worker._existing_files = {}

        # Should handle Unicode without errors
        resource_name, display_name = worker._index_episode(episode)
        
        # Verify Unicode text was passed
        call_kwargs = mock_manager.upload_transcript_text.call_args[1]
        assert "émojis 🎙️" in call_kwargs['text']