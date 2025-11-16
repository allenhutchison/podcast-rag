"""
Legacy SQLite database implementation for podcast metadata.

NOTE: This module is deprecated and only used for testing purposes.
Production code uses PostgreSQL with the models defined in src/db/models.py.
This module is maintained solely for backward compatibility with existing tests.
"""
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text
from sqlalchemy.orm import sessionmaker, DeclarativeBase
import os
from datetime import datetime, UTC

class Base(DeclarativeBase):
    pass

class Podcast(Base):
    __tablename__ = 'podcasts'
    
    id = Column(Integer, primary_key=True)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    feed_url = Column(String(512), unique=True, nullable=False)
    image_url = Column(String(512))  # URL to podcast cover image
    last_updated = Column(DateTime, default=lambda: datetime.now(UTC))
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))

class PodcastDB:
    def __init__(self, db_path="podcasts.db"):
        """Initialize the database connection.
        
        Args:
            db_path (str): Path to the SQLite database file
        """
        self.engine = create_engine(f'sqlite:///{db_path}')
        Base.metadata.create_all(self.engine)
        Session = sessionmaker(bind=self.engine)
        self.session = Session()
    
    def add_podcast(self, title, description, feed_url, image_url=None):
        """Add a new podcast to the database.
        
        Args:
            title (str): Podcast title
            description (str): Podcast description
            feed_url (str): RSS feed URL
            image_url (str, optional): URL to podcast cover image
            
        Returns:
            Podcast: The created podcast object
        """
        podcast = Podcast(
            title=title,
            description=description,
            feed_url=feed_url,
            image_url=image_url
        )
        self.session.add(podcast)
        self.session.commit()
        return podcast
    
    def get_podcast_by_url(self, feed_url):
        """Retrieve a podcast by its feed URL.
        
        Args:
            feed_url (str): RSS feed URL
            
        Returns:
            Podcast: The podcast object if found, None otherwise
        """
        return self.session.query(Podcast).filter_by(feed_url=feed_url).first()
    
    def get_all_podcasts(self):
        """Retrieve all podcasts from the database.
        
        Returns:
            list: List of Podcast objects
        """
        return self.session.query(Podcast).all()
    
    def update_podcast(self, feed_url, **kwargs):
        """Update podcast information.
        
        Args:
            feed_url (str): RSS feed URL
            **kwargs: Fields to update
            
        Returns:
            bool: True if update was successful, False otherwise
        """
        podcast = self.get_podcast_by_url(feed_url)
        if podcast:
            for key, value in kwargs.items():
                if hasattr(podcast, key):
                    setattr(podcast, key, value)
            podcast.last_updated = datetime.now(UTC)
            self.session.commit()
            return True
        return False
    
    def delete_podcast(self, feed_url):
        """Delete a podcast from the database.
        
        Args:
            feed_url (str): RSS feed URL
            
        Returns:
            bool: True if deletion was successful, False otherwise
        """
        podcast = self.get_podcast_by_url(feed_url)
        if podcast:
            self.session.delete(podcast)
            self.session.commit()
            return True
        return False
    
    def __del__(self):
        """Clean up the database session when the object is destroyed."""
        self.session.close()
