"""Tests for the Scribe-backed compatibility transcription worker."""

from unittest.mock import Mock

from src.services.scribe import ScribeClientError, ScribeTranscript
from src.workflow.workers.scribe_transcription import ScribeTranscriptionWorker


def _worker(response: ScribeTranscript):
    config = Mock()
    config.SCRIBE_LANGUAGE = "en"
    repository = Mock()
    client = Mock()
    client.submit.return_value = response
    worker = ScribeTranscriptionWorker(config, repository, client=client)

    episode = Mock()
    episode.id = "episode-1"
    episode.guid = "guid-1"
    episode.title = "Episode 1"
    episode.enclosure_url = "https://example.com/episode.mp3"
    episode.transcript_status = "pending"
    episode.transcript_retry_count = 0
    episode.transcript_external_id = None
    return worker, repository, client, episode


def test_queued_response_records_remote_handle() -> None:
    worker, repository, _, episode = _worker(ScribeTranscript(id="job-1", status="queued"))

    result = worker.transcribe_single(episode)

    assert result.status == "queued"
    repository.mark_transcript_started.assert_called_once_with("episode-1")
    repository.mark_transcript_remote_status.assert_called_once_with(
        "episode-1",
        provider="scribe",
        external_id="job-1",
        status="queued",
    )
    repository.mark_transcript_complete.assert_not_called()
    repository.mark_transcript_failed.assert_not_called()


def test_processing_response_does_not_restart_status() -> None:
    worker, repository, _, episode = _worker(ScribeTranscript(id="job-1", status="processing"))
    episode.transcript_status = "processing"

    result = worker.transcribe_single(episode)

    assert result.status == "processing"
    repository.mark_transcript_started.assert_not_called()


def test_completed_response_keeps_compatibility_copy() -> None:
    worker, repository, _, episode = _worker(
        ScribeTranscript(
            id="job-1",
            transcript_id="transcript-1",
            status="completed",
            transcript="Transcript text",
            language="en",
            model="medium",
        )
    )

    result = worker.transcribe_single(episode)

    assert result.is_complete
    assert result.external_id == "transcript-1"
    repository.mark_transcript_complete.assert_called_once_with(
        episode_id="episode-1",
        transcript_text="Transcript text",
        provider="scribe",
        external_id="transcript-1",
        model="medium",
        language="en",
    )


def test_completed_response_falls_back_to_job_id() -> None:
    worker, repository, _, episode = _worker(
        ScribeTranscript(
            id="job-1",
            status="completed",
            transcript="Transcript text",
        )
    )

    result = worker.transcribe_single(episode)

    assert result.external_id == "job-1"
    repository.mark_transcript_complete.assert_called_once_with(
        episode_id="episode-1",
        transcript_text="Transcript text",
        provider="scribe",
        external_id="job-1",
        model=None,
        language=None,
    )


def test_failed_response_is_terminal_for_this_attempt() -> None:
    worker, repository, _, episode = _worker(
        ScribeTranscript(
            id="job-1",
            transcript_id="transcript-1",
            status="failed",
            error="download failed",
        )
    )

    result = worker.transcribe_single(episode)

    assert result.status == "failed"
    assert result.is_terminal
    assert result.provider == "scribe"
    assert result.external_id == "transcript-1"
    assert result.error == "download failed"
    repository.mark_transcript_failed.assert_called_once_with(
        "episode-1",
        "download failed",
        provider="scribe",
        external_id="transcript-1",
    )


def test_request_failure_is_retryable_with_remote_identity() -> None:
    worker, repository, client, episode = _worker(ScribeTranscript(id="unused", status="queued"))
    episode.transcript_status = "processing"
    episode.transcript_external_id = "job-1"
    client.submit.side_effect = ScribeClientError("service unavailable", retryable=True)

    result = worker.transcribe_single(episode)

    assert result.status == "retryable"
    assert result.should_backoff
    assert result.provider == "scribe"
    assert result.external_id == "job-1"
    repository.mark_transcript_failed.assert_called_once_with(
        "episode-1",
        "service unavailable",
        provider="scribe",
        external_id="job-1",
    )
