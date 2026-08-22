"""Client for the shared Scribe transcription service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests

_VALID_STATUSES = {"queued", "processing", "completed", "failed"}


class ScribeClientError(RuntimeError):
    """A Scribe request failed or returned an invalid response."""


@dataclass(frozen=True)
class ScribeTranscript:
    """Validated response from Scribe."""

    id: str
    status: str
    transcript_id: str | None = None
    transcript: str | None = None
    language: str | None = None
    error: str | None = None
    duration_seconds: float | None = None
    model: str | None = None

    @classmethod
    def from_payload(cls, payload: Any) -> ScribeTranscript:
        if not isinstance(payload, dict):
            raise ScribeClientError("Scribe returned a non-object response")

        handle = payload.get("id")
        status = payload.get("status")
        if not isinstance(handle, str) or not handle:
            raise ScribeClientError("Scribe response is missing an id")
        if status not in _VALID_STATUSES:
            raise ScribeClientError(f"Scribe returned an invalid status: {status!r}")

        transcript_id = payload.get("transcript_id")
        if transcript_id is not None and not isinstance(transcript_id, str):
            raise ScribeClientError("Scribe returned an invalid transcript_id")
        transcript = payload.get("transcript")
        if status == "completed" and not isinstance(transcript, str):
            raise ScribeClientError("Completed Scribe response is missing transcript text")

        return cls(
            id=handle,
            transcript_id=transcript_id,
            status=status,
            transcript=transcript,
            language=payload.get("lang"),
            error=payload.get("error"),
            duration_seconds=payload.get("duration_seconds"),
            model=payload.get("model"),
        )


class ScribeClient:
    """Bearer-authenticated, idempotent Scribe API client."""

    def __init__(
        self,
        *,
        base_url: str,
        api_token: str,
        timeout: float = 30.0,
        session: requests.Session | None = None,
    ):
        if not api_token:
            raise ValueError("SCRIBE_API_TOKEN is required when using Scribe")
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._session = session or requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {api_token}",
                "Accept": "application/json",
            }
        )

    def submit(
        self,
        *,
        audio_url: str,
        language: str | None = None,
        hint_guid: str | None = None,
        hint_title: str | None = None,
    ) -> ScribeTranscript:
        """Submit or poll an idempotent transcription request."""
        body = {
            "audio_url": audio_url,
            "language": language,
            "hint_guid": hint_guid,
            "hint_title": hint_title,
        }
        try:
            response = self._session.post(
                f"{self._base_url}/v1/transcripts",
                json=body,
                timeout=self._timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            raise ScribeClientError(f"Scribe request failed: {exc}") from exc
        except ValueError as exc:
            raise ScribeClientError("Scribe returned invalid JSON") from exc

        return ScribeTranscript.from_payload(payload)
