"""Client for the shared Scribe transcription service."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any, Literal

import requests
from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, ValidationError, model_validator

logger = logging.getLogger(__name__)

_RETRYABLE_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}


class _ScribeRequest(BaseModel):
    """Validated request body accepted by Scribe's v1 endpoint."""

    model_config = ConfigDict(extra="forbid", strict=True)

    audio_url: AnyHttpUrl
    language: str | None = None
    hint_guid: str | None = None
    hint_title: str | None = None


class ScribeClientError(RuntimeError):
    """A Scribe request failed or returned an invalid response."""

    def __init__(self, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


class ScribeTranscript(BaseModel):
    """Validated response from Scribe."""

    model_config = ConfigDict(extra="ignore", frozen=True, populate_by_name=True, strict=True)

    id: str = Field(min_length=1)
    status: Literal["queued", "processing", "completed", "failed"]
    transcript_id: str | None = None
    transcript: str | None = None
    language: str | None = Field(default=None, alias="lang")
    error: str | None = None
    duration_seconds: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    model: str | None = None

    @model_validator(mode="after")
    def require_completed_transcript(self) -> ScribeTranscript:
        """Require transcript text, including an allowed empty string, on completion."""
        if self.status == "completed" and self.transcript is None:
            raise ValueError("completed Scribe response is missing transcript text")
        return self

    @classmethod
    def from_payload(cls, payload: Any) -> ScribeTranscript:
        """Parse a Scribe response and normalize validation failures."""
        try:
            return cls.model_validate(payload)
        except ValidationError as exc:
            raise ScribeClientError(f"Invalid Scribe response: {exc}") from exc


class ScribeClient:
    """Bearer-authenticated, idempotent Scribe API client."""

    def __init__(
        self,
        *,
        base_url: str,
        api_token: str,
        timeout: float = 30.0,
        session: requests.Session | None = None,
        max_attempts: int = 3,
        backoff_seconds: float = 0.5,
        sleep: Callable[[float], None] = time.sleep,
    ):
        """Initialize an authenticated client with bounded retry behavior."""
        if not api_token:
            raise ValueError("SCRIBE_API_TOKEN is required when using Scribe")
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if backoff_seconds < 0:
            raise ValueError("backoff_seconds must be non-negative")
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._max_attempts = max_attempts
        self._backoff_seconds = backoff_seconds
        self._sleep = sleep
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
        try:
            body = _ScribeRequest(
                audio_url=audio_url,
                language=language,
                hint_guid=hint_guid,
                hint_title=hint_title,
            ).model_dump(mode="json")
        except ValidationError as exc:
            raise ScribeClientError(f"Invalid Scribe request: {exc}") from exc

        response = None
        for attempt in range(1, self._max_attempts + 1):
            try:
                response = self._session.post(
                    f"{self._base_url}/v1/transcripts",
                    json=body,
                    timeout=self._timeout,
                )
                if response.status_code in _RETRYABLE_STATUS_CODES:
                    raise requests.HTTPError(
                        f"retryable Scribe HTTP status {response.status_code}",
                        response=response,
                    )
                response.raise_for_status()
                break
            except requests.RequestException as exc:
                status_code = getattr(getattr(exc, "response", None), "status_code", None)
                retryable = not isinstance(exc, requests.HTTPError) or (
                    status_code in _RETRYABLE_STATUS_CODES
                )
                if retryable and attempt < self._max_attempts:
                    self._sleep(self._backoff_seconds * (2 ** (attempt - 1)))
                    continue
                logger.error(
                    "Scribe request failed after %d attempt(s)",
                    attempt,
                    exc_info=True,
                )
                raise ScribeClientError(
                    f"Scribe request failed: {exc}", retryable=retryable
                ) from exc

        assert response is not None
        try:
            payload = response.json()
        except ValueError as exc:
            raise ScribeClientError("Scribe returned invalid JSON") from exc

        return ScribeTranscript.from_payload(payload)
