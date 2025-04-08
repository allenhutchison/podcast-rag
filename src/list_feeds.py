#!/usr/bin/env python
import logging
import argparse
from tabulate import tabulate

from argparse_shared import add_log_level_argument, get_base_parser
from config import Config
from db import DatabaseManager


def setup_argparse():
    """Set up the argument parser"""
    parser = get_base_parser()
    parser.description = "List all podcast feeds in the database"
    add_log_level_argument(parser)
    
    return parser.parse_args()


def list_feeds(config: Config):
    """List all feeds in the database"""
    db = DatabaseManager(config)
    
    try:
        feeds = db.get_all_feeds()
        
        if not feeds:
            print("No feeds found in the database.")
            return
            
        # Prepare data for tabulate
        table_data = []
        for feed in feeds:
            table_data.append([
                feed.id,
                feed.title,
                feed.url,
                feed.last_updated.strftime("%Y-%m-%d %H:%M:%S"),
                feed.language or "N/A",
                "Yes" if feed.image_url else "No"
            ])
            
        # Print table
        headers = ["ID", "Title", "URL", "Last Updated", "Language", "Has Image"]
        print(tabulate(table_data, headers=headers, tablefmt="grid"))
        print(f"\nTotal feeds: {len(feeds)}")
        
    finally:
        db.close()


def main():
    """Main function to list feeds"""
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
    list_feeds(config)


if __name__ == "__main__":
    main() 