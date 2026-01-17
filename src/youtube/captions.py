"""YouTube caption download and audio extraction."""

import logging
import os
import re
import subprocess
from pathlib import Path

from youtube_transcript_api import (
    NoTranscriptFound,
    TranscriptsDisabled,
    YouTubeTranscriptApi,
)

from .models import YouTubeCaption

logger = logging.getLogger(__name__)


class CaptionDownloader:
    """Download YouTube captions and extract audio for Whisper fallback."""

    def __init__(
        self,
        prefer_manual_captions: bool = True,
        default_language: str = "en",
    ):
        """Initialize the caption downloader.

        Args:
            prefer_manual_captions: Prefer human-created captions over auto-generated.
            default_language: Default language code for captions.
        """
        self.prefer_manual_captions = prefer_manual_captions
        self.default_language = default_language

    def download_captions(
        self, video_id: str, language: str | None = None
    ) -> YouTubeCaption | None:
        """Download captions/transcript for a YouTube video.

        Uses youtube-transcript-api which doesn't require API key.

        Args:
            video_id: YouTube video ID.
            language: Preferred language code (defaults to self.default_language).

        Returns:
            YouTubeCaption if found, None otherwise.
        """
        language = language or self.default_language

        try:
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)

            transcript = None
            is_auto_generated = False

            if self.prefer_manual_captions:
                # Try to get manually created transcript first
                try:
                    transcript = transcript_list.find_manually_created_transcript(
                        [language]
                    )
                    is_auto_generated = False
                except NoTranscriptFound:
                    pass

            # Fall back to auto-generated if no manual transcript
            if transcript is None:
                try:
                    transcript = transcript_list.find_generated_transcript([language])
                    is_auto_generated = True
                except NoTranscriptFound:
                    pass

            # Try any available transcript as last resort
            if transcript is None:
                try:
                    # Get any manually created transcript
                    for t in transcript_list:
                        if not t.is_generated:
                            transcript = t
                            is_auto_generated = False
                            break
                except Exception:
                    pass

            if transcript is None:
                try:
                    # Get any auto-generated transcript
                    for t in transcript_list:
                        if t.is_generated:
                            transcript = t
                            is_auto_generated = True
                            break
                except Exception:
                    pass

            if transcript is None:
                logger.info(f"No transcript available for video {video_id}")
                return None

            # Fetch the transcript data
            transcript_data = transcript.fetch()

            # Convert to plain text
            text = self._format_transcript(transcript_data)

            return YouTubeCaption(
                video_id=video_id,
                language=transcript.language_code,
                text=text,
                is_auto_generated=is_auto_generated,
            )

        except TranscriptsDisabled:
            logger.info(f"Transcripts are disabled for video {video_id}")
            return None
        except NoTranscriptFound:
            logger.info(f"No transcript found for video {video_id}")
            return None
        except Exception as e:
            logger.error(f"Error downloading transcript for video {video_id}: {e}")
            return None

    def extract_audio(
        self,
        video_url: str,
        output_path: str | Path,
        audio_format: str = "mp3",
    ) -> bool:
        """Extract audio from a YouTube video using yt-dlp.

        Used as fallback when captions are not available.

        Args:
            video_url: YouTube video URL.
            output_path: Output file path (without extension).
            audio_format: Audio format (default: mp3).

        Returns:
            True if extraction succeeded, False otherwise.
        """
        output_path = Path(output_path)

        # Ensure parent directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Build output template (yt-dlp adds extension)
        output_template = str(output_path.with_suffix(""))

        cmd = [
            "yt-dlp",
            "--extract-audio",
            f"--audio-format={audio_format}",
            "--audio-quality=0",  # Best quality
            "-o",
            f"{output_template}.%(ext)s",
            "--no-playlist",
            "--quiet",
            "--no-warnings",
            video_url,
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600,  # 10 minute timeout
            )

            if result.returncode != 0:
                logger.error(f"yt-dlp failed: {result.stderr}")
                return False

            # Check if output file exists
            expected_output = output_path.with_suffix(f".{audio_format}")
            if expected_output.exists():
                # Rename to exact requested path if needed
                if expected_output != output_path:
                    os.rename(expected_output, output_path)
                return True

            logger.error(f"Expected output file not found: {expected_output}")
            return False

        except subprocess.TimeoutExpired:
            logger.error(f"yt-dlp timed out extracting audio from {video_url}")
            return False
        except FileNotFoundError:
            logger.error("yt-dlp not found. Please install: pip install yt-dlp")
            return False
        except Exception as e:
            logger.error(f"Error extracting audio from {video_url}: {e}")
            return False

    def _format_transcript(self, transcript_data: list[dict]) -> str:
        """Format transcript data into clean text.

        Args:
            transcript_data: List of transcript segments from youtube-transcript-api.

        Returns:
            Formatted transcript text.
        """
        lines = []

        for segment in transcript_data:
            text = segment.get("text", "")
            # Clean up the text
            text = self._clean_text(text)
            if text:
                lines.append(text)

        # Join with spaces and clean up multiple spaces
        text = " ".join(lines)
        text = re.sub(r"\s+", " ", text).strip()

        return text

    def _clean_text(self, text: str) -> str:
        """Clean transcript text.

        Args:
            text: Raw transcript text.

        Returns:
            Cleaned text.
        """
        # Remove HTML entities
        text = text.replace("&amp;", "&")
        text = text.replace("&lt;", "<")
        text = text.replace("&gt;", ">")
        text = text.replace("&quot;", '"')
        text = text.replace("&#39;", "'")

        # Remove [Music], [Applause], etc.
        text = re.sub(r"\[[\w\s]+\]", "", text)

        # Remove newlines (they'll be rejoined with spaces)
        text = text.replace("\n", " ")

        return text.strip()
