"""YouTube download worker for caption/audio extraction.

Downloads YouTube captions when available, or extracts audio for Whisper fallback.
"""

import logging
import os
from pathlib import Path

from src.config import Config
from src.db.repository import PodcastRepositoryInterface
from src.workflow.workers.base import WorkerInterface, WorkerResult
from src.youtube.captions import CaptionDownloader

logger = logging.getLogger(__name__)


class YouTubeDownloadWorker(WorkerInterface):
    """Worker that downloads YouTube captions or extracts audio.

    For each pending YouTube video:
    1. If captions are available: Download captions, mark transcript complete
    2. Else: Extract audio via yt-dlp, mark download complete (Whisper will transcribe)
    """

    def __init__(
        self,
        config: Config,
        repository: PodcastRepositoryInterface,
    ):
        """Initialize the YouTube download worker.

        Args:
            config: Application configuration.
            repository: Database repository for episode operations.
        """
        self.config = config
        self.repository = repository
        self._caption_downloader: CaptionDownloader | None = None

    @property
    def name(self) -> str:
        """Human-readable name for this worker."""
        return "YouTubeDownload"

    @property
    def caption_downloader(self) -> CaptionDownloader:
        """Lazily initialize the caption downloader."""
        if self._caption_downloader is None:
            self._caption_downloader = CaptionDownloader(
                prefer_manual_captions=self.config.YOUTUBE_PREFER_MANUAL_CAPTIONS,
                default_language=self.config.YOUTUBE_CAPTIONS_LANGUAGE,
            )
        return self._caption_downloader

    def get_pending_count(self) -> int:
        """Get the count of YouTube videos pending caption/audio download.

        Returns:
            Number of YouTube videos waiting to be processed.
        """
        episodes = self.repository.get_youtube_videos_pending_caption_download(
            limit=1000
        )
        return len(episodes)

    def process_batch(self, limit: int) -> WorkerResult:
        """Process a batch of YouTube videos.

        For each video:
        - If captions available: download and mark transcript complete
        - Else: extract audio and mark download complete

        Args:
            limit: Maximum number of videos to process.

        Returns:
            WorkerResult with processing statistics.
        """
        result = WorkerResult()

        episodes = self.repository.get_youtube_videos_pending_caption_download(
            limit=limit
        )

        for episode in episodes:
            try:
                processed = self._process_episode(episode)
                if processed:
                    result.processed += 1
                else:
                    result.failed += 1
            except Exception as e:
                logger.exception(f"Error processing YouTube video {episode.id}: {e}")
                result.failed += 1
                result.errors.append(f"Episode {episode.id}: {str(e)}")

        return result

    def _process_episode(self, episode) -> bool:
        """Process a single YouTube video episode.

        Args:
            episode: Episode to process.

        Returns:
            True if successful, False otherwise.
        """
        video_id = episode.youtube_video_id
        if not video_id:
            logger.error(f"Episode {episode.id} missing youtube_video_id")
            self.repository.mark_download_failed(
                episode.id, "Missing YouTube video ID"
            )
            return False

        logger.info(f"Processing YouTube video: {episode.title} ({video_id})")

        # Try to download captions first
        if episode.youtube_captions_available:
            caption = self.caption_downloader.download_captions(
                video_id,
                language=episode.youtube_captions_language
                or self.config.YOUTUBE_CAPTIONS_LANGUAGE,
            )

            if caption:
                # Captions downloaded successfully - mark transcript complete
                logger.info(
                    f"Downloaded captions for {video_id} "
                    f"(auto={caption.is_auto_generated})"
                )
                self.repository.mark_transcript_complete(
                    episode.id,
                    transcript_text=caption.text,
                    transcript_source="youtube_captions",
                )
                # Also mark download as complete since we don't need audio
                self.repository.mark_download_complete(
                    episode.id,
                    local_path="",  # No local file
                    file_size=0,
                    file_hash="",
                )
                return True

            logger.info(
                f"Captions marked available but download failed for {video_id}, "
                f"falling back to audio extraction"
            )

        # No captions available or download failed - extract audio for Whisper
        return self._extract_audio(episode)

    def _extract_audio(self, episode) -> bool:
        """Extract audio from YouTube video for Whisper transcription.

        Args:
            episode: Episode to extract audio from.

        Returns:
            True if successful, False otherwise.
        """
        video_id = episode.youtube_video_id
        video_url = f"https://www.youtube.com/watch?v={video_id}"

        # Get podcast local directory
        podcast = self.repository.get_podcast(episode.podcast_id)
        if not podcast or not podcast.local_directory:
            # Create a default directory
            output_dir = os.path.join(
                self.config.PODCAST_DOWNLOAD_DIRECTORY, f"youtube_{video_id}"
            )
        else:
            output_dir = podcast.local_directory

        os.makedirs(output_dir, exist_ok=True)

        # Build output path
        safe_title = self._sanitize_filename(episode.title)
        output_path = Path(output_dir) / f"{safe_title}.mp3"

        logger.info(f"Extracting audio for {video_id} to {output_path}")

        success = self.caption_downloader.extract_audio(video_url, output_path)

        if success and output_path.exists():
            file_size = output_path.stat().st_size
            # Calculate simple hash (could use SHA256 for full integrity)
            file_hash = f"yt-{video_id}"

            self.repository.mark_download_complete(
                episode.id,
                local_path=str(output_path),
                file_size=file_size,
                file_hash=file_hash,
            )
            logger.info(f"Audio extracted for {video_id}: {output_path}")
            return True
        else:
            self.repository.mark_download_failed(
                episode.id, "Failed to extract audio from YouTube video"
            )
            return False

    def _sanitize_filename(self, name: str) -> str:
        """Sanitize a string for use as a filename.

        Args:
            name: Original name.

        Returns:
            Sanitized name safe for filesystem use.
        """
        # Replace problematic characters
        for char in ['/', '\\', ':', '*', '?', '"', '<', '>', '|']:
            name = name.replace(char, '_')
        # Limit length
        return name[:100].strip()
