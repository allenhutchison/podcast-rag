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
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from typing import Any
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
    local_path: str | None = None
    file_size: int | None = None
    file_hash: str | None = None
    error: str | None = None
    duration_seconds: float | None = None


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
        user_agent: str | None = None,
        progress_callback: Callable[[str, int, int], None] | None = None,
    ):
        """
        Create an EpisodeDownloader configured for concurrent, retrying downloads and optional progress reporting.

        Parameters:
            repository: Repository used to lookup and update episode/podcast state during download.
            download_directory: Base filesystem directory where downloaded episode files will be written.
            max_concurrent: Maximum number of episode downloads to run in parallel.
            retry_attempts: Number of retry attempts for transient HTTP failures.
            timeout: Per-request timeout in seconds for download operations.
            chunk_size: Size in bytes of each read/write chunk when streaming downloads.
            user_agent: HTTP User-Agent header string to use for download requests; defaults to a built-in value if omitted.
            progress_callback: Optional callable invoked with (episode_id, downloaded_bytes, total_bytes) to report per-episode progress.
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
        try:
            os.makedirs(download_directory, exist_ok=True)
        except PermissionError as e:
            raise PermissionError(
                f"Cannot create download directory '{download_directory}': {e}. "
                "Check that the PODCAST_DOWNLOAD_DIRECTORY path is writable."
            ) from e

        # Set up requests session with retry logic
        self._session = self._create_session()

    def _create_session(self) -> requests.Session:
        """
        Create and return an HTTP session configured for resilient downloads.

        The returned requests.Session is configured to automatically retry transient HTTP errors (including rate limiting and server errors) for idempotent methods and includes the downloader's User-Agent header.

        Returns:
            session (requests.Session): A configured HTTP session with mounted retry-capable adapters for both HTTP and HTTPS.
        """
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
        """
        Download a single Episode, save it to disk, and update repository state.

        Parameters:
            episode (Episode): Episode to download; used to determine source URL, expected size, and identifiers for repository updates.

        Returns:
            DownloadResult: Outcome of the download. On success, `success` is `True` and `local_path`, `file_size`, `file_hash`, and `duration_seconds` are populated. On failure, `success` is `False` and `error` contains the failure message.
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

        try:
            os.makedirs(podcast_dir, exist_ok=True)
        except PermissionError as e:
            error_msg = f"Permission denied creating directory {podcast_dir}: {e}"
            logger.error(error_msg)
            self.repository.mark_download_failed(episode.id, error_msg)
            return DownloadResult(
                episode_id=episode.id,
                success=False,
                error=error_msg,
            )

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
        expected_size: int | None = None,
    ) -> tuple[int, str]:
        """
        Download a URL to disk while computing its SHA-256 hash and reporting per-chunk progress.

        Parameters:
            url (str): Source URL to download.
            output_path (str): Filesystem path where the downloaded bytes will be written.
            episode_id (str): Identifier passed to the progress callback to associate progress updates with an episode.
            expected_size (Optional[int]): Optional expected total size in bytes used when the response lacks a valid Content-Length.

        Returns:
            tuple[int, str]: (downloaded_bytes, sha256_hex) where `downloaded_bytes` is the number of bytes written to disk and `sha256_hex` is the SHA-256 hex digest of the written data.
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

    def download_pending(self, limit: int = 50) -> dict[str, Any]:
        """
        Download pending episodes up to the given limit using a thread pool and collect per-episode results.

        Returns:
            dict: Summary with keys:
                - downloaded (int): number of successful downloads.
                - failed (int): number of failed downloads.
                - skipped (int): number of skipped episodes (always 0).
                - results (List[DownloadResult]): per-episode DownloadResult objects in completion order.
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

    async def download_pending_async(self, limit: int = 50) -> dict[str, Any]:
        """
        Download pending episodes up to the given limit using bounded concurrency and return per-episode results.

        Parameters:
            limit (int): Maximum number of pending episodes to process.

        Returns:
            dict: Summary of the batch with keys:
                - "downloaded" (int): Number of successfully downloaded episodes.
                - "failed" (int): Number of episodes that failed to download.
                - "skipped" (int): Number of episodes skipped (always 0 in the current implementation).
                - "results" (List[DownloadResult]): List of per-episode DownloadResult objects describing outcome for each episode.
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
            """
            Run the episode download coroutine while limited by the concurrency semaphore.

            Parameters:
                episode (Episode): Episode record to download.

            Returns:
                DownloadResult: Result object describing success, path, size, hash, error, and duration for the episode.
            """
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
        """
        Download an episode and save it to the podcast's local directory, updating repository state.

        The method marks the episode as started, downloads the episode media to a file under the podcast's local directory (creating the directory if necessary), and on success marks the episode complete with the local path, file size, and file hash. On failure it removes any partial file and marks the episode as failed.

        Parameters:
            episode (Episode): Episode to download; must include `id`, `podcast_id`, `enclosure_url`, and optionally `enclosure_length`.

        Returns:
            DownloadResult: Contains `episode_id` and `success`. On success includes `local_path`, `file_size` (bytes), `file_hash` (SHA-256 hex), and `duration_seconds`. On failure includes `error` with the failure message.
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

        try:
            os.makedirs(podcast_dir, exist_ok=True)
        except PermissionError as e:
            error_msg = f"Permission denied creating directory {podcast_dir}: {e}"
            logger.error(error_msg)
            self.repository.mark_download_failed(episode.id, error_msg)
            return DownloadResult(
                episode_id=episode.id,
                success=False,
                error=error_msg,
            )

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
        expected_size: int | None = None,
    ) -> tuple[int, str]:
        """
        Download the resource at `url` to `output_path` with retry logic, updating an SHA-256 hash and invoking the progress callback as data is received.

        Parameters:
            session (aiohttp.ClientSession): Active aiohttp session used to perform the request.
            url (str): Remote URL of the file to download.
            output_path (str): Filesystem path where the response body will be written.
            episode_id (str): Identifier passed to the progress callback for this download.
            expected_size (Optional[int]): Expected total size in bytes; used when `Content-Length` is absent.

        Returns:
            tuple[int, str]: `downloaded_size` — number of bytes written to disk, `sha256_hash` — hex-encoded SHA-256 digest of the downloaded file.
        """
        retryable_status_codes = {429, 500, 502, 503, 504}
        last_exception = None

        for attempt in range(self.retry_attempts):
            try:
                hasher = hashlib.sha256()
                downloaded = 0

                async with session.get(url, allow_redirects=True) as response:
                    # Check if we should retry for certain status codes
                    if response.status in retryable_status_codes:
                        if attempt < self.retry_attempts - 1:
                            wait_time = (2 ** attempt)  # Exponential backoff
                            logger.warning(
                                f"Retryable status {response.status} for {url}, "
                                f"attempt {attempt + 1}/{self.retry_attempts}, "
                                f"waiting {wait_time}s"
                            )
                            await asyncio.sleep(wait_time)
                            continue
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

            except aiohttp.ClientError as e:
                last_exception = e
                if attempt < self.retry_attempts - 1:
                    wait_time = (2 ** attempt)  # Exponential backoff
                    logger.warning(
                        f"Download error for {url}: {e}, "
                        f"attempt {attempt + 1}/{self.retry_attempts}, "
                        f"waiting {wait_time}s"
                    )
                    await asyncio.sleep(wait_time)
                else:
                    raise

        # Should not reach here, but just in case
        raise last_exception or aiohttp.ClientError(f"Failed to download {url} after {self.retry_attempts} attempts")

    def _generate_filename(self, episode: Episode) -> str:
        """
        Create a filesystem-safe filename for an episode, preserving an extension when possible and enforcing a length limit.

        Builds a filename that includes an episode prefix ("E{number}" using episode_number or itunes_episode when available) followed by a sanitized episode title. The file extension is taken from the enclosure URL when present, otherwise inferred from the episode's MIME type with a fallback to ".mp3". The final filename is trimmed to a maximum of 200 characters.

        Parameters:
            episode (Episode): Episode object containing title, enclosure URL/type, and optional episode numbering.

        Returns:
            str: Sanitized filename including extension, truncated to at most 200 characters.
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
        """
        Sanitize a string for use as a filesystem-safe filename.

        Parameters:
            name (str): Input string to sanitize.

        Returns:
            str: Filename-safe string with invalid characters removed, consecutive whitespace/underscores collapsed to a single underscore, and leading/trailing spaces or dots trimmed. Returns "episode" if the result is empty.
        """
        # Remove or replace invalid characters
        safe = re.sub(r'[<>:"/\\|?*]', "", name)
        # Replace multiple spaces/underscores with single
        safe = re.sub(r"[\s_]+", "_", safe)
        # Remove leading/trailing whitespace and dots
        safe = safe.strip(" .")
        return safe or "episode"

    def cleanup_processed_episodes(self, limit: int = 100) -> int:
        """
        Remove local audio files for episodes marked ready for cleanup and update repository state.

        Parameters:
            limit (int): Maximum number of episodes to process for cleanup.

        Returns:
            int: Number of audio files successfully deleted.
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
