import os
import feedparser
import requests
from datetime import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
import eyed3
from pathlib import Path
import xml.etree.ElementTree as ET
import logging

from src.db.models import Podcast, Episode
from src.db.database import get_db
from src.core.config import settings

# Set up logging
logger = logging.getLogger(__name__)

class PodcastManager:
    def __init__(self):
        self.base_dir = settings.PODCASTS_DIR
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def fetch_feed(self, feed_url: str) -> feedparser.FeedParserDict:
        """Fetch and parse a podcast feed."""
        response = requests.get(feed_url)
        response.raise_for_status()
        return feedparser.parse(response.content)

    def create_podcast(self, db: Session, feed_url: str) -> Podcast:
        """Create a new podcast entry from a feed URL."""
        feed = self.fetch_feed(feed_url)
        
        # Extract podcast metadata
        podcast_data = {
            "title": feed.feed.title,
            "description": feed.feed.get("description", ""),
            "feed_url": feed_url,
            "image_url": feed.feed.get("image", {}).get("href", ""),
            "author": feed.feed.get("author", ""),
            "language": feed.feed.get("language", ""),
            "last_updated": datetime.utcnow()
        }
        
        podcast = Podcast(**podcast_data)
        db.add(podcast)
        db.commit()
        db.refresh(podcast)
        
        # Create podcast directory
        podcast_dir = self.base_dir / str(podcast.id)
        podcast_dir.mkdir(exist_ok=True)
        
        return podcast

    def import_from_opml(self, db: Session, opml_content: str) -> List[Podcast]:
        """Import podcasts from OPML content."""
        try:
            root = ET.fromstring(opml_content)
            
            # Find all outline elements that have a type="rss" attribute
            # This is the standard way podcasts are represented in OPML
            outlines = root.findall(".//outline[@type='rss']")
            
            imported_podcasts = []
            for outline in outlines:
                feed_url = outline.get("xmlUrl")
                if not feed_url:
                    continue
                
                # Check if podcast already exists
                existing_podcast = db.query(Podcast).filter(Podcast.feed_url == feed_url).first()
                if existing_podcast:
                    logger.info(f"Podcast with feed URL {feed_url} already exists, skipping")
                    imported_podcasts.append(existing_podcast)
                    continue
                
                try:
                    podcast = self.create_podcast(db, feed_url)
                    imported_podcasts.append(podcast)
                    logger.info(f"Imported podcast: {podcast.title}")
                except Exception as e:
                    logger.error(f"Failed to import podcast from {feed_url}: {str(e)}")
            
            return imported_podcasts
        except ET.ParseError as e:
            logger.error(f"Failed to parse OPML content: {str(e)}")
            raise ValueError(f"Invalid OPML format: {str(e)}")
        except Exception as e:
            logger.error(f"Error importing from OPML: {str(e)}")
            raise

    def export_to_opml(self, db: Session) -> str:
        """Export all podcasts to OPML format."""
        podcasts = self.list_podcasts(db)
        
        # Create OPML structure
        opml = ET.Element("opml", version="2.0")
        head = ET.SubElement(opml, "head")
        ET.SubElement(head, "title").text = "Podcast RAG Export"
        ET.SubElement(head, "dateCreated").text = datetime.now().strftime("%a, %d %b %Y %H:%M:%S %z")
        
        body = ET.SubElement(opml, "body")
        
        # Add each podcast as an outline
        for podcast in podcasts:
            outline = ET.SubElement(body, "outline", 
                                   type="rss",
                                   text=podcast.title,
                                   title=podcast.title,
                                   xmlUrl=podcast.feed_url)
            
            # Add description if available
            if podcast.description:
                ET.SubElement(outline, "description").text = podcast.description
        
        # Convert to string
        return ET.tostring(opml, encoding="unicode", method="xml")

    def update_podcast(self, db: Session, podcast_id: int) -> Podcast:
        """Update podcast and its episodes from the feed."""
        podcast = db.query(Podcast).filter(Podcast.id == podcast_id).first()
        if not podcast:
            raise ValueError(f"Podcast with id {podcast_id} not found")
        
        feed = self.fetch_feed(podcast.feed_url)
        
        # Update podcast metadata
        podcast.title = feed.feed.title
        podcast.description = feed.feed.get("description", podcast.description)
        podcast.image_url = feed.feed.get("image", {}).get("href", podcast.image_url)
        podcast.author = feed.feed.get("author", podcast.author)
        podcast.language = feed.feed.get("language", podcast.language)
        podcast.last_updated = datetime.utcnow()
        
        # Update episodes
        for entry in feed.entries:
            episode = db.query(Episode).filter(
                Episode.podcast_id == podcast_id,
                Episode.audio_url == entry.get("link", "")
            ).first()
            
            if not episode:
                episode = Episode(
                    podcast_id=podcast_id,
                    title=entry.title,
                    description=entry.get("description", ""),
                    audio_url=entry.get("link", ""),
                    published_date=datetime.strptime(entry.published, "%a, %d %b %Y %H:%M:%S %z") if "published" in entry else None
                )
                db.add(episode)
        
        db.commit()
        db.refresh(podcast)
        return podcast

    def download_episode(self, db: Session, episode_id: int) -> Episode:
        """Download an episode's audio file."""
        episode = db.query(Episode).filter(Episode.id == episode_id).first()
        if not episode:
            raise ValueError(f"Episode with id {episode_id} not found")
        
        if episode.is_downloaded:
            return episode
        
        # Create episode directory
        episode_dir = self.base_dir / str(episode.podcast_id) / str(episode_id)
        episode_dir.mkdir(parents=True, exist_ok=True)
        
        # Download audio file
        response = requests.get(episode.audio_url, stream=True)
        response.raise_for_status()
        
        audio_path = episode_dir / "audio.mp3"
        with open(audio_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        # Update episode metadata
        audio = eyed3.load(str(audio_path))
        if audio and audio.info:
            episode.duration = int(audio.info.time_secs)
        
        episode.local_audio_path = str(audio_path)
        episode.is_downloaded = True
        db.commit()
        db.refresh(episode)
        
        return episode

    def get_podcast(self, db: Session, podcast_id: int) -> Optional[Podcast]:
        """Get a podcast by ID."""
        return db.query(Podcast).filter(Podcast.id == podcast_id).first()

    def get_episode(self, db: Session, episode_id: int) -> Optional[Episode]:
        """Get an episode by ID."""
        return db.query(Episode).filter(Episode.id == episode_id).first()

    def list_podcasts(self, db: Session) -> List[Podcast]:
        """List all podcasts."""
        return db.query(Podcast).all()

    def list_episodes(self, db: Session, podcast_id: int) -> List[Episode]:
        """List all episodes for a podcast."""
        return db.query(Episode).filter(Episode.podcast_id == podcast_id).all()

    def delete_podcast(self, db: Session, podcast_id: int) -> None:
        """Delete a podcast and its associated files."""
        podcast = self.get_podcast(db, podcast_id)
        if not podcast:
            raise ValueError(f"Podcast with id {podcast_id} not found")
        
        # Delete podcast directory
        podcast_dir = self.base_dir / str(podcast_id)
        if podcast_dir.exists():
            for episode_dir in podcast_dir.iterdir():
                if episode_dir.is_dir():
                    for file in episode_dir.iterdir():
                        file.unlink()
                    episode_dir.rmdir()
            podcast_dir.rmdir()
        
        # Delete from database
        db.delete(podcast)
        db.commit()

# Create global podcast manager instance
podcast_manager = PodcastManager() 