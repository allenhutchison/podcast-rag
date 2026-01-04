"""Metadata worker for episode metadata extraction.

Extracts and merges metadata from multiple sources:
1. Feed metadata (most trustworthy) - already in Episode model
2. MP3 ID3 tags - read from downloaded audio file
3. AI-generated metadata - fills gaps (summary, keywords, hosts, guests)
"""

import json
import logging
import os
import time
from dataclasses import dataclass
from threading import Lock
from typing import Any

from src.config import Config
from src.db.models import Episode
from src.db.repository import PodcastRepositoryInterface
from src.prompt_manager import PromptManager
from src.schemas import PodcastMetadata
from src.workflow.workers.base import WorkerInterface, WorkerResult

logger = logging.getLogger(__name__)


class RateLimiter:
    """Token bucket rate limiter for API requests."""

    def __init__(self, max_requests: int, time_window: int):
        self.max_requests = max_requests
        self.time_window = time_window
        self.tokens = max_requests
        self.last_update = time.time()
        self.lock = Lock()

    def _update_tokens(self) -> None:
        now = time.time()
        time_passed = now - self.last_update
        self.tokens = min(
            self.max_requests,
            self.tokens + (time_passed * self.max_requests / self.time_window),
        )
        self.last_update = now

    def acquire(self) -> bool:
        with self.lock:
            self._update_tokens()
            while self.tokens < 1:
                sleep_time = (1 - self.tokens) * (self.time_window / self.max_requests)
                time.sleep(sleep_time)
                self._update_tokens()
            self.tokens -= 1
            return True


@dataclass
class MergedMetadata:
    """Merged metadata from all sources."""

    # From feed (most trustworthy)
    title: str
    description: str | None = None
    published_date: str | None = None
    duration_seconds: int | None = None
    episode_number: str | None = None
    season_number: int | None = None

    # From MP3 tags
    mp3_artist: str | None = None
    mp3_album: str | None = None

    # From AI
    summary: str | None = None
    keywords: list[str] | None = None
    hosts: list[str] | None = None
    guests: list[str] | None = None
    email_content: dict[str, Any] | None = None


class MetadataWorker(WorkerInterface):
    """Worker that extracts and merges metadata from multiple sources.

    Metadata Priority (highest to lowest):
    1. Feed metadata - from RSS parsing, stored in Episode model
    2. MP3 ID3 tags - from downloaded audio file
    3. AI-generated - from transcript analysis via Gemini
    """

    def __init__(
        self,
        config: Config,
        repository: PodcastRepositoryInterface,
    ):
        """Initialize the metadata worker.

        Args:
            config: Application configuration.
            repository: Database repository for episode operations.
        """
        self.config = config
        self.repository = repository
        self._ai_client = None
        self._rate_limiter = None
        self._prompt_manager = None

    @property
    def name(self) -> str:
        """Human-readable name for this worker."""
        return "Metadata"

    def _get_ai_client(self):
        """Lazily initialize the AI client."""
        if self._ai_client is None:
            import google.genai as genai

            self._ai_client = genai.Client(api_key=self.config.GEMINI_API_KEY)
            self._rate_limiter = RateLimiter(max_requests=9, time_window=60)
            self._prompt_manager = PromptManager(
                config=self.config, print_results=False
            )
        return self._ai_client

    def _build_metadata_path(self, transcript_path: str) -> str:
        """Build metadata file path from transcript path."""
        base_path = os.path.splitext(transcript_path)[0]
        # Remove _transcription suffix if present
        if base_path.endswith("_transcription"):
            base_path = base_path[:-14]
        return base_path + "_metadata.json"

    def _read_mp3_tags(self, file_path: str) -> dict[str, Any]:
        """Read ID3 tags from MP3 file.

        Args:
            file_path: Path to MP3 file.

        Returns:
            Dict with MP3 tag values.
        """
        tags = {}
        try:
            from mutagen.easyid3 import EasyID3
            from mutagen.mp3 import MP3

            audio = MP3(file_path, ID3=EasyID3)
            tags["artist"] = audio.get("artist", [None])[0]
            tags["album"] = audio.get("album", [None])[0]
            tags["title"] = audio.get("title", [None])[0]
            tags["date"] = audio.get("date", [None])[0]
        except Exception as e:
            logger.debug(f"Could not read MP3 tags from {file_path}: {e}")

        return tags

    def _extract_ai_metadata(
        self, transcript: str, filename: str
    ) -> PodcastMetadata | None:
        """Extract metadata from transcript using AI.

        Args:
            transcript: Episode transcript text.
            filename: Original filename for context.

        Returns:
            PodcastMetadata if successful, None otherwise.
        """
        client = self._get_ai_client()
        prompt = self._prompt_manager.build_prompt(
            prompt_name="metadata_extraction",
            transcript=transcript,
            filename=filename,
        )

        try:
            self._rate_limiter.acquire()
            logger.debug("Making AI metadata extraction request")

            response = client.models.generate_content(
                model=self.config.GEMINI_MODEL_FLASH,
                contents=prompt,
                config={
                    "response_mime_type": "application/json",
                    "response_schema": PodcastMetadata,
                },
            )

            if response.text:
                data = json.loads(response.text)
                metadata = PodcastMetadata(**data)

                # Log email_content extraction status for debugging
                if metadata.email_content:
                    logger.info(
                        f"Extracted email_content for '{filename}': "
                        f"type={metadata.email_content.podcast_type}, "
                        f"teaser_len={len(metadata.email_content.teaser_summary)}, "
                        f"takeaways={len(metadata.email_content.key_takeaways)}"
                    )
                else:
                    logger.warning(f"No email_content returned by AI for '{filename}'")

                return metadata

        except Exception as e:
            logger.error(f"AI metadata extraction failed: {e}")

        return None

    def _merge_metadata(
        self,
        episode: Episode,
        mp3_tags: dict[str, Any],
        ai_metadata: PodcastMetadata | None,
    ) -> MergedMetadata:
        """Merge metadata from all sources.

        Priority: Feed > MP3 > AI

        Args:
            episode: Episode with feed metadata.
            mp3_tags: Tags from MP3 file.
            ai_metadata: AI-extracted metadata.

        Returns:
            MergedMetadata with combined data.
        """
        # Start with feed metadata (most trustworthy)
        merged = MergedMetadata(
            title=episode.title,
            description=episode.description,
            published_date=(
                episode.published_date.isoformat() if episode.published_date else None
            ),
            duration_seconds=episode.duration_seconds,
            episode_number=episode.episode_number,
            season_number=episode.season_number,
        )

        # Add MP3 tags
        merged.mp3_artist = mp3_tags.get("artist")
        merged.mp3_album = mp3_tags.get("album")

        # Add AI-generated metadata
        if ai_metadata:
            merged.summary = ai_metadata.summary
            merged.keywords = ai_metadata.keywords
            merged.hosts = ai_metadata.hosts
            merged.guests = ai_metadata.guests

            # Extract email content if available
            if ai_metadata.email_content:
                merged.email_content = ai_metadata.email_content.model_dump()

            # Use MP3 artist as host fallback if no hosts identified
            if not merged.hosts and merged.mp3_artist:
                merged.hosts = [merged.mp3_artist]

        return merged

    def get_pending_count(self) -> int:
        """Get the count of episodes pending metadata extraction.

        Returns:
            Number of episodes waiting for metadata.
        """
        episodes = self.repository.get_episodes_pending_metadata(limit=1000)
        return len(episodes)

    def _process_episode(self, episode: Episode) -> MergedMetadata:
        """Process a single episode for metadata extraction.

        Args:
            episode: Episode to process.

        Returns:
            MergedMetadata with combined data from all sources.

        Raises:
            Exception: If processing fails.
        """
        # Get transcript text from database or file
        transcript = self.repository.get_transcript_text(episode.id)
        if not transcript:
            raise ValueError(f"Episode {episode.id} has no transcript content")

        # Read MP3 tags if file exists
        mp3_tags = {}
        if episode.local_file_path and os.path.exists(episode.local_file_path):
            mp3_tags = self._read_mp3_tags(episode.local_file_path)

        # Extract AI metadata
        filename = episode.title or f"episode_{episode.id}"
        ai_metadata = self._extract_ai_metadata(transcript, filename)

        # Merge all sources
        merged = self._merge_metadata(episode, mp3_tags, ai_metadata)

        logger.info(f"Metadata extracted for episode {episode.id}")
        return merged

    def process_batch(self, limit: int) -> WorkerResult:
        """Process a batch of episodes for metadata extraction.

        Args:
            limit: Maximum number of episodes to process.

        Returns:
            WorkerResult with processing statistics.
        """
        result = WorkerResult()

        try:
            episodes = self.repository.get_episodes_pending_metadata(limit=limit)

            if not episodes:
                logger.info("No episodes pending metadata extraction")
                return result

            logger.info(f"Processing {len(episodes)} episodes for metadata")

            for episode in episodes:
                try:
                    # Mark as processing
                    self.repository.mark_metadata_started(episode.id)

                    # Process and get merged metadata
                    merged = self._process_episode(episode)

                    # Log email_content storage for debugging
                    if merged.email_content:
                        logger.info(
                            f"Storing email_content for episode {episode.id}: "
                            f"keys={list(merged.email_content.keys())}"
                        )
                    else:
                        logger.warning(
                            f"No email_content to store for episode {episode.id}"
                        )

                    # Mark as complete with all extracted data
                    self.repository.mark_metadata_complete(
                        episode_id=episode.id,
                        summary=merged.summary,
                        keywords=merged.keywords,
                        hosts=merged.hosts,
                        guests=merged.guests,
                        mp3_artist=merged.mp3_artist,
                        mp3_album=merged.mp3_album,
                        email_content=merged.email_content,
                    )
                    result.processed += 1

                except ValueError as e:
                    error_msg = f"Episode {episode.id}: {e}"
                    logger.error(error_msg)
                    self.repository.mark_metadata_failed(episode.id, str(e))
                    result.failed += 1
                    result.errors.append(error_msg)

                except Exception as e:
                    error_msg = f"Episode {episode.id}: {e}"
                    logger.exception(error_msg)
                    self.repository.mark_metadata_failed(episode.id, str(e))
                    result.failed += 1
                    result.errors.append(error_msg)

        except Exception as e:
            logger.exception(f"Metadata batch failed: {e}")
            result.failed += 1
            result.errors.append(str(e))

        return result
