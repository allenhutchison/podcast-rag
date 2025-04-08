#!/usr/bin/env python
import os
import sqlite3
import logging
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass
from enum import Enum

from src.config import Config


class JobStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class JobType(Enum):
    DOWNLOAD = "download"
    METADATA_EXTRACTION = "metadata_extraction"
    TRANSCRIPTION = "transcription"
    EMBEDDINGS_CREATION = "embeddings_creation"
    MP3_DELETION = "mp3_deletion"


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
    download_date: Optional[datetime] = None


@dataclass
class Job:
    id: int
    episode_id: int
    job_type: JobType
    status: JobStatus
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    result_data: Optional[str] = None


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
            
            # Episodes table - removed downloaded field as it's now tracked in jobs
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
                    download_date TIMESTAMP,
                    FOREIGN KEY (feed_id) REFERENCES feeds (id)
                )
            ''')
            
            # Jobs table for tracking workflow
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    episode_id INTEGER NOT NULL,
                    job_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    error_message TEXT,
                    result_data TEXT,
                    FOREIGN KEY (episode_id) REFERENCES episodes (id)
                )
            ''')
            
            # Create indexes for faster lookups
            self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_episodes_feed_id ON episodes (feed_id)')
            self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_episodes_guid ON episodes (guid)')
            self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_episodes_published_date ON episodes (published_date)')
            self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_jobs_episode_id ON jobs (episode_id)')
            self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs (status)')
            self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_jobs_type ON jobs (job_type)')
            
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
            
    def get_all_episodes(self) -> List[Episode]:
        """Get all episodes from the database"""
        try:
            self.cursor.execute('SELECT * FROM episodes')
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
                    download_date=datetime.fromisoformat(row['download_date']) if row['download_date'] else None
                )
                for row in rows
            ]
        except sqlite3.Error as e:
            logging.error(f"Error getting all episodes: {e}")
            raise
            
    def add_episode(self, episode: Episode) -> int:
        """Add a new episode to the database"""
        try:
            self.cursor.execute('''
                INSERT INTO episodes (
                    feed_id, title, guid, url, published_date, description,
                    duration, file_size, local_path, download_date
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                episode.feed_id, episode.title, episode.guid, episode.url,
                episode.published_date, episode.description, episode.duration,
                episode.file_size, episode.local_path, episode.download_date
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
                    duration = ?, file_size = ?, local_path = ?, download_date = ?
                WHERE id = ?
            ''', (
                episode.title, episode.url, episode.published_date,
                episode.description, episode.duration, episode.file_size,
                episode.local_path, episode.download_date, episode.id
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
                    download_date=datetime.fromisoformat(row['download_date']) if row['download_date'] else None
                )
            return None
        except sqlite3.Error as e:
            logging.error(f"Error getting episode by GUID: {e}")
            raise
            
    def get_episode_by_id(self, episode_id: int) -> Optional[Episode]:
        """Get an episode by its ID"""
        try:
            self.cursor.execute('SELECT * FROM episodes WHERE id = ?', (episode_id,))
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
                    download_date=datetime.fromisoformat(row['download_date']) if row['download_date'] else None
                )
            return None
        except sqlite3.Error as e:
            logging.error(f"Error getting episode by ID: {e}")
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
                    download_date=datetime.fromisoformat(row['download_date']) if row['download_date'] else None
                )
                for row in rows
            ]
        except sqlite3.Error as e:
            logging.error(f"Error getting episodes by feed: {e}")
            raise
            
    def get_downloaded_episodes(self) -> List[Episode]:
        """Get all downloaded episodes by checking for completed download jobs"""
        try:
            self.cursor.execute('''
                SELECT e.* FROM episodes e
                JOIN jobs j ON e.id = j.episode_id
                WHERE j.job_type = ? AND j.status = ?
            ''', (JobType.DOWNLOAD.value, JobStatus.COMPLETED.value))
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
                    download_date=datetime.fromisoformat(row['download_date']) if row['download_date'] else None
                )
                for row in rows
            ]
        except sqlite3.Error as e:
            logging.error(f"Error getting downloaded episodes: {e}")
            raise
            
    # Job management methods
    def create_job(self, episode_id: int, job_type: JobType) -> int:
        """Create a new job for an episode"""
        try:
            self.cursor.execute('''
                INSERT INTO jobs (episode_id, job_type, status, created_at)
                VALUES (?, ?, ?, ?)
            ''', (episode_id, job_type.value, JobStatus.PENDING.value, datetime.now()))
            self.conn.commit()
            return self.cursor.lastrowid
        except sqlite3.Error as e:
            logging.error(f"Error creating job: {e}")
            self.conn.rollback()
            raise
            
    def start_job(self, job_id: int):
        """Mark a job as in progress"""
        try:
            self.cursor.execute('''
                UPDATE jobs
                SET status = ?, started_at = ?
                WHERE id = ?
            ''', (JobStatus.IN_PROGRESS.value, datetime.now(), job_id))
            self.conn.commit()
        except sqlite3.Error as e:
            logging.error(f"Error starting job: {e}")
            self.conn.rollback()
            raise
            
    def complete_job(self, job_id: int, result_data: Optional[str] = None):
        """Mark a job as completed"""
        try:
            self.cursor.execute('''
                UPDATE jobs
                SET status = ?, completed_at = ?, result_data = ?
                WHERE id = ?
            ''', (JobStatus.COMPLETED.value, datetime.now(), result_data, job_id))
            self.conn.commit()
        except sqlite3.Error as e:
            logging.error(f"Error completing job: {e}")
            self.conn.rollback()
            raise
            
    def fail_job(self, job_id: int, error_message: str):
        """Mark a job as failed"""
        try:
            self.cursor.execute('''
                UPDATE jobs
                SET status = ?, completed_at = ?, error_message = ?
                WHERE id = ?
            ''', (JobStatus.FAILED.value, datetime.now(), error_message, job_id))
            self.conn.commit()
        except sqlite3.Error as e:
            logging.error(f"Error failing job: {e}")
            self.conn.rollback()
            raise
            
    def get_job(self, job_id: int) -> Optional[Job]:
        """Get a job by its ID"""
        try:
            self.cursor.execute('SELECT * FROM jobs WHERE id = ?', (job_id,))
            row = self.cursor.fetchone()
            if row:
                return Job(
                    id=row['id'],
                    episode_id=row['episode_id'],
                    job_type=JobType(row['job_type']),
                    status=JobStatus(row['status']),
                    created_at=datetime.fromisoformat(row['created_at']),
                    started_at=datetime.fromisoformat(row['started_at']) if row['started_at'] else None,
                    completed_at=datetime.fromisoformat(row['completed_at']) if row['completed_at'] else None,
                    error_message=row['error_message'],
                    result_data=row['result_data']
                )
            return None
        except sqlite3.Error as e:
            logging.error(f"Error getting job: {e}")
            raise
            
    def get_pending_jobs(self, job_type: Optional[JobType] = None) -> List[Job]:
        """Get all pending jobs, optionally filtered by job type"""
        try:
            query = 'SELECT * FROM jobs WHERE status = ?'
            params = [JobStatus.PENDING.value]
            
            if job_type:
                query += ' AND job_type = ?'
                params.append(job_type.value)
                
            query += ' ORDER BY created_at ASC'
            
            self.cursor.execute(query, params)
            rows = self.cursor.fetchall()
            
            return [
                Job(
                    id=row['id'],
                    episode_id=row['episode_id'],
                    job_type=JobType(row['job_type']),
                    status=JobStatus(row['status']),
                    created_at=datetime.fromisoformat(row['created_at']),
                    started_at=datetime.fromisoformat(row['started_at']) if row['started_at'] else None,
                    completed_at=datetime.fromisoformat(row['completed_at']) if row['completed_at'] else None,
                    error_message=row['error_message'],
                    result_data=row['result_data']
                )
                for row in rows
            ]
        except sqlite3.Error as e:
            logging.error(f"Error getting pending jobs: {e}")
            raise
            
    def get_jobs_for_episode(self, episode_id: int) -> List[Job]:
        """Get all jobs for a specific episode"""
        try:
            self.cursor.execute('SELECT * FROM jobs WHERE episode_id = ? ORDER BY created_at ASC', (episode_id,))
            rows = self.cursor.fetchall()
            
            return [
                Job(
                    id=row['id'],
                    episode_id=row['episode_id'],
                    job_type=JobType(row['job_type']),
                    status=JobStatus(row['status']),
                    created_at=datetime.fromisoformat(row['created_at']),
                    started_at=datetime.fromisoformat(row['started_at']) if row['started_at'] else None,
                    completed_at=datetime.fromisoformat(row['completed_at']) if row['completed_at'] else None,
                    error_message=row['error_message'],
                    result_data=row['result_data']
                )
                for row in rows
            ]
        except sqlite3.Error as e:
            logging.error(f"Error getting jobs for episode: {e}")
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