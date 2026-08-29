"""Tests for validated Scribe configuration."""

import pytest
from pydantic import ValidationError

from src.config import Config, ScribeSettings


def test_scribe_settings_default_to_https() -> None:
    settings = ScribeSettings()

    assert str(settings.base_url).rstrip("/") == "https://scribe.vycari.ai"
    assert settings.transcription_backend == "local"
    assert settings.request_timeout == 30.0


def test_scribe_settings_reject_http_without_explicit_opt_in() -> None:
    with pytest.raises(ValidationError, match="SCRIBE_ALLOW_INSECURE_HTTP"):
        ScribeSettings.model_validate({"base_url": "http://scribe:8000"})

    settings = ScribeSettings.model_validate(
        {
            "base_url": "http://scribe:8000",
            "allow_insecure_http": "true",
        }
    )
    assert settings.allow_insecure_http is True


@pytest.mark.parametrize("timeout", ["0", "-1", "inf", "nan"])
def test_scribe_settings_require_positive_finite_timeout(timeout: str) -> None:
    with pytest.raises(ValidationError):
        ScribeSettings.model_validate({"request_timeout": timeout})


def test_config_populates_normalized_scribe_attributes(monkeypatch) -> None:
    monkeypatch.setattr("src.config.load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setenv("TRANSCRIPTION_BACKEND", "SCRIBE")
    monkeypatch.setenv("SCRIBE_BASE_URL", "https://scribe.example.com/")
    monkeypatch.setenv("SCRIBE_API_TOKEN", "token")
    monkeypatch.setenv("SCRIBE_REQUEST_TIMEOUT", "12.5")
    monkeypatch.setenv("SCRIBE_LANGUAGE", "")

    config = Config()

    assert config.TRANSCRIPTION_BACKEND == "scribe"
    assert config.SCRIBE_BASE_URL == "https://scribe.example.com"
    assert config.SCRIBE_API_TOKEN == "token"
    assert config.SCRIBE_REQUEST_TIMEOUT == 12.5
    assert config.SCRIBE_LANGUAGE is None
