#!/usr/bin/env python
import logging
import argparse
import os
from typing import List

from src.argparse_shared import (add_dry_run_argument, add_log_level_argument,
                          get_base_parser)
from src.config import Config
from src.file_manager import FileManager
from src.podcast_downloader import PodcastDownloader
from datetime import timedelta


def setup_argparse():
    """Set up the argument parser"""
    parser = get_base_parser()
    parser.description = "Download podcasts from feeds and transcribe them"
    add_dry_run_argument(parser)
    add_log_level_argument(parser)
    
    # Add download-specific arguments
    parser.add_argument('-f', '--feed', help='RSS feed URL to download from')
    parser.add_argument('--feed-file', help='File containing a list of RSS feed URLs (one per line)')
    parser.add_argument('--limit', type=int, default=5, 
                        help='Maximum number of episodes to download per feed')
    parser.add_argument('--min-age-days', type=int, 
                        help='Only download episodes newer than this many days')
    parser.add_argument('--skip-transcription', action='store_true',
                        help='Skip transcription and only download podcasts')
    parser.add_argument('--skip-download', action='store_true',
                        help='Skip download and only transcribe existing podcasts')
    parser.add_argument('--skip-vectordb', action='store_true',
                        help='Skip vector database operations (ChromaDB)')
    
    return parser.parse_args()


def download_podcasts(config: Config, args) -> List[str]:
    """Download podcasts from specified feeds"""
    if args.skip_download:
        logging.info("Skipping podcast downloads as requested")
        return []
        
    downloader = PodcastDownloader(config=config, dry_run=args.dry_run)
    
    processed_dirs = []
    if args.feed:
        podcast_dir = downloader.process_feed(
            args.feed, 
            limit=args.limit, 
            min_age_days=args.min_age_days
        )
        if podcast_dir:
            processed_dirs.append(podcast_dir)
    elif args.feed_file:
        with open(args.feed_file, 'r') as f:
            feeds = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        processed_dirs = downloader.process_feed_list(
            feeds, 
            limit_per_feed=args.limit, 
            min_age_days=args.min_age_days
        )
    else:
        logging.warning("No feed or feed file specified, skipping download")
        
    return processed_dirs


def transcribe_podcasts(config: Config, args, podcast_dirs: List[str] = None):
    """Transcribe downloaded podcasts"""
    if args.skip_transcription:
        logging.info("Skipping transcription as requested")
        return

    file_manager = FileManager(config=config, dry_run=args.dry_run,
                              skip_vectordb=args.skip_vectordb)
    
    if podcast_dirs:
        # Transcribe specific directories that were just downloaded
        for podcast_dir in podcast_dirs:
            logging.info(f"Processing downloaded podcast directory: {podcast_dir}")
            file_manager.process_podcast(podcast_dir)
    else:
        # Process the entire base directory
        logging.info(f"Processing all podcasts in {config.BASE_DIRECTORY}")
        file_manager.process_directory()


def main():
    """Main function to download and transcribe podcasts"""
    args = setup_argparse()
    
    # Configure logging
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), "INFO"),
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler()]
    )
    
    # Load configuration
    config = Config(env_file=args.env_file)
    
    # Download podcasts if required
    podcast_dirs = download_podcasts(config, args)
    
    # Transcribe podcasts
    transcribe_podcasts(config, args, podcast_dirs)
    
    logging.info("Download and transcription process complete")


if __name__ == "__main__":
    main() 