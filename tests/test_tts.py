"""Tests for TTS rendering service."""

from unittest.mock import MagicMock, patch

import pytest

from src.config import Config
from src.services.tts import AUDIO_MIME_TYPE, render_tts_to_mp3


@pytest.fixture
def mock_config():
    config = MagicMock(spec=Config)
    config.GEMINI_API_KEY = "test_key"
    config.GEMINI_TTS_MODEL = "gemini-3.1-flash-tts-preview"
    config.GEMINI_TTS_VOICE = "Puck"
    config.BRIEFING_AUDIO_SAMPLE_RATE = 24000
    return config


class TestRenderTtsToMp3:
    @patch("src.services.tts.genai.Client")
    @patch("src.services.tts.subprocess.run")
    def test_successful_render(self, mock_subprocess, mock_client_cls, mock_config):
        # google-genai returns inline_data.data as raw PCM bytes
        pcm_data = b"\x00\x01" * 100

        mock_part = MagicMock()
        mock_part.inline_data.data = pcm_data
        mock_candidate = MagicMock()
        mock_candidate.content.parts = [mock_part]
        mock_response = MagicMock()
        mock_response.candidates = [mock_candidate]
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response
        mock_client_cls.return_value = mock_client

        # Mock ffmpeg (PCM -> MP3)
        ffmpeg_result = MagicMock()
        ffmpeg_result.returncode = 0
        ffmpeg_result.stdout = b"fake mp3"
        ffmpeg_result.stderr = b""
        # First call: ffmpeg, second: ffprobe. Both run without text mode,
        # so stdout is bytes (ffprobe duration is decoded in _probe_duration).
        mock_subprocess.side_effect = [ffmpeg_result, MagicMock(stdout=b"180.5\n")]

        mp3, duration = render_tts_to_mp3("test script", mock_config)
        assert mp3 == b"fake mp3"
        assert duration == 180
        # ffmpeg must receive the raw PCM unchanged (not re-decoded as base64)
        assert mock_subprocess.call_args_list[0].kwargs["input"] == pcm_data

    @patch("src.services.tts.genai.Client")
    @patch("src.services.tts.subprocess.run")
    def test_prepends_style_prefix(self, mock_subprocess, mock_client_cls, mock_config):
        mock_part = MagicMock()
        mock_part.inline_data.data = b"\x00\x01" * 100
        mock_candidate = MagicMock()
        mock_candidate.content.parts = [mock_part]
        mock_response = MagicMock()
        mock_response.candidates = [mock_candidate]
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response
        mock_client_cls.return_value = mock_client

        ffmpeg_result = MagicMock(returncode=0, stdout=b"fake mp3", stderr=b"")
        mock_subprocess.side_effect = [ffmpeg_result, MagicMock(stdout=b"180.5\n")]

        render_tts_to_mp3("Here is the briefing.", mock_config)

        contents = mock_client.models.generate_content.call_args.kwargs["contents"]
        # A single up-front delivery instruction keeps pace/volume uniform and
        # the original script still follows it verbatim.
        assert contents.startswith("Read the following")
        assert "consistent pace and volume" in contents
        assert contents.endswith("Here is the briefing.")

    @patch("src.services.tts.genai.Client")
    def test_api_failure_returns_none(self, mock_client_cls, mock_config):
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = RuntimeError("API error")
        mock_client_cls.return_value = mock_client

        mp3, duration = render_tts_to_mp3("test script", mock_config)
        assert mp3 is None
        assert duration is None

    @patch("src.services.tts.genai.Client")
    def test_empty_pcm_returns_none(self, mock_client_cls, mock_config):
        mock_part = MagicMock()
        mock_part.inline_data = None
        mock_candidate = MagicMock()
        mock_candidate.content.parts = [mock_part]
        mock_response = MagicMock()
        mock_response.candidates = [mock_candidate]
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response
        mock_client_cls.return_value = mock_client

        mp3, duration = render_tts_to_mp3("test script", mock_config)
        assert mp3 is None
        assert duration is None

    @patch("src.services.tts.genai.Client")
    @patch("src.services.tts.subprocess.run")
    def test_ffmpeg_failure_returns_none(self, mock_subprocess, mock_client_cls, mock_config):
        import base64
        pcm_data = b"\x00\x01" * 100
        encoded = base64.b64encode(pcm_data)

        mock_part = MagicMock()
        mock_part.inline_data.data = encoded
        mock_candidate = MagicMock()
        mock_candidate.content.parts = [mock_part]
        mock_response = MagicMock()
        mock_response.candidates = [mock_candidate]
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response
        mock_client_cls.return_value = mock_client

        # ffmpeg fails
        ffmpeg_result = MagicMock()
        ffmpeg_result.returncode = 1
        ffmpeg_result.stderr = b"ffmpeg error"
        mock_subprocess.return_value = ffmpeg_result

        mp3, duration = render_tts_to_mp3("test script", mock_config)
        assert mp3 is None
        assert duration is None


def test_mime_type():
    assert AUDIO_MIME_TYPE == "audio/mpeg"
