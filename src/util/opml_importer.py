import logging
from typing import List, Dict, Optional
from urllib.parse import urlparse
import listparser

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
            # Use listparser to parse the OPML content
            result = listparser.parse(opml_content)
            
            # Check if there were any parsing errors
            if result.bozo:
                self.logger.error(f"Error parsing OPML: {result.bozo_exception}")
            
            podcasts = []
            seen_urls = set()  # Track seen URLs to avoid duplicates
            
            # Process each feed entry from listparser
            for feed in result.feeds:
                feed_url = feed.url
                
                # Skip if we've seen this URL before
                if feed_url in seen_urls:
                    continue
                seen_urls.add(feed_url)
                
                # Get the title and description
                title = feed.title or ""
                
                # If there's no title, extract it from the URL
                if not title:
                    title = self._extract_domain_from_url(feed_url)
                
                # Get description if available
                description = ""
                if hasattr(feed, "description"):
                    description = feed.description or ""
                
                self.logger.info(f"Parsing podcast: title='{title}', feed_url='{feed_url}'")
                
                podcast = {
                    'title': title,
                    'feed_url': feed_url,
                    'description': description,
                    'image_url': getattr(feed, "image", {}).get("href", "") if hasattr(feed, "image") else ""
                }
                
                # Validate the feed URL
                if not self._is_valid_feed_url(podcast['feed_url']):
                    self.logger.warning(f"Invalid feed URL for podcast '{podcast['title']}': {podcast['feed_url']}")
                    continue
                
                podcasts.append(podcast)
            
            return podcasts
            
        except Exception as e:
            self.logger.error(f"Failed to parse OPML content: {e}")
            return []
    
    def _extract_domain_from_url(self, url: str) -> str:
        """Extract a readable name from the domain in a URL.
        
        Args:
            url (str): URL to extract domain from
            
        Returns:
            str: Clean domain name suitable for display
        """
        try:
            domain = urlparse(url).netloc
            # Remove subdomains like www, feeds, etc.
            main_domain = '.'.join(domain.split('.')[-2:]) if len(domain.split('.')) > 1 else domain
            # Remove TLD
            name = main_domain.split('.')[0]
            # Clean up the name
            return name.replace('-', ' ').replace('_', ' ').title()
        except:
            return url
    
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