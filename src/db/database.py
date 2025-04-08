#!/usr/bin/env python
import os
import sqlite3
import logging
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass

from src.config import Config


@dataclass
class Feed:
    id: int
    title: str
    url: str
    last_updated: datetime
    description: Optional[str] = None
    language: Optional[str] = None
    image_url: Optional[str] = None


@dataclass
class Episode:
    id: int
    feed_id: int
    title: str
    guid: str
    url: str
    published_date: datetime
    description: Optional[str] = None
    duration: Optional[str] = None
    file_size: Optional[int] = None
    local_path: Optional[str] = None
    downloaded: bool = False
    download_date: Optional[datetime] = None


class DatabaseManager:
    def __init__(self, config: Config):
        self.config = config
        self.db_path = os.path.join(config.BASE_DIRECTORY, "podcast.db")
        self.conn = None
        self.cursor = None
        self._connect()
        self._create_tables()
        
    def _connect(self):
        """Connect to the SQLite database"""
        try:
            # Ensure the directory exists
            db_dir = os.path.dirname(self.db_path)
            os.makedirs(db_dir, exist_ok=True)
            logging.info(f"Created database directory: {db_dir}")
            
            self.conn = sqlite3.connect(self.db_path)
            self.conn.row_factory = sqlite3.Row  # This enables column access by name
            self.cursor = self.conn.cursor()
            logging.info(f"Connected to database at {self.db_path}")
        except sqlite3.Error as e:
            logging.error(f"Error connecting to database: {e}")
            raise
            
    def _create_tables(self):
        """Create the necessary tables if they don't exist"""
        try:
            # Feeds table
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS feeds (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL UNIQUE,
                    last_updated TIMESTAMP NOT NULL,
                    description TEXT,
                    language TEXT,
                    image_url TEXT
                )
            ''')
            
            # Episodes table
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS episodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    feed_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    guid TEXT NOT NULL UNIQUE,
                    url TEXT NOT NULL,
                    published_date TIMESTAMP NOT NULL,
                    description TEXT,
                    duration TEXT,
                    file_size INTEGER,
                    local_path TEXT,
                    downloaded BOOLEAN DEFAULT 0,
                    download_date TIMESTAMP,
                    FOREIGN KEY (feed_id) REFERENCES feeds (id)
                )
            ''')
            
            # Create indexes for faster lookups
            self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_episodes_feed_id ON episodes (feed_id)')
            self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_episodes_guid ON episodes (guid)')
            self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_episodes_published_date ON episodes (published_date)')
            
            self.conn.commit()
            logging.info("Database tables created successfully")
        except sqlite3.Error as e:
            logging.error(f"Error creating tables: {e}")
            raise
            
    def add_feed(self, feed: Feed) -> int:
        """Add a new feed to the database"""
        try:
            self.cursor.execute('''
                INSERT INTO feeds (title, url, last_updated, description, language, image_url)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (feed.title, feed.url, feed.last_updated, feed.description, feed.language, feed.image_url))
            self.conn.commit()
            return self.cursor.lastrowid
        except sqlite3.Error as e:
            logging.error(f"Error adding feed: {e}")
            self.conn.rollback()
            raise
            
    def update_feed(self, feed: Feed):
        """Update an existing feed in the database"""
        try:
            self.cursor.execute('''
                UPDATE feeds
                SET title = ?, last_updated = ?, description = ?, language = ?, image_url = ?
                WHERE id = ?
            ''', (feed.title, feed.last_updated, feed.description, feed.language, feed.image_url, feed.id))
            self.conn.commit()
        except sqlite3.Error as e:
            logging.error(f"Error updating feed: {e}")
            self.conn.rollback()
            raise
            
    def get_feed_by_url(self, url: str) -> Optional[Feed]:
        """Get a feed by its URL"""
        try:
            self.cursor.execute('SELECT * FROM feeds WHERE url = ?', (url,))
            row = self.cursor.fetchone()
            if row:
                return Feed(
                    id=row['id'],
                    title=row['title'],
                    url=row['url'],
                    last_updated=datetime.fromisoformat(row['last_updated']),
                    description=row['description'],
                    language=row['language'],
                    image_url=row['image_url']
                )
            return None
        except sqlite3.Error as e:
            logging.error(f"Error getting feed by URL: {e}")
            raise
            
    def get_all_feeds(self) -> List[Feed]:
        """Get all feeds from the database"""
        try:
            self.cursor.execute('SELECT * FROM feeds')
            rows = self.cursor.fetchall()
            return [
                Feed(
                    id=row['id'],
                    title=row['title'],
                    url=row['url'],
                    last_updated=datetime.fromisoformat(row['last_updated']),
                    description=row['description'],
                    language=row['language'],
                    image_url=row['image_url']
                )
                for row in rows
            ]
        except sqlite3.Error as e:
            logging.error(f"Error getting all feeds: {e}")
            raise
            
    def add_episode(self, episode: Episode) -> int:
        """Add a new episode to the database"""
        try:
            self.cursor.execute('''
                INSERT INTO episodes (
                    feed_id, title, guid, url, published_date, description,
                    duration, file_size, local_path, downloaded, download_date
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                episode.feed_id, episode.title, episode.guid, episode.url,
                episode.published_date, episode.description, episode.duration,
                episode.file_size, episode.local_path, episode.downloaded,
                episode.download_date
            ))
            self.conn.commit()
            return self.cursor.lastrowid
        except sqlite3.Error as e:
            logging.error(f"Error adding episode: {e}")
            self.conn.rollback()
            raise
            
    def update_episode(self, episode: Episode):
        """Update an existing episode in the database"""
        try:
            self.cursor.execute('''
                UPDATE episodes
                SET title = ?, url = ?, published_date = ?, description = ?,
                    duration = ?, file_size = ?, local_path = ?, downloaded = ?,
                    download_date = ?
                WHERE id = ?
            ''', (
                episode.title, episode.url, episode.published_date,
                episode.description, episode.duration, episode.file_size,
                episode.local_path, episode.downloaded, episode.download_date,
                episode.id
            ))
            self.conn.commit()
        except sqlite3.Error as e:
            logging.error(f"Error updating episode: {e}")
            self.conn.rollback()
            raise
            
    def get_episode_by_guid(self, guid: str) -> Optional[Episode]:
        """Get an episode by its GUID"""
        try:
            self.cursor.execute('SELECT * FROM episodes WHERE guid = ?', (guid,))
            row = self.cursor.fetchone()
            if row:
                return Episode(
                    id=row['id'],
                    feed_id=row['feed_id'],
                    title=row['title'],
                    guid=row['guid'],
                    url=row['url'],
                    published_date=datetime.fromisoformat(row['published_date']),
                    description=row['description'],
                    duration=row['duration'],
                    file_size=row['file_size'],
                    local_path=row['local_path'],
                    downloaded=bool(row['downloaded']),
                    download_date=datetime.fromisoformat(row['download_date']) if row['download_date'] else None
                )
            return None
        except sqlite3.Error as e:
            logging.error(f"Error getting episode by GUID: {e}")
            raise
            
    def get_episodes_by_feed(self, feed_id: int, limit: int = None, min_age_days: int = None) -> List[Episode]:
        """Get episodes for a specific feed with optional filtering"""
        try:
            query = 'SELECT * FROM episodes WHERE feed_id = ?'
            params = [feed_id]
            
            if min_age_days is not None:
                query += ' AND published_date >= datetime("now", ?)'
                params.append(f'-{min_age_days} days')
                
            query += ' ORDER BY published_date DESC'
            
            if limit is not None:
                query += ' LIMIT ?'
                params.append(limit)
                
            self.cursor.execute(query, params)
            rows = self.cursor.fetchall()
            
            return [
                Episode(
                    id=row['id'],
                    feed_id=row['feed_id'],
                    title=row['title'],
                    guid=row['guid'],
                    url=row['url'],
                    published_date=datetime.fromisoformat(row['published_date']),
                    description=row['description'],
                    duration=row['duration'],
                    file_size=row['file_size'],
                    local_path=row['local_path'],
                    downloaded=bool(row['downloaded']),
                    download_date=datetime.fromisoformat(row['download_date']) if row['download_date'] else None
                )
                for row in rows
            ]
        except sqlite3.Error as e:
            logging.error(f"Error getting episodes by feed: {e}")
            raise
            
    def get_downloaded_episodes(self) -> List[Episode]:
        """Get all downloaded episodes"""
        try:
            self.cursor.execute('SELECT * FROM episodes WHERE downloaded = 1')
            rows = self.cursor.fetchall()
            
            return [
                Episode(
                    id=row['id'],
                    feed_id=row['feed_id'],
                    title=row['title'],
                    guid=row['guid'],
                    url=row['url'],
                    published_date=datetime.fromisoformat(row['published_date']),
                    description=row['description'],
                    duration=row['duration'],
                    file_size=row['file_size'],
                    local_path=row['local_path'],
                    downloaded=bool(row['downloaded']),
                    download_date=datetime.fromisoformat(row['download_date']) if row['download_date'] else None
                )
                for row in rows
            ]
        except sqlite3.Error as e:
            logging.error(f"Error getting downloaded episodes: {e}")
            raise
            
    def close(self):
        """Close the database connection"""
        if self.conn:
            self.conn.close()
            logging.info("Database connection closed")
            
    def __enter__(self):
        """Context manager entry"""
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close() 