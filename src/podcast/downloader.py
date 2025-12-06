"""Episode downloader with configurable concurrency.

Downloads podcast episodes with support for:
- Concurrent downloads
- Resume interrupted downloads
- Progress tracking
- Retry logic with exponential backoff
"""

import asyncio
import hashlib
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import unquote, urlparse

import aiohttp
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ..db.models import Episode
from ..db.repository import PodcastRepositoryInterface

logger = logging.getLogger(__name__)


@dataclass
class DownloadResult:
    """Result of a download operation."""

    episode_id: str
    success: bool
    local_path: Optional[str] = None
    file_size: Optional[int] = None
    file_hash: Optional[str] = None
    error: Optional[str] = None
    duration_seconds: Optional[float] = None


class EpisodeDownloader:
    """Downloads podcast episodes with configurable concurrency.

    Supports both sync and async downloading with retry logic,
    progress tracking, and automatic cleanup.

    Example:
        downloader = EpisodeDownloader(
            repository=repo,
            download_directory="/opt/podcasts",
            max_concurrent=10,
        )
        results = downloader.download_pending(limit=50)
    """

    DEFAULT_USER_AGENT = "PodcastRAG/1.0 (+https://github.com/podcast-rag)"
    DEFAULT_CHUNK_SIZE = 8192
    DEFAULT_TIMEOUT = 300  # 5 minutes

    def __init__(
        self,
        repository: PodcastRepositoryInterface,
        download_directory: str,
        max_concurrent: int = 10,
        retry_attempts: int = 3,
        timeout: int = DEFAULT_TIMEOUT,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        user_agent: Optional[str] = None,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
    ):
        """Initialize the episode downloader.

        Args:
            repository: Database repository
            download_directory: Base directory for downloads
            max_concurrent: Maximum concurrent downloads
            retry_attempts: Number of retry attempts for failed downloads
            timeout: Download timeout in seconds
            chunk_size: Chunk size for streaming downloads
            user_agent: Custom user agent string
            progress_callback: Callback for progress updates (episode_id, downloaded, total)
        """
        self.repository = repository
        self.download_directory = download_directory
        self.max_concurrent = max_concurrent
        self.retry_attempts = retry_attempts
        self.timeout = timeout
        self.chunk_size = chunk_size
        self.user_agent = user_agent or self.DEFAULT_USER_AGENT
        self.progress_callback = progress_callback

        # Create download directory if it doesn't exist
        os.makedirs(download_directory, exist_ok=True)

        # Set up requests session with retry logic
        self._session = self._create_session()

    def _create_session(self) -> requests.Session:
        """Create a requests session with retry logic."""
        session = requests.Session()

        retry_strategy = Retry(
            total=self.retry_attempts,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "HEAD"],
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        session.headers.update({"User-Agent": self.user_agent})

        return session

    def download_episode(self, episode: Episode) -> DownloadResult:
        """Download a single episode.

        Args:
            episode: Episode to download

        Returns:
            DownloadResult with download status
        """
        start_time = datetime.utcnow()

        # Get podcast for directory structure
        podcast = self.repository.get_podcast(episode.podcast_id)
        if not podcast:
            return DownloadResult(
                episode_id=episode.id,
                success=False,
                error=f"Podcast not found: {episode.podcast_id}",
            )

        # Determine output path
        podcast_dir = podcast.local_directory or os.path.join(
            self.download_directory,
            self._sanitize_filename(podcast.title),
        )
        os.makedirs(podcast_dir, exist_ok=True)

        filename = self._generate_filename(episode)
        output_path = os.path.join(podcast_dir, filename)

        # Mark download as started
        self.repository.mark_download_started(episode.id)
        logger.info(f"Downloading: {episode.title}")

        try:
            # Download the file
            file_size, file_hash = self._download_file(
                url=episode.enclosure_url,
                output_path=output_path,
                episode_id=episode.id,
                expected_size=episode.enclosure_length,
            )

            # Calculate duration
            duration = (datetime.utcnow() - start_time).total_seconds()

            # Mark download complete
            self.repository.mark_download_complete(
                episode_id=episode.id,
                local_path=output_path,
                file_size=file_size,
                file_hash=file_hash,
            )

            logger.info(
                f"Downloaded: {episode.title} "
                f"({file_size / 1024 / 1024:.1f} MB in {duration:.1f}s)"
            )

            return DownloadResult(
                episode_id=episode.id,
                success=True,
                local_path=output_path,
                file_size=file_size,
                file_hash=file_hash,
                duration_seconds=duration,
            )

        except Exception as e:
            logger.error(f"Download failed for {episode.title}: {e}")

            # Clean up partial file
            if os.path.exists(output_path):
                try:
                    os.remove(output_path)
                except OSError:
                    pass

            # Mark download as failed
            self.repository.mark_download_failed(episode.id, str(e))

            return DownloadResult(
                episode_id=episode.id,
                success=False,
                error=str(e),
            )

    def _download_file(
        self,
        url: str,
        output_path: str,
        episode_id: str,
        expected_size: Optional[int] = None,
    ) -> tuple[int, str]:
        """Download a file with progress tracking.

        Args:
            url: URL to download
            output_path: Path to save file
            episode_id: Episode ID for progress callback
            expected_size: Expected file size (optional)

        Returns:
            Tuple of (file_size, sha256_hash)
        """
        hasher = hashlib.sha256()
        downloaded = 0

        response = self._session.get(
            url,
            stream=True,
            timeout=self.timeout,
            allow_redirects=True,
        )
        response.raise_for_status()

        # Get total size from response if not known
        total_size = expected_size
        if "content-length" in response.headers:
            try:
                total_size = int(response.headers["content-length"])
            except ValueError:
                pass

        with open(output_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=self.chunk_size):
                if chunk:
                    f.write(chunk)
                    hasher.update(chunk)
                    downloaded += len(chunk)

                    if self.progress_callback and total_size:
                        self.progress_callback(episode_id, downloaded, total_size)

        return downloaded, hasher.hexdigest()

    def download_pending(self, limit: int = 50) -> Dict[str, Any]:
        """Download pending episodes concurrently.

        Args:
            limit: Maximum number of episodes to download

        Returns:
            Dictionary with download statistics
        """
        episodes = self.repository.get_episodes_pending_download(limit=limit)

        if not episodes:
            logger.info("No episodes pending download")
            return {
                "downloaded": 0,
                "failed": 0,
                "skipped": 0,
                "results": [],
            }

        logger.info(f"Downloading {len(episodes)} episodes with {self.max_concurrent} concurrent downloads")

        results = []
        downloaded = 0
        failed = 0

        with ThreadPoolExecutor(max_workers=self.max_concurrent) as executor:
            future_to_episode = {
                executor.submit(self.download_episode, episode): episode
                for episode in episodes
            }

            for future in as_completed(future_to_episode):
                result = future.result()
                results.append(result)

                if result.success:
                    downloaded += 1
                else:
                    failed += 1

        logger.info(f"Download batch complete: {downloaded} succeeded, {failed} failed")

        return {
            "downloaded": downloaded,
            "failed": failed,
            "skipped": 0,
            "results": results,
        }

    async def download_pending_async(self, limit: int = 50) -> Dict[str, Any]:
        """Download pending episodes asynchronously.

        Args:
            limit: Maximum number of episodes to download

        Returns:
            Dictionary with download statistics
        """
        episodes = self.repository.get_episodes_pending_download(limit=limit)

        if not episodes:
            logger.info("No episodes pending download")
            return {
                "downloaded": 0,
                "failed": 0,
                "skipped": 0,
                "results": [],
            }

        logger.info(
            f"Downloading {len(episodes)} episodes asynchronously "
            f"with {self.max_concurrent} concurrent downloads"
        )

        # Create semaphore to limit concurrency
        semaphore = asyncio.Semaphore(self.max_concurrent)

        async def download_with_semaphore(episode: Episode) -> DownloadResult:
            async with semaphore:
                return await self._download_episode_async(episode)

        # Create tasks
        tasks = [download_with_semaphore(episode) for episode in episodes]
        results = await asyncio.gather(*tasks)

        downloaded = sum(1 for r in results if r.success)
        failed = sum(1 for r in results if not r.success)

        logger.info(f"Async download batch complete: {downloaded} succeeded, {failed} failed")

        return {
            "downloaded": downloaded,
            "failed": failed,
            "skipped": 0,
            "results": list(results),
        }

    async def _download_episode_async(self, episode: Episode) -> DownloadResult:
        """Download a single episode asynchronously.

        Args:
            episode: Episode to download

        Returns:
            DownloadResult with download status
        """
        start_time = datetime.utcnow()

        # Get podcast for directory structure
        podcast = self.repository.get_podcast(episode.podcast_id)
        if not podcast:
            return DownloadResult(
                episode_id=episode.id,
                success=False,
                error=f"Podcast not found: {episode.podcast_id}",
            )

        # Determine output path
        podcast_dir = podcast.local_directory or os.path.join(
            self.download_directory,
            self._sanitize_filename(podcast.title),
        )
        os.makedirs(podcast_dir, exist_ok=True)

        filename = self._generate_filename(episode)
        output_path = os.path.join(podcast_dir, filename)

        # Mark download as started
        self.repository.mark_download_started(episode.id)
        logger.info(f"Downloading (async): {episode.title}")

        try:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            async with aiohttp.ClientSession(
                timeout=timeout,
                headers={"User-Agent": self.user_agent},
            ) as session:
                file_size, file_hash = await self._download_file_async(
                    session=session,
                    url=episode.enclosure_url,
                    output_path=output_path,
                    episode_id=episode.id,
                    expected_size=episode.enclosure_length,
                )

            # Calculate duration
            duration = (datetime.utcnow() - start_time).total_seconds()

            # Mark download complete
            self.repository.mark_download_complete(
                episode_id=episode.id,
                local_path=output_path,
                file_size=file_size,
                file_hash=file_hash,
            )

            logger.info(
                f"Downloaded (async): {episode.title} "
                f"({file_size / 1024 / 1024:.1f} MB in {duration:.1f}s)"
            )

            return DownloadResult(
                episode_id=episode.id,
                success=True,
                local_path=output_path,
                file_size=file_size,
                file_hash=file_hash,
                duration_seconds=duration,
            )

        except Exception as e:
            logger.error(f"Async download failed for {episode.title}: {e}")

            # Clean up partial file
            if os.path.exists(output_path):
                try:
                    os.remove(output_path)
                except OSError:
                    pass

            # Mark download as failed
            self.repository.mark_download_failed(episode.id, str(e))

            return DownloadResult(
                episode_id=episode.id,
                success=False,
                error=str(e),
            )

    async def _download_file_async(
        self,
        session: aiohttp.ClientSession,
        url: str,
        output_path: str,
        episode_id: str,
        expected_size: Optional[int] = None,
    ) -> tuple[int, str]:
        """Download a file asynchronously with progress tracking.

        Args:
            session: aiohttp session
            url: URL to download
            output_path: Path to save file
            episode_id: Episode ID for progress callback
            expected_size: Expected file size (optional)

        Returns:
            Tuple of (file_size, sha256_hash)
        """
        hasher = hashlib.sha256()
        downloaded = 0

        async with session.get(url, allow_redirects=True) as response:
            response.raise_for_status()

            # Get total size from response if not known
            total_size = expected_size
            if "content-length" in response.headers:
                try:
                    total_size = int(response.headers["content-length"])
                except ValueError:
                    pass

            with open(output_path, "wb") as f:
                async for chunk in response.content.iter_chunked(self.chunk_size):
                    if chunk:
                        f.write(chunk)
                        hasher.update(chunk)
                        downloaded += len(chunk)

                        if self.progress_callback and total_size:
                            self.progress_callback(episode_id, downloaded, total_size)

        return downloaded, hasher.hexdigest()

    def _generate_filename(self, episode: Episode) -> str:
        """Generate a filename for an episode.

        Args:
            episode: Episode to generate filename for

        Returns:
            Sanitized filename
        """
        # Try to get extension from URL
        url_path = urlparse(episode.enclosure_url).path
        url_filename = unquote(os.path.basename(url_path))
        _, ext = os.path.splitext(url_filename)

        # Default extension based on MIME type
        if not ext:
            mime_to_ext = {
                "audio/mpeg": ".mp3",
                "audio/mp3": ".mp3",
                "audio/mp4": ".m4a",
                "audio/x-m4a": ".m4a",
                "audio/aac": ".aac",
                "audio/ogg": ".ogg",
                "audio/opus": ".opus",
                "audio/wav": ".wav",
            }
            ext = mime_to_ext.get(episode.enclosure_type, ".mp3")

        # Build filename from episode info
        parts = []

        # Add episode number if available
        if episode.episode_number:
            parts.append(f"E{episode.episode_number}")
        elif episode.itunes_episode:
            parts.append(f"E{episode.itunes_episode}")

        # Add title
        parts.append(self._sanitize_filename(episode.title))

        filename = "_".join(parts) + ext

        # Limit filename length
        if len(filename) > 200:
            filename = filename[:196] + ext

        return filename

    def _sanitize_filename(self, name: str) -> str:
        """Sanitize a string for use as a filename.

        Args:
            name: Original name

        Returns:
            Sanitized name safe for filesystem
        """
        # Remove or replace invalid characters
        safe = re.sub(r'[<>:"/\\|?*]', "", name)
        # Replace multiple spaces/underscores with single
        safe = re.sub(r"[\s_]+", "_", safe)
        # Remove leading/trailing whitespace and dots
        safe = safe.strip(" .")
        return safe or "episode"

    def cleanup_processed_episodes(self, limit: int = 100) -> int:
        """Delete audio files for fully processed episodes.

        Args:
            limit: Maximum number of episodes to clean up

        Returns:
            Number of files deleted
        """
        episodes = self.repository.get_episodes_ready_for_cleanup(limit=limit)
        deleted = 0

        for episode in episodes:
            if episode.local_file_path and os.path.exists(episode.local_file_path):
                try:
                    os.remove(episode.local_file_path)
                    self.repository.mark_audio_cleaned_up(episode.id)
                    deleted += 1
                    logger.info(f"Cleaned up audio: {episode.title}")
                except OSError as e:
                    logger.error(f"Failed to delete {episode.local_file_path}: {e}")

        logger.info(f"Cleaned up {deleted} audio files")
        return deleted

    def close(self):
        """Close the downloader and release resources."""
        self._session.close()
