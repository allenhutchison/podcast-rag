import xml.etree.ElementTree as ET
import logging
from typing import List, Dict, Optional
from urllib.parse import urlparse

from src.db.metadatadb import PodcastDB

class OPMLImporter:
    """Class to import podcasts from OPML files into the database."""
    
    def __init__(self, db: PodcastDB):
        """Initialize the OPML importer with a database connection.
        
        Args:
            db (PodcastDB): Database connection to store podcasts
        """
        self.db = db
        self.logger = logging.getLogger(__name__)
    
    def parse_opml(self, opml_content: str) -> List[Dict[str, str]]:
        """Parse OPML content and extract podcast information.
        
        Args:
            opml_content (str): The content of the OPML file
            
        Returns:
            List[Dict[str, str]]: List of dictionaries containing podcast information
        """
        try:
            root = ET.fromstring(opml_content)
            # Find all outline elements that have either type="rss" or xmlUrl attribute
            podcasts = []
            seen_urls = set()  # Track seen URLs to avoid duplicates
            
            # Use a more specific XPath to find podcast entries
            for outline in root.findall(".//outline[@xmlUrl]"):
                feed_url = outline.get('xmlUrl', '')
                
                # Skip if we've seen this URL before
                if feed_url in seen_urls:
                    continue
                seen_urls.add(feed_url)
                
                podcast = {
                    'title': outline.get('text', ''),
                    'feed_url': feed_url,
                    'description': outline.get('description', ''),
                    'image_url': outline.get('imageUrl', '')  # Some OPML files include image URLs
                }
                
                # Validate the feed URL
                if not self._is_valid_feed_url(podcast['feed_url']):
                    self.logger.warning(f"Invalid feed URL for podcast '{podcast['title']}': {podcast['feed_url']}")
                    continue
                
                # Validate image URL if present
                if podcast['image_url'] and not self._is_valid_feed_url(podcast['image_url']):
                    self.logger.warning(f"Invalid image URL for podcast '{podcast['title']}': {podcast['image_url']}")
                    podcast['image_url'] = ''  # Clear invalid image URL
                
                podcasts.append(podcast)
            
            return podcasts
            
        except ET.ParseError as e:
            self.logger.error(f"Failed to parse OPML content: {e}")
            return []
    
    def _is_valid_feed_url(self, url: str) -> bool:
        """Check if a URL is valid and likely to be a podcast feed.
        
        Args:
            url (str): URL to validate
            
        Returns:
            bool: True if the URL is valid, False otherwise
        """
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except Exception:
            return False
    
    def import_from_file(self, file_path: str) -> int:
        """Import podcasts from an OPML file.
        
        Args:
            file_path (str): Path to the OPML file
            
        Returns:
            int: Number of podcasts successfully imported
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                opml_content = f.read()
            
            podcasts = self.parse_opml(opml_content)
            imported_count = 0
            
            for podcast in podcasts:
                try:
                    # Check if podcast already exists
                    existing = self.db.get_podcast_by_url(podcast['feed_url'])
                    if existing:
                        self.logger.info(f"Podcast already exists: {podcast['title']}")
                        continue
                    
                    # Add new podcast to database
                    self.db.add_podcast(
                        title=podcast['title'],
                        description=podcast['description'],
                        feed_url=podcast['feed_url'],
                        image_url=podcast['image_url'] or None
                    )
                    imported_count += 1
                    self.logger.info(f"Successfully imported podcast: {podcast['title']}")
                    
                except Exception as e:
                    self.logger.error(f"Failed to import podcast '{podcast['title']}': {e}")
            
            return imported_count
            
        except Exception as e:
            self.logger.error(f"Failed to read OPML file '{file_path}': {e}")
            return 0
    
    def import_from_string(self, opml_content: str) -> int:
        """Import podcasts from OPML content string.
        
        Args:
            opml_content (str): The content of the OPML file
            
        Returns:
            int: Number of podcasts successfully imported
        """
        podcasts = self.parse_opml(opml_content)
        imported_count = 0
        
        for podcast in podcasts:
            try:
                # Check if podcast already exists
                existing = self.db.get_podcast_by_url(podcast['feed_url'])
                if existing:
                    self.logger.info(f"Podcast already exists: {podcast['title']}")
                    continue
                
                # Add new podcast to database
                self.db.add_podcast(
                    title=podcast['title'],
                    description=podcast['description'],
                    feed_url=podcast['feed_url'],
                    image_url=podcast['image_url'] or None
                )
                imported_count += 1
                self.logger.info(f"Successfully imported podcast: {podcast['title']}")
                
            except Exception as e:
                self.logger.error(f"Failed to import podcast '{podcast['title']}': {e}")
        
        return imported_count 