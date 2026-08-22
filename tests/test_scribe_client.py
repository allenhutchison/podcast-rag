"""Tests for the podcast-rag Scribe API client."""

from unittest.mock import Mock

import pytest
import requests

from src.services.scribe import ScribeClient, ScribeClientError, ScribeTranscript


def _client(response: Mock) -> tuple[ScribeClient, Mock]:
    session = Mock()
    session.headers = {}
    session.post.return_value = response
    return (
        ScribeClient(
            base_url="http://scribe:8000/",
            api_token="secret",
            timeout=12,
            session=session,
        ),
        session,
    )


def test_submit_sends_idempotent_request() -> None:
    response = Mock()
    response.json.return_value = {"id": "job-1", "status": "queued"}
    client, session = _client(response)

    result = client.submit(
        audio_url="https://example.com/episode.mp3",
        language="en",
        hint_guid="episode-guid",
        hint_title="Episode title",
    )

    assert result == ScribeTranscript(id="job-1", status="queued")
    session.post.assert_called_once_with(
        "http://scribe:8000/v1/transcripts",
        json={
            "audio_url": "https://example.com/episode.mp3",
            "language": "en",
            "hint_guid": "episode-guid",
            "hint_title": "Episode title",
        },
        timeout=12,
    )


def test_submit_parses_completed_response() -> None:
    response = Mock()
    response.json.return_value = {
        "id": "job-1",
        "transcript_id": "transcript-1",
        "status": "completed",
        "transcript": "Hello world",
        "lang": "en",
        "model": "medium",
        "duration_seconds": 10.5,
    }
    client, _ = _client(response)

    result = client.submit(audio_url="https://example.com/episode.mp3")

    assert result.transcript_id == "transcript-1"
    assert result.transcript == "Hello world"
    assert result.language == "en"


def test_completed_response_requires_transcript() -> None:
    with pytest.raises(ScribeClientError, match="missing transcript"):
        ScribeTranscript.from_payload({"id": "transcript-1", "status": "completed"})


def test_request_error_is_sanitized_as_client_error() -> None:
    session = Mock()
    session.headers = {}
    session.post.side_effect = requests.Timeout("timed out")
    client = ScribeClient(
        base_url="http://scribe:8000",
        api_token="secret",
        session=session,
    )

    with pytest.raises(ScribeClientError, match="Scribe request failed"):
        client.submit(audio_url="https://example.com/episode.mp3")


def test_token_is_required() -> None:
    with pytest.raises(ValueError, match="SCRIBE_API_TOKEN"):
        ScribeClient(base_url="http://scribe:8000", api_token="")
