"""Tests for generate_audio_script function in briefing_generator."""

from unittest.mock import MagicMock, patch

import pytest

from src.config import Config
from src.services.briefing_generator import generate_audio_script


@pytest.fixture
def mock_config():
    config = MagicMock(spec=Config)
    config.GEMINI_API_KEY = "test_key"
    config.GEMINI_MODEL_FLASH = "gemini-2.5-flash"
    return config


@pytest.fixture
def briefing_data():
    return {
        "headline": "AI and Geopolitics Today",
        "briefing": (
            "Today's listening landscape is dominated by a single, unsettling question: "
            "Who holds the kill switch? Whether it's the U.S. government's ban on frontier "
            "models or the Trump administration's high-stakes gamble with Tehran, the theme "
            "of 2026 is becoming clear: control is the ultimate currency."
        ),
        "key_themes": ["AI governance", "Geopolitics"],
        "episode_highlights": [
            {
                "podcast_name": "Hard Fork",
                "episode_title": "AI Future Debate",
                "analysis": (
                    "Daniel Cocotello's AI 2027 scenario predicting superintelligence via "
                    "recursive self-improvement by 2028 is a terrifyingly plausible "
                    "counterweight to Sayesh Kapoor's grounded skepticism."
                ),
            }
        ],
        "connection_insight": "Control is the theme of 2026.",
    }


class TestGenerateAudioScript:
    @patch("src.services.briefing_generator.genai.Client")
    @patch("src.services.briefing_generator._retry_generate_content")
    def test_successful_generation(self, mock_retry, mock_client_cls, mock_config, briefing_data):
        mock_response = MagicMock()
        mock_response.text = "Welcome to your daily briefing. AI and Geopolitics Today..."
        mock_retry.return_value = mock_response

        result = generate_audio_script(briefing_data, mock_config)

        assert result is not None
        assert "daily briefing" in result.lower()
        # Verify prompt was formatted with briefing JSON
        _client_arg, kwargs = mock_retry.call_args
        assert "briefing_json" in kwargs["contents"] or "headline" in kwargs["contents"]

    @patch("src.services.briefing_generator._retry_generate_content")
    def test_empty_response_returns_none(self, mock_retry, mock_config, briefing_data):
        mock_response = MagicMock()
        mock_response.text = ""
        mock_retry.return_value = mock_response

        result = generate_audio_script(briefing_data, mock_config)
        assert result is None

    @patch("src.services.briefing_generator._retry_generate_content")
    def test_exception_returns_none(self, mock_retry, mock_config, briefing_data):
        mock_retry.side_effect = RuntimeError("API failure")

        result = generate_audio_script(briefing_data, mock_config)
        assert result is None

    @patch("src.services.briefing_generator._retry_generate_content")
    def test_uses_flash_model(self, mock_retry, mock_config, briefing_data):
        mock_response = MagicMock()
        mock_response.text = "script"
        mock_retry.return_value = mock_response

        generate_audio_script(briefing_data, mock_config)
        _args, kwargs = mock_retry.call_args
        assert kwargs["model"] == mock_config.GEMINI_MODEL_FLASH

    @patch("src.services.briefing_generator._retry_generate_content")
    def test_output_is_plain_text(self, mock_retry, mock_config, briefing_data):
        mock_response = MagicMock()
        mock_response.text = "Some spoken text without markdown."
        mock_retry.return_value = mock_response

        result = generate_audio_script(briefing_data, mock_config)
        assert "#" not in result  # no markdown headers
