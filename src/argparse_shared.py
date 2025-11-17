import argparse

def get_base_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Transcribe podcasts using Whisper")
    parser.add_argument("-e", "--env-file", help="Path to a custom .env file", default=None)
    return parser

def add_dry_run_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("-d", "--dry-run", action="store_true", help="Perform a dry run without making changes")

def add_log_level_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("-l", "--log-level", help="Set log level (DEBUG, INFO, WARNING, ERROR)", default="INFO")

def add_episode_path_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("-p", "--episode-path", help="Path to an MP3 file", required=True)

def add_query_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("-q", "--query", help="Query to search", required=True)

def add_sync_remote_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--sync-remote", action="store_true", help="Force sync with remote File Search store (rebuilds local cache)")

def add_skip_vectordb_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--skip-vectordb", action="store_true", help="Skip File Search indexing operations (transcription and metadata only)")