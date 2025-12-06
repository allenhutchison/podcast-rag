"""Repository pattern implementation for podcast data persistence.

Provides an abstract interface and SQLAlchemy implementation for database operations.
Supports both SQLite (local development) and PostgreSQL (Cloud SQL production).
"""

import logging
import os
import shutil
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from .models import Base, Episode, Podcast

logger = logging.getLogger(__name__)


class PodcastRepositoryInterface(ABC):
    """Abstract interface for podcast data persistence.

    Implementations must support both SQLite and PostgreSQL backends.
    """

    # --- Podcast Operations ---

    @abstractmethod
    def create_podcast(self, feed_url: str, title: str, **kwargs) -> Podcast:
        """Create a new podcast subscription."""
        pass

    @abstractmethod
    def get_podcast(self, podcast_id: str) -> Optional[Podcast]:
        """Get podcast by ID."""
        pass

    @abstractmethod
    def get_podcast_by_feed_url(self, feed_url: str) -> Optional[Podcast]:
        """Get podcast by feed URL."""
        pass

    @abstractmethod
    def list_podcasts(
        self, subscribed_only: bool = True, limit: Optional[int] = None
    ) -> List[Podcast]:
        """List all podcasts, optionally filtering by subscription status."""
        pass

    @abstractmethod
    def update_podcast(self, podcast_id: str, **kwargs) -> Optional[Podcast]:
        """Update podcast attributes."""
        pass

    @abstractmethod
    def delete_podcast(self, podcast_id: str, delete_files: bool = False) -> bool:
        """Delete a podcast and optionally its files."""
        pass

    # --- Episode Operations ---

    @abstractmethod
    def create_episode(
        self,
        podcast_id: str,
        guid: str,
        title: str,
        enclosure_url: str,
        enclosure_type: str,
        **kwargs,
    ) -> Episode:
        """Create a new episode."""
        pass

    @abstractmethod
    def get_episode(self, episode_id: str) -> Optional[Episode]:
        """Get episode by ID."""
        pass

    @abstractmethod
    def get_episode_by_guid(self, podcast_id: str, guid: str) -> Optional[Episode]:
        """Get episode by GUID within a podcast."""
        pass

    @abstractmethod
    def list_episodes(
        self,
        podcast_id: Optional[str] = None,
        download_status: Optional[str] = None,
        transcript_status: Optional[str] = None,
        file_search_status: Optional[str] = None,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> List[Episode]:
        """List episodes with optional filtering."""
        pass

    @abstractmethod
    def update_episode(self, episode_id: str, **kwargs) -> Optional[Episode]:
        """Update episode attributes."""
        pass

    @abstractmethod
    def delete_episode(self, episode_id: str, delete_files: bool = False) -> bool:
        """Delete an episode and optionally its files."""
        pass

    # --- Batch Operations ---

    @abstractmethod
    def get_or_create_episode(
        self,
        podcast_id: str,
        guid: str,
        title: str,
        enclosure_url: str,
        enclosure_type: str,
        **kwargs,
    ) -> tuple[Episode, bool]:
        """Get existing episode or create new one. Returns (episode, created)."""
        pass

    @abstractmethod
    def get_episodes_pending_download(self, limit: int = 10) -> List[Episode]:
        """Get episodes that need to be downloaded."""
        pass

    @abstractmethod
    def get_episodes_pending_transcription(self, limit: int = 10) -> List[Episode]:
        """Get downloaded episodes that need transcription."""
        pass

    @abstractmethod
    def get_episodes_pending_metadata(self, limit: int = 10) -> List[Episode]:
        """Get transcribed episodes that need metadata extraction."""
        pass

    @abstractmethod
    def get_episodes_pending_indexing(self, limit: int = 10) -> List[Episode]:
        """Get episodes with metadata that need File Search indexing."""
        pass

    @abstractmethod
    def get_episodes_ready_for_cleanup(self, limit: int = 10) -> List[Episode]:
        """Get fully processed episodes with audio files that can be deleted."""
        pass

    # --- Status Update Helpers ---

    @abstractmethod
    def mark_download_started(self, episode_id: str) -> None:
        """Mark episode as currently downloading."""
        pass

    @abstractmethod
    def mark_download_complete(
        self, episode_id: str, local_path: str, file_size: int, file_hash: str
    ) -> None:
        """Mark episode download as complete."""
        pass

    @abstractmethod
    def mark_download_failed(self, episode_id: str, error: str) -> None:
        """Mark episode download as failed."""
        pass

    @abstractmethod
    def mark_transcript_started(self, episode_id: str) -> None:
        """Mark episode as currently being transcribed."""
        pass

    @abstractmethod
    def mark_transcript_complete(self, episode_id: str, transcript_path: str) -> None:
        """Mark episode transcription as complete."""
        pass

    @abstractmethod
    def mark_transcript_failed(self, episode_id: str, error: str) -> None:
        """Mark episode transcription as failed."""
        pass

    @abstractmethod
    def mark_metadata_started(self, episode_id: str) -> None:
        """Mark episode metadata extraction as started."""
        pass

    @abstractmethod
    def mark_metadata_complete(
        self,
        episode_id: str,
        metadata_path: str,
        summary: Optional[str] = None,
        keywords: Optional[List[str]] = None,
        hosts: Optional[List[str]] = None,
        guests: Optional[List[str]] = None,
    ) -> None:
        """Mark episode metadata extraction as complete."""
        pass

    @abstractmethod
    def mark_metadata_failed(self, episode_id: str, error: str) -> None:
        """Mark episode metadata extraction as failed."""
        pass

    @abstractmethod
    def mark_indexing_started(self, episode_id: str) -> None:
        """Mark episode as being uploaded to File Search."""
        pass

    @abstractmethod
    def mark_indexing_complete(
        self, episode_id: str, resource_name: str, display_name: str
    ) -> None:
        """Mark episode File Search indexing as complete."""
        pass

    @abstractmethod
    def mark_indexing_failed(self, episode_id: str, error: str) -> None:
        """Mark episode File Search indexing as failed."""
        pass

    @abstractmethod
    def mark_audio_cleaned_up(self, episode_id: str) -> None:
        """Mark episode audio file as deleted after processing."""
        pass

    # --- Statistics ---

    @abstractmethod
    def get_podcast_stats(self, podcast_id: str) -> Dict[str, Any]:
        """Get statistics for a podcast."""
        pass

    @abstractmethod
    def get_overall_stats(self) -> Dict[str, Any]:
        """Get overall system statistics."""
        pass

    # --- Connection Management ---

    @abstractmethod
    def close(self) -> None:
        """Close database connection."""
        pass


class SQLAlchemyPodcastRepository(PodcastRepositoryInterface):
    """SQLAlchemy-based implementation of the podcast repository.

    Supports SQLite for local development and PostgreSQL for production.
    """

    def __init__(
        self,
        database_url: str,
        pool_size: int = 5,
        max_overflow: int = 10,
        echo: bool = False,
    ):
        """Initialize the repository with database connection.

        Args:
            database_url: SQLAlchemy database URL
            pool_size: Connection pool size (ignored for SQLite)
            max_overflow: Maximum overflow connections (ignored for SQLite)
            echo: Whether to log SQL statements
        """
        self.database_url = database_url

        # SQLite doesn't support connection pooling
        if database_url.startswith("sqlite"):
            self.engine = create_engine(
                database_url,
                echo=echo,
                connect_args={"check_same_thread": False},
            )
        else:
            self.engine = create_engine(
                database_url,
                pool_size=pool_size,
                max_overflow=max_overflow,
                echo=echo,
            )

        self.SessionLocal = sessionmaker(bind=self.engine)

        # Create tables if they don't exist
        Base.metadata.create_all(self.engine)
        logger.info(f"Database initialized: {database_url.split('@')[-1] if '@' in database_url else database_url}")

    def _get_session(self) -> Session:
        """Get a new database session."""
        return self.SessionLocal()

    # --- Podcast Operations ---

    def create_podcast(self, feed_url: str, title: str, **kwargs) -> Podcast:
        """Create a new podcast subscription."""
        with self._get_session() as session:
            podcast = Podcast(feed_url=feed_url, title=title, **kwargs)
            session.add(podcast)
            session.commit()
            session.refresh(podcast)
            logger.info(f"Created podcast: {title} ({podcast.id})")
            return podcast

    def get_podcast(self, podcast_id: str) -> Optional[Podcast]:
        """Get podcast by ID."""
        with self._get_session() as session:
            return session.get(Podcast, podcast_id)

    def get_podcast_by_feed_url(self, feed_url: str) -> Optional[Podcast]:
        """Get podcast by feed URL."""
        with self._get_session() as session:
            stmt = select(Podcast).where(Podcast.feed_url == feed_url)
            return session.scalar(stmt)

    def list_podcasts(
        self, subscribed_only: bool = True, limit: Optional[int] = None
    ) -> List[Podcast]:
        """List all podcasts, optionally filtering by subscription status."""
        with self._get_session() as session:
            stmt = select(Podcast)
            if subscribed_only:
                stmt = stmt.where(Podcast.is_subscribed == True)
            stmt = stmt.order_by(Podcast.title)
            if limit:
                stmt = stmt.limit(limit)
            return list(session.scalars(stmt).all())

    def update_podcast(self, podcast_id: str, **kwargs) -> Optional[Podcast]:
        """Update podcast attributes."""
        with self._get_session() as session:
            podcast = session.get(Podcast, podcast_id)
            if podcast:
                for key, value in kwargs.items():
                    if hasattr(podcast, key):
                        setattr(podcast, key, value)
                podcast.updated_at = datetime.utcnow()
                session.commit()
                session.refresh(podcast)
                logger.debug(f"Updated podcast {podcast_id}: {kwargs.keys()}")
            return podcast

    def delete_podcast(self, podcast_id: str, delete_files: bool = False) -> bool:
        """Delete a podcast and optionally its files."""
        with self._get_session() as session:
            podcast = session.get(Podcast, podcast_id)
            if not podcast:
                return False

            if delete_files and podcast.local_directory:
                if os.path.exists(podcast.local_directory):
                    shutil.rmtree(podcast.local_directory)
                    logger.info(f"Deleted podcast directory: {podcast.local_directory}")

            session.delete(podcast)
            session.commit()
            logger.info(f"Deleted podcast: {podcast.title} ({podcast_id})")
            return True

    # --- Episode Operations ---

    def create_episode(
        self,
        podcast_id: str,
        guid: str,
        title: str,
        enclosure_url: str,
        enclosure_type: str,
        **kwargs,
    ) -> Episode:
        """Create a new episode."""
        with self._get_session() as session:
            episode = Episode(
                podcast_id=podcast_id,
                guid=guid,
                title=title,
                enclosure_url=enclosure_url,
                enclosure_type=enclosure_type,
                **kwargs,
            )
            session.add(episode)
            session.commit()
            session.refresh(episode)
            logger.debug(f"Created episode: {title} ({episode.id})")
            return episode

    def get_episode(self, episode_id: str) -> Optional[Episode]:
        """Get episode by ID."""
        with self._get_session() as session:
            return session.get(Episode, episode_id)

    def get_episode_by_guid(self, podcast_id: str, guid: str) -> Optional[Episode]:
        """Get episode by GUID within a podcast."""
        with self._get_session() as session:
            stmt = select(Episode).where(
                Episode.podcast_id == podcast_id, Episode.guid == guid
            )
            return session.scalar(stmt)

    def list_episodes(
        self,
        podcast_id: Optional[str] = None,
        download_status: Optional[str] = None,
        transcript_status: Optional[str] = None,
        file_search_status: Optional[str] = None,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> List[Episode]:
        """List episodes with optional filtering."""
        with self._get_session() as session:
            stmt = select(Episode)

            if podcast_id:
                stmt = stmt.where(Episode.podcast_id == podcast_id)
            if download_status:
                stmt = stmt.where(Episode.download_status == download_status)
            if transcript_status:
                stmt = stmt.where(Episode.transcript_status == transcript_status)
            if file_search_status:
                stmt = stmt.where(Episode.file_search_status == file_search_status)

            stmt = stmt.order_by(Episode.published_date.desc())
            stmt = stmt.offset(offset)
            if limit:
                stmt = stmt.limit(limit)

            return list(session.scalars(stmt).all())

    def update_episode(self, episode_id: str, **kwargs) -> Optional[Episode]:
        """Update episode attributes."""
        with self._get_session() as session:
            episode = session.get(Episode, episode_id)
            if episode:
                for key, value in kwargs.items():
                    if hasattr(episode, key):
                        setattr(episode, key, value)
                episode.updated_at = datetime.utcnow()
                session.commit()
                session.refresh(episode)
                logger.debug(f"Updated episode {episode_id}: {kwargs.keys()}")
            return episode

    def delete_episode(self, episode_id: str, delete_files: bool = False) -> bool:
        """Delete an episode and optionally its files."""
        with self._get_session() as session:
            episode = session.get(Episode, episode_id)
            if not episode:
                return False

            if delete_files:
                for path_attr in ["local_file_path", "transcript_path", "metadata_path"]:
                    path = getattr(episode, path_attr)
                    if path and os.path.exists(path):
                        os.remove(path)
                        logger.debug(f"Deleted file: {path}")

            session.delete(episode)
            session.commit()
            logger.debug(f"Deleted episode: {episode.title} ({episode_id})")
            return True

    # --- Batch Operations ---

    def get_or_create_episode(
        self,
        podcast_id: str,
        guid: str,
        title: str,
        enclosure_url: str,
        enclosure_type: str,
        **kwargs,
    ) -> tuple[Episode, bool]:
        """Get existing episode or create new one. Returns (episode, created)."""
        existing = self.get_episode_by_guid(podcast_id, guid)
        if existing:
            return existing, False

        episode = self.create_episode(
            podcast_id=podcast_id,
            guid=guid,
            title=title,
            enclosure_url=enclosure_url,
            enclosure_type=enclosure_type,
            **kwargs,
        )
        return episode, True

    def get_episodes_pending_download(self, limit: int = 10) -> List[Episode]:
        """Get episodes that need to be downloaded."""
        with self._get_session() as session:
            stmt = (
                select(Episode)
                .where(Episode.download_status == "pending")
                .order_by(Episode.published_date.desc())
                .limit(limit)
            )
            return list(session.scalars(stmt).all())

    def get_episodes_pending_transcription(self, limit: int = 10) -> List[Episode]:
        """Get downloaded episodes that need transcription."""
        with self._get_session() as session:
            stmt = (
                select(Episode)
                .where(
                    Episode.download_status == "completed",
                    Episode.transcript_status == "pending",
                    Episode.local_file_path.isnot(None),
                )
                .order_by(Episode.published_date.desc())
                .limit(limit)
            )
            return list(session.scalars(stmt).all())

    def get_episodes_pending_metadata(self, limit: int = 10) -> List[Episode]:
        """Get transcribed episodes that need metadata extraction."""
        with self._get_session() as session:
            stmt = (
                select(Episode)
                .where(
                    Episode.transcript_status == "completed",
                    Episode.metadata_status == "pending",
                    Episode.transcript_path.isnot(None),
                )
                .order_by(Episode.published_date.desc())
                .limit(limit)
            )
            return list(session.scalars(stmt).all())

    def get_episodes_pending_indexing(self, limit: int = 10) -> List[Episode]:
        """Get episodes with metadata that need File Search indexing."""
        with self._get_session() as session:
            stmt = (
                select(Episode)
                .where(
                    Episode.metadata_status == "completed",
                    Episode.file_search_status == "pending",
                    Episode.transcript_path.isnot(None),
                )
                .order_by(Episode.published_date.desc())
                .limit(limit)
            )
            return list(session.scalars(stmt).all())

    def get_episodes_ready_for_cleanup(self, limit: int = 10) -> List[Episode]:
        """Get fully processed episodes with audio files that can be deleted."""
        with self._get_session() as session:
            stmt = (
                select(Episode)
                .where(
                    Episode.transcript_status == "completed",
                    Episode.metadata_status == "completed",
                    Episode.file_search_status == "indexed",
                    Episode.local_file_path.isnot(None),
                )
                .limit(limit)
            )
            return list(session.scalars(stmt).all())

    # --- Status Update Helpers ---

    def mark_download_started(self, episode_id: str) -> None:
        """Mark episode as currently downloading."""
        self.update_episode(episode_id, download_status="downloading")

    def mark_download_complete(
        self, episode_id: str, local_path: str, file_size: int, file_hash: str
    ) -> None:
        """Mark episode download as complete."""
        self.update_episode(
            episode_id,
            download_status="completed",
            local_file_path=local_path,
            file_size_bytes=file_size,
            file_hash=file_hash,
            downloaded_at=datetime.utcnow(),
            download_error=None,
        )

    def mark_download_failed(self, episode_id: str, error: str) -> None:
        """Mark episode download as failed."""
        self.update_episode(
            episode_id,
            download_status="failed",
            download_error=error,
        )

    def mark_transcript_started(self, episode_id: str) -> None:
        """Mark episode as currently being transcribed."""
        self.update_episode(episode_id, transcript_status="processing")

    def mark_transcript_complete(self, episode_id: str, transcript_path: str) -> None:
        """Mark episode transcription as complete."""
        self.update_episode(
            episode_id,
            transcript_status="completed",
            transcript_path=transcript_path,
            transcribed_at=datetime.utcnow(),
            transcript_error=None,
        )

    def mark_transcript_failed(self, episode_id: str, error: str) -> None:
        """Mark episode transcription as failed."""
        self.update_episode(
            episode_id,
            transcript_status="failed",
            transcript_error=error,
        )

    def mark_metadata_started(self, episode_id: str) -> None:
        """Mark episode metadata extraction as started."""
        self.update_episode(episode_id, metadata_status="processing")

    def mark_metadata_complete(
        self,
        episode_id: str,
        metadata_path: str,
        summary: Optional[str] = None,
        keywords: Optional[List[str]] = None,
        hosts: Optional[List[str]] = None,
        guests: Optional[List[str]] = None,
    ) -> None:
        """Mark episode metadata extraction as complete."""
        self.update_episode(
            episode_id,
            metadata_status="completed",
            metadata_path=metadata_path,
            ai_summary=summary,
            ai_keywords=keywords,
            ai_hosts=hosts,
            ai_guests=guests,
            metadata_error=None,
        )

    def mark_metadata_failed(self, episode_id: str, error: str) -> None:
        """Mark episode metadata extraction as failed."""
        self.update_episode(
            episode_id,
            metadata_status="failed",
            metadata_error=error,
        )

    def mark_indexing_started(self, episode_id: str) -> None:
        """Mark episode as being uploaded to File Search."""
        self.update_episode(episode_id, file_search_status="uploading")

    def mark_indexing_complete(
        self, episode_id: str, resource_name: str, display_name: str
    ) -> None:
        """Mark episode File Search indexing as complete."""
        self.update_episode(
            episode_id,
            file_search_status="indexed",
            file_search_resource_name=resource_name,
            file_search_display_name=display_name,
            file_search_uploaded_at=datetime.utcnow(),
            file_search_error=None,
        )

    def mark_indexing_failed(self, episode_id: str, error: str) -> None:
        """Mark episode File Search indexing as failed."""
        self.update_episode(
            episode_id,
            file_search_status="failed",
            file_search_error=error,
        )

    def mark_audio_cleaned_up(self, episode_id: str) -> None:
        """Mark episode audio file as deleted after processing."""
        episode = self.get_episode(episode_id)
        if episode and episode.local_file_path:
            if os.path.exists(episode.local_file_path):
                os.remove(episode.local_file_path)
                logger.info(f"Deleted audio file: {episode.local_file_path}")
            self.update_episode(episode_id, local_file_path=None)

    # --- Statistics ---

    def get_podcast_stats(self, podcast_id: str) -> Dict[str, Any]:
        """Get statistics for a podcast."""
        with self._get_session() as session:
            podcast = session.get(Podcast, podcast_id)
            if not podcast:
                return {}

            episodes = self.list_episodes(podcast_id=podcast_id, limit=None)

            return {
                "podcast_id": podcast_id,
                "title": podcast.title,
                "total_episodes": len(episodes),
                "pending_download": sum(
                    1 for e in episodes if e.download_status == "pending"
                ),
                "downloading": sum(
                    1 for e in episodes if e.download_status == "downloading"
                ),
                "downloaded": sum(
                    1 for e in episodes if e.download_status == "completed"
                ),
                "download_failed": sum(
                    1 for e in episodes if e.download_status == "failed"
                ),
                "pending_transcription": sum(
                    1 for e in episodes if e.transcript_status == "pending"
                ),
                "transcribed": sum(
                    1 for e in episodes if e.transcript_status == "completed"
                ),
                "indexed": sum(
                    1 for e in episodes if e.file_search_status == "indexed"
                ),
                "fully_processed": sum(1 for e in episodes if e.is_fully_processed),
            }

    def get_overall_stats(self) -> Dict[str, Any]:
        """Get overall system statistics."""
        with self._get_session() as session:
            podcasts = self.list_podcasts(subscribed_only=False, limit=None)
            episodes = self.list_episodes(limit=None)

            return {
                "total_podcasts": len(podcasts),
                "subscribed_podcasts": sum(1 for p in podcasts if p.is_subscribed),
                "total_episodes": len(episodes),
                "pending_download": sum(
                    1 for e in episodes if e.download_status == "pending"
                ),
                "downloading": sum(
                    1 for e in episodes if e.download_status == "downloading"
                ),
                "downloaded": sum(
                    1 for e in episodes if e.download_status == "completed"
                ),
                "download_failed": sum(
                    1 for e in episodes if e.download_status == "failed"
                ),
                "pending_transcription": sum(
                    1 for e in episodes if e.transcript_status == "pending"
                ),
                "transcribing": sum(
                    1 for e in episodes if e.transcript_status == "processing"
                ),
                "transcribed": sum(
                    1 for e in episodes if e.transcript_status == "completed"
                ),
                "transcript_failed": sum(
                    1 for e in episodes if e.transcript_status == "failed"
                ),
                "pending_indexing": sum(
                    1 for e in episodes if e.file_search_status == "pending"
                ),
                "indexed": sum(
                    1 for e in episodes if e.file_search_status == "indexed"
                ),
                "fully_processed": sum(1 for e in episodes if e.is_fully_processed),
            }

    # --- Connection Management ---

    def close(self) -> None:
        """Close database connection."""
        self.engine.dispose()
        logger.info("Database connection closed")
