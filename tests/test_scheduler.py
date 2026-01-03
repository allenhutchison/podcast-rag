"""Tests for scheduler module."""

import pytest
from unittest.mock import Mock, patch, MagicMock

from src.scheduler import run_pipeline
from src.workflow.orchestrator import PipelineStats
from src.workflow.post_processor import PostProcessingStats


class TestRunPipeline:
    """Tests for run_pipeline function."""

    @pytest.fixture
    def mock_config(self):
        """Create a mock config."""
        config = Mock()
        config.DATABASE_URL = "sqlite:///:memory:"
        config.PODCAST_DOWNLOAD_DIRECTORY = "/tmp/podcasts"
        config.GEMINI_API_KEY = "test_key"
        return config

    @pytest.fixture
    def mock_pipeline_config(self):
        """Create a mock pipeline config."""
        config = Mock()
        config.sync_interval_seconds = 900
        config.download_buffer_size = 10
        config.post_processing_workers = 2
        return config

    @pytest.fixture
    def mock_repository(self):
        """Create a mock repository."""
        return Mock()

    def test_run_pipeline_calls_orchestrator(
        self, mock_config, mock_pipeline_config, mock_repository
    ):
        """Test that run_pipeline creates and runs the orchestrator."""
        mock_stats = PipelineStats()
        mock_stats.episodes_transcribed = 5
        mock_stats.transcription_failures = 1
        mock_stats.stopped_at = mock_stats.started_at

        with patch(
            "src.scheduler.PipelineOrchestrator"
        ) as mock_orchestrator_class:
            mock_orchestrator = Mock()
            mock_orchestrator.run.return_value = mock_stats
            mock_orchestrator_class.return_value = mock_orchestrator

            run_pipeline(mock_config, mock_pipeline_config, mock_repository)

            mock_orchestrator_class.assert_called_once_with(
                config=mock_config,
                pipeline_config=mock_pipeline_config,
                repository=mock_repository,
            )
            mock_orchestrator.run.assert_called_once()

    def test_run_pipeline_logs_stats(
        self, mock_config, mock_pipeline_config, mock_repository, caplog
    ):
        """Test that run_pipeline logs the statistics."""
        mock_stats = PipelineStats()
        mock_stats.episodes_transcribed = 10
        mock_stats.transcription_failures = 2
        mock_stats.stopped_at = mock_stats.started_at

        with patch(
            "src.scheduler.PipelineOrchestrator"
        ) as mock_orchestrator_class:
            mock_orchestrator = Mock()
            mock_orchestrator.run.return_value = mock_stats
            mock_orchestrator_class.return_value = mock_orchestrator

            import logging
            with caplog.at_level(logging.INFO):
                run_pipeline(mock_config, mock_pipeline_config, mock_repository)

            assert "10 transcribed" in caplog.text
            assert "2 failed" in caplog.text

    def test_run_pipeline_with_post_processing_stats(
        self, mock_config, mock_pipeline_config, mock_repository, caplog
    ):
        """Test that run_pipeline logs post-processing stats when available."""
        mock_stats = PipelineStats()
        mock_stats.episodes_transcribed = 5
        mock_stats.transcription_failures = 0
        mock_stats.stopped_at = mock_stats.started_at

        # Add post-processing stats
        post_stats = PostProcessingStats()
        post_stats.metadata_processed = 5
        post_stats.metadata_failed = 1
        post_stats.indexing_processed = 4
        post_stats.indexing_failed = 0
        post_stats.cleanup_processed = 3
        post_stats.cleanup_failed = 0
        mock_stats.post_processing = post_stats

        with patch(
            "src.scheduler.PipelineOrchestrator"
        ) as mock_orchestrator_class:
            mock_orchestrator = Mock()
            mock_orchestrator.run.return_value = mock_stats
            mock_orchestrator_class.return_value = mock_orchestrator

            import logging
            with caplog.at_level(logging.INFO):
                run_pipeline(mock_config, mock_pipeline_config, mock_repository)

            assert "metadata=5/1" in caplog.text
            assert "indexing=4/0" in caplog.text
            assert "cleanup=3/0" in caplog.text

    def test_run_pipeline_without_post_processing(
        self, mock_config, mock_pipeline_config, mock_repository, caplog
    ):
        """Test run_pipeline when there are no post-processing stats."""
        mock_stats = PipelineStats()
        mock_stats.episodes_transcribed = 3
        mock_stats.transcription_failures = 0
        mock_stats.stopped_at = mock_stats.started_at
        mock_stats.post_processing = None

        with patch(
            "src.scheduler.PipelineOrchestrator"
        ) as mock_orchestrator_class:
            mock_orchestrator = Mock()
            mock_orchestrator.run.return_value = mock_stats
            mock_orchestrator_class.return_value = mock_orchestrator

            import logging
            with caplog.at_level(logging.INFO):
                run_pipeline(mock_config, mock_pipeline_config, mock_repository)

            # Should not have post-processing log line
            assert "metadata=" not in caplog.text
