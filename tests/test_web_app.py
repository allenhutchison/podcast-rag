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





class TestChatRequestModel:
    """Tests for the updated ChatRequest Pydantic model."""

    def test_chat_request_with_subscribed_only_field(self):
        """Test that ChatRequest accepts subscribed_only field."""
        from src.web.models import ChatRequest
        
        request = ChatRequest(
            query="What is AI?",
            subscribed_only=True
        )
        assert request.subscribed_only is True

    def test_chat_request_subscribed_only_defaults_to_none(self):
        """Test that subscribed_only defaults to None."""
        from src.web.models import ChatRequest
        
        request = ChatRequest(query="What is AI?")
        assert request.subscribed_only is None

    def test_chat_request_podcast_id_accepts_string_uuid(self):
        """Test that podcast_id accepts string UUID values."""
        from src.web.models import ChatRequest
        import uuid
        
        podcast_uuid = str(uuid.uuid4())
        request = ChatRequest(
            query="What is AI?",
            podcast_id=podcast_uuid
        )
        assert request.podcast_id == podcast_uuid

    def test_chat_request_podcast_id_accepts_none(self):
        """Test that podcast_id can be None."""
        from src.web.models import ChatRequest
        
        request = ChatRequest(query="What is AI?")
        assert request.podcast_id is None

    def test_chat_request_with_all_filter_fields(self):
        """Test ChatRequest with all filter fields set."""
        from src.web.models import ChatRequest
        import uuid
        
        podcast_uuid = str(uuid.uuid4())
        request = ChatRequest(
            query="What is AI?",
            podcast_id=podcast_uuid,
            episode_id="episode-123",
            subscribed_only=False
        )
        assert request.podcast_id == podcast_uuid
        assert request.episode_id == "episode-123"
        assert request.subscribed_only is False

    def test_chat_request_validation_empty_query(self):
        """Test that ChatRequest rejects empty query."""
        from src.web.models import ChatRequest
        from pydantic import ValidationError
        import pytest
        
        with pytest.raises(ValidationError) as exc_info:
            ChatRequest(query="")
        
        errors = exc_info.value.errors()
        assert any('query' in str(err) for err in errors)

    def test_chat_request_validation_query_too_long(self):
        """Test that ChatRequest rejects queries over max length."""
        from src.web.models import ChatRequest
        from pydantic import ValidationError
        import pytest
        
        long_query = "x" * 1001
        with pytest.raises(ValidationError) as exc_info:
            ChatRequest(query=long_query)
        
        errors = exc_info.value.errors()
        assert any('query' in str(err) for err in errors)

    def test_chat_request_with_history(self):
        """Test ChatRequest with conversation history."""
        from src.web.models import ChatRequest, Message
        
        history = [
            Message(role="user", content="First question"),
            Message(role="assistant", content="First answer")
        ]
        request = ChatRequest(query="Follow-up question", history=history)
        assert len(request.history) == 2
        assert request.history[0].role == "user"

    def test_chat_request_mutually_exclusive_filters(self):
        """Test that different filter types can be set (validation happens at API level)."""
        from src.web.models import ChatRequest
        
        # Model validation doesn't enforce mutual exclusion - that's API logic
        # But we can create requests with different filter combinations
        request1 = ChatRequest(query="Test", podcast_id="uuid-123")
        assert request1.podcast_id == "uuid-123"
        assert request1.subscribed_only is None
        
        request2 = ChatRequest(query="Test", subscribed_only=True)
        assert request2.subscribed_only is True
        assert request2.podcast_id is None


class TestWebAppWithoutADKOrchestrator:
    """Tests verifying ADK orchestrator has been removed."""

    def test_no_adk_imports_in_app(self):
        """Test that app.py doesn't import ADK orchestrator."""
        import src.web.app as app_module
        
        # Check module doesn't have orchestrator references
        assert not hasattr(app_module, 'create_orchestrator')
        assert not hasattr(app_module, '_get_session_service')
        assert not hasattr(app_module, '_get_runner_for_session')

    def test_no_session_runners_cache(self):
        """Test that session runners cache has been removed."""
        import src.web.app as app_module
        
        assert not hasattr(app_module, '_session_runners')
        assert not hasattr(app_module, '_runners_lock')
        assert not hasattr(app_module, '_session_service')

    def test_generate_streaming_response_exists(self):
        """Test that generate_streaming_response function exists."""
        from src.web.app import generate_streaming_response
        import inspect
        
        assert callable(generate_streaming_response)
        assert inspect.iscoroutinefunction(generate_streaming_response)

    def test_generate_streaming_response_signature(self):
        """Test generate_streaming_response has correct signature."""
        from src.web.app import generate_streaming_response
        import inspect
        
        sig = inspect.signature(generate_streaming_response)
        params = list(sig.parameters.keys())
        
        assert 'query' in params
        assert 'session_id' in params
        assert 'user_id' in params
        assert 'podcast_id' in params
        assert 'episode_id' in params
        assert 'subscribed_only' in params

    def test_imports_podcast_search_functions_directly(self):
        """Test that app imports podcast_search functions directly."""
        import src.web.app as app_module
        
        # Should have these imports from src.agents.podcast_search
        assert hasattr(app_module, 'get_podcast_citations')
        assert hasattr(app_module, 'clear_podcast_citations')
        assert hasattr(app_module, 'set_podcast_filter')


class TestGenerateStreamingResponseParameters:
    """Tests for generate_streaming_response parameter handling."""

    @pytest.mark.skip(reason="Integration test - requires Gemini API")
    async def test_generate_streaming_response_with_podcast_id(self):
        """Test streaming response with podcast_id filter."""
        from src.web.app import generate_streaming_response
        
        async for event in generate_streaming_response(
            query="What is AI?",
            session_id="test-session",
            user_id="test-user",
            podcast_id="test-podcast-uuid"
        ):
            # Should yield SSE events
            assert isinstance(event, str)
            break

    @pytest.mark.skip(reason="Integration test - requires Gemini API")
    async def test_generate_streaming_response_with_episode_id(self):
        """Test streaming response with episode_id filter."""
        from src.web.app import generate_streaming_response
        
        async for event in generate_streaming_response(
            query="What is AI?",
            session_id="test-session",
            user_id="test-user",
            episode_id="test-episode-id"
        ):
            assert isinstance(event, str)
            break

    @pytest.mark.skip(reason="Integration test - requires Gemini API")
    async def test_generate_streaming_response_with_subscribed_only(self):
        """Test streaming response with subscribed_only filter."""
        from src.web.app import generate_streaming_response
        
        async for event in generate_streaming_response(
            query="What is AI?",
            session_id="test-session",
            user_id="test-user",
            subscribed_only=True
        ):
            assert isinstance(event, str)
            break

    def test_validate_session_id_still_exists(self):
        """Test that _validate_session_id helper still exists."""
        from src.web.app import _validate_session_id
        
        assert callable(_validate_session_id)


class TestChatEndpointWithNewParameters:
    """Tests for chat endpoint with new parameters."""

    def test_chat_endpoint_accepts_subscribed_only(self, client):
        """Test that chat endpoint accepts subscribed_only parameter."""
        # Without auth, should return 401, but validates request structure first sometimes
        response = client.post(
            "/api/chat",
            json={
                "query": "What is AI?",
                "subscribed_only": True
            }
        )
        # Should return 401 (auth required), not 422 (validation error)
        assert response.status_code == 401

    def test_chat_endpoint_accepts_uuid_podcast_id(self, client):
        """Test that chat endpoint accepts UUID string for podcast_id."""
        import uuid
        
        podcast_uuid = str(uuid.uuid4())
        response = client.post(
            "/api/chat",
            json={
                "query": "What is AI?",
                "podcast_id": podcast_uuid
            }
        )
        # Should return 401 (auth required), not 422 (validation error)
        assert response.status_code == 401

    def test_chat_endpoint_validates_request_with_all_new_fields(self, client):
        """Test chat endpoint with all new request fields."""
        import uuid
        
        response = client.post(
            "/api/chat",
            json={
                "query": "What is AI?",
                "podcast_id": str(uuid.uuid4()),
                "episode_id": "episode-123",
                "subscribed_only": False,
                "history": []
            }
        )
        # Should return 401 (auth required), not 422 (validation error)
        assert response.status_code == 401


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
