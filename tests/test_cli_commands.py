"""Tests for CLI podcast_commands module."""

import pytest
from unittest.mock import Mock, patch, MagicMock
import sys

from src.cli.podcast_commands import (
    create_parser,
    main,
    import_opml,
    add_podcast,
    sync_feeds,
    download_episodes,
    list_podcasts,
    show_status,
    cleanup_audio,
    run_pipeline,
)


class TestCreateParser:
    """Tests for create_parser function."""

    def test_creates_argument_parser(self):
        """Test that create_parser returns an argument parser."""
        parser = create_parser()
        assert parser is not None

    def test_has_env_file_argument(self):
        """Test that parser has --env-file argument."""
        parser = create_parser()
        args = parser.parse_args(["--env-file", "/path/.env", "list"])
        assert args.env_file == "/path/.env"

    def test_import_opml_subcommand(self):
        """Test import-opml subcommand parsing."""
        parser = create_parser()
        args = parser.parse_args(["import-opml", "/path/to/file.opml", "--dry-run"])
        assert args.command == "import-opml"
        assert args.file == "/path/to/file.opml"
        assert args.dry_run is True

    def test_add_subcommand(self):
        """Test add subcommand parsing."""
        parser = create_parser()
        args = parser.parse_args(["add", "https://example.com/feed.xml"])
        assert args.command == "add"
        assert args.url == "https://example.com/feed.xml"

    def test_sync_subcommand(self):
        """Test sync subcommand parsing."""
        parser = create_parser()
        args = parser.parse_args(["sync", "--podcast-id", "123"])
        assert args.command == "sync"
        assert args.podcast_id == "123"

    def test_download_subcommand(self):
        """Test download subcommand parsing."""
        parser = create_parser()
        args = parser.parse_args(["download", "--limit", "10", "--concurrent", "5", "--async"])
        assert args.command == "download"
        assert args.limit == 10
        assert args.concurrent == 5
        assert args.async_mode is True

    def test_list_subcommand(self):
        """Test list subcommand parsing."""
        parser = create_parser()
        args = parser.parse_args(["list", "--all", "--limit", "50"])
        assert args.command == "list"
        assert args.all is True
        assert args.limit == 50

    def test_status_subcommand(self):
        """Test status subcommand parsing."""
        parser = create_parser()
        args = parser.parse_args(["status", "--podcast-id", "abc123"])
        assert args.command == "status"
        assert args.podcast_id == "abc123"

    def test_cleanup_subcommand(self):
        """Test cleanup subcommand parsing."""
        parser = create_parser()
        args = parser.parse_args(["cleanup", "--dry-run", "--limit", "200"])
        assert args.command == "cleanup"
        assert args.dry_run is True
        assert args.limit == 200

    def test_pipeline_subcommand(self):
        """Test pipeline subcommand parsing."""
        parser = create_parser()
        args = parser.parse_args(["pipeline"])
        assert args.command == "pipeline"


class TestMain:
    """Tests for main function."""

    def test_no_command_prints_help(self, capsys):
        """Test that main prints help when no command given."""
        with patch("sys.argv", ["cli"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1

    @patch("src.cli.podcast_commands.Config")
    @patch("src.cli.podcast_commands.import_opml")
    def test_routes_to_import_opml(self, mock_import, mock_config):
        """Test that main routes to import_opml command."""
        mock_config.return_value = Mock()
        with patch("sys.argv", ["cli", "import-opml", "/path/file.opml"]):
            main()
        mock_import.assert_called_once()

    @patch("src.cli.podcast_commands.Config")
    @patch("src.cli.podcast_commands.add_podcast")
    def test_routes_to_add_podcast(self, mock_add, mock_config):
        """Test that main routes to add command."""
        mock_config.return_value = Mock()
        with patch("sys.argv", ["cli", "add", "https://example.com/feed.xml"]):
            main()
        mock_add.assert_called_once()


class TestImportOpml:
    """Tests for import_opml function."""

    @pytest.fixture
    def mock_config(self):
        """Create mock config."""
        config = Mock()
        config.DATABASE_URL = "sqlite:///:memory:"
        config.DB_POOL_SIZE = 5
        config.DB_MAX_OVERFLOW = 10
        config.DB_ECHO = False
        return config

    @pytest.fixture
    def mock_args(self, tmp_path):
        """Create mock args."""
        # Create a test OPML file
        opml_file = tmp_path / "test.opml"
        opml_content = """<?xml version="1.0" encoding="UTF-8"?>
        <opml version="2.0">
            <head><title>Test OPML</title></head>
            <body>
                <outline type="rss" text="Test Podcast" xmlUrl="https://example.com/feed.xml"/>
            </body>
        </opml>"""
        opml_file.write_text(opml_content)

        args = Mock()
        args.file = str(opml_file)
        args.dry_run = False
        args.update_existing = False
        return args

    @patch("src.cli.podcast_commands.create_repository")
    @patch("src.cli.podcast_commands.import_opml_to_repository")
    def test_import_opml_success(self, mock_import, mock_create_repo, mock_config, mock_args, capsys):
        """Test successful OPML import."""
        mock_repo = Mock()
        mock_create_repo.return_value = mock_repo
        mock_import.return_value = {"added": 1, "skipped": 0, "failed": 0}

        import_opml(mock_args, mock_config)

        mock_import.assert_called_once()
        captured = capsys.readouterr()
        assert "Added: 1" in captured.out

    @patch("src.cli.podcast_commands.create_repository")
    def test_import_opml_dry_run(self, mock_create_repo, mock_config, mock_args, capsys):
        """Test OPML import dry run."""
        mock_repo = Mock()
        mock_create_repo.return_value = mock_repo
        mock_args.dry_run = True

        import_opml(mock_args, mock_config)

        captured = capsys.readouterr()
        assert "[DRY RUN]" in captured.out


class TestAddPodcast:
    """Tests for add_podcast function."""

    @pytest.fixture
    def mock_config(self):
        """Create mock config."""
        config = Mock()
        config.DATABASE_URL = "sqlite:///:memory:"
        config.DB_POOL_SIZE = 5
        config.DB_MAX_OVERFLOW = 10
        config.DB_ECHO = False
        config.PODCAST_DOWNLOAD_DIRECTORY = "/tmp/podcasts"
        return config

    @pytest.fixture
    def mock_args(self):
        """Create mock args."""
        args = Mock()
        args.url = "https://example.com/feed.xml"
        return args

    @patch("src.cli.podcast_commands.create_repository")
    @patch("src.cli.podcast_commands.FeedSyncService")
    def test_add_podcast_success(self, mock_service_class, mock_create_repo, mock_config, mock_args, capsys):
        """Test successful podcast addition."""
        mock_repo = Mock()
        mock_create_repo.return_value = mock_repo

        mock_service = Mock()
        mock_service.add_podcast_from_url.return_value = {
            "error": None,
            "title": "Test Podcast",
            "podcast_id": "123",
            "episodes": 10,
        }
        mock_service_class.return_value = mock_service

        add_podcast(mock_args, mock_config)

        captured = capsys.readouterr()
        assert "Added podcast: Test Podcast" in captured.out
        assert "ID: 123" in captured.out

    @patch("src.cli.podcast_commands.create_repository")
    @patch("src.cli.podcast_commands.FeedSyncService")
    def test_add_podcast_error(self, mock_service_class, mock_create_repo, mock_config, mock_args):
        """Test podcast addition with error."""
        mock_repo = Mock()
        mock_create_repo.return_value = mock_repo

        mock_service = Mock()
        mock_service.add_podcast_from_url.return_value = {
            "error": "Invalid feed URL",
        }
        mock_service_class.return_value = mock_service

        with pytest.raises(SystemExit) as exc_info:
            add_podcast(mock_args, mock_config)
        assert exc_info.value.code == 1


class TestSyncFeeds:
    """Tests for sync_feeds function."""

    @pytest.fixture
    def mock_config(self):
        """Create mock config."""
        config = Mock()
        config.DATABASE_URL = "sqlite:///:memory:"
        config.DB_POOL_SIZE = 5
        config.DB_MAX_OVERFLOW = 10
        config.DB_ECHO = False
        config.PODCAST_DOWNLOAD_DIRECTORY = "/tmp/podcasts"
        return config

    @patch("src.cli.podcast_commands.create_repository")
    @patch("src.cli.podcast_commands.FeedSyncService")
    def test_sync_single_podcast(self, mock_service_class, mock_create_repo, mock_config, capsys):
        """Test syncing a single podcast."""
        mock_repo = Mock()
        mock_create_repo.return_value = mock_repo

        mock_service = Mock()
        mock_service.sync_podcast.return_value = {
            "error": None,
            "new_episodes": 5,
            "updated": 2,
        }
        mock_service_class.return_value = mock_service

        args = Mock()
        args.podcast_id = "123"

        sync_feeds(args, mock_config)

        captured = capsys.readouterr()
        assert "New episodes: 5" in captured.out

    @patch("src.cli.podcast_commands.create_repository")
    @patch("src.cli.podcast_commands.FeedSyncService")
    def test_sync_all_podcasts(self, mock_service_class, mock_create_repo, mock_config, capsys):
        """Test syncing all podcasts."""
        mock_repo = Mock()
        mock_create_repo.return_value = mock_repo

        mock_service = Mock()
        mock_service.sync_all_podcasts.return_value = {
            "synced": 10,
            "failed": 1,
            "new_episodes": 25,
        }
        mock_service_class.return_value = mock_service

        args = Mock()
        args.podcast_id = None

        sync_feeds(args, mock_config)

        captured = capsys.readouterr()
        assert "Podcasts synced: 10" in captured.out
        assert "New episodes: 25" in captured.out


class TestDownloadEpisodes:
    """Tests for download_episodes function."""

    @pytest.fixture
    def mock_config(self):
        """Create mock config."""
        config = Mock()
        config.DATABASE_URL = "sqlite:///:memory:"
        config.DB_POOL_SIZE = 5
        config.DB_MAX_OVERFLOW = 10
        config.DB_ECHO = False
        config.PODCAST_DOWNLOAD_DIRECTORY = "/tmp/podcasts"
        config.PODCAST_MAX_CONCURRENT_DOWNLOADS = 5
        config.PODCAST_DOWNLOAD_RETRY_ATTEMPTS = 3
        config.PODCAST_DOWNLOAD_TIMEOUT = 300
        config.PODCAST_CHUNK_SIZE = 8192
        return config

    @patch("src.cli.podcast_commands.create_repository")
    @patch("src.cli.podcast_commands.EpisodeDownloader")
    def test_download_sync_mode(self, mock_downloader_class, mock_create_repo, mock_config, capsys):
        """Test downloading in sync mode."""
        mock_repo = Mock()
        mock_create_repo.return_value = mock_repo

        mock_downloader = Mock()
        mock_downloader.download_pending.return_value = {
            "downloaded": 5,
            "failed": 1,
            "results": [],
        }
        mock_downloader_class.return_value = mock_downloader

        args = Mock()
        args.limit = 10
        args.concurrent = None
        args.async_mode = False

        download_episodes(args, mock_config)

        captured = capsys.readouterr()
        assert "Downloaded: 5" in captured.out
        mock_downloader.download_pending.assert_called_once()

    @patch("src.cli.podcast_commands.create_repository")
    @patch("src.cli.podcast_commands.EpisodeDownloader")
    @patch("src.cli.podcast_commands.asyncio.run")
    def test_download_async_mode(self, mock_async_run, mock_downloader_class, mock_create_repo, mock_config, capsys):
        """Test downloading in async mode."""
        mock_repo = Mock()
        mock_create_repo.return_value = mock_repo

        mock_downloader = Mock()
        mock_async_run.return_value = {
            "downloaded": 3,
            "failed": 0,
            "results": [],
        }
        mock_downloader_class.return_value = mock_downloader

        args = Mock()
        args.limit = 10
        args.concurrent = None
        args.async_mode = True

        download_episodes(args, mock_config)

        captured = capsys.readouterr()
        assert "Downloaded: 3" in captured.out
        mock_async_run.assert_called_once()


class TestListPodcasts:
    """Tests for list_podcasts function."""

    @pytest.fixture
    def mock_config(self):
        """Create mock config."""
        config = Mock()
        config.DATABASE_URL = "sqlite:///:memory:"
        config.DB_POOL_SIZE = 5
        config.DB_MAX_OVERFLOW = 10
        config.DB_ECHO = False
        return config

    @patch("src.cli.podcast_commands.create_repository")
    def test_list_podcasts_empty(self, mock_create_repo, mock_config, capsys):
        """Test listing when no podcasts exist."""
        mock_repo = Mock()
        mock_repo.list_podcasts_with_subscribers.return_value = []
        mock_create_repo.return_value = mock_repo

        args = Mock()
        args.all = False
        args.limit = None

        list_podcasts(args, mock_config)

        captured = capsys.readouterr()
        assert "No podcasts found" in captured.out

    @patch("src.cli.podcast_commands.create_repository")
    def test_list_podcasts_with_data(self, mock_create_repo, mock_config, capsys):
        """Test listing podcasts with data."""
        mock_podcast = Mock()
        mock_podcast.id = "pod-123"
        mock_podcast.title = "Test Podcast"

        mock_repo = Mock()
        mock_repo.list_podcasts_with_subscribers.return_value = [mock_podcast]
        mock_repo.list_episodes.return_value = [Mock(), Mock()]  # 2 episodes
        mock_repo.get_podcast_subscriber_counts.return_value = {"pod-123": 3}
        mock_create_repo.return_value = mock_repo

        args = Mock()
        args.all = False
        args.limit = None

        list_podcasts(args, mock_config)

        captured = capsys.readouterr()
        assert "Test Podcast" in captured.out
        assert "Subscribers" in captured.out  # Column header


class TestShowStatus:
    """Tests for show_status function."""

    @pytest.fixture
    def mock_config(self):
        """Create mock config."""
        config = Mock()
        config.DATABASE_URL = "sqlite:///:memory:"
        config.DB_POOL_SIZE = 5
        config.DB_MAX_OVERFLOW = 10
        config.DB_ECHO = False
        return config

    @patch("src.cli.podcast_commands.create_repository")
    def test_show_status_overall(self, mock_create_repo, mock_config, capsys):
        """Test showing overall status."""
        mock_repo = Mock()
        mock_repo.get_overall_stats.return_value = {
            "total_podcasts": 10,
            "subscribed_podcasts": 8,
            "total_episodes": 500,
            "pending_download": 50,
            "downloading": 5,
            "downloaded": 400,
            "download_failed": 10,
            "pending_transcription": 100,
            "transcribing": 5,
            "transcribed": 350,
            "transcript_failed": 5,
            "pending_indexing": 50,
            "indexed": 300,
            "fully_processed": 295,
        }
        mock_create_repo.return_value = mock_repo

        args = Mock()
        args.podcast_id = None

        show_status(args, mock_config)

        captured = capsys.readouterr()
        assert "Total podcasts: 10" in captured.out
        assert "Subscribed: 8" in captured.out

    @patch("src.cli.podcast_commands.create_repository")
    def test_show_status_single_podcast(self, mock_create_repo, mock_config, capsys):
        """Test showing status for single podcast."""
        mock_repo = Mock()
        mock_repo.get_podcast_stats.return_value = {
            "title": "Test Podcast",
            "total_episodes": 100,
            "pending_download": 10,
            "downloading": 2,
            "downloaded": 80,
            "download_failed": 5,
            "pending_transcription": 20,
            "transcribed": 70,
            "indexed": 60,
            "fully_processed": 55,
        }
        mock_create_repo.return_value = mock_repo

        args = Mock()
        args.podcast_id = "123"

        show_status(args, mock_config)

        captured = capsys.readouterr()
        assert "Podcast: Test Podcast" in captured.out
        assert "Total episodes: 100" in captured.out

    @patch("src.cli.podcast_commands.create_repository")
    def test_show_status_podcast_not_found(self, mock_create_repo, mock_config):
        """Test showing status when podcast not found."""
        mock_repo = Mock()
        mock_repo.get_podcast_stats.return_value = None
        mock_create_repo.return_value = mock_repo

        args = Mock()
        args.podcast_id = "nonexistent"

        with pytest.raises(SystemExit) as exc_info:
            show_status(args, mock_config)
        assert exc_info.value.code == 1


class TestCleanupAudio:
    """Tests for cleanup_audio function."""

    @pytest.fixture
    def mock_config(self):
        """Create mock config."""
        config = Mock()
        config.DATABASE_URL = "sqlite:///:memory:"
        config.DB_POOL_SIZE = 5
        config.DB_MAX_OVERFLOW = 10
        config.DB_ECHO = False
        config.PODCAST_DOWNLOAD_DIRECTORY = "/tmp/podcasts"
        return config

    @patch("src.cli.podcast_commands.create_repository")
    def test_cleanup_dry_run(self, mock_create_repo, mock_config, capsys):
        """Test cleanup in dry run mode."""
        mock_episode = Mock()
        mock_episode.title = "Test Episode"
        mock_episode.local_file_path = "/tmp/episode.mp3"

        mock_repo = Mock()
        mock_repo.get_episodes_ready_for_cleanup.return_value = [mock_episode]
        mock_create_repo.return_value = mock_repo

        args = Mock()
        args.dry_run = True
        args.limit = 100

        cleanup_audio(args, mock_config)

        captured = capsys.readouterr()
        assert "[DRY RUN]" in captured.out
        assert "Test Episode" in captured.out

    @patch("src.cli.podcast_commands.create_repository")
    @patch("src.cli.podcast_commands.EpisodeDownloader")
    def test_cleanup_actual(self, mock_downloader_class, mock_create_repo, mock_config, capsys):
        """Test actual cleanup."""
        mock_repo = Mock()
        mock_create_repo.return_value = mock_repo

        mock_downloader = Mock()
        mock_downloader.cleanup_processed_episodes.return_value = 15
        mock_downloader_class.return_value = mock_downloader

        args = Mock()
        args.dry_run = False
        args.limit = 100

        cleanup_audio(args, mock_config)

        captured = capsys.readouterr()
        assert "Cleaned up 15 audio files" in captured.out


class TestRunPipeline:
    """Tests for run_pipeline function."""

    @pytest.fixture
    def mock_config(self):
        """Create mock config."""
        config = Mock()
        config.DATABASE_URL = "sqlite:///:memory:"
        config.DB_POOL_SIZE = 5
        config.DB_MAX_OVERFLOW = 10
        config.DB_ECHO = False
        return config

    @patch("src.cli.podcast_commands.create_repository")
    @patch("src.cli.podcast_commands.PipelineConfig")
    @patch("src.cli.podcast_commands.PipelineOrchestrator")
    def test_run_pipeline(self, mock_orchestrator_class, mock_pipeline_config_class, mock_create_repo, mock_config, capsys):
        """Test running the pipeline."""
        mock_repo = Mock()
        mock_create_repo.return_value = mock_repo

        mock_pipeline_config = Mock()
        mock_pipeline_config.sync_interval_seconds = 900
        mock_pipeline_config.download_buffer_size = 10
        mock_pipeline_config.post_processing_workers = 2
        mock_pipeline_config.max_retries = 3
        mock_pipeline_config_class.from_env.return_value = mock_pipeline_config

        mock_stats = Mock()
        mock_stats.episodes_transcribed = 5
        mock_stats.transcription_failures = 1
        mock_stats.duration_seconds = 120.5
        mock_stats.post_processing = None

        mock_orchestrator = Mock()
        mock_orchestrator.run.return_value = mock_stats
        mock_orchestrator_class.return_value = mock_orchestrator

        args = Mock()

        run_pipeline(args, mock_config)

        captured = capsys.readouterr()
        assert "Transcribed: 5" in captured.out
        assert "Transcription failures: 1" in captured.out

    @patch("src.cli.podcast_commands.create_repository")
    @patch("src.cli.podcast_commands.PipelineConfig")
    @patch("src.cli.podcast_commands.PipelineOrchestrator")
    def test_run_pipeline_with_post_processing(self, mock_orchestrator_class, mock_pipeline_config_class, mock_create_repo, mock_config, capsys):
        """Test running the pipeline with post-processing stats."""
        mock_repo = Mock()
        mock_create_repo.return_value = mock_repo

        mock_pipeline_config = Mock()
        mock_pipeline_config.sync_interval_seconds = 900
        mock_pipeline_config.download_buffer_size = 10
        mock_pipeline_config.post_processing_workers = 2
        mock_pipeline_config.max_retries = 3
        mock_pipeline_config_class.from_env.return_value = mock_pipeline_config

        mock_post_stats = Mock()
        mock_post_stats.metadata_processed = 5
        mock_post_stats.metadata_failed = 1
        mock_post_stats.indexing_processed = 4
        mock_post_stats.indexing_failed = 0
        mock_post_stats.cleanup_processed = 3
        mock_post_stats.cleanup_failed = 0

        mock_stats = Mock()
        mock_stats.episodes_transcribed = 5
        mock_stats.transcription_failures = 0
        mock_stats.duration_seconds = 100.0
        mock_stats.post_processing = mock_post_stats

        mock_orchestrator = Mock()
        mock_orchestrator.run.return_value = mock_stats
        mock_orchestrator_class.return_value = mock_orchestrator

        args = Mock()

        run_pipeline(args, mock_config)

        captured = capsys.readouterr()
        assert "Metadata: 5 processed" in captured.out
        assert "Indexing: 4 processed" in captured.out
