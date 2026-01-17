"""Repository pattern implementation for podcast data persistence.

Provides an abstract interface and SQLAlchemy implementation for database operations.
Supports both SQLite (local development) and PostgreSQL (Cloud SQL production).
"""

import logging
import os
import shutil
from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import String, cast, create_engine, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, sessionmaker

from .models import ChatMessage, Conversation, Episode, Podcast, User, UserSubscription

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
            **kwargs: Additional Podcast attributes to set (e.g., description, author, image_url).

        Returns:
            Podcast: The persisted Podcast instance with updated identifiers and timestamps.
        """
        pass

    @abstractmethod
    def get_podcast(self, podcast_id: str) -> Podcast | None:
        """
        Retrieve a podcast by its identifier.

        Returns:
            Podcast if a podcast with the given ID exists, `None` otherwise.
        """
        pass

    @abstractmethod
    def get_podcast_by_feed_url(self, feed_url: str) -> Podcast | None:
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
        self,
        limit: int | None = None,
        sort_by: str = "recency",
        sort_order: str = "desc"
    ) -> list[Podcast]:
        """
        Return all podcasts with configurable sorting.

        Use list_podcasts_with_subscribers() to get only podcasts with active subscribers.

        Parameters:
            limit (Optional[int]): Maximum number of podcasts to return; if None, no limit is applied.
            sort_by (str): Field to sort by ("recency", "subscribers", "alphabetical"). Default is "recency".
            sort_order (str): Sort direction ("asc" or "desc"). Default is "desc".

        Returns:
            List[Podcast]: Podcasts sorted according to parameters.
        """
        pass

    @abstractmethod
    def update_podcast(self, podcast_id: str, **kwargs) -> Podcast | None:
        """
        Update attributes of an existing podcast.

        Parameters:
            podcast_id (str): The podcast's primary key.
            **kwargs: Podcast fields to update (for example `title`, `feed_url`, `image_url`).

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

    @abstractmethod
    def list_podcasts_with_subscribers(
        self, limit: int | None = None, source_type: str | None = None
    ) -> list[Podcast]:
        """List podcasts that have at least one user subscribed.

        This is used by the pipeline to determine which podcasts need to be synced.
        Only podcasts with active user subscriptions are returned.

        Args:
            limit: Maximum number of podcasts to return.
            source_type: Filter by source type ("rss", "youtube", or None for all).

        Returns:
            List[Podcast]: Podcasts with at least one subscriber.
        """
        pass

    @abstractmethod
    def get_podcast_by_youtube_channel_id(self, channel_id: str) -> Podcast | None:
        """Retrieve a podcast by its YouTube channel ID.

        Args:
            channel_id: YouTube channel ID (UC... format).

        Returns:
            Podcast if found, None otherwise.
        """
        pass

    @abstractmethod
    def get_youtube_videos_pending_caption_download(
        self, limit: int = 10
    ) -> list[Episode]:
        """Get YouTube videos that need caption/audio download.

        Returns videos where:
        - source_type is "youtube_video"
        - download_status is "pending"

        Args:
            limit: Maximum number of episodes to return.

        Returns:
            List of episodes pending caption/audio download.
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
    def get_episode(self, episode_id: str) -> Episode | None:
        """
        Retrieve an episode by its primary key.

        Returns:
            The Episode instance if found, `None` otherwise.
        """
        pass

    @abstractmethod
    def get_episode_by_guid(self, podcast_id: str, guid: str) -> Episode | None:
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
    def get_latest_episode(self, podcast_id: str) -> Episode | None:
        """
        Retrieve the most recent episode for a podcast based on published_date.

        Parameters:
            podcast_id (str): The podcast's primary identifier.

        Returns:
            Optional[Episode]: The most recent Episode if found, `None` otherwise.
        """
        pass

    @abstractmethod
    def get_episode_by_file_search_display_name(
        self, display_name: str
    ) -> Episode | None:
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
    def get_podcast_by_description_display_name(
        self, display_name: str
    ) -> Podcast | None:
        """
        Retrieve a podcast by its description File Search display name.

        Used by the web app to look up podcast metadata for discovery queries.

        Parameters:
            display_name (str): The description_file_search_display_name (e.g., "Podcast_Name_description.txt")

        Returns:
            Optional[Podcast]: The matching Podcast if found, `None` otherwise.
        """
        pass

    @abstractmethod
    def list_episodes(
        self,
        podcast_id: str | None = None,
        download_status: str | None = None,
        transcript_status: str | None = None,
        metadata_status: str | None = None,
        file_search_status: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Episode]:
        """
        List episodes, optionally filtered and paginated.

        Parameters:
            podcast_id (Optional[str]): If provided, only episodes belonging to this podcast are returned.
            download_status (Optional[str]): If provided, filter episodes by download status (e.g., "pending", "completed", "failed").
            transcript_status (Optional[str]): If provided, filter episodes by transcript status (e.g., "pending", "completed", "failed").
            metadata_status (Optional[str]): If provided, filter episodes by metadata status (e.g., "pending", "completed", "failed").
            file_search_status (Optional[str]): If provided, filter episodes by file search/indexing status (e.g., "pending", "indexed", "failed").
            limit (Optional[int]): Maximum number of episodes to return. If None, no limit is applied.
            offset (int): Number of episodes to skip before returning results (for pagination).

        Returns:
            List[Episode]: A list of Episode objects matching the provided filters, ordered by published date descending and subject to offset/limit.
        """
        pass

    @abstractmethod
    def count_episodes(
        self,
        podcast_id: str | None = None,
        download_status: str | None = None,
        transcript_status: str | None = None,
        metadata_status: str | None = None,
        file_search_status: str | None = None,
    ) -> int:
        """
        Count episodes matching the given filters.

        Parameters:
            podcast_id (Optional[str]): If provided, only count episodes belonging to this podcast.
            download_status (Optional[str]): If provided, filter by download status.
            transcript_status (Optional[str]): If provided, filter by transcript status.
            metadata_status (Optional[str]): If provided, filter by metadata status.
            file_search_status (Optional[str]): If provided, filter by file search status.

        Returns:
            int: Count of episodes matching the filters.
        """
        pass

    @abstractmethod
    def update_episode(self, episode_id: str, **kwargs) -> Episode | None:
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
    def get_existing_episode_guids(self, podcast_id: str) -> set[str]:
        """
        Get all existing episode GUIDs for a podcast in a single query.

        This is an optimized batch operation for sync - instead of checking
        each episode individually (N queries), fetch all GUIDs at once (1 query).

        Parameters:
            podcast_id (str): ID of the podcast.

        Returns:
            set[str]: Set of GUIDs for all episodes belonging to this podcast.
        """
        pass

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
    ) -> list[Episode]:
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
    ) -> list[Episode]:
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
    def get_episodes_pending_download(self, limit: int = 10) -> list[Episode]:
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
    def get_episodes_pending_transcription(self, limit: int = 10) -> list[Episode]:
        """
        Retrieve downloaded episodes that still require transcription.

        Parameters:
            limit (int): Maximum number of episodes to return.

        Returns:
            List[Episode]: Episodes where the download is completed, transcription has not started or is pending, and a local audio file is present, ordered by most recently published.
        """
        pass

    @abstractmethod
    def get_episodes_pending_metadata(self, limit: int = 10) -> list[Episode]:
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
    def get_episodes_pending_indexing(self, limit: int = 10) -> list[Episode]:
        """
        Return episodes whose metadata is complete and are awaiting File Search indexing.

        Episodes returned have metadata_status set to "completed", file_search_status set to "pending", and a transcript path present. Results are ordered by published date (newest first) and limited to at most `limit` items.

        Returns:
            List[Episode]: A list of episodes matching the indexing criteria, ordered by published date descending, up to `limit`.
        """
        pass

    @abstractmethod
    def count_episodes_pending_indexing(self) -> int:
        """
        Count episodes pending File Search indexing.

        Returns:
            int: Number of episodes waiting to be indexed.
        """
        pass

    @abstractmethod
    def get_episodes_ready_for_cleanup(self, limit: int = 10) -> list[Episode]:
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
        transcript_path: str | None = None,
        transcript_source: str | None = None,
    ) -> None:
        """
        Mark an episode's transcription as completed and store the transcript content.

        Updates the episode record to store the transcript text, mark transcription as completed,
        record the completion timestamp, and persist the change to the database.

        Parameters:
            episode_id (str): Primary key of the episode to update.
            transcript_text (str): Full transcript content.
            transcript_path (str, optional): Legacy file path, kept for backward compatibility.
            transcript_source (str, optional): Source of transcript ("whisper" | "youtube_captions").
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
        summary: str | None = None,
        keywords: list[str] | None = None,
        hosts: list[str] | None = None,
        guests: list[str] | None = None,
        mp3_artist: str | None = None,
        mp3_album: str | None = None,
        email_content: dict[str, Any] | None = None,
        metadata_path: str | None = None,
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
            email_content (Optional[Dict[str, Any]]): Email-optimized content for digest emails.
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

    # --- Podcast Description Indexing ---

    @abstractmethod
    def get_podcasts_pending_description_indexing(self, limit: int = 10) -> list[Podcast]:
        """
        Return podcasts with descriptions that need File Search indexing.

        Podcasts returned have a non-empty description and description_file_search_status
        set to "pending". Results are ordered by created_at and limited to `limit` items.

        Returns:
            List[Podcast]: Podcasts ready for description indexing.
        """
        pass

    @abstractmethod
    def count_podcasts_pending_description_indexing(self) -> int:
        """
        Count podcasts pending description indexing.

        Returns:
            int: Number of podcasts waiting to have descriptions indexed.
        """
        pass

    @abstractmethod
    def mark_description_indexing_started(self, podcast_id: str) -> None:
        """
        Mark a podcast's description as in-progress for File Search indexing.

        Updates the podcast's description_file_search_status to "uploading" and
        clears any previous error.

        Parameters:
            podcast_id (str): Primary key of the podcast to update.
        """
        pass

    @abstractmethod
    def mark_description_indexing_complete(
        self, podcast_id: str, resource_name: str, display_name: str
    ) -> None:
        """
        Record that a podcast's description indexing finished successfully.

        Parameters:
            podcast_id (str): Identifier of the podcast whose indexing completed.
            resource_name (str): File Search resource name for the indexed document.
            display_name (str): Human-readable name for the indexed resource.
        """
        pass

    @abstractmethod
    def mark_description_indexing_failed(self, podcast_id: str, error: str) -> None:
        """
        Record that description indexing for the specified podcast failed.

        Parameters:
            podcast_id (str): The ID of the podcast whose indexing failed.
            error (str): A human-readable error message describing the failure.
        """
        pass

    # --- Bulk Reset Operations (for migrations) ---

    @abstractmethod
    def reset_all_episode_indexing_status(self) -> int:
        """
        Reset all episodes' file_search_status to pending.

        Clears file_search_error, file_search_resource_name, file_search_display_name,
        and file_search_uploaded_at for all episodes that are not already pending.

        Returns:
            int: Number of episodes reset.
        """
        pass

    @abstractmethod
    def count_episodes_not_pending_indexing(self) -> int:
        """
        Count episodes that are not in pending indexing status.

        Returns:
            int: Number of episodes with file_search_status != 'pending'.
        """
        pass

    @abstractmethod
    def reset_all_podcast_description_indexing_status(self) -> int:
        """
        Reset all podcasts' description_file_search_status to pending.

        Clears description_file_search_error, description_file_search_resource_name,
        description_file_search_display_name, and description_file_search_uploaded_at
        for all podcasts that are not already pending.

        Returns:
            int: Number of podcasts reset.
        """
        pass

    @abstractmethod
    def count_podcasts_not_pending_description_indexing(self) -> int:
        """
        Count podcasts that are not in pending description indexing status.

        Returns:
            int: Number of podcasts with description_file_search_status != 'pending'.
        """
        pass

    # --- Transcript Access ---

    @abstractmethod
    def get_transcript_text(self, episode_id: str) -> str | None:
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
    def get_podcast_stats(self, podcast_id: str) -> dict[str, Any]:
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
    def get_podcast_episode_counts(self, podcast_ids: list[str]) -> dict[str, int]:
        """
        Efficiently get episode counts for multiple podcasts in a single query.

        This method is optimized for batch operations and uses a single SQL GROUP BY
        query instead of N separate queries. Ideal for listing podcasts with stats.

        Parameters:
            podcast_ids (List[str]): List of podcast IDs to get counts for.

        Returns:
            Dict[str, int]: Mapping of podcast_id -> episode_count.
                            Podcasts with 0 episodes will have count = 0.
        """
        pass

    @abstractmethod
    def get_podcast_subscriber_counts(self, podcast_ids: list[str]) -> dict[str, int]:
        """
        Efficiently get subscriber counts for multiple podcasts in a single query.

        This method is optimized for batch operations and uses a single SQL GROUP BY
        query instead of N separate queries. Ideal for listing podcasts with stats.

        Parameters:
            podcast_ids (List[str]): List of podcast IDs to get counts for.

        Returns:
            Dict[str, int]: Mapping of podcast_id -> subscriber_count.
                            Podcasts with 0 subscribers will have count = 0.
        """
        pass

    @abstractmethod
    def get_overall_stats(self) -> dict[str, Any]:
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
    def get_next_for_transcription(self) -> Episode | None:
        """Get the next episode ready for transcription.

        Returns the most recently published episode that is downloaded
        and pending transcription, excluding permanently failed episodes.

        Returns:
            Episode ready for transcription, or None if none available.
        """
        pass

    @abstractmethod
    def get_next_pending_post_processing(self) -> Episode | None:
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
            stage: Processing stage ("download", "transcript", "metadata", or "indexing").
        """
        pass

    # --- User Operations ---

    @abstractmethod
    def create_user(
        self,
        google_id: str,
        email: str,
        name: str | None = None,
        picture_url: str | None = None,
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
    def get_user(self, user_id: str) -> User | None:
        """Get a user by ID.

        Args:
            user_id: The user's UUID.

        Returns:
            Optional[User]: The user if found, None otherwise.
        """
        pass

    @abstractmethod
    def get_user_by_google_id(self, google_id: str) -> User | None:
        """Get a user by their Google ID.

        Args:
            google_id: Google's unique user identifier.

        Returns:
            Optional[User]: The user if found, None otherwise.
        """
        pass

    @abstractmethod
    def get_user_by_email(self, email: str) -> User | None:
        """Get a user by email address.

        Args:
            email: User's email address.

        Returns:
            Optional[User]: The user if found, None otherwise.
        """
        pass

    @abstractmethod
    def update_user(self, user_id: str, **kwargs) -> User | None:
        """Update a user's attributes.

        Args:
            user_id: The user's UUID.
            **kwargs: Attributes to update (name, picture_url, last_login, etc.).

        Returns:
            Optional[User]: The updated user if found, None otherwise.
        """
        pass

    @abstractmethod
    def list_users(
        self,
        is_admin: bool | None = None,
        is_active: bool | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[User]:
        """List users with optional filtering.

        Args:
            is_admin: Filter by admin status (optional).
            is_active: Filter by active status (optional).
            limit: Maximum number of users to return (optional).
            offset: Number of users to skip.

        Returns:
            List[User]: List of users matching the filters.
        """
        pass

    @abstractmethod
    def set_user_admin_status(self, user_id: str, is_admin: bool) -> User | None:
        """Set a user's admin status.

        Args:
            user_id: The user's UUID.
            is_admin: Whether the user should be an admin.

        Returns:
            Optional[User]: The updated user if found, None otherwise.
        """
        pass

    @abstractmethod
    def get_user_count(self, is_admin: bool | None = None) -> int:
        """Get total count of users with optional filtering.

        Args:
            is_admin: Filter by admin status (optional).

        Returns:
            int: Number of users matching the filter.
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
    def get_user_subscriptions(
        self,
        user_id: str,
        sort_by: str = "recency",
        sort_order: str = "desc"
    ) -> list[Podcast]:
        """Get all podcasts a user is subscribed to.

        Args:
            user_id: The user's UUID.
            sort_by: Field to sort by ("recency", "subscribers", "alphabetical"). Defaults to "recency".
            sort_order: Sort direction ("asc" or "desc"). Defaults to "desc".

        Returns:
            List[Podcast]: List of podcasts the user is subscribed to, sorted according to parameters.
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
        self, user_id: str, limit: int | None = None
    ) -> list[Podcast]:
        """List podcasts the user is subscribed to.

        This is the user-filtered equivalent of list_podcasts().

        Args:
            user_id: The user's UUID.
            limit: Maximum number of podcasts to return.

        Returns:
            List[Podcast]: List of subscribed podcasts.
        """
        pass

    # --- Email Digest Operations ---

    @abstractmethod
    def get_users_for_email_digest(self, limit: int = 100) -> list[User]:
        """Return users eligible for email digest.

        Returns users where:
        - email_digest_enabled is True
        - is_active is True
        - last_email_digest_sent is None or more than 20 hours ago

        Note: The caller must call mark_email_digest_sent() after successfully
        sending an email to update the user's last_email_digest_sent timestamp.
        This ensures users are only marked as "sent" when they actually receive
        an email (important for timezone-based delivery filtering).

        Args:
            limit: Maximum number of users to return (default 100).

        Returns:
            List[User]: Users eligible for email digest processing.
        """
        pass

    @abstractmethod
    def get_new_episodes_for_user_since(
        self, user_id: str, since: datetime, limit: int = 50
    ) -> list[Episode]:
        """Get new fully-processed episodes for a user's subscriptions published since a date.

        Only returns episodes with ai_summary populated (fully processed) and
        published_date after the specified time.

        Args:
            user_id: The user's UUID.
            since: Only include episodes published after this datetime.
            limit: Maximum number of episodes to return.

        Returns:
            List[Episode]: New processed episodes from user's subscribed podcasts.
        """
        pass

    @abstractmethod
    def mark_email_digest_sent(self, user_id: str) -> None:
        """Update user's last_email_digest_sent timestamp to now.

        Args:
            user_id: The user's UUID.
        """
        pass

    @abstractmethod
    def get_recent_processed_episodes(self, limit: int = 5) -> list[Episode]:
        """Get the most recently processed episodes from the database.

        Returns episodes with ai_summary populated, ordered by published_date descending.
        Used for email preview fallback when user has no subscriptions.

        Args:
            limit: Maximum number of episodes to return.

        Returns:
            List[Episode]: Recent processed episodes from any podcast.
        """
        pass

    # --- Conversation Operations ---

    @abstractmethod
    def create_conversation(
        self,
        user_id: str,
        scope: str,
        podcast_id: str | None = None,
        episode_id: str | None = None,
        title: str | None = None,
    ) -> Conversation:
        """Create a new conversation for a user.

        Args:
            user_id: The user's UUID.
            scope: Chat scope ('subscriptions', 'all', 'podcast', 'episode').
            podcast_id: Optional podcast ID for 'podcast' or 'episode' scope.
            episode_id: Optional episode ID for 'episode' scope.
            title: Optional conversation title.

        Returns:
            Conversation: The newly created conversation.
        """
        pass

    @abstractmethod
    def get_conversation(self, conversation_id: str) -> Conversation | None:
        """Get a conversation by ID with its messages.

        Args:
            conversation_id: The conversation UUID.

        Returns:
            Optional[Conversation]: The conversation if found, None otherwise.
        """
        pass

    @abstractmethod
    def list_conversations(
        self, user_id: str, limit: int = 50, offset: int = 0
    ) -> list[Conversation]:
        """List conversations for a user, ordered by most recent first.

        Args:
            user_id: The user's UUID.
            limit: Maximum number of conversations to return.
            offset: Number of conversations to skip.

        Returns:
            List[Conversation]: User's conversations ordered by updated_at desc.
        """
        pass

    @abstractmethod
    def update_conversation(
        self, conversation_id: str, **kwargs
    ) -> Conversation | None:
        """Update a conversation's attributes.

        Args:
            conversation_id: The conversation UUID.
            **kwargs: Fields to update (title, scope, podcast_id, episode_id).

        Returns:
            Optional[Conversation]: Updated conversation if found, None otherwise.
        """
        pass

    @abstractmethod
    def delete_conversation(self, conversation_id: str) -> bool:
        """Delete a conversation and all its messages.

        Args:
            conversation_id: The conversation UUID.

        Returns:
            bool: True if deleted, False if not found.
        """
        pass

    @abstractmethod
    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        citations: list[dict[str, Any]] | None = None,
    ) -> ChatMessage:
        """Add a message to a conversation.

        Args:
            conversation_id: The conversation UUID.
            role: Message role ('user' or 'assistant').
            content: Message content.
            citations: Optional list of citation objects for assistant messages.

        Returns:
            ChatMessage: The newly created message.
        """
        pass

    @abstractmethod
    def get_messages(
        self, conversation_id: str, limit: int = 100, offset: int = 0
    ) -> list[ChatMessage]:
        """Get messages for a conversation, ordered by creation time.

        Args:
            conversation_id: The conversation UUID.
            limit: Maximum number of messages to return.
            offset: Number of messages to skip.

        Returns:
            List[ChatMessage]: Messages ordered by created_at asc.
        """
        pass

    @abstractmethod
    def count_conversations(self, user_id: str) -> int:
        """Count total conversations for a user.

        Args:
            user_id: The user's UUID.

        Returns:
            int: Number of conversations.
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
        pool_size: int = 3,  # Supabase-optimized
        max_overflow: int = 2,  # Supabase-optimized
        echo: bool = False,
        pool_pre_ping: bool = True,  # Detect stale connections
        pool_recycle: int = 1800,  # Recycle connections after 30 minutes
    ):
        """
        Initialize the repository and configure its SQLAlchemy engine and session factory.

        Creates an engine appropriate for the provided database URL, prepares a session factory, and ensures the ORM tables are created.

        Parameters:
            database_url (str): SQLAlchemy-compatible database URL.
            pool_size (int): Connection pool size for non-SQLite databases (default 3 for Supabase).
            max_overflow (int): Maximum overflow connections for non-SQLite databases (default 2 for Supabase).
            echo (bool): If true, enable SQLAlchemy SQL statement logging.
            pool_pre_ping (bool): If true, test connections for liveness before using them (recommended for Supabase).
            pool_recycle (int): Seconds after which to recycle connections (default 1800 = 30 minutes).
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
            # PostgreSQL (including Supabase)
            self.engine = create_engine(
                database_url,
                pool_size=pool_size,
                max_overflow=max_overflow,
                pool_pre_ping=pool_pre_ping,  # Test connections before use
                pool_recycle=pool_recycle,  # Proactively recycle stale connections
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

    def get_podcast(self, podcast_id: str) -> Podcast | None:
        """
        Retrieve a podcast by its primary key.

        Returns:
            Podcast | None: The matching Podcast instance if found, `None` otherwise.
        """
        with self._get_session() as session:
            return session.get(Podcast, podcast_id)

    def get_podcast_by_feed_url(self, feed_url: str) -> Podcast | None:
        """
        Finds the podcast record that matches the given RSS/Atom feed URL.

        Returns:
            Podcast or None: The `Podcast` instance with `feed_url`, or `None` if no match is found.
        """
        with self._get_session() as session:
            stmt = select(Podcast).where(Podcast.feed_url == feed_url)
            return session.scalar(stmt)

    def list_podcasts(
        self,
        limit: int | None = None,
        sort_by: str = "recency",
        sort_order: str = "desc"
    ) -> list[Podcast]:
        """
        List all podcasts with configurable sorting.

        Use list_podcasts_with_subscribers() to get only podcasts with active subscribers.

        Parameters:
            limit (Optional[int]): Maximum number of podcasts to return; if None, no limit is applied.
            sort_by (str): Field to sort by ("recency", "subscribers", "alphabetical")
            sort_order (str): Sort direction ("asc" or "desc")

        Returns:
            List[Podcast]: Podcasts ordered by the specified criteria.
        """
        with self._get_session() as session:
            # Build base query
            stmt = select(Podcast)

            # Determine sort column
            if sort_by == "recency":
                order_col = Podcast.last_new_episode
            elif sort_by == "alphabetical":
                order_col = Podcast.title
            elif sort_by == "subscribers":
                # Subquery to count subscribers per podcast
                subscriber_count = (
                    select(func.count(UserSubscription.user_id))
                    .where(UserSubscription.podcast_id == Podcast.id)
                    .correlate(Podcast)
                    .scalar_subquery()
                )
                order_col = subscriber_count
            else:
                # Fallback to alphabetical for invalid sort_by
                order_col = Podcast.title

            # Apply sort direction
            # For recency, handle nulls by placing them last regardless of direction
            if sort_by == "recency":
                if sort_order == "desc":
                    stmt = stmt.order_by(order_col.desc().nullslast())
                else:
                    stmt = stmt.order_by(order_col.asc().nullslast())
            else:
                if sort_order == "desc":
                    stmt = stmt.order_by(order_col.desc())
                else:
                    stmt = stmt.order_by(order_col.asc())

            if limit:
                stmt = stmt.limit(limit)
            return list(session.scalars(stmt).all())

    def update_podcast(self, podcast_id: str, **kwargs) -> Podcast | None:
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

    def list_podcasts_with_subscribers(
        self, limit: int | None = None, source_type: str | None = None
    ) -> list[Podcast]:
        """List podcasts that have at least one user subscribed.

        This is used by the pipeline to determine which podcasts need to be synced.
        Only podcasts with active user subscriptions are returned.

        Args:
            limit: Maximum number of podcasts to return.
            source_type: Filter by source type ("rss", "youtube", or None for all).

        Returns:
            List[Podcast]: Podcasts with at least one subscriber.
        """
        with self._get_session() as session:
            # Get distinct podcast IDs that have at least one subscription
            subquery = (
                select(UserSubscription.podcast_id)
                .distinct()
                .subquery()
            )
            stmt = select(Podcast).where(Podcast.id.in_(select(subquery)))
            if source_type:
                stmt = stmt.where(Podcast.source_type == source_type)
            if limit:
                stmt = stmt.limit(limit)
            return list(session.scalars(stmt).all())

    def get_podcast_by_youtube_channel_id(self, channel_id: str) -> Podcast | None:
        """Retrieve a podcast by its YouTube channel ID.

        Args:
            channel_id: YouTube channel ID (UC... format).

        Returns:
            Podcast if found, None otherwise.
        """
        with self._get_session() as session:
            stmt = select(Podcast).where(Podcast.youtube_channel_id == channel_id)
            return session.scalar(stmt)

    def get_youtube_videos_pending_caption_download(
        self, limit: int = 10
    ) -> list[Episode]:
        """Get YouTube videos that need caption/audio download.

        Returns videos where:
        - source_type is "youtube_video"
        - download_status is "pending"

        Args:
            limit: Maximum number of episodes to return.

        Returns:
            List of episodes pending caption/audio download.
        """
        with self._get_session() as session:
            stmt = (
                select(Episode)
                .where(Episode.source_type == "youtube_video")
                .where(Episode.download_status == "pending")
                .order_by(Episode.published_date.desc().nullslast())
                .limit(limit)
            )
            return list(session.scalars(stmt).all())

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

    def get_episode(self, episode_id: str) -> Episode | None:
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

    def get_episode_by_guid(self, podcast_id: str, guid: str) -> Episode | None:
        """
        Retrieve an episode by its GUID for the specified podcast.

        @returns The Episode if found, `None` otherwise.
        """
        with self._get_session() as session:
            stmt = select(Episode).where(
                Episode.podcast_id == podcast_id, Episode.guid == guid
            )
            return session.scalar(stmt)

    def get_latest_episode(self, podcast_id: str) -> Episode | None:
        """
        Retrieve the most recent episode for a podcast based on published_date.

        @returns The most recent Episode if found, `None` otherwise.
        """
        with self._get_session() as session:
            stmt = (
                select(Episode)
                .where(Episode.podcast_id == podcast_id)
                .where(Episode.published_date.isnot(None))
                .order_by(Episode.published_date.desc())
                .limit(1)
            )
            return session.scalar(stmt)

    def get_episode_by_file_search_display_name(
        self, display_name: str
    ) -> Episode | None:
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

    def get_podcast_by_description_display_name(
        self, display_name: str
    ) -> Podcast | None:
        """
        Retrieve a podcast by its description File Search display name.

        Used by the web app to look up podcast metadata for discovery queries.

        @returns The Podcast if found, `None` otherwise.
        """
        with self._get_session() as session:
            stmt = (
                select(Podcast)
                .where(Podcast.description_file_search_display_name == display_name)
            )
            return session.scalars(stmt).first()

    def list_episodes(
        self,
        podcast_id: str | None = None,
        download_status: str | None = None,
        transcript_status: str | None = None,
        metadata_status: str | None = None,
        file_search_status: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Episode]:
        """
        Retrieve episodes optionally filtered by podcast and processing statuses, with pagination.

        Parameters:
            podcast_id (Optional[str]): Filter episodes belonging to the given podcast.
            download_status (Optional[str]): Filter by download status (e.g., "pending", "completed", "failed").
            transcript_status (Optional[str]): Filter by transcription status (e.g., "pending", "completed", "failed").
            metadata_status (Optional[str]): Filter by metadata status (e.g., "pending", "completed", "failed").
            file_search_status (Optional[str]): Filter by file-search/indexing status (e.g., "pending", "indexed", "failed").
            limit (Optional[int]): Maximum number of episodes to return. If None, no limit is applied.
            offset (int): Number of episodes to skip before collecting results (for pagination).

        Returns:
            List[Episode]: Episodes matching the supplied filters ordered by published date (newest first).
        """
        with self._get_session() as session:
            stmt = select(Episode).options(joinedload(Episode.podcast))

            if podcast_id:
                stmt = stmt.where(Episode.podcast_id == podcast_id)
            if download_status:
                stmt = stmt.where(Episode.download_status == download_status)
            if transcript_status:
                stmt = stmt.where(Episode.transcript_status == transcript_status)
            if metadata_status:
                stmt = stmt.where(Episode.metadata_status == metadata_status)
            if file_search_status:
                stmt = stmt.where(Episode.file_search_status == file_search_status)

            stmt = stmt.order_by(Episode.published_date.desc())
            stmt = stmt.offset(offset)
            if limit:
                stmt = stmt.limit(limit)

            return list(session.scalars(stmt).unique().all())

    def count_episodes(
        self,
        podcast_id: str | None = None,
        download_status: str | None = None,
        transcript_status: str | None = None,
        metadata_status: str | None = None,
        file_search_status: str | None = None,
    ) -> int:
        """
        Count episodes matching the given filters.

        Parameters:
            podcast_id (Optional[str]): If provided, only count episodes belonging to this podcast.
            download_status (Optional[str]): If provided, filter by download status.
            transcript_status (Optional[str]): If provided, filter by transcript status.
            metadata_status (Optional[str]): If provided, filter by metadata status.
            file_search_status (Optional[str]): If provided, filter by file search status.

        Returns:
            int: Count of episodes matching the filters.
        """
        with self._get_session() as session:
            stmt = select(func.count(Episode.id))

            if podcast_id:
                stmt = stmt.where(Episode.podcast_id == podcast_id)
            if download_status:
                stmt = stmt.where(Episode.download_status == download_status)
            if transcript_status:
                stmt = stmt.where(Episode.transcript_status == transcript_status)
            if metadata_status:
                stmt = stmt.where(Episode.metadata_status == metadata_status)
            if file_search_status:
                stmt = stmt.where(Episode.file_search_status == file_search_status)

            return session.scalar(stmt) or 0

    def update_episode(self, episode_id: str, **kwargs) -> Episode | None:
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

    def get_existing_episode_guids(self, podcast_id: str) -> set[str]:
        """
        Get all existing episode GUIDs for a podcast in a single query.

        This is an optimized batch operation for sync - instead of checking
        each episode individually (N queries), fetch all GUIDs at once (1 query).

        Parameters:
            podcast_id (str): ID of the podcast.

        Returns:
            set[str]: Set of GUIDs for all episodes belonging to this podcast.
        """
        with self._get_session() as session:
            stmt = select(Episode.guid).where(Episode.podcast_id == podcast_id)
            return set(session.scalars(stmt).all())

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
    ) -> list[Episode]:
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
    ) -> list[Episode]:
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

    def get_episodes_pending_download(self, limit: int = 10) -> list[Episode]:
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

    def get_episodes_pending_transcription(self, limit: int = 10) -> list[Episode]:
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

    def get_episodes_pending_metadata(self, limit: int = 10) -> list[Episode]:
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

    def get_episodes_pending_indexing(self, limit: int = 10) -> list[Episode]:
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

    def count_episodes_pending_indexing(self) -> int:
        """
        Count episodes pending File Search indexing.

        Returns:
            int: Number of episodes waiting to be indexed.
        """
        with self._get_session() as session:
            return (
                session.scalar(
                    select(func.count(Episode.id)).where(
                        Episode.metadata_status == "completed",
                        Episode.file_search_status == "pending",
                        or_(
                            Episode.transcript_text.isnot(None),
                            Episode.transcript_path.isnot(None),
                        ),
                    )
                )
                or 0
            )

    def get_episodes_ready_for_cleanup(self, limit: int = 10) -> list[Episode]:
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
        transcript_path: str | None = None,
        transcript_source: str | None = None,
    ) -> None:
        """
        Mark an episode's transcription as complete and store the transcript content.

        Parameters:
            episode_id (str): ID of the episode to update.
            transcript_text (str): Full transcript content.
            transcript_path (str, optional): Legacy file path, kept for backward compatibility.
            transcript_source (str, optional): Source of transcript ("whisper" | "youtube_captions").

        Notes:
            Sets `transcript_status` to "completed", stores `transcript_text` (and optionally
            `transcript_path` and `transcript_source`), sets `transcribed_at` to the current
            UTC time, and clears `transcript_error`.
        """
        self.update_episode(
            episode_id,
            transcript_status="completed",
            transcript_text=transcript_text,
            transcript_path=transcript_path,
            transcript_source=transcript_source,
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
        summary: str | None = None,
        keywords: list[str] | None = None,
        hosts: list[str] | None = None,
        guests: list[str] | None = None,
        mp3_artist: str | None = None,
        mp3_album: str | None = None,
        email_content: dict[str, Any] | None = None,
        metadata_path: str | None = None,
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
            email_content (Optional[Dict[str, Any]]): Email-optimized content for digest emails.
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
            ai_email_content=email_content,
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

    # --- Podcast Description Indexing ---

    def get_podcasts_pending_description_indexing(self, limit: int = 10) -> list[Podcast]:
        """
        Return podcasts with descriptions that need File Search indexing.

        Podcasts returned have a non-empty description and description_file_search_status
        set to "pending". Results are ordered by created_at and limited to `limit` items.

        Returns:
            List[Podcast]: Podcasts ready for description indexing.
        """
        with self._get_session() as session:
            stmt = (
                select(Podcast)
                .where(
                    Podcast.description.isnot(None),
                    Podcast.description != "",
                    Podcast.description_file_search_status == "pending",
                )
                .order_by(Podcast.created_at.asc())
                .limit(limit)
            )
            return list(session.scalars(stmt).all())

    def count_podcasts_pending_description_indexing(self) -> int:
        """
        Count podcasts pending description indexing.

        Returns:
            int: Number of podcasts waiting to have descriptions indexed.
        """
        with self._get_session() as session:
            return (
                session.scalar(
                    select(func.count(Podcast.id)).where(
                        Podcast.description.isnot(None),
                        Podcast.description != "",
                        Podcast.description_file_search_status == "pending",
                    )
                )
                or 0
            )

    def mark_description_indexing_started(self, podcast_id: str) -> None:
        """
        Mark a podcast's description as in-progress for File Search indexing.

        Updates the podcast's description_file_search_status to "uploading" and
        clears any previous error.

        Parameters:
            podcast_id (str): Primary key of the podcast to update.
        """
        self.update_podcast(
            podcast_id,
            description_file_search_status="uploading",
            description_file_search_error=None,
        )

    def mark_description_indexing_complete(
        self, podcast_id: str, resource_name: str, display_name: str
    ) -> None:
        """
        Record that a podcast's description indexing finished successfully.

        Parameters:
            podcast_id (str): Identifier of the podcast whose indexing completed.
            resource_name (str): File Search resource name for the indexed document.
            display_name (str): Human-readable name for the indexed resource.
        """
        self.update_podcast(
            podcast_id,
            description_file_search_status="indexed",
            description_file_search_resource_name=resource_name,
            description_file_search_display_name=display_name,
            description_file_search_uploaded_at=datetime.now(UTC),
            description_file_search_error=None,
        )

    def mark_description_indexing_failed(self, podcast_id: str, error: str) -> None:
        """
        Record that description indexing for the specified podcast failed.

        Parameters:
            podcast_id (str): The ID of the podcast whose indexing failed.
            error (str): A human-readable error message describing the failure.
        """
        self.update_podcast(
            podcast_id,
            description_file_search_status="failed",
            description_file_search_error=error,
        )

    # --- Bulk Reset Operations (for migrations) ---

    def reset_all_episode_indexing_status(self) -> int:
        """
        Reset all episodes' file_search_status to pending.

        Returns:
            int: Number of episodes reset.
        """
        from sqlalchemy import text

        with self._get_session() as session:
            result = session.execute(
                text("""
                    UPDATE episodes
                    SET file_search_status = 'pending',
                        file_search_error = NULL,
                        file_search_resource_name = NULL,
                        file_search_display_name = NULL,
                        file_search_uploaded_at = NULL
                    WHERE file_search_status != 'pending'
                """)
            )
            session.commit()
            return result.rowcount

    def count_episodes_not_pending_indexing(self) -> int:
        """
        Count episodes that are not in pending indexing status.

        Returns:
            int: Number of episodes with file_search_status != 'pending'.
        """
        from sqlalchemy import text

        with self._get_session() as session:
            result = session.execute(
                text("SELECT COUNT(*) FROM episodes WHERE file_search_status != 'pending'")
            )
            return result.scalar() or 0

    def reset_all_podcast_description_indexing_status(self) -> int:
        """
        Reset all podcasts' description_file_search_status to pending.

        Returns:
            int: Number of podcasts reset.
        """
        from sqlalchemy import text

        with self._get_session() as session:
            result = session.execute(
                text("""
                    UPDATE podcasts
                    SET description_file_search_status = 'pending',
                        description_file_search_error = NULL,
                        description_file_search_resource_name = NULL,
                        description_file_search_display_name = NULL,
                        description_file_search_uploaded_at = NULL
                    WHERE description_file_search_status != 'pending'
                """)
            )
            session.commit()
            return result.rowcount

    def count_podcasts_not_pending_description_indexing(self) -> int:
        """
        Count podcasts that are not in pending description indexing status.

        Returns:
            int: Number of podcasts with description_file_search_status != 'pending'.
        """
        from sqlalchemy import text

        with self._get_session() as session:
            result = session.execute(
                text("SELECT COUNT(*) FROM podcasts WHERE description_file_search_status != 'pending'")
            )
            return result.scalar() or 0

    # --- Transcript Access ---

    def get_transcript_text(self, episode_id: str) -> str | None:
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
                with open(episode.transcript_path, encoding="utf-8") as f:
                    return f.read()
            except (OSError, UnicodeDecodeError) as e:
                logger.warning(f"Failed to read transcript file {episode.transcript_path}: {e}")
                return None

        return None

    # --- Statistics ---

    def get_podcast_stats(self, podcast_id: str) -> dict[str, Any]:
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

    def get_podcast_episode_counts(self, podcast_ids: list[str]) -> dict[str, int]:
        """
        Efficiently get episode counts for multiple podcasts in a single query.

        Uses a single SQL GROUP BY query instead of N separate queries, resulting
        in significantly better performance when fetching counts for many podcasts.

        Parameters:
            podcast_ids (List[str]): List of podcast IDs to get counts for.

        Returns:
            Dict[str, int]: Mapping of podcast_id -> episode_count.
                            Podcasts with 0 episodes will have count = 0.
        """
        from sqlalchemy import func

        if not podcast_ids:
            return {}

        with self._get_session() as session:
            # Single query with GROUP BY to count episodes per podcast
            counts = (
                session.query(
                    Episode.podcast_id,
                    func.count(Episode.id).label('episode_count')
                )
                .filter(Episode.podcast_id.in_(podcast_ids))
                .group_by(Episode.podcast_id)
                .all()
            )

            # Convert to dict and ensure all requested podcasts are in result (with 0 for missing)
            count_map = {str(podcast_id): count for podcast_id, count in counts}

            # Fill in 0 for podcasts with no episodes
            for podcast_id in podcast_ids:
                if podcast_id not in count_map:
                    count_map[podcast_id] = 0

            return count_map

    def get_podcast_subscriber_counts(self, podcast_ids: list[str]) -> dict[str, int]:
        """
        Efficiently get subscriber counts for multiple podcasts in a single query.

        Uses a single SQL GROUP BY query instead of N separate queries, resulting
        in significantly better performance when fetching counts for many podcasts.

        Parameters:
            podcast_ids (List[str]): List of podcast IDs to get counts for.

        Returns:
            Dict[str, int]: Mapping of podcast_id -> subscriber_count.
                            Podcasts with 0 subscribers will have count = 0.
        """
        from sqlalchemy import func

        if not podcast_ids:
            return {}

        with self._get_session() as session:
            # Single query with GROUP BY to count subscribers per podcast
            counts = (
                session.query(
                    UserSubscription.podcast_id,
                    func.count(UserSubscription.user_id).label('subscriber_count')
                )
                .filter(UserSubscription.podcast_id.in_(podcast_ids))
                .group_by(UserSubscription.podcast_id)
                .all()
            )

            # Convert to dict and ensure all requested podcasts are in result (with 0 for missing)
            count_map = {str(podcast_id): count for podcast_id, count in counts}

            # Fill in 0 for podcasts with no subscribers
            for podcast_id in podcast_ids:
                if podcast_id not in count_map:
                    count_map[podcast_id] = 0

            return count_map

    def get_overall_stats(self) -> dict[str, Any]:
        """
        Return aggregated system-wide counts for podcasts and episodes across processing stages.

        Optimized to use SQL aggregations instead of loading all records into memory.

        @returns:
            stats (Dict[str, Any]): Mapping of statistic names to integer counts:
                - total_podcasts: Total number of podcasts in the repository.
                - subscribed_podcasts: Number of podcasts with at least one user subscriber.
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
        from sqlalchemy import case

        with self._get_session() as session:
            # Podcast counts (efficient SQL aggregations)
            total_podcasts = session.scalar(select(func.count(Podcast.id))) or 0
            # Count podcasts with at least one subscriber
            subscribed_podcasts = session.scalar(
                select(func.count(func.distinct(UserSubscription.podcast_id)))
            ) or 0

            # Episode counts by status (single query with conditional aggregation)
            episode_stats = session.execute(
                select(
                    func.count(Episode.id).label('total_episodes'),
                    # Download status counts
                    func.count(case((Episode.download_status == 'pending', 1))).label('pending_download'),
                    func.count(case((Episode.download_status == 'downloading', 1))).label('downloading'),
                    func.count(case((Episode.download_status == 'completed', 1))).label('downloaded'),
                    func.count(case((Episode.download_status == 'failed', 1))).label('download_failed'),
                    # Transcript status counts
                    func.count(case((Episode.transcript_status == 'pending', 1))).label('pending_transcription'),
                    func.count(case((Episode.transcript_status == 'processing', 1))).label('transcribing'),
                    func.count(case((Episode.transcript_status == 'completed', 1))).label('transcribed'),
                    func.count(case((Episode.transcript_status == 'failed', 1))).label('transcript_failed'),
                    # File search status counts
                    func.count(case((Episode.file_search_status == 'pending', 1))).label('pending_indexing'),
                    func.count(case((Episode.file_search_status == 'indexed', 1))).label('indexed'),
                )
            ).one()

            # Fully processed count (separate query as it involves computed property)
            # Episodes are fully processed when all stages are complete
            fully_processed = session.scalar(
                select(func.count(Episode.id)).where(
                    Episode.download_status == 'completed',
                    Episode.transcript_status == 'completed',
                    Episode.file_search_status == 'indexed'
                )
            ) or 0

            return {
                "total_podcasts": total_podcasts,
                "subscribed_podcasts": subscribed_podcasts,
                "total_episodes": episode_stats.total_episodes,
                "pending_download": episode_stats.pending_download,
                "downloading": episode_stats.downloading,
                "downloaded": episode_stats.downloaded,
                "download_failed": episode_stats.download_failed,
                "pending_transcription": episode_stats.pending_transcription,
                "transcribing": episode_stats.transcribing,
                "transcribed": episode_stats.transcribed,
                "transcript_failed": episode_stats.transcript_failed,
                "pending_indexing": episode_stats.pending_indexing,
                "indexed": episode_stats.indexed,
                "fully_processed": fully_processed,
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

    def get_next_for_transcription(self) -> Episode | None:
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

    def get_next_pending_post_processing(self) -> Episode | None:
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
            stage: Stage name ('download', 'transcript', 'metadata', or 'indexing').
        """
        status_map = {
            "download": ("download_status", "download_error"),
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
        name: str | None = None,
        picture_url: str | None = None,
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
                logger.info(f"Created new user: user_id={user.id}")
                return user
            except IntegrityError as e:
                session.rollback()
                logger.info(f"User already exists, fetching existing: google_id={google_id}")
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
                # If we can't find the existing user, re-raise with chaining
                raise ValueError(
                    f"IntegrityError but user not found: google_id={google_id}"
                ) from e

    def get_user(self, user_id: str) -> User | None:
        """Get a user by ID."""
        with self._get_session() as session:
            return session.get(User, user_id)

    def get_user_by_google_id(self, google_id: str) -> User | None:
        """Get a user by their Google ID."""
        with self._get_session() as session:
            stmt = select(User).where(User.google_id == google_id)
            return session.scalar(stmt)

    def get_user_by_email(self, email: str) -> User | None:
        """Get a user by email address."""
        with self._get_session() as session:
            stmt = select(User).where(User.email == email)
            return session.scalar(stmt)

    def update_user(self, user_id: str, **kwargs) -> User | None:
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

    def list_users(
        self,
        is_admin: bool | None = None,
        is_active: bool | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[User]:
        """List users with optional filtering."""
        with self._get_session() as session:
            stmt = select(User)
            if is_admin is not None:
                stmt = stmt.where(User.is_admin == is_admin)
            if is_active is not None:
                stmt = stmt.where(User.is_active == is_active)
            stmt = stmt.order_by(User.created_at.desc())
            stmt = stmt.offset(offset)
            if limit:
                stmt = stmt.limit(limit)
            return list(session.scalars(stmt).all())

    def set_user_admin_status(self, user_id: str, is_admin: bool) -> User | None:
        """Set a user's admin status."""
        return self.update_user(user_id, is_admin=is_admin)

    def get_user_count(self, is_admin: bool | None = None) -> int:
        """Get total count of users with optional filtering."""
        with self._get_session() as session:
            stmt = select(func.count(User.id))
            if is_admin is not None:
                stmt = stmt.where(User.is_admin == is_admin)
            return session.scalar(stmt) or 0

    # --- Subscription Operations ---

    def subscribe_user_to_podcast(self, user_id: str, podcast_id: str) -> UserSubscription:
        """Subscribe a user to a podcast.

        Handles race conditions where concurrent requests may both pass the
        pre-check. If an IntegrityError occurs due to unique constraint
        violation, returns the existing subscription instead of raising.
        """
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

            try:
                session.commit()
                session.refresh(subscription)
                logger.info(f"User {user_id} subscribed to podcast {podcast_id}")
                return subscription
            except IntegrityError:
                # Race condition: another request created the subscription
                session.rollback()
                logger.debug(
                    f"Subscription race condition for user {user_id}, podcast {podcast_id}"
                )
                # Re-query for the existing subscription
                existing = session.scalar(
                    select(UserSubscription).where(
                        UserSubscription.user_id == user_id,
                        UserSubscription.podcast_id == podcast_id,
                    )
                )
                if existing:
                    return existing
                # Should not happen, but re-raise if subscription still not found
                raise

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

    def get_user_subscriptions(
        self,
        user_id: str,
        sort_by: str = "recency",
        sort_order: str = "desc"
    ) -> list[Podcast]:
        """Get all podcasts a user is subscribed to."""
        with self._get_session() as session:
            # Build base query
            stmt = (
                select(Podcast)
                .join(UserSubscription, Podcast.id == UserSubscription.podcast_id)
                .where(UserSubscription.user_id == user_id)
            )

            # Determine sort column
            if sort_by == "recency":
                order_col = Podcast.last_new_episode
            elif sort_by == "alphabetical":
                order_col = Podcast.title
            elif sort_by == "subscribers":
                # Subquery to count subscribers per podcast
                subscriber_count = (
                    select(func.count(UserSubscription.user_id))
                    .where(UserSubscription.podcast_id == Podcast.id)
                    .correlate(Podcast)
                    .scalar_subquery()
                )
                order_col = subscriber_count
            else:
                # Fallback to alphabetical for invalid sort_by
                order_col = Podcast.title

            # Apply sort direction
            # For recency, handle nulls by placing them last regardless of direction
            if sort_by == "recency":
                if sort_order == "desc":
                    stmt = stmt.order_by(order_col.desc().nullslast())
                else:
                    stmt = stmt.order_by(order_col.asc().nullslast())
            else:
                if sort_order == "desc":
                    stmt = stmt.order_by(order_col.desc())
                else:
                    stmt = stmt.order_by(order_col.asc())

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
        self, user_id: str, limit: int | None = None
    ) -> list[Podcast]:
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

    # --- Email Digest Operations ---

    def get_users_for_email_digest(self, limit: int = 100) -> list[User]:
        """Return users eligible for email digest.

        Returns users where:
        - email_digest_enabled is True
        - is_active is True
        - last_email_digest_sent is NULL or older than 20 hours

        Note: The caller must call mark_email_digest_sent() after successfully
        sending an email to update the user's last_email_digest_sent timestamp.
        This ensures users are only marked as "sent" when they actually receive
        an email (important for timezone-based delivery filtering).
        """
        twenty_hours_ago = datetime.now(UTC) - timedelta(hours=20)

        with self._get_session() as session:
            # Build query for eligible users
            base_conditions = [
                User.email_digest_enabled.is_(True),
                User.is_active.is_(True),
                or_(
                    User.last_email_digest_sent.is_(None),
                    User.last_email_digest_sent < twenty_hours_ago
                )
            ]

            stmt = (
                select(User)
                .where(*base_conditions)
                .order_by(User.last_email_digest_sent.asc().nullsfirst())
                .limit(limit)
            )
            users = list(session.scalars(stmt).all())

            # Expunge users so they can be used after session closes
            for user in users:
                session.expunge(user)

            return users

    def get_new_episodes_for_user_since(
        self, user_id: str, since: datetime, limit: int = 50
    ) -> list[Episode]:
        """Get new fully-processed episodes for a user's subscriptions published since a date.

        Only returns episodes with ai_summary populated (fully processed) and
        published_date after the specified time.
        """
        with self._get_session() as session:
            stmt = (
                select(Episode)
                .options(joinedload(Episode.podcast))
                .join(UserSubscription, Episode.podcast_id == UserSubscription.podcast_id)
                .where(
                    UserSubscription.user_id == user_id,
                    Episode.published_date > since,
                    Episode.ai_summary.isnot(None),
                    Episode.metadata_status == "completed",
                )
                .order_by(Episode.published_date.desc())
                .limit(limit)
            )
            return list(session.scalars(stmt).unique().all())

    def mark_email_digest_sent(self, user_id: str) -> None:
        """Update user's last_email_digest_sent timestamp to now."""
        self.update_user(user_id, last_email_digest_sent=datetime.now(UTC))

    def get_recent_processed_episodes(self, limit: int = 5) -> list[Episode]:
        """Get the most recently processed episodes from the database.

        Returns episodes with ai_summary populated, ordered by published_date descending.
        Used for email preview fallback when user has no subscriptions.
        """
        with self._get_session() as session:
            stmt = (
                select(Episode)
                .options(joinedload(Episode.podcast))
                .where(
                    Episode.ai_summary.isnot(None),
                    Episode.metadata_status == "completed",
                )
                .order_by(Episode.published_date.desc())
                .limit(limit)
            )
            return list(session.scalars(stmt).unique().all())

    # --- Conversation Operations ---

    def create_conversation(
        self,
        user_id: str,
        scope: str,
        podcast_id: str | None = None,
        episode_id: str | None = None,
        title: str | None = None,
    ) -> Conversation:
        """Create a new conversation for a user."""
        with self._get_session() as session:
            conversation = Conversation(
                user_id=user_id,
                scope=scope,
                podcast_id=podcast_id,
                episode_id=episode_id,
                title=title,
            )
            session.add(conversation)
            session.commit()
            session.refresh(conversation)
            return conversation

    def get_conversation(self, conversation_id: str) -> Conversation | None:
        """Get a conversation by ID with its messages and related entities."""
        with self._get_session() as session:
            stmt = (
                select(Conversation)
                .options(
                    joinedload(Conversation.messages),
                    joinedload(Conversation.podcast),
                    joinedload(Conversation.episode),
                )
                .where(Conversation.id == conversation_id)
            )
            return session.scalars(stmt).unique().first()

    def list_conversations(
        self, user_id: str, limit: int = 50, offset: int = 0
    ) -> list[Conversation]:
        """List conversations for a user, ordered by most recent first."""
        with self._get_session() as session:
            stmt = (
                select(Conversation)
                .options(
                    joinedload(Conversation.podcast),
                    joinedload(Conversation.episode),
                )
                .where(Conversation.user_id == user_id)
                .order_by(Conversation.updated_at.desc())
                .offset(offset)
                .limit(limit)
            )
            return list(session.scalars(stmt).unique().all())

    def update_conversation(
        self, conversation_id: str, **kwargs
    ) -> Conversation | None:
        """Update a conversation's attributes."""
        with self._get_session() as session:
            conversation = session.get(Conversation, conversation_id)
            if not conversation:
                return None

            allowed_fields = {"title", "scope", "podcast_id", "episode_id"}
            for key, value in kwargs.items():
                if key in allowed_fields:
                    setattr(conversation, key, value)

            conversation.updated_at = datetime.now(UTC)
            session.commit()
            session.refresh(conversation)
            return conversation

    def delete_conversation(self, conversation_id: str) -> bool:
        """Delete a conversation and all its messages (via cascade)."""
        with self._get_session() as session:
            conversation = session.get(Conversation, conversation_id)
            if not conversation:
                return False

            session.delete(conversation)
            session.commit()
            return True

    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        citations: list[dict[str, Any]] | None = None,
    ) -> ChatMessage:
        """Add a message to a conversation and update conversation's updated_at."""
        with self._get_session() as session:
            message = ChatMessage(
                conversation_id=conversation_id,
                role=role,
                content=content,
                citations=citations,
            )
            session.add(message)

            # Update conversation's updated_at timestamp and message count
            conversation = session.get(Conversation, conversation_id)
            if conversation:
                conversation.updated_at = datetime.now(UTC)
                conversation.message_count = (conversation.message_count or 0) + 1

            session.commit()
            session.refresh(message)
            return message

    def get_messages(
        self, conversation_id: str, limit: int = 100, offset: int = 0
    ) -> list[ChatMessage]:
        """Get messages for a conversation, ordered by creation time."""
        with self._get_session() as session:
            stmt = (
                select(ChatMessage)
                .where(ChatMessage.conversation_id == conversation_id)
                .order_by(ChatMessage.created_at.asc())
                .offset(offset)
                .limit(limit)
            )
            return list(session.scalars(stmt).all())

    def count_conversations(self, user_id: str) -> int:
        """Count total conversations for a user."""
        with self._get_session() as session:
            stmt = (
                select(func.count())
                .select_from(Conversation)
                .where(Conversation.user_id == user_id)
            )
            return session.scalar(stmt) or 0

    # --- Connection Management ---

    def close(self) -> None:
        """
        Dispose the SQLAlchemy engine and release database connections and resources.

        This closes all pooled connections and frees underlying resources held by the engine.
        """
        self.engine.dispose()
        logger.info("Database connection closed")
