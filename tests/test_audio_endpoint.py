"""Tests for briefing audio endpoints and _parse_range helper."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.web.app import _parse_range, app
from src.web.auth import get_current_user


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


def _override_auth(user_id: str = "user-1"):
    """Override the get_current_user dependency for testing."""
    app.dependency_overrides[get_current_user] = lambda: {"sub": user_id}


def _clear_auth():
    """Clear auth override."""
    app.dependency_overrides.pop(get_current_user, None)


class TestParseRange:
    """Tests for the _parse_range helper — pure function, no auth."""

    def test_full_range(self):
        assert _parse_range("bytes=0-99", 100) == (0, 99)

    def test_open_ended_range(self):
        assert _parse_range("bytes=50-", 100) == (50, 99)

    def test_prefix_range(self):
        assert _parse_range("bytes=0-49", 100) == (0, 49)

    def test_suffix_range(self):
        assert _parse_range("bytes=-10", 100) == (90, 99)

    def test_suffix_larger_than_total(self):
        assert _parse_range("bytes=-200", 100) == (0, 99)

    def test_start_beyond_total_returns_none(self):
        assert _parse_range("bytes=100-", 100) is None

    def test_inverted_range_returns_none(self):
        assert _parse_range("bytes=100-50", 200) is None

    def test_invalid_unit_returns_none(self):
        assert _parse_range("items=0-99", 100) is None

    def test_malformed_range_returns_none(self):
        assert _parse_range("bytes=abc-def", 100) is None

    def test_none_header(self):
        assert _parse_range(None, 100) is None  # type: ignore[arg-type]


class TestAudioEndpointAuth:
    """Test that audio endpoints require auth and check ownership."""

    def test_post_audio_requires_auth(self, client):
        response = client.post("/api/feed/briefing/fake-id/audio")
        assert response.status_code == 401

    def test_get_audio_requires_auth(self, client):
        response = client.get("/api/feed/briefing/fake-id/audio")
        assert response.status_code == 401

    @patch("src.web.app._repository")
    def test_post_audio_other_user_404(self, mock_repo, client):
        """User cannot trigger audio for another user's briefing."""
        _override_auth("user-1")
        try:
            briefing = MagicMock()
            briefing.user_id = "user-2"  # Different user
            mock_repo.get_briefing_by_id.return_value = briefing

            response = client.post("/api/feed/briefing/briefing-123/audio")
            assert response.status_code == 404
        finally:
            _clear_auth()

    @patch("src.web.app._repository")
    def test_get_audio_other_user_404(self, mock_repo, client):
        """User cannot stream another user's briefing audio."""
        _override_auth("user-1")
        try:
            briefing = MagicMock()
            briefing.user_id = "user-2"
            briefing.audio_data = b"mp3"
            briefing.audio_status = "ready"
            briefing.audio_mime_type = "audio/mpeg"
            mock_repo.get_briefing_by_id.return_value = briefing

            response = client.get("/api/feed/briefing/briefing-123/audio")
            assert response.status_code == 404
        finally:
            _clear_auth()

    @patch("src.web.app._repository")
    def test_get_audio_not_generated_404(self, mock_repo, client):
        """GET returns 404 when audio not yet generated."""
        _override_auth("user-1")
        try:
            briefing = MagicMock()
            briefing.user_id = "user-1"
            briefing.audio_data = None
            briefing.audio_status = None
            mock_repo.get_briefing_by_id.return_value = briefing

            response = client.get("/api/feed/briefing/briefing-123/audio")
            assert response.status_code == 404
        finally:
            _clear_auth()


class TestServeAudioRange:
    """Test Range header handling on the GET endpoint."""

    @patch("src.web.app._repository")
    def test_full_response_200(self, mock_repo, client):
        """GET without Range returns 200 with full body."""
        _override_auth("user-1")
        try:
            briefing = MagicMock()
            briefing.user_id = "user-1"
            briefing.audio_data = b"\x00\x01\x02\x03" * 25  # 100 bytes
            briefing.audio_status = "ready"
            briefing.audio_mime_type = "audio/mpeg"
            mock_repo.get_briefing_by_id.return_value = briefing

            response = client.get("/api/feed/briefing/briefing-123/audio")
            assert response.status_code == 200
            assert response.headers["Content-Length"] == "100"
            assert response.headers["Accept-Ranges"] == "bytes"
            assert len(response.content) == 100
        finally:
            _clear_auth()

    @patch("src.web.app._repository")
    def test_partial_response_206(self, mock_repo, client):
        """GET with valid Range returns 206 with chunk."""
        _override_auth("user-1")
        try:
            briefing = MagicMock()
            briefing.user_id = "user-1"
            briefing.audio_data = b"\x00\x01\x02\x03" * 25  # 100 bytes
            briefing.audio_status = "ready"
            briefing.audio_mime_type = "audio/mpeg"
            mock_repo.get_briefing_by_id.return_value = briefing

            response = client.get(
                "/api/feed/briefing/briefing-123/audio",
                headers={"Range": "bytes=0-49"},
            )
            assert response.status_code == 206
            assert response.headers["Content-Range"] == "bytes 0-49/100"
            assert response.headers["Content-Length"] == "50"
            assert len(response.content) == 50
        finally:
            _clear_auth()

    @patch("src.web.app._repository")
    def test_unsatisfiable_range_416(self, mock_repo, client):
        """GET with out-of-bounds Range returns 416."""
        _override_auth("user-1")
        try:
            briefing = MagicMock()
            briefing.user_id = "user-1"
            briefing.audio_data = b"\x00\x01\x02\x03" * 25  # 100 bytes
            briefing.audio_status = "ready"
            briefing.audio_mime_type = "audio/mpeg"
            mock_repo.get_briefing_by_id.return_value = briefing

            response = client.get(
                "/api/feed/briefing/briefing-123/audio",
                headers={"Range": "bytes=200-300"},
            )
            assert response.status_code == 416
            assert response.headers["Content-Range"] == "bytes */100"
        finally:
            _clear_auth()