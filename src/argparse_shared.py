import argparse

def get_base_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Transcribe podcasts using Whisper")
    parser.add_argument("-e", "--env-file", help="Path to a custom .env file", default=None)
    return parser

def add_dry_run_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("-d", "--dry-run", action="store_true", help="Perform a dry run without actual operations.")

def add_log_level_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("-l", "--log-level", help="Set log level (DEBUG, INFO, WARNING, ERROR)", default="INFO")