"""
Tests for the web application endpoints and functionality.
"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.web.app import app


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


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
            "service": "podcast-rag"
        }


class TestChatEndpoint:
    """Tests for the /api/chat endpoint."""

    def test_chat_endpoint_requires_auth(self, client):
        """Test that chat endpoint requires authentication."""
        response = client.post(
            "/api/chat",
            json={"query": "What is AI?"}
        )
        # Without authentication, should return 401
        assert response.status_code == 401

    def test_chat_endpoint_requires_query(self, client):
        """Test that chat endpoint rejects empty queries (returns 401 without auth)."""
        response = client.post(
            "/api/chat",
            json={"query": ""}
        )
        # Without authentication, should return 401 before validation
        assert response.status_code == 401

    @pytest.mark.skip(reason="Rate limiting causes test instability - test manually")
    def test_chat_endpoint_rejects_whitespace_query(self, client):
        """Test that chat endpoint rejects whitespace-only queries."""
        response = client.post(
            "/api/chat",
            json={"query": "   "}
        )
        assert response.status_code in [400, 401, 422]

    @pytest.mark.skip(reason="Requires ADK components - test manually with live service")
    def test_chat_endpoint_streams_response(self, client):
        """Test that chat endpoint returns SSE stream."""
        response = client.post(
            "/api/chat",
            json={"query": "What is AI?"}
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/event-stream; charset=utf-8"

    @pytest.mark.skip(reason="Requires ADK components - test manually with live service")
    def test_chat_endpoint_with_history(self, client):
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
        """Test that chat endpoint validates request format (returns 401 without auth)."""
        # Missing query field - but auth is checked first
        response = client.post(
            "/api/chat",
            json={}
        )
        assert response.status_code == 401  # Auth checked before validation


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

    def test_index_has_adk_branding(self, client):
        """Test that index page shows ADK multi-agent branding."""
        response = client.get("/")
        content = response.text
        assert "ADK" in content or "Multi-Agent" in content


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
    def test_rate_limit_enforced(self, client):
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
            content="invalid json",
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

    def test_adk_timeout_config(self):
        """Test that ADK timeout configuration is available."""
        from src.web.app import config
        assert hasattr(config, "ADK_PARALLEL_TIMEOUT")
        assert config.ADK_PARALLEL_TIMEOUT == 30



class TestChatRequestModelSubscribedOnly:
    """Tests for the new subscribed_only field in ChatRequest."""

    def test_chat_request_with_subscribed_only_true(self):
        """Test ChatRequest with subscribed_only=True."""
        from src.web.models import ChatRequest
        
        request = ChatRequest(
            query="Test query",
            subscribed_only=True
        )
        
        assert request.query == "Test query"
        assert request.subscribed_only is True
        assert request.podcast_id is None
        assert request.episode_id is None

    def test_chat_request_subscribed_only_defaults_to_none(self):
        """Test that subscribed_only defaults to None."""
        from src.web.models import ChatRequest
        
        request = ChatRequest(query="Test query")
        
        assert request.subscribed_only is None

    def test_chat_request_with_all_scope_parameters(self):
        """Test ChatRequest with multiple scope parameters."""
        from src.web.models import ChatRequest
        
        request = ChatRequest(
            query="Test query",
            podcast_id="podcast-123",
            episode_id="episode-456",
            subscribed_only=True
        )
        
        assert request.podcast_id == "podcast-123"
        assert request.episode_id == "episode-456"
        assert request.subscribed_only is True


class TestGenerateStreamingResponseSignature:
    """Tests for the updated generate_streaming_response function signature."""

    def test_generate_streaming_response_accepts_user_id(self):
        """Test that generate_streaming_response accepts user_id parameter."""
        from src.web.app import generate_streaming_response
        import inspect
        
        sig = inspect.signature(generate_streaming_response)
        params = list(sig.parameters.keys())
        
        assert 'user_id' in params
        assert 'session_id' in params
        assert 'query' in params

    def test_generate_streaming_response_accepts_subscribed_only(self):
        """Test that generate_streaming_response accepts subscribed_only parameter."""
        from src.web.app import generate_streaming_response
        import inspect
        
        sig = inspect.signature(generate_streaming_response)
        params = list(sig.parameters.keys())
        
        assert 'subscribed_only' in params
        param = sig.parameters['subscribed_only']
        assert param.default is None


class TestValidateSessionIdEdgeCases:
    """Additional edge case tests for session ID validation."""

    def test_validate_session_id_with_unicode_characters(self):
        """Test session ID with unicode characters."""
        from src.web.app import _validate_session_id
        import uuid
        
        unicode_id = "session-🎧-test"
        result = _validate_session_id(unicode_id)
        
        assert result != unicode_id
        uuid.UUID(result)

    def test_validate_session_id_with_spaces(self):
        """Test session ID with spaces."""
        from src.web.app import _validate_session_id
        import uuid
        
        spaced_id = "session with spaces"
        result = _validate_session_id(spaced_id)
        
        assert result != spaced_id
        uuid.UUID(result)



if __name__ == "__main__":
    pytest.main([__file__, "-v"])
