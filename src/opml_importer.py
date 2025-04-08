#!/usr/bin/env python
import logging
import os
import xml.etree.ElementTree as ET
from typing import List, Dict, Optional
from datetime import datetime

from src.argparse_shared import (add_dry_run_argument, add_log_level_argument, 
                          get_base_parser)
from src.config import Config
from src.db import DatabaseManager, Feed


class OPMLImporter:
    def __init__(self, config: Config, dry_run=False):
        self.config = config
        self.dry_run = dry_run
        
        # Ensure database directory exists
        if not os.path.exists(config.BASE_DIRECTORY):
            os.makedirs(config.BASE_DIRECTORY, exist_ok=True)
            logging.info(f"Created base directory: {config.BASE_DIRECTORY}")
            
        self.db = DatabaseManager(config)
        self.stats = {
            "feeds_found": 0,
            "feeds_added": 0,
            "feeds_updated": 0,
            "feeds_skipped": 0,
            "import_errors": 0
        }
        
    def parse_opml(self, opml_path: str) -> List[Dict]:
        """Parse an OPML file and extract podcast feeds"""
        logging.info(f"Parsing OPML file: {opml_path}")
        
        try:
            tree = ET.parse(opml_path)
            root = tree.getroot()
            
            # Find all outline elements that represent podcast feeds
            feeds = []
            
            # OPML structure can vary, so we need to handle different formats
            # First, try to find direct feed outlines
            for outline in root.findall(".//outline[@type='rss']"):
                feed = self._extract_feed_from_outline(outline)
                if feed:
                    feeds.append(feed)
                    
            # If no direct feeds found, look for outlines with xmlUrl attribute
            if not feeds:
                for outline in root.findall(".//outline[@xmlUrl]"):
                    feed = self._extract_feed_from_outline(outline)
                    if feed:
                        feeds.append(feed)
                        
            # If still no feeds, look for any outline with a URL attribute
            if not feeds:
                for outline in root.findall(".//outline[@url]"):
                    feed = self._extract_feed_from_outline(outline)
                    if feed:
                        feeds.append(feed)
            
            self.stats["feeds_found"] = len(feeds)
            return feeds
            
        except Exception as e:
            logging.error(f"Error parsing OPML file {opml_path}: {e}")
            self.stats["import_errors"] += 1
            return []
            
    def _extract_feed_from_outline(self, outline: ET.Element) -> Optional[Dict]:
        """Extract feed information from an outline element"""
        try:
            # Try different attribute names for the feed URL
            url = outline.get('xmlUrl') or outline.get('url') or outline.get('href')
            if not url:
                return None
                
            # Get feed title
            title = outline.get('text') or outline.get('title')
            if not title:
                return None
                
            # Get optional attributes
            description = outline.get('description')
            language = outline.get('language')
            image_url = outline.get('imageUrl')
            
            return {
                'title': title,
                'url': url,
                'description': description,
                'language': language,
                'image_url': image_url
            }
            
        except Exception as e:
            logging.error(f"Error extracting feed from outline: {e}")
            return None
            
    def import_feeds(self, opml_path: str) -> int:
        """Import feeds from an OPML file into the database"""
        feeds = self.parse_opml(opml_path)
        
        if not feeds:
            logging.warning(f"No valid feeds found in {opml_path}")
            return 0
            
        imported_count = 0
        
        for feed_data in feeds:
            try:
                # Check if feed already exists
                existing_feed = self.db.get_feed_by_url(feed_data['url'])
                
                if existing_feed:
                    # Update existing feed
                    existing_feed.title = feed_data['title']
                    existing_feed.last_updated = datetime.now()
                    existing_feed.description = feed_data.get('description')
                    existing_feed.language = feed_data.get('language')
                    existing_feed.image_url = feed_data.get('image_url')
                    
                    if not self.dry_run:
                        self.db.update_feed(existing_feed)
                        logging.info(f"Updated feed: {existing_feed.title}")
                    else:
                        logging.info(f"Would update feed: {existing_feed.title}")
                        
                    self.stats["feeds_updated"] += 1
                else:
                    # Create new feed
                    new_feed = Feed(
                        id=0,  # Will be set by database
                        title=feed_data['title'],
                        url=feed_data['url'],
                        last_updated=datetime.now(),
                        description=feed_data.get('description'),
                        language=feed_data.get('language'),
                        image_url=feed_data.get('image_url')
                    )
                    
                    if not self.dry_run:
                        feed_id = self.db.add_feed(new_feed)
                        logging.info(f"Added feed: {new_feed.title}")
                    else:
                        logging.info(f"Would add feed: {new_feed.title}")
                        
                    self.stats["feeds_added"] += 1
                    
                imported_count += 1
                
            except Exception as e:
                logging.error(f"Error importing feed {feed_data.get('title', 'Unknown')}: {e}")
                self.stats["import_errors"] += 1
                
        self.log_stats()
        return imported_count
        
    def log_stats(self):
        """Log import statistics"""
        logging.info(f"Feeds found in OPML: {self.stats['feeds_found']}")
        logging.info(f"Feeds added: {self.stats['feeds_added']}")
        logging.info(f"Feeds updated: {self.stats['feeds_updated']}")
        logging.info(f"Feeds skipped: {self.stats['feeds_skipped']}")
        logging.info(f"Import errors: {self.stats['import_errors']}")
        
    def __del__(self):
        """Clean up database connection when object is destroyed"""
        if hasattr(self, 'db'):
            self.db.close()


if __name__ == "__main__":
    parser = get_base_parser()
    parser.description = "Import podcast feeds from an OPML file"
    add_dry_run_argument(parser)
    add_log_level_argument(parser)
    
    # Add OPML-specific arguments
    parser.add_argument('opml_file', help='Path to the OPML file to import')
    
    args = parser.parse_args()
    
    # Configure logging
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), "INFO"),
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler()]
    )
    
    # Load configuration
    config = Config(env_file=args.env_file)
    
    # Create importer
    importer = OPMLImporter(config=config, dry_run=args.dry_run)
    
    # Import feeds
    importer.import_feeds(args.opml_file) 