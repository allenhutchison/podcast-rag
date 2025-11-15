import logging
import os
import time
from typing import List, Dict, Optional, Tuple
from datetime import datetime
import feedparser
import requests
from dataclasses import dataclass
import eyed3
from pathlib import Path

from src.config import Config


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


class PodcastDownloader:
    def __init__(self, config: Config, dry_run: bool = False):
        self.config = config
        self.dry_run = dry_run
        self.stats = {
            "feeds_processed": 0,
            "episodes_found": 0,
            "episodes_downloaded": 0,
            "episodes_skipped": 0,
            "download_errors": 0
        }
        
    def parse_feed(self, feed_url: str) -> Tuple[str, List[PodcastEpisode]]:
        """Parse a podcast RSS feed and return podcast name and list of episodes"""
        logging.info(f"Parsing feed: {feed_url}")
        
        try:
            feed = feedparser.parse(feed_url)
            podcast_title = feed.feed.title
            
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


if __name__ == "__main__":
    from argparse_shared import (add_dry_run_argument, add_log_level_argument, get_base_parser)
    import argparse
    
    parser = get_base_parser()
    parser.description = "Download podcast episodes from RSS feeds"
    add_dry_run_argument(parser)
    add_log_level_argument(parser)
    
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
    
    # Create downloader
    downloader = PodcastDownloader(config=config, dry_run=args.dry_run)
    
    # Process feeds
    if args.feed:
        downloader.process_feed(args.feed, limit=args.limit, min_age_days=args.min_age_days)
    elif args.feed_file:
        with open(args.feed_file, 'r') as f:
            feeds = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        downloader.process_feed_list(feeds, limit_per_feed=args.limit, min_age_days=args.min_age_days)
    else:
        parser.error("Either --feed or --feed-file must be specified") 