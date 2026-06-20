"""Text-to-Speech rendering using Gemini TTS.

Converts a briefing script into MP3 bytes using
gemini-3.1-flash-tts-preview. Handles PCM decoding and ffmpeg transcoding.
"""

import base64
import logging
import subprocess

from google import genai
from google.genai import types

from src.config import Config

logger = logging.getLogger(__name__)

# MIME type for the output MP3
AUDIO_MIME_TYPE = "audio/mpeg"


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

        response = client.models.generate_content(
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
        )
        if result.returncode != 0:
            logger.error("ffmpeg PCM->MP3 failed: %s", result.stderr.decode(errors="replace"))
            return None
        return result.stdout
    except Exception:
        logger.exception("ffmpeg subprocess failed")
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
            capture_output=True, text=True,
        )
        return int(float(result.stdout.strip()))
    except Exception:
        logger.warning("Could not probe audio duration", exc_info=True)
        return None
