"""Tests for the podcast-rag Scribe API client."""

from unittest.mock import Mock, call

import pytest
import requests

from src.services.scribe import ScribeClient, ScribeClientError, ScribeTranscript


def _client(response: Mock) -> tuple[ScribeClient, Mock]:
    session = Mock()
    session.headers = {}
    response.status_code = 200
    session.post.return_value = response
    return (
        ScribeClient(
            base_url="https://scribe.example.com/",
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
        "https://scribe.example.com/v1/transcripts",
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
        base_url="https://scribe.example.com",
        api_token="secret",
        session=session,
        backoff_seconds=0,
    )

    with pytest.raises(ScribeClientError, match="Scribe request failed"):
        client.submit(audio_url="https://example.com/episode.mp3")


def test_token_is_required() -> None:
    with pytest.raises(ValueError, match="SCRIBE_API_TOKEN"):
        ScribeClient(base_url="https://scribe.example.com", api_token="")


def test_submit_retries_transient_failures_with_same_body() -> None:
    response = Mock(status_code=200)
    response.json.return_value = {"id": "job-1", "status": "queued"}
    session = Mock(headers={})
    session.post.side_effect = [
        requests.Timeout("first timeout"),
        Mock(status_code=503),
        response,
    ]
    sleep = Mock()
    client = ScribeClient(
        base_url="https://scribe.example.com",
        api_token="secret",
        timeout=12,
        session=session,
        backoff_seconds=0.25,
        sleep=sleep,
    )

    result = client.submit(audio_url="https://example.com/episode.mp3")

    assert result.status == "queued"
    assert session.post.call_count == 3
    assert [call.kwargs["json"] for call in session.post.call_args_list] == [
        session.post.call_args_list[0].kwargs["json"]
    ] * 3
    assert sleep.call_args_list == [call(0.25), call(0.5)]


def test_submit_logs_final_failure(caplog) -> None:
    session = Mock(headers={})
    session.post.side_effect = requests.Timeout("timed out")
    client = ScribeClient(
        base_url="https://scribe.example.com",
        api_token="secret",
        session=session,
        backoff_seconds=0,
    )

    with caplog.at_level("ERROR"), pytest.raises(ScribeClientError) as exc_info:
        client.submit(audio_url="https://example.com/episode.mp3")

    assert exc_info.value.retryable is True
    assert session.post.call_count == 3
    assert any(
        record.exc_info and "after 3 attempt(s)" in record.message for record in caplog.records
    )


def test_submit_does_not_retry_terminal_http_failure() -> None:
    response = Mock(status_code=400)
    response.raise_for_status.side_effect = requests.HTTPError("bad request", response=response)
    session = Mock(headers={})
    session.post.return_value = response
    client = ScribeClient(
        base_url="https://scribe.example.com",
        api_token="secret",
        session=session,
    )

    with pytest.raises(ScribeClientError) as exc_info:
        client.submit(audio_url="https://example.com/episode.mp3")

    assert exc_info.value.retryable is False
    session.post.assert_called_once()


def test_invalid_request_and_response_fields_raise_client_error() -> None:
    response = Mock(status_code=200)
    response.json.return_value = {
        "id": "job-1",
        "status": "queued",
        "lang": 123,
    }
    client, session = _client(response)

    with pytest.raises(ScribeClientError, match="Invalid Scribe request"):
        client.submit(audio_url=object())  # type: ignore[arg-type]
    session.post.assert_not_called()

    with pytest.raises(ScribeClientError, match="Invalid Scribe response"):
        client.submit(audio_url="https://example.com/episode.mp3")
