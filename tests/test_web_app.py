"""
Tests for the web application endpoints and functionality.
"""

import json
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from fastapi.testclient import TestClient

from src.web.app import app, count_tokens


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


@pytest.fixture
def mock_rag_manager():
    """Mock the RAG manager to avoid actual API calls."""
    with patch("src.web.app.rag_manager") as mock:
        mock.query = Mock(return_value="This is a test answer.")
        mock.get_citations = Mock(return_value=[
            {
                "index": 0,
                "title": "test_episode.txt",
                "text": "Test content",
                "uri": None
            }
        ])
        mock.file_search_manager.get_document_metadata_from_cache = Mock(return_value={
            "metadata": {
                "podcast": "Test Podcast",
                "episode": "Test Episode",
                "release_date": "2024-01-01"
            }
        })
        yield mock


class TestHealthEndpoint:
    """Tests for the /health endpoint."""

    def test_health_endpoint_returns_200(self, client):
        """Test that health endpoint returns 200 OK."""
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_endpoint_returns_correct_data(self, client):
        """Test that health endpoint returns correct health data."""
        response = client.get("/health")
        assert response.json() == {
            "status": "healthy",
            "service": "podcast-rag-web"
        }


class TestChatEndpoint:
    """Tests for the /api/chat endpoint."""

    def test_chat_endpoint_requires_query(self, client):
        """Test that chat endpoint rejects empty queries."""
        response = client.post(
            "/api/chat",
            json={"query": ""}
        )
        # FastAPI returns 422 for validation errors (empty string fails .strip())
        # But our custom validation in the endpoint returns 400
        assert response.status_code in [400, 422]

    @pytest.mark.skip(reason="Rate limiting causes test instability - test manually")
    def test_chat_endpoint_rejects_whitespace_query(self, client):
        """Test that chat endpoint rejects whitespace-only queries."""
        response = client.post(
            "/api/chat",
            json={"query": "   "}
        )
        assert response.status_code in [400, 422]

    @pytest.mark.skip(reason="Rate limiting makes this test flaky - test manually")
    def test_chat_endpoint_streams_response(self, client, mock_rag_manager):
        """Test that chat endpoint returns SSE stream."""
        response = client.post(
            "/api/chat",
            json={"query": "What is AI?"}
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/event-stream; charset=utf-8"

    @pytest.mark.skip(reason="Rate limiting makes this test flaky - test manually")
    def test_chat_endpoint_with_history(self, client, mock_rag_manager):
        """Test that chat endpoint accepts conversation history."""
        response = client.post(
            "/api/chat",
            json={
                "query": "What else?",
                "history": [
                    {"role": "user", "content": "What is AI?"},
                    {"role": "assistant", "content": "AI stands for artificial intelligence."}
                ]
            }
        )
        assert response.status_code == 200

    def test_chat_endpoint_validates_request_format(self, client):
        """Test that chat endpoint validates request format."""
        # Missing query field
        response = client.post(
            "/api/chat",
            json={}
        )
        assert response.status_code == 422  # Validation error


class TestTokenCounting:
    """Tests for the token counting functionality."""

    def test_count_tokens_with_tokenizer(self):
        """Test token counting when tiktoken is available."""
        text = "This is a test sentence."
        tokens = count_tokens(text)
        assert isinstance(tokens, int)
        assert tokens > 0

    def test_count_tokens_fallback(self):
        """Test token counting fallback when tiktoken is unavailable."""
        with patch("src.web.app.tokenizer", None):
            text = "This is a test sentence."
            tokens = count_tokens(text)
            # Fallback uses character estimation (4 chars per token)
            assert tokens == len(text) // 4


class TestStaticFiles:
    """Tests for static file serving."""

    def test_index_page_loads(self, client):
        """Test that index.html loads successfully."""
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_index_contains_chat_form(self, client):
        """Test that index page contains chat interface elements."""
        response = client.get("/")
        content = response.text
        assert "chatForm" in content
        assert "queryInput" in content
        assert "submitBtn" in content
        assert "newChatBtn" in content


class TestCORSConfiguration:
    """Tests for CORS middleware configuration."""

    def test_cors_headers_present(self, client):
        """Test that CORS headers are present in responses."""
        response = client.options(
            "/api/chat",
            headers={"Origin": "http://localhost:3000"}
        )
        assert "access-control-allow-origin" in response.headers

    def test_cors_allows_configured_origins(self, client):
        """Test that CORS allows the configured origins."""
        response = client.get(
            "/health",
            headers={"Origin": "http://localhost:3000"}
        )
        assert response.status_code == 200


class TestRateLimiting:
    """Tests for rate limiting functionality."""

    @pytest.mark.skip(reason="Rate limiting test requires careful timing - test manually")
    def test_rate_limit_enforced(self, client, mock_rag_manager):
        """Test that rate limiting is enforced on chat endpoint."""
        # Make requests up to the limit
        for i in range(11):  # Default is 10/minute
            response = client.post(
                "/api/chat",
                json={"query": f"Test query {i}"}
            )
            if i < 10:
                assert response.status_code == 200
            else:
                # 11th request should be rate limited
                assert response.status_code == 429


class TestErrorHandling:
    """Tests for error handling in the application."""

    def test_invalid_json_returns_422(self, client):
        """Test that invalid JSON returns 422 Unprocessable Entity."""
        response = client.post(
            "/api/chat",
            data="invalid json",
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 422

    def test_404_for_unknown_routes(self, client):
        """Test that unknown routes return 404."""
        response = client.get("/nonexistent")
        assert response.status_code == 404


class TestConfiguration:
    """Tests for configuration handling."""

    def test_config_loaded_correctly(self):
        """Test that configuration is loaded from Config class."""
        from src.web.app import config
        assert hasattr(config, "WEB_ALLOWED_ORIGINS")
        assert hasattr(config, "WEB_MAX_CONVERSATION_TOKENS")
        assert hasattr(config, "WEB_STREAMING_DELAY")
        assert hasattr(config, "WEB_RATE_LIMIT")
        assert hasattr(config, "WEB_PORT")

    def test_default_config_values(self):
        """Test that default configuration values are set."""
        from src.web.app import config
        assert config.WEB_MAX_CONVERSATION_TOKENS == 200000
        assert config.WEB_STREAMING_DELAY == 0.05
        assert config.WEB_RATE_LIMIT == "10/minute"
        assert config.WEB_PORT == 8080


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
