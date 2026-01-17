"""CLI commands for podcast management.

Provides commands for:
- Importing OPML files
- Adding podcasts from feed URLs
- Adding YouTube channels
- Syncing feeds
- Downloading episodes
- Viewing status and statistics
"""

import argparse
import asyncio
import logging
import sys

from ..config import Config
from ..db.factory import create_repository
from ..podcast.downloader import EpisodeDownloader
from ..podcast.feed_sync import FeedSyncService
from ..podcast.opml_parser import OPMLParser, import_opml_to_repository
from ..workflow.config import PipelineConfig
from ..workflow.orchestrator import PipelineOrchestrator

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def import_opml(args, config: Config):
    """
    Import podcasts defined in an OPML file into the repository.

    Parses the OPML file specified by args.file, shows the discovered feeds, and imports them into the database unless args.dry_run is true. When importing, existing feed handling is controlled by args.update_existing (if false, existing feeds are skipped). Prints import statistics and ensures the repository is closed on completion.

    Parameters:
        args: CLI arguments with at least the attributes:
            - file (str): Path to the OPML file to import.
            - dry_run (bool): If true, show feeds that would be imported without modifying the database.
            - update_existing (bool): If true, update existing feeds; otherwise skip them.
        config (Config): Application configuration providing database connection settings used to create the repository.
    """
    logger.info(f"Importing OPML file: {args.file}")

    repository = create_repository(
        database_url=config.DATABASE_URL,
        pool_size=config.DB_POOL_SIZE,
        max_overflow=config.DB_MAX_OVERFLOW,
        echo=config.DB_ECHO,
    )

    try:
        # First, parse and show what we'll import
        parser = OPMLParser()
        result = parser.parse_file(args.file)

        print(f"\nFound {len(result.feeds)} podcast feeds in OPML file")
        if result.title:
            print(f"OPML Title: {result.title}")

        if args.dry_run:
            print("\n[DRY RUN] Would import the following feeds:")
            for feed in result.feeds:
                print(f"  - {feed.title or 'Unknown'}: {feed.feed_url}")
            return

        # Import to database
        stats = import_opml_to_repository(
            opml_path=args.file,
            repository=repository,
            skip_existing=not args.update_existing,
        )

        print("\nImport complete:")
        print(f"  Added: {stats['added']}")
        print(f"  Skipped: {stats['skipped']}")
        print(f"  Failed: {stats['failed']}")

    finally:
        repository.close()


def add_podcast(args, config: Config):
    """
    Add a podcast to the repository using the feed URL provided in args.

    If the feed cannot be added the function prints the error and exits the process with status 1. On success it prints the podcast title, ID, and number of episodes. The repository is closed before returning.

    Parameters:
        args: Parsed CLI arguments; expects `args.url` to contain the feed URL to add.
        config (Config): Application configuration used to construct the repository and determine the download directory.
    """
    logger.info(f"Adding podcast from: {args.url}")

    repository = create_repository(
        database_url=config.DATABASE_URL,
        pool_size=config.DB_POOL_SIZE,
        max_overflow=config.DB_MAX_OVERFLOW,
        echo=config.DB_ECHO,
    )

    try:
        sync_service = FeedSyncService(
            repository=repository,
            download_directory=config.PODCAST_DOWNLOAD_DIRECTORY,
        )

        result = sync_service.add_podcast_from_url(args.url)

        if result["error"]:
            print(f"Error: {result['error']}")
            sys.exit(1)

        print(f"\nAdded podcast: {result['title']}")
        print(f"  ID: {result['podcast_id']}")
        print(f"  Episodes: {result['episodes']}")

    finally:
        repository.close()


def add_youtube(args, config: Config):
    """Add a YouTube channel to the repository.

    Parameters:
        args: Parsed CLI arguments with:
            - url: YouTube channel URL or handle (e.g., @mkbhd)
            - max_videos: Maximum videos to sync on add (optional)
        config: Application configuration.
    """
    if not config.YOUTUBE_API_KEY:
        print("Error: YOUTUBE_API_KEY not configured")
        print("Please set YOUTUBE_API_KEY in your environment or Doppler config")
        sys.exit(1)

    logger.info(f"Adding YouTube channel: {args.url}")

    repository = create_repository(
        database_url=config.DATABASE_URL,
        pool_size=config.DB_POOL_SIZE,
        max_overflow=config.DB_MAX_OVERFLOW,
        echo=config.DB_ECHO,
    )

    try:
        from ..youtube.api_client import YouTubeAPIClient
        from ..youtube.channel_sync import YouTubeChannelSyncService

        api_client = YouTubeAPIClient(api_key=config.YOUTUBE_API_KEY)
        sync_service = YouTubeChannelSyncService(
            repository=repository,
            api_client=api_client,
            download_directory=config.PODCAST_DOWNLOAD_DIRECTORY,
            default_max_videos=config.YOUTUBE_DEFAULT_MAX_VIDEOS,
        )

        max_videos = args.max_videos or config.YOUTUBE_DEFAULT_MAX_VIDEOS
        result = sync_service.add_channel_from_url(args.url, max_videos=max_videos)

        if result["error"]:
            print(f"Error: {result['error']}")
            sys.exit(1)

        print(f"\nAdded YouTube channel: {result['title']}")
        print(f"  ID: {result['podcast_id']}")
        print(f"  Videos synced: {result['videos']}")

    finally:
        repository.close()


def sync_feeds(args, config: Config):
    """Sync podcast feeds to get new episodes."""
    repository = create_repository(
        database_url=config.DATABASE_URL,
        pool_size=config.DB_POOL_SIZE,
        max_overflow=config.DB_MAX_OVERFLOW,
        echo=config.DB_ECHO,
    )

    try:
        sync_service = FeedSyncService(
            repository=repository,
            download_directory=config.PODCAST_DOWNLOAD_DIRECTORY,
        )

        if args.podcast_id:
            logger.info(f"Syncing podcast: {args.podcast_id}")
            result = sync_service.sync_podcast(args.podcast_id)

            if result["error"]:
                print(f"Error: {result['error']}")
                sys.exit(1)

            print("\nSync complete:")
            print(f"  New episodes: {result['new_episodes']}")
            print(f"  Updated: {result['updated']}")
        else:
            logger.info("Syncing all podcasts")
            result = sync_service.sync_all_podcasts()

            print("\nSync complete:")
            print(f"  Podcasts synced: {result['synced']}")
            print(f"  Podcasts failed: {result['failed']}")
            print(f"  New episodes: {result['new_episodes']}")

    finally:
        repository.close()


def download_episodes(args, config: Config):
    """
    Download pending podcast episodes according to CLI options and configuration.

    Performs episode downloads using the repository and EpisodeDownloader, prints a summary of downloaded and failed items, and lists up to the first 10 failures.

    Parameters:
        args: Parsed command-line arguments with relevant attributes:
            - limit (int | None): maximum number of episodes to download (defaults to 50 when not set).
            - concurrent (int | None): maximum concurrent downloads override (falls back to config when not set).
            - async_mode (bool): whether to run downloads using the downloader's async path.
        config (Config): Application configuration providing database and download settings used to create the repository and downloader.
    """
    repository = create_repository(
        database_url=config.DATABASE_URL,
        pool_size=config.DB_POOL_SIZE,
        max_overflow=config.DB_MAX_OVERFLOW,
        echo=config.DB_ECHO,
    )

    downloader = None
    try:
        downloader = EpisodeDownloader(
            repository=repository,
            download_directory=config.PODCAST_DOWNLOAD_DIRECTORY,
            max_concurrent=args.concurrent or config.PODCAST_MAX_CONCURRENT_DOWNLOADS,
            retry_attempts=config.PODCAST_DOWNLOAD_RETRY_ATTEMPTS,
            timeout=config.PODCAST_DOWNLOAD_TIMEOUT,
            chunk_size=config.PODCAST_CHUNK_SIZE,
        )

        limit = args.limit or 50

        if args.async_mode:
            logger.info(f"Downloading up to {limit} episodes (async mode)")
            result = asyncio.run(downloader.download_pending_async(limit=limit))
        else:
            logger.info(f"Downloading up to {limit} episodes")
            result = downloader.download_pending(limit=limit)

        print("\nDownload complete:")
        print(f"  Downloaded: {result['downloaded']}")
        print(f"  Failed: {result['failed']}")

        # Show failures
        failures = [r for r in result["results"] if not r.success]
        if failures:
            print("\nFailed downloads:")
            for f in failures[:10]:  # Show first 10
                print(f"  - {f.episode_id}: {f.error}")

    finally:
        if downloader:
            downloader.close()
        repository.close()


def list_podcasts(args, config: Config):
    """
    Prints a table of podcasts to stdout.

    Displays podcasts from the repository as rows containing ID, title (truncated to 40 characters),
    episode count, subscriber count, and source type. When `args.all` is false, only shows podcasts
    with subscribers.

    Parameters:
        args: argparse.Namespace with at least:
            - all (bool): If true, include all podcasts; otherwise only podcasts with subscribers.
            - source (str | None): Filter by source type ("rss", "youtube", or None for all).
            - limit (int | None): Maximum number of podcasts to retrieve; when None, no limit is applied.
    """
    repository = create_repository(
        database_url=config.DATABASE_URL,
        pool_size=config.DB_POOL_SIZE,
        max_overflow=config.DB_MAX_OVERFLOW,
        echo=config.DB_ECHO,
    )

    try:
        # Normalize source filter
        source_type = None
        if hasattr(args, 'source') and args.source and args.source != 'all':
            source_type = args.source

        if args.all:
            podcasts = repository.list_podcasts(limit=args.limit)
            # Manual filter by source type for list_podcasts
            if source_type:
                podcasts = [p for p in podcasts if p.source_type == source_type]
        else:
            podcasts = repository.list_podcasts_with_subscribers(
                limit=args.limit, source_type=source_type
            )

        if not podcasts:
            print("No podcasts found")
            return

        # Get subscriber counts for all podcasts in one query
        podcast_ids = [p.id for p in podcasts]
        subscriber_counts = repository.get_podcast_subscriber_counts(podcast_ids)

        print(f"\n{'ID':<36}  {'Title':<40}  {'Type':<8}  {'Episodes':<10}  {'Subscribers'}")
        print("-" * 115)

        for podcast in podcasts:
            # Get episode count
            episodes = repository.list_episodes(podcast_id=podcast.id)
            sub_count = subscriber_counts.get(podcast.id, 0)
            source_label = "YouTube" if podcast.source_type == "youtube" else "RSS"
            print(
                f"{podcast.id:<36}  "
                f"{podcast.title[:40]:<40}  "
                f"{source_label:<8}  "
                f"{len(episodes):<10}  "
                f"{sub_count}"
            )

    finally:
        repository.close()


def show_status(args, config: Config):
    """
    Display overall statistics or detailed status for a specific podcast to stdout.

    Parameters:
        args: Parsed command-line arguments. If `args.podcast_id` is provided, the command prints detailed stats for that podcast; otherwise it prints aggregated overall statistics.
        config (Config): Application configuration used to create the repository and read database connection settings.

    Notes:
        Exits with status code 1 if a specified `podcast_id` is not found.
    """
    repository = create_repository(
        database_url=config.DATABASE_URL,
        pool_size=config.DB_POOL_SIZE,
        max_overflow=config.DB_MAX_OVERFLOW,
        echo=config.DB_ECHO,
    )

    try:
        if args.podcast_id:
            stats = repository.get_podcast_stats(args.podcast_id)
            if not stats:
                print(f"Podcast not found: {args.podcast_id}")
                sys.exit(1)

            print(f"\nPodcast: {stats['title']}")
            print(f"  Total episodes: {stats['total_episodes']}")
            print("\n  Download Status:")
            print(f"    Pending: {stats['pending_download']}")
            print(f"    Downloading: {stats['downloading']}")
            print(f"    Completed: {stats['downloaded']}")
            print(f"    Failed: {stats['download_failed']}")
            print("\n  Processing Status:")
            print(f"    Pending transcription: {stats['pending_transcription']}")
            print(f"    Transcribed: {stats['transcribed']}")
            print(f"    Indexed: {stats['indexed']}")
            print(f"    Fully processed: {stats['fully_processed']}")
        else:
            stats = repository.get_overall_stats()

            print("\nOverall Statistics:")
            print(f"  Total podcasts: {stats['total_podcasts']}")
            print(f"  Subscribed: {stats['subscribed_podcasts']}")
            print(f"  Total episodes: {stats['total_episodes']}")
            print("\n  Download Status:")
            print(f"    Pending: {stats['pending_download']}")
            print(f"    Downloading: {stats['downloading']}")
            print(f"    Completed: {stats['downloaded']}")
            print(f"    Failed: {stats['download_failed']}")
            print("\n  Transcription Status:")
            print(f"    Pending: {stats['pending_transcription']}")
            print(f"    Processing: {stats['transcribing']}")
            print(f"    Completed: {stats['transcribed']}")
            print(f"    Failed: {stats['transcript_failed']}")
            print("\n  Indexing Status:")
            print(f"    Pending: {stats['pending_indexing']}")
            print(f"    Indexed: {stats['indexed']}")
            print(f"\n  Fully processed: {stats['fully_processed']}")

    finally:
        repository.close()


def cleanup_audio(args, config: Config):
    """
    Remove downloaded audio files for episodes that are fully processed.

    If `args.dry_run` is true, print a summary and list up to 20 episodes (from the queried limit) that would be deleted without modifying files. Otherwise, delete up to `args.limit` processed-episode audio files (default 100) and print the number of files cleaned.
    """
    repository = create_repository(
        database_url=config.DATABASE_URL,
        pool_size=config.DB_POOL_SIZE,
        max_overflow=config.DB_MAX_OVERFLOW,
        echo=config.DB_ECHO,
    )

    downloader = None
    try:
        if args.dry_run:
            episodes = repository.get_episodes_ready_for_cleanup(limit=args.limit or 100)
            print(f"\n[DRY RUN] Would delete audio for {len(episodes)} episodes:")
            for ep in episodes[:20]:
                print(f"  - {ep.title}: {ep.local_file_path}")
            return

        downloader = EpisodeDownloader(
            repository=repository,
            download_directory=config.PODCAST_DOWNLOAD_DIRECTORY,
            max_concurrent=1,  # Not used for cleanup
        )

        deleted = downloader.cleanup_processed_episodes(limit=args.limit or 100)
        print(f"\nCleaned up {deleted} audio files")

    finally:
        if downloader:
            downloader.close()
        repository.close()


def run_pipeline(args, config: Config):
    """Run the pipeline-oriented orchestrator.

    Optimized for continuous GPU utilization during transcription.
    Runs until interrupted with Ctrl+C.

    Parameters:
        args: Parsed CLI arguments (currently unused but kept for consistency).
        config (Config): Application configuration.
    """
    repository = create_repository(
        database_url=config.DATABASE_URL,
        pool_size=config.DB_POOL_SIZE,
        max_overflow=config.DB_MAX_OVERFLOW,
        echo=config.DB_ECHO,
    )

    try:
        pipeline_config = PipelineConfig.from_env()
        orchestrator = PipelineOrchestrator(
            config=config,
            pipeline_config=pipeline_config,
            repository=repository,
        )

        print("Starting pipeline orchestrator...")
        print(f"  Sync interval: {pipeline_config.sync_interval_seconds}s")
        print(f"  Download buffer: {pipeline_config.download_buffer_size} episodes")
        print(f"  Post-processing workers: {pipeline_config.post_processing_workers}")
        print(f"  Max retries: {pipeline_config.max_retries}")
        print("\nPress Ctrl+C to stop\n")

        stats = orchestrator.run()

        print("\nPipeline stopped.")
        print(f"  Transcribed: {stats.episodes_transcribed}")
        print(f"  Transcription failures: {stats.transcription_failures}")
        print(f"  Duration: {stats.duration_seconds:.1f}s")

        if stats.post_processing:
            print("\n  Post-processing:")
            print(
                f"    Metadata: {stats.post_processing.metadata_processed} processed, "
                f"{stats.post_processing.metadata_failed} failed"
            )
            print(
                f"    Indexing: {stats.post_processing.indexing_processed} processed, "
                f"{stats.post_processing.indexing_failed} failed"
            )
            print(
                f"    Cleanup: {stats.post_processing.cleanup_processed} processed, "
                f"{stats.post_processing.cleanup_failed} failed"
            )

    finally:
        repository.close()


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser."""
    parser = argparse.ArgumentParser(
        description="Podcast management CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--env-file",
        help="Path to .env file",
        default=None,
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # import-opml command
    import_parser = subparsers.add_parser(
        "import-opml",
        help="Import podcasts from an OPML file",
    )
    import_parser.add_argument("file", help="Path to OPML file")
    import_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be imported without making changes",
    )
    import_parser.add_argument(
        "--update-existing",
        action="store_true",
        help="Update existing podcasts instead of skipping",
    )

    # add command
    add_parser = subparsers.add_parser(
        "add",
        help="Add a podcast from feed URL",
    )
    add_parser.add_argument("url", help="RSS feed URL")

    # add-youtube command
    add_youtube_parser = subparsers.add_parser(
        "add-youtube",
        help="Add a YouTube channel",
    )
    add_youtube_parser.add_argument(
        "url",
        help="YouTube channel URL or handle (e.g., @mkbhd, https://youtube.com/@mkbhd)",
    )
    add_youtube_parser.add_argument(
        "--max-videos",
        type=int,
        help="Maximum number of videos to sync (default: from config)",
    )

    # sync command
    sync_parser = subparsers.add_parser(
        "sync",
        help="Sync podcast feeds",
    )
    sync_parser.add_argument(
        "--podcast-id",
        help="Sync specific podcast by ID",
    )

    # download command
    download_parser = subparsers.add_parser(
        "download",
        help="Download pending episodes",
    )
    download_parser.add_argument(
        "--limit",
        type=int,
        help="Maximum number of episodes to download",
    )
    download_parser.add_argument(
        "--concurrent",
        type=int,
        help="Number of concurrent downloads",
    )
    download_parser.add_argument(
        "--async",
        dest="async_mode",
        action="store_true",
        help="Use async download mode",
    )

    # list command
    list_parser = subparsers.add_parser(
        "list",
        help="List podcasts",
    )
    list_parser.add_argument(
        "--all",
        action="store_true",
        help="Include all podcasts (default: only podcasts with subscribers)",
    )
    list_parser.add_argument(
        "--source",
        choices=["rss", "youtube", "all"],
        default="all",
        help="Filter by source type (default: all)",
    )
    list_parser.add_argument(
        "--limit",
        type=int,
        help="Maximum number of podcasts to show",
    )

    # status command
    status_parser = subparsers.add_parser(
        "status",
        help="Show status and statistics",
    )
    status_parser.add_argument(
        "--podcast-id",
        help="Show status for specific podcast",
    )

    # cleanup command
    cleanup_parser = subparsers.add_parser(
        "cleanup",
        help="Clean up audio files for processed episodes",
    )
    cleanup_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be deleted without making changes",
    )
    cleanup_parser.add_argument(
        "--limit",
        type=int,
        help="Maximum number of files to clean up",
    )

    # pipeline command (optimized for continuous GPU utilization)
    subparsers.add_parser(
        "pipeline",
        help="Run the pipeline orchestrator (optimized for continuous GPU utilization)",
    )

    return parser


def main():
    """Main entry point for the CLI."""
    parser = create_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Load configuration
    config = Config(env_file=args.env_file)

    # Route to appropriate command
    commands = {
        "import-opml": import_opml,
        "add": add_podcast,
        "add-youtube": add_youtube,
        "sync": sync_feeds,
        "download": download_episodes,
        "list": list_podcasts,
        "status": show_status,
        "cleanup": cleanup_audio,
        "pipeline": run_pipeline,
    }

    command_func = commands.get(args.command)
    if command_func:
        command_func(args, config)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
