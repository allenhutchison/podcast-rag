#!/usr/bin/env python
import logging
import argparse
from datetime import datetime

from src.argparse_shared import (add_dry_run_argument, add_log_level_argument, 
                          get_base_parser)
from src.config import Config
from src.db import DatabaseManager


def setup_argparse():
    """Set up the argument parser"""
    parser = get_base_parser()
    parser.description = "List all podcast feeds in the database"
    add_log_level_argument(parser)
    
    # Add feed-specific arguments
    parser.add_argument('--language', help='Filter feeds by language code (e.g. en)')
    parser.add_argument('--has-image', action='store_true', help='Show only feeds with images')
    
    return parser.parse_args()


def list_feeds(config: Config, args):
    """List all feeds in the database"""
    db = DatabaseManager(config)
    
    try:
        feeds = db.get_all_feeds()
        
        # Apply filters
        if args.language:
            feeds = [f for f in feeds if f.language == args.language]
        if args.has_image:
            feeds = [f for f in feeds if f.image_url]
            
        if not feeds:
            print("No feeds found matching the criteria.")
            return
            
        # Print header
        print("\nPodcast Feeds:")
        print("-" * 100)
        print(f"{'ID':<5} {'Title':<40} {'Language':<10} {'Last Updated':<20} {'Has Image':<10}")
        print("-" * 100)
        
        # Print each feed
        for feed in feeds:
            has_image = "Yes" if feed.image_url else "No"
            last_updated = feed.last_updated.strftime("%Y-%m-%d %H:%M")
            print(f"{feed.id:<5} {feed.title[:37]+'...':<40} {feed.language or 'N/A':<10} {last_updated:<20} {has_image:<10}")
            
        print("-" * 100)
        print(f"\nTotal feeds: {len(feeds)}")
        
    finally:
        db.close()


def main():
    """Main function to list podcast feeds"""
    args = setup_argparse()
    
    # Configure logging
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), "INFO"),
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler()]
    )
    
    # Load configuration
    config = Config(env_file=args.env_file)
    
    # List feeds
    list_feeds(config, args)


if __name__ == "__main__":
    main() 