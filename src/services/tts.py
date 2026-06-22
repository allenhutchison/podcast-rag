"""Text-to-Speech rendering using Gemini TTS.

Converts a briefing script into MP3 bytes using
gemini-3.1-flash-tts-preview. Handles PCM decoding and ffmpeg transcoding.
"""

import base64
import logging
import random
import subprocess
import time

from google import genai
from google.genai import types

from src.config import Config

logger = logging.getLogger(__name__)

# MIME type for the output MP3
AUDIO_MIME_TYPE = "audio/mpeg"

# Retry config for transient Gemini API errors
_MAX_RETRIES = 3
_BASE_DELAY = 1.0
_MAX_DELAY = 10.0

# Subprocess timeout (seconds) for ffmpeg/ffprobe
_SUBPROCESS_TIMEOUT = 120


def _is_retryable(exc: Exception) -> bool:
    """Check if an exception is a transient API error worth retrying."""
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    if status in (429, 500, 502, 503, 504):
        return True
    msg = str(exc)
    return "429" in msg or "500" in msg or "503" in msg


def _retry_tts_call(client, *, model, contents, config):
    """Call generate_content with exponential backoff on transient errors."""
    last_exc = None
    for attempt in range(_MAX_RETRIES):
        try:
            return client.models.generate_content(
                model=model, contents=contents, config=config
            )
        except Exception as exc:
            last_exc = exc
            if not _is_retryable(exc) or attempt == _MAX_RETRIES - 1:
                raise
            delay = min(_BASE_DELAY * (2 ** attempt) + random.uniform(0, 0.5), _MAX_DELAY)
            logger.warning(
                "Gemini TTS call failed (attempt %d/%d), retrying in %.1fs: %s",
                attempt + 1, _MAX_RETRIES, delay, exc,
            )
            time.sleep(delay)
    raise last_exc  # type: ignore[misc]


def render_tts_to_mp3(
    script: str, config: Config
) -> tuple[bytes | None, int | None]:
    """Render a script to MP3 bytes via Gemini TTS.

    Args:
        script: Spoken-prose script text.
        config: Application configuration.

    Returns:
        (mp3_bytes, duration_seconds). Both None on failure.
    """
    try:
        client = genai.Client(api_key=config.GEMINI_API_KEY)

        response = _retry_tts_call(
            client,
            model=config.GEMINI_TTS_MODEL,
            contents=script,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name=config.GEMINI_TTS_VOICE,
                        )
                    )
                ),
            ),
        )
    except Exception:
        logger.exception("Gemini TTS API call failed")
        return None, None

    # Extract PCM audio from response
    pcm_bytes = b""
    try:
        for candidate in response.candidates:
            for part in candidate.content.parts:
                if part.inline_data and part.inline_data.data:
                    pcm_bytes += base64.b64decode(part.inline_data.data)
    except Exception:
        logger.exception("Failed to extract audio data from TTS response")
        return None, None

    if not pcm_bytes:
        logger.error("TTS returned no audio data")
        return None, None

    # Transcode PCM -> MP3 via ffmpeg
    sample_rate = config.BRIEFING_AUDIO_SAMPLE_RATE
    mp3_bytes = _pcm_to_mp3(pcm_bytes, sample_rate)
    if mp3_bytes is None:
        return None, None

    duration = _probe_duration(mp3_bytes)
    return mp3_bytes, duration


def _pcm_to_mp3(pcm_bytes: bytes, sample_rate: int) -> bytes | None:
    """Transcode raw PCM s16le to MP3 via ffmpeg."""
    try:
        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "s16le",
                "-ar", str(sample_rate),
                "-ac", "1",
                "-i", "pipe:0",
                "-codec:a", "libmp3lame",
                "-b:a", "64k",
                "-f", "mp3",
                "pipe:1",
            ],
            input=pcm_bytes,
            capture_output=True,
            timeout=_SUBPROCESS_TIMEOUT,
        )
        if result.returncode != 0:
            logger.error("ffmpeg PCM->MP3 failed: %s", result.stderr.decode(errors="replace"))
            return None
        return result.stdout
    except subprocess.TimeoutExpired:
        logger.error("ffmpeg PCM->MP3 timed out after %ds", _SUBPROCESS_TIMEOUT)
        return None
    except OSError:
        logger.exception("ffmpeg subprocess failed to start")
        return None


def _probe_duration(mp3_bytes: bytes) -> int | None:
    """Get audio duration in seconds using ffprobe via stdin."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                "-f", "mp3",
                "pipe:0",
            ],
            input=mp3_bytes,
            # No text=True: input is bytes, and text mode would try to
            # .encode() the bytes (AttributeError). Decode stdout manually.
            capture_output=True,
            timeout=_SUBPROCESS_TIMEOUT,
        )
        return int(float(result.stdout.decode(errors="replace").strip()))
    except subprocess.TimeoutExpired:
        logger.warning("ffprobe timed out after %ds", _SUBPROCESS_TIMEOUT)
        return None
    except (OSError, ValueError):
        logger.warning("Could not probe audio duration", exc_info=True)
        return None
