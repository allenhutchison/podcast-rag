#!/usr/bin/env python
import logging
import os
import time
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
import feedparser
import requests
from dataclasses import dataclass
import eyed3
from pathlib import Path

from src.argparse_shared import (add_dry_run_argument, add_log_level_argument, 
                          get_base_parser)
from src.config import Config
from src.db.database import DatabaseManager, Feed as DBFeed, Episode as DBEpisode


@dataclass
class PodcastEpisode:
    title: str
    url: str
    guid: str
    published_date: datetime
    description: str
    duration: Optional[str] = None
    file_size: Optional[int] = None
    
    @property
    def filename(self) -> str:
        """Generate a safe filename from the episode title"""
        # Replace invalid characters
        safe_title = "".join(c if c.isalnum() or c in ' -_' else '_' for c in self.title)
        # Limit filename length
        if len(safe_title) > 100:
            safe_title = safe_title[:100]
        return f"{safe_title}.mp3"


class DownloadManager:
    def __init__(self, config: Config, dry_run=False):
        self.config = config
        self.dry_run = dry_run
        self.stats = {
            "feeds_processed": 0,
            "episodes_found": 0,
            "episodes_added": 0,
            "episodes_updated": 0,
            "download_errors": 0
        }
        self.db = DatabaseManager(config)
        
    def parse_feed(self, feed: DBFeed) -> List[PodcastEpisode]:
        """Parse a podcast RSS feed and return list of episodes"""
        logging.info(f"Parsing feed: {feed.url}")
        
        try:
            parsed_feed = feedparser.parse(feed.url)
            podcast_title = parsed_feed.feed.title
            
            # Update feed information
            feed.title = podcast_title
            feed.last_updated = datetime.now()
            feed.description = parsed_feed.feed.get('description')
            feed.language = parsed_feed.feed.get('language')
            feed.image_url = parsed_feed.feed.get('image', {}).get('href')
            self.db.update_feed(feed)
            
            episodes = []
            for entry in parsed_feed.entries:
                for link in entry.links:
                    if link.get('type') == 'audio/mpeg' or link.get('rel') == 'enclosure':
                        url = link.get('href')
                        file_size = link.get('length')
                        
                        # Try to get publication date
                        published_date = None
                        if hasattr(entry, 'published_parsed') and entry.published_parsed:
                            published_date = datetime(*entry.published_parsed[:6])
                        else:
                            published_date = datetime.now()  # Fallback
                        
                        # Try to get duration
                        duration = None
                        if hasattr(entry, 'itunes_duration'):
                            duration = entry.itunes_duration
                            
                        # Create episode object
                        episode = PodcastEpisode(
                            title=entry.title,
                            url=url,
                            guid=entry.id if hasattr(entry, 'id') else url,
                            published_date=published_date,
                            description=entry.description if hasattr(entry, 'description') else "",
                            duration=duration,
                            file_size=int(file_size) if file_size and file_size.isdigit() else None
                        )
                        episodes.append(episode)
                        
                        # Check if episode already exists in database
                        db_episode = self.db.get_episode_by_guid(episode.guid)
                        if db_episode:
                            # Update existing episode
                            db_episode.title = episode.title
                            db_episode.url = episode.url
                            db_episode.published_date = episode.published_date
                            db_episode.description = episode.description
                            db_episode.duration = episode.duration
                            db_episode.file_size = episode.file_size
                            self.db.update_episode(db_episode)
                            self.stats['episodes_updated'] += 1
                        else:
                            # Add new episode
                            db_episode = DBEpisode(
                                id=0,  # Will be set by database
                                feed_id=feed.id,
                                title=episode.title,
                                guid=episode.guid,
                                url=episode.url,
                                published_date=episode.published_date,
                                description=episode.description,
                                duration=episode.duration,
                                file_size=episode.file_size,
                                local_path=None,
                                downloaded=False,
                                download_date=None
                            )
                            self.db.add_episode(db_episode)
                            self.stats['episodes_added'] += 1
            
            self.stats['episodes_found'] += len(episodes)
            self.stats['feeds_processed'] += 1
            
            return episodes
            
        except Exception as e:
            logging.error(f"Error parsing feed {feed.url}: {e}")
            return []
            
    def process_feed(self, feed: DBFeed, limit: int = 5, min_age_days: int = None) -> None:
        """Process a single podcast feed - update episode database without downloading"""
        episodes = self.parse_feed(feed)
        
        if not episodes:
            logging.warning(f"No valid podcast data found for feed: {feed.url}")
            return
            
        # Sort episodes by date (newest first)
        episodes.sort(key=lambda x: x.published_date, reverse=True)
        
        # Apply age filter if specified
        if min_age_days is not None:
            cutoff_date = datetime.now() - timedelta(days=min_age_days)
            episodes = [ep for ep in episodes if ep.published_date >= cutoff_date]
        
        # Apply episode limit
        if limit > 0:
            episodes = episodes[:limit]
            
        # No need to download episodes as requested
        logging.info(f"Processed {len(episodes)} episodes for feed: {feed.title}")
            
    def process_all_feeds(self, limit_per_feed: int = 5, min_age_days: int = None) -> None:
        """Process all feeds from the database"""
        feeds = self.db.get_all_feeds()
        
        if not feeds:
            logging.warning("No feeds found in the database")
            return
            
        logging.info(f"Found {len(feeds)} feeds in the database")
        
        for feed in feeds:
            self.process_feed(feed, limit=limit_per_feed, min_age_days=min_age_days)
                
        self.log_stats()
        
    def log_stats(self):
        """Log processing statistics"""
        logging.info(f"Feeds processed: {self.stats['feeds_processed']}")
        logging.info(f"Episodes found: {self.stats['episodes_found']}")
        logging.info(f"Episodes added: {self.stats['episodes_added']}")
        logging.info(f"Episodes updated: {self.stats['episodes_updated']}")
        logging.info(f"Download errors: {self.stats['download_errors']}")
        
    def __del__(self):
        """Clean up database connection when object is destroyed"""
        if hasattr(self, 'db'):
            self.db.close()


if __name__ == "__main__":
    parser = get_base_parser()
    parser.description = "Update podcast episode database from RSS feeds"
    add_dry_run_argument(parser)
    add_log_level_argument(parser)
    
    # Add processing-specific arguments
    parser.add_argument('--limit', type=int, default=5, 
                        help='Maximum number of episodes to process per feed')
    parser.add_argument('--min-age-days', type=int, 
                        help='Only process episodes newer than this many days')
    
    args = parser.parse_args()
    
    # Configure logging
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), "INFO"),
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler()]
    )
    
    # Load configuration
    config = Config(env_file=args.env_file)
    
    # Create download manager
    manager = DownloadManager(config=config, dry_run=args.dry_run)
    
    # Process all feeds from the database
    manager.process_all_feeds(limit_per_feed=args.limit, min_age_days=args.min_age_days) 