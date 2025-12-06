"""CLI commands for podcast management.

Provides commands for:
- Importing OPML files
- Adding podcasts from feed URLs
- Syncing feeds
- Downloading episodes
- Viewing status and statistics
"""

import argparse
import asyncio
import logging
import sys
from typing import Optional

from ..config import Config
from ..db.factory import create_repository
from ..podcast.downloader import EpisodeDownloader
from ..podcast.feed_sync import FeedSyncService
from ..podcast.opml_parser import OPMLParser, import_opml_to_repository

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

        print(f"\nImport complete:")
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

            print(f"\nSync complete:")
            print(f"  New episodes: {result['new_episodes']}")
            print(f"  Updated: {result['updated']}")
        else:
            logger.info("Syncing all podcasts")
            result = sync_service.sync_all_podcasts()

            print(f"\nSync complete:")
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

        print(f"\nDownload complete:")
        print(f"  Downloaded: {result['downloaded']}")
        print(f"  Failed: {result['failed']}")

        # Show failures
        failures = [r for r in result["results"] if not r.success]
        if failures:
            print(f"\nFailed downloads:")
            for f in failures[:10]:  # Show first 10
                print(f"  - {f.episode_id}: {f.error}")

    finally:
        if downloader:
            downloader.close()
        repository.close()


def list_podcasts(args, config: Config):
    """
    Prints a table of podcasts to stdout.
    
    Displays podcasts from the repository as rows containing ID, title (truncated to 40 characters), episode count, and subscription status. Honors the following fields on `args`: `all` (when true, include unsubscribed podcasts) and `limit` (maximum number of podcasts to list).
    
    Parameters:
        args: argparse.Namespace with at least:
            - all (bool): If true, include unsubscribed podcasts; otherwise only subscribed podcasts.
            - limit (int | None): Maximum number of podcasts to retrieve; when None, the repository default is used.
    """
    repository = create_repository(
        database_url=config.DATABASE_URL,
        pool_size=config.DB_POOL_SIZE,
        max_overflow=config.DB_MAX_OVERFLOW,
        echo=config.DB_ECHO,
    )

    try:
        podcasts = repository.list_podcasts(
            subscribed_only=not args.all,
            limit=args.limit,
        )

        if not podcasts:
            print("No podcasts found")
            return

        print(f"\n{'ID':<36}  {'Title':<40}  {'Episodes':<10}  {'Status'}")
        print("-" * 100)

        for podcast in podcasts:
            # Get episode count
            episodes = repository.list_episodes(podcast_id=podcast.id)
            status = "Subscribed" if podcast.is_subscribed else "Unsubscribed"
            print(
                f"{podcast.id:<36}  "
                f"{podcast.title[:40]:<40}  "
                f"{len(episodes):<10}  "
                f"{status}"
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
            print(f"\n  Download Status:")
            print(f"    Pending: {stats['pending_download']}")
            print(f"    Downloading: {stats['downloading']}")
            print(f"    Completed: {stats['downloaded']}")
            print(f"    Failed: {stats['download_failed']}")
            print(f"\n  Processing Status:")
            print(f"    Pending transcription: {stats['pending_transcription']}")
            print(f"    Transcribed: {stats['transcribed']}")
            print(f"    Indexed: {stats['indexed']}")
            print(f"    Fully processed: {stats['fully_processed']}")
        else:
            stats = repository.get_overall_stats()

            print(f"\nOverall Statistics:")
            print(f"  Total podcasts: {stats['total_podcasts']}")
            print(f"  Subscribed: {stats['subscribed_podcasts']}")
            print(f"  Total episodes: {stats['total_episodes']}")
            print(f"\n  Download Status:")
            print(f"    Pending: {stats['pending_download']}")
            print(f"    Downloading: {stats['downloading']}")
            print(f"    Completed: {stats['downloaded']}")
            print(f"    Failed: {stats['download_failed']}")
            print(f"\n  Transcription Status:")
            print(f"    Pending: {stats['pending_transcription']}")
            print(f"    Processing: {stats['transcribing']}")
            print(f"    Completed: {stats['transcribed']}")
            print(f"    Failed: {stats['transcript_failed']}")
            print(f"\n  Indexing Status:")
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
        help="Include unsubscribed podcasts",
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
        "sync": sync_feeds,
        "download": download_episodes,
        "list": list_podcasts,
        "status": show_status,
        "cleanup": cleanup_audio,
    }

    command_func = commands.get(args.command)
    if command_func:
        command_func(args, config)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()