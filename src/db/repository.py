"""Repository pattern implementation for podcast data persistence.

Provides an abstract interface and SQLAlchemy implementation for database operations.
Supports both SQLite (local development) and PostgreSQL (Cloud SQL production).
"""

import logging
import os
import shutil
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import String, cast, create_engine, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, sessionmaker

from .models import Base, Episode, Podcast, User, UserSubscription

logger = logging.getLogger(__name__)


def _escape_like_pattern(value: str) -> str:
    """
    Escape special characters for use in SQL LIKE patterns.

    Escapes backslashes, percent signs, underscores, and double quotes
    to prevent unintended pattern matching or injection in LIKE clauses.

    The escape order matters: backslashes must be escaped first since
    they are used as the escape character.

    Args:
        value: The raw string to escape

    Returns:
        str: Escaped string safe for use in LIKE patterns
    """
    # Escape backslash first (it's the escape character)
    escaped = value.replace('\\', '\\\\')
    # Escape LIKE wildcards
    escaped = escaped.replace('%', '\\%')
    escaped = escaped.replace('_', '\\_')
    # Escape double quotes (used in JSON string matching)
    escaped = escaped.replace('"', '\\"')
    return escaped


class PodcastRepositoryInterface(ABC):
    """Abstract interface for podcast data persistence.

    Implementations must support both SQLite and PostgreSQL backends.
    """

    # --- Podcast Operations ---

    @abstractmethod
    def create_podcast(self, feed_url: str, title: str, **kwargs) -> Podcast:
        """
        Create and persist a new podcast subscription for the given feed URL and title.
        
        Parameters:
            feed_url (str): RSS or Atom feed URL of the podcast.
            title (str): Display title for the podcast subscription.
            **kwargs: Additional Podcast attributes to set (e.g., description, is_subscribed, image_url).
        
        Returns:
            Podcast: The persisted Podcast instance with updated identifiers and timestamps.
        """
        pass

    @abstractmethod
    def get_podcast(self, podcast_id: str) -> Optional[Podcast]:
        """
        Retrieve a podcast by its identifier.
        
        Returns:
            Podcast if a podcast with the given ID exists, `None` otherwise.
        """
        pass

    @abstractmethod
    def get_podcast_by_feed_url(self, feed_url: str) -> Optional[Podcast]:
        """
        Retrieve a podcast matching the given feed URL.
        
        Parameters:
            feed_url (str): The podcast RSS/Atom feed URL to look up.
        
        Returns:
            The matching `Podcast` if found, `None` otherwise.
        """
        pass

    @abstractmethod
    def list_podcasts(
        self, subscribed_only: bool = True, limit: Optional[int] = None
    ) -> List[Podcast]:
        """
        Return podcasts optionally filtered to subscribed ones and limited in count.
        
        Queries podcasts ordered by title. If `subscribed_only` is True, only podcasts with an active subscription are returned. `limit` caps the number of results when provided.
        
        Parameters:
            subscribed_only (bool): If True, include only subscribed podcasts. Default is True.
            limit (Optional[int]): Maximum number of podcasts to return; if None, no limit is applied.
        
        Returns:
            List[Podcast]: Podcasts matching the filters, ordered by title.
        """
        pass

    @abstractmethod
    def update_podcast(self, podcast_id: str, **kwargs) -> Optional[Podcast]:
        """
        Update attributes of an existing podcast.
        
        Parameters:
            podcast_id (str): The podcast's primary key.
            **kwargs: Podcast fields to update (for example `title`, `feed_url`, `is_subscribed`).
        
        Returns:
            Optional[Podcast]: The updated Podcast instance if found and updated, `None` if no podcast with `podcast_id` exists.
        """
        pass

    @abstractmethod
    def delete_podcast(self, podcast_id: str, delete_files: bool = False) -> bool:
        """
        Remove a podcast record from the database.
        
        If `delete_files` is True, associated local files (podcast directory and contained files) will be removed from disk before the database record is deleted.
        
        Parameters:
            podcast_id (str): The primary key/identifier of the podcast to delete.
            delete_files (bool): Whether to remove associated local files from disk prior to deleting the record.
        
        Returns:
            bool: `True` if a podcast was found and deleted, `False` if no podcast with `podcast_id` exists.
        """
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
        """
        Create and persist a new Episode for the given podcast.
        
        Parameters:
            podcast_id (str): ID of the podcast to associate the episode with.
            guid (str): Globally unique identifier for the episode (within the podcast).
            title (str): Episode title.
            enclosure_url (str): URL of the episode media file.
            enclosure_type (str): MIME type of the enclosure (e.g., "audio/mpeg").
            **kwargs: Optional episode attributes such as `published_date`, `duration`,
                `summary`, `local_file_path`, `transcript_path`, `metadata_path`, and other
                model fields to set on creation.
        
        Returns:
            Episode: The newly created and persisted Episode instance.
        """
        pass

    @abstractmethod
    def get_episode(self, episode_id: str) -> Optional[Episode]:
        """
        Retrieve an episode by its primary key.
        
        Returns:
            The Episode instance if found, `None` otherwise.
        """
        pass

    @abstractmethod
    def get_episode_by_guid(self, podcast_id: str, guid: str) -> Optional[Episode]:
        """
        Retrieve an episode by its GUID within the specified podcast.

        Parameters:
            podcast_id (str): The podcast's primary identifier.
            guid (str): The episode GUID as provided by the podcast feed.

        Returns:
            Optional[Episode]: The matching Episode if found, `None` otherwise.
        """
        pass

    @abstractmethod
    def get_episode_by_file_search_display_name(
        self, display_name: str
    ) -> Optional[Episode]:
        """
        Retrieve an episode by its File Search display name.

        Used by the web app to look up episode metadata for citations.

        Parameters:
            display_name (str): The file_search_display_name (e.g., "episode_transcription.txt")

        Returns:
            Optional[Episode]: The matching Episode if found, `None` otherwise.
        """
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
        """
        List episodes, optionally filtered and paginated.
        
        Parameters:
            podcast_id (Optional[str]): If provided, only episodes belonging to this podcast are returned.
            download_status (Optional[str]): If provided, filter episodes by download status (e.g., "pending", "completed", "failed").
            transcript_status (Optional[str]): If provided, filter episodes by transcript status (e.g., "pending", "completed", "failed").
            file_search_status (Optional[str]): If provided, filter episodes by file search/indexing status (e.g., "pending", "indexed", "failed").
            limit (Optional[int]): Maximum number of episodes to return. If None, no limit is applied.
            offset (int): Number of episodes to skip before returning results (for pagination).
        
        Returns:
            List[Episode]: A list of Episode objects matching the provided filters, ordered by published date descending and subject to offset/limit.
        """
        pass

    @abstractmethod
    def update_episode(self, episode_id: str, **kwargs) -> Optional[Episode]:
        """
        Update attributes of an episode record.
        
        Parameters:
            episode_id (str): The primary key of the episode to update.
            **kwargs: Episode attributes to set; keys matching model fields will be applied, other keys are ignored.
        
        Returns:
            Optional[Episode]: The updated Episode instance if found and updated, `None` if no episode with `episode_id` exists.
        """
        pass

    @abstractmethod
    def delete_episode(self, episode_id: str, delete_files: bool = False) -> bool:
        """
        Delete the episode identified by episode_id and, optionally, its associated files.
        
        Parameters:
            episode_id (str): The primary key / identifier of the episode to delete.
            delete_files (bool): If True, remove associated local files (e.g., audio, transcript, metadata) when present.
        
        Returns:
            bool: `True` if the episode existed and was deleted, `False` otherwise.
        """
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
        """
        Retrieve an episode by GUID within a podcast, creating and persisting a new Episode when none exists.
        
        Parameters:
            podcast_id (str): ID of the podcast the episode belongs to.
            guid (str): Episode GUID used to identify uniqueness within the podcast.
            title (str): Episode title to use when creating a new episode.
            enclosure_url (str): URL of the episode media enclosure.
            enclosure_type (str): MIME type or media type of the enclosure (e.g., "audio/mpeg").
            **kwargs: Optional additional Episode fields to set when creating a new episode (e.g., published_date, duration).
        
        Returns:
            tuple[Episode, bool]: A tuple of (episode, created) where `episode` is the found or newly created Episode and `created` is `True` if a new record was created, `False` if an existing record was returned.
        """
        pass

    @abstractmethod
    def search_episodes_by_keyword(
        self, keyword: str, limit: int = 50
    ) -> List[Episode]:
        """
        Search for episodes containing the specified keyword in ai_keywords.

        Parameters:
            keyword (str): The keyword to search for (case-insensitive).
            limit (int): Maximum number of episodes to return (default 50).

        Returns:
            List[Episode]: Episodes with matching keywords, ordered by published_date descending.
        """
        pass

    @abstractmethod
    def search_episodes_by_person(
        self, name: str, limit: int = 50
    ) -> List[Episode]:
        """
        Search for episodes featuring the specified person as host or guest.

        Parameters:
            name (str): The person's name to search for (case-insensitive).
            limit (int): Maximum number of episodes to return (default 50).

        Returns:
            List[Episode]: Episodes with matching hosts or guests, ordered by published_date descending.
        """
        pass

    @abstractmethod
    def get_episodes_pending_download(self, limit: int = 10) -> List[Episode]:
        """
        Retrieve episodes that are pending download.

        Returns episodes whose download_status is "pending", ordered by published_date descending and limited to the most recent `limit` entries.

        Parameters:
            limit (int): Maximum number of episodes to return (default 10).

        Returns:
            List[Episode]: A list of Episode objects pending download.
        """
        pass

    @abstractmethod
    def get_episodes_pending_transcription(self, limit: int = 10) -> List[Episode]:
        """
        Retrieve downloaded episodes that still require transcription.
        
        Parameters:
            limit (int): Maximum number of episodes to return.
        
        Returns:
            List[Episode]: Episodes where the download is completed, transcription has not started or is pending, and a local audio file is present, ordered by most recently published.
        """
        pass

    @abstractmethod
    def get_episodes_pending_metadata(self, limit: int = 10) -> List[Episode]:
        """
        Return transcribed episodes that still require metadata extraction.
        
        Retrieves episodes whose transcription is complete, whose metadata status is pending, and that have a transcript path present; results are ordered by published date (newest first) and limited by `limit`.
        
        Parameters:
            limit (int): Maximum number of episodes to return.
        
        Returns:
            List[Episode]: A list of episodes matching the metadata-pending criteria.
        """
        pass

    @abstractmethod
    def get_episodes_pending_indexing(self, limit: int = 10) -> List[Episode]:
        """
        Return episodes whose metadata is complete and are awaiting File Search indexing.
        
        Episodes returned have metadata_status set to "completed", file_search_status set to "pending", and a transcript path present. Results are ordered by published date (newest first) and limited to at most `limit` items.
        
        Returns:
            List[Episode]: A list of episodes matching the indexing criteria, ordered by published date descending, up to `limit`.
        """
        pass

    @abstractmethod
    def get_episodes_ready_for_cleanup(self, limit: int = 10) -> List[Episode]:
        """
        Identify episodes whose audio files can be removed.
        
        Episodes returned have a local audio file present and have completed transcription and metadata processing, with file-search indexing marked as completed. Results are limited to the most relevant entries according to `limit`.
        
        Parameters:
        	limit (int): Maximum number of episodes to return.
        
        Returns:
        	List[Episode]: Episodes eligible for audio cleanup.
        """
        pass

    # --- Status Update Helpers ---

    @abstractmethod
    def mark_download_started(self, episode_id: str) -> None:
        """
        Mark the episode identified by episode_id as downloading by setting its download status to 'in_progress' and recording the download start timestamp.
        """
        pass

    @abstractmethod
    def mark_download_complete(
        self, episode_id: str, local_path: str, file_size: int, file_hash: str
    ) -> None:
        """
        Mark an episode as downloaded and record the downloaded file's metadata.
        
        Parameters:
            episode_id (str): ID of the episode to update.
            local_path (str): Filesystem path where the downloaded file is stored.
            file_size (int): Size of the downloaded file in bytes.
            file_hash (str): Hash of the downloaded file (for integrity verification, e.g. SHA-256).
        """
        pass

    @abstractmethod
    def mark_download_failed(self, episode_id: str, error: str) -> None:
        """
        Mark an episode's download as failed and record the failure reason.
        
        Updates the episode's download-related status to indicate failure and stores the provided error message for diagnostics.
        
        Parameters:
            episode_id (str): The unique identifier of the episode to update.
            error (str): A human-readable error message or failure reason to record.
        """
        pass

    @abstractmethod
    def mark_transcript_started(self, episode_id: str) -> None:
        """
        Mark an episode as having transcription started.
        
        Sets the episode's transcript status to "in_progress", records the transcription start timestamp, and clears any existing transcript error on the episode record.
        
        Parameters:
            episode_id (str): The primary key/ID of the episode to update.
        """
        pass

    @abstractmethod
    def mark_transcript_complete(
        self,
        episode_id: str,
        transcript_text: str,
        transcript_path: Optional[str] = None,
    ) -> None:
        """
        Mark an episode's transcription as completed and store the transcript content.

        Updates the episode record to store the transcript text, mark transcription as completed,
        record the completion timestamp, and persist the change to the database.

        Parameters:
            episode_id (str): Primary key of the episode to update.
            transcript_text (str): Full transcript content.
            transcript_path (str, optional): Legacy file path, kept for backward compatibility.
        """
        pass

    @abstractmethod
    def mark_transcript_failed(self, episode_id: str, error: str) -> None:
        """
        Mark an episode's transcription as failed and record the failure reason.
        
        Parameters:
            episode_id (str): Identifier of the episode whose transcription failed.
            error (str): Human-readable error message or reason for the failure.
        """
        pass

    @abstractmethod
    def mark_metadata_started(self, episode_id: str) -> None:
        """Mark episode metadata extraction as started."""
        pass

    @abstractmethod
    def mark_metadata_complete(
        self,
        episode_id: str,
        summary: Optional[str] = None,
        keywords: Optional[List[str]] = None,
        hosts: Optional[List[str]] = None,
        guests: Optional[List[str]] = None,
        mp3_artist: Optional[str] = None,
        mp3_album: Optional[str] = None,
        metadata_path: Optional[str] = None,
    ) -> None:
        """
        Record that metadata extraction for an episode completed and persist the extracted metadata.

        Parameters:
            episode_id (str): Identifier of the episode to update.
            summary (Optional[str]): Short textual summary extracted for the episode.
            keywords (Optional[List[str]]): List of keywords or tags extracted from the episode.
            hosts (Optional[List[str]]): List of host names identified in the episode.
            guests (Optional[List[str]]): List of guest names identified in the episode.
            mp3_artist (Optional[str]): MP3 ID3 artist tag from the audio file.
            mp3_album (Optional[str]): MP3 ID3 album tag from the audio file.
            metadata_path (Optional[str]): Legacy file path, kept for backward compatibility.
        """
        pass

    @abstractmethod
    def mark_metadata_failed(self, episode_id: str, error: str) -> None:
        """
        Mark an episode's metadata extraction as failed and record the failure reason.
        
        Parameters:
            episode_id (str): ID of the episode to update.
            error (str): Human-readable error message or failure reason to store.
        """
        pass

    @abstractmethod
    def mark_indexing_started(self, episode_id: str) -> None:
        """
        Mark an episode as in-progress for File Search indexing.
        
        Updates the episode's file search status to "indexing", records the indexing start time, and clears any previous indexing error for the specified episode.
        
        Parameters:
            episode_id (str): Primary key of the episode to update.
        """
        pass

    @abstractmethod
    def mark_indexing_complete(
        self, episode_id: str, resource_name: str, display_name: str
    ) -> None:
        """
        Record that an episode's file-search indexing finished and store the index resource details.
        
        Parameters:
            episode_id (str): Identifier of the episode whose indexing completed.
            resource_name (str): Unique name or identifier of the index resource created for the episode.
            display_name (str): Human-readable name for the indexed resource to display in UIs or logs.
        """
        pass

    @abstractmethod
    def mark_indexing_failed(self, episode_id: str, error: str) -> None:
        """
        Record that File Search indexing for the specified episode failed, store the provided error message, and persist the status update with an associated timestamp.
        
        Parameters:
            episode_id (str): The ID of the episode whose indexing failed.
            error (str): A human-readable error message describing the failure.
        """
        pass

    @abstractmethod
    def mark_audio_cleaned_up(self, episode_id: str) -> None:
        """
        Clear an episode's local audio file and remove its on-disk file if present.
        
        Deletes the episode's local audio file from disk (when a path exists) and clears the stored local file path on the episode record so the database no longer references the removed file.
        
        Parameters:
            episode_id (str): The primary key of the episode to clean up.
        """
        pass

    # --- Transcript Access ---

    @abstractmethod
    def get_transcript_text(self, episode_id: str) -> Optional[str]:
        """
        Get the transcript text for an episode.

        Returns the transcript content from the database (`transcript_text` column).
        For legacy episodes with only `transcript_path`, reads the file content.

        Parameters:
            episode_id (str): ID of the episode.

        Returns:
            The transcript text if available, None otherwise.
        """
        pass

    # --- Statistics ---

    @abstractmethod
    def get_podcast_stats(self, podcast_id: str) -> Dict[str, Any]:
        """
        Compute statistics for a single podcast.
        
        Parameters:
            podcast_id (str): The podcast primary key to compute statistics for.
        
        Returns:
            stats (Dict[str, Any]): A dictionary containing per-podcast statistics and counts, typically including:
                - podcast (dict): A short snapshot of the podcast (e.g., `id`, `title`, `feed_url`, `is_subscribed`).
                - total_episodes (int): Total number of episodes for the podcast.
                - by_download_status (dict): Counts keyed by download status (e.g., `pending`, `in_progress`, `completed`, `failed`).
                - by_transcript_status (dict): Counts keyed by transcript status (e.g., `pending`, `in_progress`, `completed`, `failed`).
                - by_metadata_status (dict): Counts keyed by metadata status (e.g., `pending`, `in_progress`, `completed`, `failed`).
                - by_indexing_status (dict): Counts keyed by file-search/indexing status (e.g., `pending`, `indexed`, `failed`).
                - ready_for_cleanup (int): Number of episodes eligible for audio file cleanup.
        """
        pass

    @abstractmethod
    def get_overall_stats(self) -> Dict[str, Any]:
        """
        Collects system-wide statistics for podcasts and episodes.
        
        Returns:
            stats (Dict[str, Any]): A dictionary containing aggregated system metrics, including:
                - total_podcasts: total number of podcasts tracked.
                - total_episodes: total number of episodes tracked.
                - counts_by_download_status: mapping of download status -> count.
                - counts_by_transcript_status: mapping of transcript status -> count.
                - counts_by_metadata_status: mapping of metadata status -> count.
                - counts_by_file_search_status: mapping of file-search/indexing status -> count.
                - pending_download: count of episodes awaiting download.
                - pending_transcription: count of downloaded episodes awaiting transcription.
                - pending_metadata: count of transcribed episodes awaiting metadata extraction.
                - pending_indexing: count of episodes awaiting file-search indexing.
                - ready_for_cleanup: count of episodes eligible for audio file cleanup.
        """
        pass

    # --- Pipeline Operations ---

    @abstractmethod
    def get_download_buffer_count(self) -> int:
        """Count episodes ready for transcription (downloaded, pending transcription).

        Returns:
            Number of episodes in the download buffer ready for transcription.
        """
        pass

    @abstractmethod
    def get_next_for_transcription(self) -> Optional[Episode]:
        """Get the next episode ready for transcription.

        Returns the most recently published episode that is downloaded
        and pending transcription, excluding permanently failed episodes.

        Returns:
            Episode ready for transcription, or None if none available.
        """
        pass

    @abstractmethod
    def get_next_pending_post_processing(self) -> Optional[Episode]:
        """Get the next episode needing post-processing.

        Returns an episode that has completed transcription but still
        needs metadata extraction, indexing, or cleanup.

        Returns:
            Episode needing post-processing, or None if none available.
        """
        pass

    @abstractmethod
    def increment_retry_count(self, episode_id: str, stage: str) -> int:
        """Increment the retry count for a processing stage.

        Args:
            episode_id: ID of the episode.
            stage: Processing stage ("transcript", "metadata", or "indexing").

        Returns:
            The new retry count after incrementing.
        """
        pass

    @abstractmethod
    def mark_permanently_failed(
        self, episode_id: str, stage: str, error: str
    ) -> None:
        """Mark an episode as permanently failed for a processing stage.

        Args:
            episode_id: ID of the episode.
            stage: Processing stage ("transcript", "metadata", or "indexing").
            error: Error message describing the failure.
        """
        pass

    @abstractmethod
    def reset_episode_for_retry(self, episode_id: str, stage: str) -> None:
        """Reset an episode's status to pending for retry.

        Clears the error and resets status to pending for the given stage.

        Args:
            episode_id: ID of the episode.
            stage: Processing stage ("transcript", "metadata", or "indexing").
        """
        pass

    # --- User Operations ---

    @abstractmethod
    def create_user(
        self,
        google_id: str,
        email: str,
        name: Optional[str] = None,
        picture_url: Optional[str] = None,
    ) -> User:
        """Create a new user from Google OAuth data.

        Args:
            google_id: Google's unique user identifier.
            email: User's email address.
            name: User's display name (optional).
            picture_url: URL to user's profile picture (optional).

        Returns:
            User: The newly created user.
        """
        pass

    @abstractmethod
    def get_user(self, user_id: str) -> Optional[User]:
        """Get a user by ID.

        Args:
            user_id: The user's UUID.

        Returns:
            Optional[User]: The user if found, None otherwise.
        """
        pass

    @abstractmethod
    def get_user_by_google_id(self, google_id: str) -> Optional[User]:
        """Get a user by their Google ID.

        Args:
            google_id: Google's unique user identifier.

        Returns:
            Optional[User]: The user if found, None otherwise.
        """
        pass

    @abstractmethod
    def get_user_by_email(self, email: str) -> Optional[User]:
        """Get a user by email address.

        Args:
            email: User's email address.

        Returns:
            Optional[User]: The user if found, None otherwise.
        """
        pass

    @abstractmethod
    def update_user(self, user_id: str, **kwargs) -> Optional[User]:
        """Update a user's attributes.

        Args:
            user_id: The user's UUID.
            **kwargs: Attributes to update (name, picture_url, last_login, etc.).

        Returns:
            Optional[User]: The updated user if found, None otherwise.
        """
        pass

    # --- Subscription Operations ---

    @abstractmethod
    def subscribe_user_to_podcast(self, user_id: str, podcast_id: str) -> UserSubscription:
        """Subscribe a user to a podcast.

        Args:
            user_id: The user's UUID.
            podcast_id: The podcast's UUID.

        Returns:
            UserSubscription: The subscription record.

        Raises:
            IntegrityError: If subscription already exists.
        """
        pass

    @abstractmethod
    def unsubscribe_user_from_podcast(self, user_id: str, podcast_id: str) -> bool:
        """Unsubscribe a user from a podcast.

        Args:
            user_id: The user's UUID.
            podcast_id: The podcast's UUID.

        Returns:
            bool: True if unsubscribed, False if subscription didn't exist.
        """
        pass

    @abstractmethod
    def get_user_subscriptions(self, user_id: str) -> List[Podcast]:
        """Get all podcasts a user is subscribed to.

        Args:
            user_id: The user's UUID.

        Returns:
            List[Podcast]: List of podcasts the user is subscribed to.
        """
        pass

    @abstractmethod
    def is_user_subscribed(self, user_id: str, podcast_id: str) -> bool:
        """Check if a user is subscribed to a podcast.

        Args:
            user_id: The user's UUID.
            podcast_id: The podcast's UUID.

        Returns:
            bool: True if subscribed, False otherwise.
        """
        pass

    @abstractmethod
    def list_podcasts_for_user(
        self, user_id: str, limit: Optional[int] = None
    ) -> List[Podcast]:
        """List podcasts the user is subscribed to.

        This is the user-filtered equivalent of list_podcasts().

        Args:
            user_id: The user's UUID.
            limit: Maximum number of podcasts to return.

        Returns:
            List[Podcast]: List of subscribed podcasts.
        """
        pass

    # --- Connection Management ---

    @abstractmethod
    def close(self) -> None:
        """
        Close and release all database connections and engine resources used by the repository.

        This will dispose the underlying SQLAlchemy engine and free associated connection pool resources so the repository can be cleanly shut down.
        """
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
        """
        Initialize the repository and configure its SQLAlchemy engine and session factory.
        
        Creates an engine appropriate for the provided database URL, prepares a session factory, and ensures the ORM tables are created.
        
        Parameters:
            database_url (str): SQLAlchemy-compatible database URL.
            pool_size (int): Connection pool size for non-SQLite databases.
            max_overflow (int): Maximum overflow connections for non-SQLite databases.
            echo (bool): If true, enable SQLAlchemy SQL statement logging.
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

        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False)

        logger.info(f"Database initialized: {database_url.split('@')[-1] if '@' in database_url else database_url}")

    def _get_session(self) -> Session:
        """
        Obtain a new SQLAlchemy database session from the repository's session factory.
        
        Returns:
            A fresh `Session` instance bound to the repository's engine.
        """
        return self.SessionLocal()

    # --- Podcast Operations ---

    def create_podcast(self, feed_url: str, title: str, **kwargs) -> Podcast:
        """
        Create and persist a new podcast subscription.
        
        Parameters:
            feed_url (str): URL of the podcast RSS/Atom feed.
            title (str): Human-readable title for the podcast.
            **kwargs: Additional Podcast fields to set on creation.
        
        Returns:
            Podcast: The newly created Podcast instance with its database-generated ID populated.
        """
        with self._get_session() as session:
            podcast = Podcast(feed_url=feed_url, title=title, **kwargs)
            session.add(podcast)
            session.commit()
            session.refresh(podcast)
            logger.info(f"Created podcast: {title} ({podcast.id})")
            return podcast

    def get_podcast(self, podcast_id: str) -> Optional[Podcast]:
        """
        Retrieve a podcast by its primary key.
        
        Returns:
            Podcast | None: The matching Podcast instance if found, `None` otherwise.
        """
        with self._get_session() as session:
            return session.get(Podcast, podcast_id)

    def get_podcast_by_feed_url(self, feed_url: str) -> Optional[Podcast]:
        """
        Finds the podcast record that matches the given RSS/Atom feed URL.
        
        Returns:
            Podcast or None: The `Podcast` instance with `feed_url`, or `None` if no match is found.
        """
        with self._get_session() as session:
            stmt = select(Podcast).where(Podcast.feed_url == feed_url)
            return session.scalar(stmt)

    def list_podcasts(
        self, subscribed_only: bool = True, limit: Optional[int] = None
    ) -> List[Podcast]:
        """
        List podcasts, optionally restricting results to subscribed podcasts.
        
        Parameters:
            subscribed_only (bool): If True, include only podcasts with `is_subscribed` set to True.
            limit (Optional[int]): Maximum number of podcasts to return; if None, no limit is applied.
        
        Returns:
            List[Podcast]: Podcasts ordered by title.
        """
        with self._get_session() as session:
            stmt = select(Podcast)
            if subscribed_only:
                stmt = stmt.where(Podcast.is_subscribed.is_(True))
            stmt = stmt.order_by(Podcast.title)
            if limit:
                stmt = stmt.limit(limit)
            return list(session.scalars(stmt).all())

    def update_podcast(self, podcast_id: str, **kwargs) -> Optional[Podcast]:
        """
        Update attributes of an existing podcast.
        
        Only attributes that exist on the Podcast model are set from `kwargs`. If the podcast is found, its `updated_at` timestamp is set to the current UTC time, the changes are persisted, and the refreshed Podcast instance is returned.
        
        Parameters:
            podcast_id (str): Primary key of the podcast to update.
            **kwargs: Model attributes and their new values to apply to the podcast.
        
        Returns:
            Optional[Podcast]: The updated Podcast instance if found, `None` if no podcast with `podcast_id` exists.
        """
        with self._get_session() as session:
            podcast = session.get(Podcast, podcast_id)
            if podcast:
                for key, value in kwargs.items():
                    if hasattr(podcast, key):
                        setattr(podcast, key, value)
                podcast.updated_at = datetime.now(UTC)
                session.commit()
                session.refresh(podcast)
                logger.debug(f"Updated podcast {podcast_id}: {kwargs.keys()}")
            return podcast

    def delete_podcast(self, podcast_id: str, delete_files: bool = False) -> bool:
        """
        Remove a podcast record from the database.
        
        If `delete_files` is True and the podcast has a `local_directory`, that directory is removed from disk if present. If the podcast ID does not exist, no changes are made.
        
        Parameters:
            podcast_id (str): The primary key of the podcast to delete.
            delete_files (bool): If True, remove the podcast's local directory from disk when present.
        
        Returns:
            bool: `True` if a podcast was found and deleted, `False` if no podcast with the given ID exists.
        """
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
        """
        Create and persist a new Episode for a podcast.
        
        Parameters:
            podcast_id (str): ID of the parent podcast.
            guid (str): Globally unique identifier for the episode within the podcast.
            title (str): Episode title.
            enclosure_url (str): URL of the episode media file.
            enclosure_type (str): MIME type or media type of the enclosure (e.g., "audio/mpeg").
            **kwargs: Additional Episode fields to set on creation (e.g., published_date, duration).
        
        Returns:
            episode (Episode): The persisted Episode instance with database-generated fields populated.
        """
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
        """
        Retrieve an episode by its ID.

        Returns:
            The Episode with the given ID, or `None` if no matching episode exists.
        """
        with self._get_session() as session:
            stmt = (
                select(Episode)
                .options(joinedload(Episode.podcast))
                .where(Episode.id == episode_id)
            )
            return session.scalars(stmt).unique().first()

    def get_episode_by_guid(self, podcast_id: str, guid: str) -> Optional[Episode]:
        """
        Retrieve an episode by its GUID for the specified podcast.

        @returns The Episode if found, `None` otherwise.
        """
        with self._get_session() as session:
            stmt = select(Episode).where(
                Episode.podcast_id == podcast_id, Episode.guid == guid
            )
            return session.scalar(stmt)

    def get_episode_by_file_search_display_name(
        self, display_name: str
    ) -> Optional[Episode]:
        """
        Retrieve an episode by its File Search display name.

        Used by the web app to look up episode metadata for citations.

        @returns The Episode if found, `None` otherwise.
        """
        with self._get_session() as session:
            stmt = (
                select(Episode)
                .options(joinedload(Episode.podcast))
                .where(Episode.file_search_display_name == display_name)
            )
            return session.scalars(stmt).unique().first()

    def list_episodes(
        self,
        podcast_id: Optional[str] = None,
        download_status: Optional[str] = None,
        transcript_status: Optional[str] = None,
        file_search_status: Optional[str] = None,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> List[Episode]:
        """
        Retrieve episodes optionally filtered by podcast and processing statuses, with pagination.
        
        Parameters:
            podcast_id (Optional[str]): Filter episodes belonging to the given podcast.
            download_status (Optional[str]): Filter by download status (e.g., "pending", "completed", "failed").
            transcript_status (Optional[str]): Filter by transcription status (e.g., "pending", "completed", "failed").
            file_search_status (Optional[str]): Filter by file-search/indexing status (e.g., "pending", "indexed", "failed").
            limit (Optional[int]): Maximum number of episodes to return. If None, no limit is applied.
            offset (int): Number of episodes to skip before collecting results (for pagination).
        
        Returns:
            List[Episode]: Episodes matching the supplied filters ordered by published date (newest first).
        """
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
        """
        Update attributes of an existing episode.
        
        The provided keyword arguments are applied to matching attributes on the episode record; the episode's `updated_at` timestamp is set to the current UTC time and the change is persisted.
        
        Parameters:
            episode_id (str): Primary key of the episode to update.
            **kwargs: Episode attributes to set (only attributes that exist on the model are applied).
        
        Returns:
            Optional[Episode]: The updated Episode instance, or `None` if no episode with `episode_id` exists.
        """
        with self._get_session() as session:
            episode = session.get(Episode, episode_id)
            if episode:
                for key, value in kwargs.items():
                    if hasattr(episode, key):
                        setattr(episode, key, value)
                episode.updated_at = datetime.now(UTC)
                session.commit()
                session.refresh(episode)
                logger.debug(f"Updated episode {episode_id}: {kwargs.keys()}")
            return episode

    def delete_episode(self, episode_id: str, delete_files: bool = False) -> bool:
        """
        Delete an episode record from the database and optionally remove its associated files from disk.
        
        Parameters:
            episode_id (str): The primary key of the episode to delete.
            delete_files (bool): If True, remove any existing files referenced by the episode
                ('local_file_path', 'transcript_path', 'metadata_path').
        
        Returns:
            bool: True if the episode was found and deleted, False if no episode with the given id exists.
        """
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
        """
        Ensure an Episode exists for the given podcast by GUID; create and persist it if missing.

        Uses optimistic creation with IntegrityError handling to avoid race conditions
        in concurrent scenarios.

        Parameters:
            podcast_id (str): ID of the podcast that owns the episode.
            guid (str): Unique identifier of the episode within the podcast.
            title (str): Title to set when creating a new episode.
            enclosure_url (str): Media enclosure URL for a new episode.
            enclosure_type (str): MIME type or descriptor of the enclosure.
            **kwargs: Additional fields forwarded to episode creation.

        Returns:
            tuple[Episode, bool]: (episode, created) where `created` is `True` if a new episode was created, `False` if an existing episode was returned.
        """
        # First check if episode exists
        existing = self.get_episode_by_guid(podcast_id, guid)
        if existing:
            return existing, False

        # Try to create; handle race condition if another process created it
        try:
            episode = self.create_episode(
                podcast_id=podcast_id,
                guid=guid,
                title=title,
                enclosure_url=enclosure_url,
                enclosure_type=enclosure_type,
                **kwargs,
            )
            return episode, True
        except IntegrityError:
            # Another process created the episode; fetch and return it
            existing = self.get_episode_by_guid(podcast_id, guid)
            if existing:
                return existing, False
            raise  # Re-raise if we still can't find it (unexpected state)

    def search_episodes_by_keyword(
        self, keyword: str, limit: int = 50
    ) -> List[Episode]:
        """
        Search for episodes containing the specified keyword in ai_keywords.

        Uses case-insensitive JSON string matching for cross-database compatibility
        (SQLite and PostgreSQL) via lower() + like() instead of ilike().
        Special LIKE characters are escaped to prevent injection.
        """
        # Lowercase and escape special characters for case-insensitive LIKE
        escaped_keyword = _escape_like_pattern(keyword.lower())
        pattern = f'%"{escaped_keyword}"%'

        with self._get_session() as session:
            # Use func.lower() + like() for portable case-insensitive search
            # (ilike is PostgreSQL-specific and not supported by SQLite)
            stmt = (
                select(Episode)
                .options(joinedload(Episode.podcast))
                .where(
                    func.lower(cast(Episode.ai_keywords, String)).like(
                        pattern, escape='\\'
                    )
                )
                .order_by(Episode.published_date.desc())
                .limit(limit)
            )
            return list(session.scalars(stmt).unique().all())

    def search_episodes_by_person(
        self, name: str, limit: int = 50
    ) -> List[Episode]:
        """
        Search for episodes featuring the specified person as host or guest.

        Uses case-insensitive JSON string matching for cross-database compatibility
        (SQLite and PostgreSQL) via lower() + like() instead of ilike().
        Special LIKE characters are escaped to prevent injection.
        """
        # Lowercase and escape special characters for case-insensitive LIKE
        escaped_name = _escape_like_pattern(name.lower())
        pattern = f'%"{escaped_name}"%'

        with self._get_session() as session:
            # Use func.lower() + like() for portable case-insensitive search
            # (ilike is PostgreSQL-specific and not supported by SQLite)
            stmt = (
                select(Episode)
                .options(joinedload(Episode.podcast))
                .where(
                    or_(
                        func.lower(cast(Episode.ai_hosts, String)).like(
                            pattern, escape='\\'
                        ),
                        func.lower(cast(Episode.ai_guests, String)).like(
                            pattern, escape='\\'
                        ),
                    )
                )
                .order_by(Episode.published_date.desc())
                .limit(limit)
            )
            return list(session.scalars(stmt).unique().all())

    def get_episodes_pending_download(self, limit: int = 10) -> List[Episode]:
        """
        Retrieve pending episodes awaiting download.
        
        Parameters:
            limit (int): Maximum number of episodes to return (default 10).
        
        Returns:
            List[Episode]: Episodes with `download_status == "pending"`, ordered by `published_date` descending, up to `limit` items.
        """
        with self._get_session() as session:
            stmt = (
                select(Episode)
                .where(Episode.download_status == "pending")
                .order_by(Episode.published_date.desc())
                .limit(limit)
            )
            return list(session.scalars(stmt).all())

    def get_episodes_pending_transcription(self, limit: int = 10) -> List[Episode]:
        """
        Return episodes that have been downloaded and are awaiting transcription.
        
        @returns List[Episode]: Episodes with download_status == "completed", transcript_status == "pending", and a non-null local_file_path, ordered by published_date descending and limited to the provided `limit`.
        """
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
        """
        Selects transcribed episodes that require metadata extraction.

        Parameters:
            limit (int): Maximum number of episodes to return (default 10).

        Returns:
            List[Episode]: Episodes whose `transcript_status` is "completed", `metadata_status` is "pending",
            and have transcript content (either `transcript_text` or legacy `transcript_path`),
            ordered by `published_date` descending.
        """
        with self._get_session() as session:
            stmt = (
                select(Episode)
                .where(
                    Episode.transcript_status == "completed",
                    Episode.metadata_status == "pending",
                    or_(
                        Episode.transcript_text.isnot(None),
                        Episode.transcript_path.isnot(None),
                    ),
                )
                .order_by(Episode.published_date.desc())
                .limit(limit)
            )
            return list(session.scalars(stmt).all())

    def get_episodes_pending_indexing(self, limit: int = 10) -> List[Episode]:
        """
        Return episodes that have completed metadata and are pending File Search indexing.

        Parameters:
            limit (int): Maximum number of episodes to return.

        Returns:
            List[Episode]: Episodes where `metadata_status == "completed"`, `file_search_status == "pending"`,
            and have transcript content, ordered by `published_date` descending up to `limit`.
        """
        with self._get_session() as session:
            stmt = (
                select(Episode)
                .options(joinedload(Episode.podcast))
                .where(
                    Episode.metadata_status == "completed",
                    Episode.file_search_status == "pending",
                    or_(
                        Episode.transcript_text.isnot(None),
                        Episode.transcript_path.isnot(None),
                    ),
                )
                .order_by(Episode.published_date.desc())
                .limit(limit)
            )
            return list(session.scalars(stmt).unique().all())

    def get_episodes_ready_for_cleanup(self, limit: int = 10) -> List[Episode]:
        """
        Return episodes that are fully processed and have local audio files eligible for deletion.
        
        Parameters:
            limit (int): Maximum number of episodes to return.
        
        Returns:
            List[Episode]: Episodes where transcript_status == "completed", metadata_status == "completed",
            file_search_status == "indexed", and local_file_path is set; limited to `limit` items.
        """
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
        """
        Mark an episode's download status as downloading.
        
        Updates the episode identified by `episode_id` so its download status becomes "downloading".
        
        Parameters:
            episode_id (str): Identifier of the episode to mark as downloading.
        """
        self.update_episode(episode_id, download_status="downloading")

    def mark_download_complete(
        self, episode_id: str, local_path: str, file_size: int, file_hash: str
    ) -> None:
        """
        Record that an episode's download finished and persist its download metadata.
        
        Parameters:
            episode_id (str): Identifier of the episode to update.
            local_path (str): Filesystem path to the downloaded audio file.
            file_size (int): Size of the downloaded file in bytes.
            file_hash (str): Hash of the downloaded file used for integrity verification.
        """
        self.update_episode(
            episode_id,
            download_status="completed",
            local_file_path=local_path,
            file_size_bytes=file_size,
            file_hash=file_hash,
            downloaded_at=datetime.now(UTC),
            download_error=None,
        )

    def mark_download_failed(self, episode_id: str, error: str) -> None:
        """
        Record that an episode's download failed and store the provided error message.
        
        Parameters:
            episode_id (str): ID of the episode to update.
            error (str): Human-readable error message describing the failure.
        """
        self.update_episode(
            episode_id,
            download_status="failed",
            download_error=error,
        )

    def mark_transcript_started(self, episode_id: str) -> None:
        """Mark episode as currently being transcribed."""
        self.update_episode(episode_id, transcript_status="processing")

    def mark_transcript_complete(
        self,
        episode_id: str,
        transcript_text: str,
        transcript_path: Optional[str] = None,
    ) -> None:
        """
        Mark an episode's transcription as complete and store the transcript content.

        Parameters:
            episode_id (str): ID of the episode to update.
            transcript_text (str): Full transcript content.
            transcript_path (str, optional): Legacy file path, kept for backward compatibility.

        Notes:
            Sets `transcript_status` to "completed", stores `transcript_text` (and optionally
            `transcript_path`), sets `transcribed_at` to the current UTC time, and clears
            `transcript_error`.
        """
        self.update_episode(
            episode_id,
            transcript_status="completed",
            transcript_text=transcript_text,
            transcript_path=transcript_path,
            transcribed_at=datetime.now(UTC),
            transcript_error=None,
        )

    def mark_transcript_failed(self, episode_id: str, error: str) -> None:
        """
        Mark an episode's transcription as failed and record the error message.
        
        Parameters:
            episode_id (str): Identifier of the episode to update.
            error (str): Human-readable error message describing the transcription failure.
        """
        self.update_episode(
            episode_id,
            transcript_status="failed",
            transcript_error=error,
        )

    def mark_metadata_started(self, episode_id: str) -> None:
        """
        Mark metadata extraction for the specified episode as started.
        
        Parameters:
            episode_id (str): The ID of the episode whose metadata status will be set to "processing".
        """
        self.update_episode(episode_id, metadata_status="processing")

    def mark_metadata_complete(
        self,
        episode_id: str,
        summary: Optional[str] = None,
        keywords: Optional[List[str]] = None,
        hosts: Optional[List[str]] = None,
        guests: Optional[List[str]] = None,
        mp3_artist: Optional[str] = None,
        mp3_album: Optional[str] = None,
        metadata_path: Optional[str] = None,
    ) -> None:
        """
        Mark an episode's metadata extraction as completed and store the resulting metadata.

        Parameters:
            episode_id (str): The ID of the episode to update.
            summary (Optional[str]): Generated summary text for the episode, if available.
            keywords (Optional[List[str]]): Extracted keywords or tags for the episode.
            hosts (Optional[List[str]]): Identified hosts associated with the episode.
            guests (Optional[List[str]]): Identified guests associated with the episode.
            mp3_artist (Optional[str]): MP3 ID3 artist tag from the audio file.
            mp3_album (Optional[str]): MP3 ID3 album tag from the audio file.
            metadata_path (Optional[str]): Legacy file path, kept for backward compatibility.
        """
        self.update_episode(
            episode_id,
            metadata_status="completed",
            metadata_path=metadata_path,
            ai_summary=summary,
            ai_keywords=keywords,
            ai_hosts=hosts,
            ai_guests=guests,
            mp3_artist=mp3_artist,
            mp3_album=mp3_album,
            metadata_error=None,
        )

    def mark_metadata_failed(self, episode_id: str, error: str) -> None:
        """
        Mark an episode's metadata extraction as failed and record the error message.
        
        Parameters:
            episode_id (str): ID of the episode to update.
            error (str): Error message describing the failure.
        """
        self.update_episode(
            episode_id,
            metadata_status="failed",
            metadata_error=error,
        )

    def mark_indexing_started(self, episode_id: str) -> None:
        """
        Mark an episode as currently being uploaded to the File Search index.
        
        Parameters:
            episode_id (str): The ID of the episode to mark.
        """
        self.update_episode(episode_id, file_search_status="uploading")

    def mark_indexing_complete(
        self, episode_id: str, resource_name: str, display_name: str
    ) -> None:
        """
        Mark an episode as successfully indexed in the File Search system.
        
        Updates the episode's record to set file_search_status to "indexed", store the File Search resource identifier and display name, record the current UTC upload time, and clear any previous file search error.
        
        Parameters:
            episode_id (str): ID of the episode to update.
            resource_name (str): Internal resource identifier returned by the File Search service.
            display_name (str): Human-readable name for the indexed resource.
        """
        self.update_episode(
            episode_id,
            file_search_status="indexed",
            file_search_resource_name=resource_name,
            file_search_display_name=display_name,
            file_search_uploaded_at=datetime.now(UTC),
            file_search_error=None,
        )

    def mark_indexing_failed(self, episode_id: str, error: str) -> None:
        """
        Mark an episode's File Search indexing as failed.
        
        Parameters:
            episode_id (str): ID of the episode to update.
            error (str): Error message to record on the episode's indexing failure.
        """
        self.update_episode(
            episode_id,
            file_search_status="failed",
            file_search_error=error,
        )

    def mark_audio_cleaned_up(self, episode_id: str) -> None:
        """
        Remove an episode's local audio file (if present) and clear its stored file path.
        
        If the episode exists and has a non-empty local_file_path, this will remove the file from disk when it exists and update the episode record to set local_file_path to None.
        
        Parameters:
            episode_id (str): The ID of the episode whose audio file should be cleaned up.
        """
        episode = self.get_episode(episode_id)
        if episode and episode.local_file_path:
            if os.path.exists(episode.local_file_path):
                os.remove(episode.local_file_path)
                logger.info(f"Deleted audio file: {episode.local_file_path}")
            self.update_episode(episode_id, local_file_path=None)

    # --- Transcript Access ---

    def get_transcript_text(self, episode_id: str) -> Optional[str]:
        """
        Get the transcript text for an episode.

        Returns the transcript content from the database (`transcript_text` column).
        For legacy episodes with only `transcript_path`, reads the file content.

        Parameters:
            episode_id (str): ID of the episode.

        Returns:
            The transcript text if available, None otherwise.
        """
        episode = self.get_episode(episode_id)
        if not episode:
            return None

        # Prefer database-stored text (use 'is not None' to allow empty strings)
        if episode.transcript_text is not None:
            return episode.transcript_text

        # Fall back to reading from file for legacy episodes
        if episode.transcript_path and os.path.exists(episode.transcript_path):
            try:
                with open(episode.transcript_path, "r", encoding="utf-8") as f:
                    return f.read()
            except (OSError, UnicodeDecodeError) as e:
                logger.warning(f"Failed to read transcript file {episode.transcript_path}: {e}")
                return None

        return None

    # --- Statistics ---

    def get_podcast_stats(self, podcast_id: str) -> Dict[str, Any]:
        """
        Return a snapshot of processing statistics for the specified podcast.
        
        If the podcast ID does not exist, returns an empty dict.
        
        Returns:
            stats (Dict[str, Any]): A dictionary containing:
                - `podcast_id`: The podcast's ID.
                - `title`: The podcast's title.
                - `total_episodes`: Total number of episodes for the podcast.
                - `pending_download`: Count of episodes with download status "pending".
                - `downloading`: Count of episodes with download status "downloading".
                - `downloaded`: Count of episodes with download status "completed".
                - `download_failed`: Count of episodes with download status "failed".
                - `pending_transcription`: Count of episodes with transcript status "pending".
                - `transcribed`: Count of episodes with transcript status "completed".
                - `indexed`: Count of episodes with file search status "indexed".
                - `fully_processed`: Count of episodes considered fully processed.
        """
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
        """
        Return aggregated system-wide counts for podcasts and episodes across processing stages.
        
        @returns:
            stats (Dict[str, Any]): Mapping of statistic names to integer counts:
                - total_podcasts: Total number of podcasts in the repository.
                - subscribed_podcasts: Number of podcasts marked as subscribed.
                - total_episodes: Total number of episodes in the repository.
                - pending_download: Episodes with download_status == "pending".
                - downloading: Episodes with download_status == "downloading".
                - downloaded: Episodes with download_status == "completed".
                - download_failed: Episodes with download_status == "failed".
                - pending_transcription: Episodes with transcript_status == "pending".
                - transcribing: Episodes with transcript_status == "processing".
                - transcribed: Episodes with transcript_status == "completed".
                - transcript_failed: Episodes with transcript_status == "failed".
                - pending_indexing: Episodes with file_search_status == "pending".
                - indexed: Episodes with file_search_status == "indexed".
                - fully_processed: Episodes considered fully processed (all final processing steps complete).
        """
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

    # --- Pipeline Mode Methods ---

    def get_download_buffer_count(self) -> int:
        """Get count of episodes ready for transcription (download buffer).

        Returns:
            Number of episodes that are downloaded and pending transcription.
        """
        with self._get_session() as session:
            stmt = (
                select(func.count(Episode.id))
                .where(
                    Episode.download_status == "completed",
                    Episode.transcript_status == "pending",
                    Episode.local_file_path.isnot(None),
                )
            )
            return session.scalar(stmt) or 0

    def get_next_for_transcription(self) -> Optional[Episode]:
        """Get the next single episode ready for transcription.

        Returns episodes ordered by published_date (newest first),
        excluding permanently failed episodes.

        Returns:
            Episode to transcribe, or None if no work available.
        """
        with self._get_session() as session:
            stmt = (
                select(Episode)
                .where(
                    Episode.download_status == "completed",
                    Episode.transcript_status == "pending",
                    Episode.local_file_path.isnot(None),
                )
                .order_by(Episode.published_date.desc())
                .limit(1)
            )
            return session.scalars(stmt).first()

    def get_next_pending_post_processing(self) -> Optional[Episode]:
        """Get the next episode needing post-processing (metadata or indexing).

        Returns episodes ordered by published_date (newest first).
        Prioritizes metadata extraction over indexing.

        Returns:
            Episode to post-process, or None if no work available.
        """
        with self._get_session() as session:
            # First check for episodes needing metadata
            stmt = (
                select(Episode)
                .options(joinedload(Episode.podcast))
                .where(
                    Episode.transcript_status == "completed",
                    Episode.metadata_status == "pending",
                    or_(
                        Episode.transcript_text.isnot(None),
                        Episode.transcript_path.isnot(None),
                    ),
                )
                .order_by(Episode.published_date.desc())
                .limit(1)
            )
            episode = session.scalars(stmt).unique().first()
            if episode:
                return episode

            # Then check for episodes needing indexing
            stmt = (
                select(Episode)
                .options(joinedload(Episode.podcast))
                .where(
                    Episode.metadata_status == "completed",
                    Episode.file_search_status == "pending",
                    or_(
                        Episode.transcript_text.isnot(None),
                        Episode.transcript_path.isnot(None),
                    ),
                )
                .order_by(Episode.published_date.desc())
                .limit(1)
            )
            return session.scalars(stmt).unique().first()

    def increment_retry_count(self, episode_id: str, stage: str) -> int:
        """Increment and return the retry count for a processing stage.

        Args:
            episode_id: Episode to update.
            stage: Stage name ('transcript', 'metadata', or 'indexing').

        Returns:
            New retry count after increment.

        Raises:
            ValueError: If stage name is invalid.
        """
        field_map = {
            "transcript": "transcript_retry_count",
            "metadata": "metadata_retry_count",
            "indexing": "indexing_retry_count",
        }

        if stage not in field_map:
            raise ValueError(f"Invalid stage: {stage}")

        field_name = field_map[stage]

        with self._get_session() as session:
            episode = session.get(Episode, episode_id)
            if episode is None:
                raise ValueError(f"Episode not found: {episode_id}")

            current_count = getattr(episode, field_name) or 0
            new_count = current_count + 1
            setattr(episode, field_name, new_count)
            session.commit()
            return new_count

    def mark_permanently_failed(self, episode_id: str, stage: str, error: str) -> None:
        """Mark an episode as permanently failed for a stage.

        Sets the status to 'permanently_failed' which excludes it from future
        processing attempts.

        Args:
            episode_id: Episode to mark.
            stage: Stage name ('transcript', 'metadata', or 'indexing').
            error: Error message describing the failure.
        """
        status_map = {
            "transcript": ("transcript_status", "transcript_error"),
            "metadata": ("metadata_status", "metadata_error"),
            "indexing": ("file_search_status", "file_search_error"),
        }

        if stage not in status_map:
            raise ValueError(f"Invalid stage: {stage}")

        status_field, error_field = status_map[stage]
        self.update_episode(
            episode_id,
            **{status_field: "permanently_failed", error_field: error}
        )

    def reset_episode_for_retry(self, episode_id: str, stage: str) -> None:
        """Reset an episode's status to pending for retry.

        Args:
            episode_id: Episode to reset.
            stage: Stage name ('transcript', 'metadata', or 'indexing').
        """
        status_map = {
            "transcript": ("transcript_status", "transcript_error"),
            "metadata": ("metadata_status", "metadata_error"),
            "indexing": ("file_search_status", "file_search_error"),
        }

        if stage not in status_map:
            raise ValueError(f"Invalid stage: {stage}")

        status_field, error_field = status_map[stage]
        self.update_episode(
            episode_id,
            **{status_field: "pending", error_field: None}
        )

    # --- User Operations ---

    def create_user(
        self,
        google_id: str,
        email: str,
        name: Optional[str] = None,
        picture_url: Optional[str] = None,
    ) -> User:
        """Create a new user from Google OAuth data.

        If a user with the same google_id or email already exists,
        returns the existing user instead of raising an error.
        """
        with self._get_session() as session:
            user = User(
                google_id=google_id,
                email=email,
                name=name,
                picture_url=picture_url,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
                last_login=datetime.now(UTC),
            )
            session.add(user)
            try:
                session.commit()
                session.refresh(user)
                logger.info(f"Created new user: {email}")
                return user
            except IntegrityError:
                session.rollback()
                logger.info(f"User already exists, fetching existing: {email}")
                # Try to find by google_id first, then by email
                existing = session.execute(
                    select(User).where(User.google_id == google_id)
                ).scalar_one_or_none()
                if existing:
                    return existing
                existing = session.execute(
                    select(User).where(User.email == email)
                ).scalar_one_or_none()
                if existing:
                    return existing
                # If we can't find the existing user, re-raise
                raise ValueError(f"IntegrityError but user not found: {email}")

    def get_user(self, user_id: str) -> Optional[User]:
        """Get a user by ID."""
        with self._get_session() as session:
            return session.get(User, user_id)

    def get_user_by_google_id(self, google_id: str) -> Optional[User]:
        """Get a user by their Google ID."""
        with self._get_session() as session:
            stmt = select(User).where(User.google_id == google_id)
            return session.scalar(stmt)

    def get_user_by_email(self, email: str) -> Optional[User]:
        """Get a user by email address."""
        with self._get_session() as session:
            stmt = select(User).where(User.email == email)
            return session.scalar(stmt)

    def update_user(self, user_id: str, **kwargs) -> Optional[User]:
        """Update a user's attributes."""
        with self._get_session() as session:
            user = session.get(User, user_id)
            if not user:
                return None

            for key, value in kwargs.items():
                if hasattr(user, key):
                    setattr(user, key, value)

            user.updated_at = datetime.now(UTC)
            session.commit()
            session.refresh(user)
            return user

    # --- Subscription Operations ---

    def subscribe_user_to_podcast(self, user_id: str, podcast_id: str) -> UserSubscription:
        """Subscribe a user to a podcast."""
        with self._get_session() as session:
            # Check if already subscribed
            existing = session.scalar(
                select(UserSubscription).where(
                    UserSubscription.user_id == user_id,
                    UserSubscription.podcast_id == podcast_id,
                )
            )
            if existing:
                return existing

            subscription = UserSubscription(
                user_id=user_id,
                podcast_id=podcast_id,
                subscribed_at=datetime.now(UTC),
            )
            session.add(subscription)
            session.commit()
            session.refresh(subscription)
            logger.info(f"User {user_id} subscribed to podcast {podcast_id}")
            return subscription

    def unsubscribe_user_from_podcast(self, user_id: str, podcast_id: str) -> bool:
        """Unsubscribe a user from a podcast."""
        with self._get_session() as session:
            subscription = session.scalar(
                select(UserSubscription).where(
                    UserSubscription.user_id == user_id,
                    UserSubscription.podcast_id == podcast_id,
                )
            )
            if not subscription:
                return False

            session.delete(subscription)
            session.commit()
            logger.info(f"User {user_id} unsubscribed from podcast {podcast_id}")
            return True

    def get_user_subscriptions(self, user_id: str) -> List[Podcast]:
        """Get all podcasts a user is subscribed to."""
        with self._get_session() as session:
            stmt = (
                select(Podcast)
                .join(UserSubscription, Podcast.id == UserSubscription.podcast_id)
                .where(UserSubscription.user_id == user_id)
                .order_by(Podcast.title)
            )
            return list(session.scalars(stmt).all())

    def is_user_subscribed(self, user_id: str, podcast_id: str) -> bool:
        """Check if a user is subscribed to a podcast."""
        with self._get_session() as session:
            subscription = session.scalar(
                select(UserSubscription).where(
                    UserSubscription.user_id == user_id,
                    UserSubscription.podcast_id == podcast_id,
                )
            )
            return subscription is not None

    def list_podcasts_for_user(
        self, user_id: str, limit: Optional[int] = None
    ) -> List[Podcast]:
        """List podcasts the user is subscribed to."""
        with self._get_session() as session:
            stmt = (
                select(Podcast)
                .join(UserSubscription, Podcast.id == UserSubscription.podcast_id)
                .where(UserSubscription.user_id == user_id)
                .order_by(Podcast.title)
            )
            if limit:
                stmt = stmt.limit(limit)
            return list(session.scalars(stmt).all())

    # --- Connection Management ---

    def close(self) -> None:
        """
        Dispose the SQLAlchemy engine and release database connections and resources.
        
        This closes all pooled connections and frees underlying resources held by the engine.
        """
        self.engine.dispose()
        logger.info("Database connection closed")