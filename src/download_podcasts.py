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

from argparse_shared import (add_dry_run_argument, add_log_level_argument, 
                          get_base_parser)
from config import Config
from db import DatabaseManager, Feed as DBFeed, Episode as DBEpisode


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
            "episodes_downloaded": 0,
            "episodes_skipped": 0,
            "download_errors": 0
        }
        self.db = DatabaseManager(config)
        
    def parse_feed(self, feed_url: str) -> Tuple[str, List[PodcastEpisode]]:
        """Parse a podcast RSS feed and return podcast name and list of episodes"""
        logging.info(f"Parsing feed: {feed_url}")
        
        try:
            feed = feedparser.parse(feed_url)
            podcast_title = feed.feed.title
            
            # Check if feed already exists in database
            db_feed = self.db.get_feed_by_url(feed_url)
            if db_feed:
                # Update existing feed
                db_feed.title = podcast_title
                db_feed.last_updated = datetime.now()
                db_feed.description = feed.feed.get('description')
                db_feed.language = feed.feed.get('language')
                db_feed.image_url = feed.feed.get('image', {}).get('href')
                self.db.update_feed(db_feed)
                feed_id = db_feed.id
            else:
                # Create new feed
                db_feed = DBFeed(
                    id=0,  # Will be set by database
                    title=podcast_title,
                    url=feed_url,
                    last_updated=datetime.now(),
                    description=feed.feed.get('description'),
                    language=feed.feed.get('language'),
                    image_url=feed.feed.get('image', {}).get('href')
                )
                feed_id = self.db.add_feed(db_feed)
            
            episodes = []
            for entry in feed.entries:
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
                        else:
                            # Add new episode
                            db_episode = DBEpisode(
                                id=0,  # Will be set by database
                                feed_id=feed_id,
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
            
            self.stats['episodes_found'] += len(episodes)
            self.stats['feeds_processed'] += 1
            
            return podcast_title, episodes
            
        except Exception as e:
            logging.error(f"Error parsing feed {feed_url}: {e}")
            return "", []
            
    def download_episode(self, episode: PodcastEpisode, podcast_dir: str) -> bool:
        """Download a podcast episode to the specified directory"""
        os.makedirs(podcast_dir, exist_ok=True)
        output_path = os.path.join(podcast_dir, episode.filename)
        
        # Check if episode is already downloaded in database
        db_episode = self.db.get_episode_by_guid(episode.guid)
        if db_episode and db_episode.downloaded and os.path.exists(db_episode.local_path):
            logging.info(f"Skipping {episode.title} - already downloaded")
            self.stats['episodes_skipped'] += 1
            return False
            
        # Skip if file already exists
        if os.path.exists(output_path):
            logging.info(f"Skipping {episode.title} - file already exists")
            self.stats['episodes_skipped'] += 1
            return False
            
        if self.dry_run:
            logging.info(f"Dry run: Would download {episode.title} to {output_path}")
            return False
            
        try:
            logging.info(f"Downloading {episode.title}")
            
            # Stream download with progress updates
            with requests.get(episode.url, stream=True) as response:
                response.raise_for_status()
                total_size = int(response.headers.get('content-length', 0))
                
                with open(output_path, 'wb') as f:
                    downloaded = 0
                    chunk_size = 8192
                    
                    for chunk in response.iter_content(chunk_size=chunk_size):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            
                            # Log progress for large files
                            if total_size > 1_000_000 and downloaded % (total_size // 10) < chunk_size:
                                percent = int(downloaded / total_size * 100)
                                logging.debug(f"Download progress: {percent}%")
            
            # Add ID3 metadata if possible
            try:
                audio_file = eyed3.load(output_path)
                if audio_file and audio_file.tag:
                    audio_file.tag.title = episode.title
                    audio_file.tag.comments.set(episode.description)
                    audio_file.tag.save()
            except Exception as e:
                logging.warning(f"Could not add ID3 tags to {output_path}: {e}")
                
            # Update episode in database
            if db_episode:
                db_episode.local_path = output_path
                db_episode.downloaded = True
                db_episode.download_date = datetime.now()
                self.db.update_episode(db_episode)
                
            self.stats['episodes_downloaded'] += 1
            return True
            
        except Exception as e:
            logging.error(f"Error downloading {episode.title}: {e}")
            self.stats['download_errors'] += 1
            
            # Remove partial file if it exists
            if os.path.exists(output_path):
                os.remove(output_path)
                
            return False
            
    def process_feed(self, feed_url: str, limit: int = 5, min_age_days: int = None) -> str:
        """Process a single podcast feed - download recent episodes"""
        podcast_title, episodes = self.parse_feed(feed_url)
        
        if not podcast_title or not episodes:
            logging.warning(f"No valid podcast data found for feed: {feed_url}")
            return None
            
        # Create a directory for this podcast
        safe_title = "".join(c if c.isalnum() or c in ' -_' else '_' for c in podcast_title)
        podcast_dir = os.path.join(self.config.BASE_DIRECTORY, safe_title)
        
        # Sort episodes by date (newest first)
        episodes.sort(key=lambda x: x.published_date, reverse=True)
        
        # Apply age filter if specified
        if min_age_days is not None:
            cutoff_date = datetime.now() - timedelta(days=min_age_days)
            episodes = [ep for ep in episodes if ep.published_date >= cutoff_date]
        
        # Apply episode limit
        if limit > 0:
            episodes = episodes[:limit]
            
        # Download each episode
        for episode in episodes:
            self.download_episode(episode, podcast_dir)
            
        return podcast_dir
            
    def process_feed_list(self, feed_list: List[str], limit_per_feed: int = 5, min_age_days: int = None) -> List[str]:
        """Process a list of podcast feeds"""
        processed_dirs = []
        
        for feed_url in feed_list:
            podcast_dir = self.process_feed(feed_url, limit=limit_per_feed, min_age_days=min_age_days)
            if podcast_dir:
                processed_dirs.append(podcast_dir)
                
        self.log_stats()
        return processed_dirs
        
    def log_stats(self):
        """Log download statistics"""
        logging.info(f"Feeds processed: {self.stats['feeds_processed']}")
        logging.info(f"Episodes found: {self.stats['episodes_found']}")
        logging.info(f"Episodes downloaded: {self.stats['episodes_downloaded']}")
        logging.info(f"Episodes skipped: {self.stats['episodes_skipped']}")
        logging.info(f"Download errors: {self.stats['download_errors']}")
        
    def __del__(self):
        """Clean up database connection when object is destroyed"""
        if hasattr(self, 'db'):
            self.db.close()


if __name__ == "__main__":
    parser = get_base_parser()
    parser.description = "Download podcasts from RSS feeds"
    add_dry_run_argument(parser)
    add_log_level_argument(parser)
    
    # Add download-specific arguments
    parser.add_argument('-f', '--feed', help='RSS feed URL to download from')
    parser.add_argument('--feed-file', help='File containing a list of RSS feed URLs (one per line)')
    parser.add_argument('--limit', type=int, default=5, 
                        help='Maximum number of episodes to download per feed')
    parser.add_argument('--min-age-days', type=int, 
                        help='Only download episodes newer than this many days')
    
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
    
    # Process feeds
    if args.feed:
        manager.process_feed(args.feed, limit=args.limit, min_age_days=args.min_age_days)
    elif args.feed_file:
        with open(args.feed_file, 'r') as f:
            feeds = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        manager.process_feed_list(feeds, limit_per_feed=args.limit, min_age_days=args.min_age_days)
    else:
        parser.error("Either --feed or --feed-file must be specified") 