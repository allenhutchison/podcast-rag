"""
Tests for the web application endpoints and functionality.
"""


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


class TestDopplerEnvLoading:
    """Tests for Doppler ENV JSON blob loading."""

    def test_load_doppler_env_parses_json(self):
        """Test that _load_doppler_env parses JSON and sets env vars."""
        import json
        import os

        from src.config import _load_doppler_env

        # Set up test data
        test_vars = {"TEST_DOPPLER_VAR": "test_value", "TEST_DOPPLER_NUM": "42"}
        os.environ["ENV"] = json.dumps(test_vars)

        try:
            _load_doppler_env()
            assert os.environ.get("TEST_DOPPLER_VAR") == "test_value"
            assert os.environ.get("TEST_DOPPLER_NUM") == "42"
        finally:
            # Clean up
            os.environ.pop("ENV", None)
            os.environ.pop("TEST_DOPPLER_VAR", None)
            os.environ.pop("TEST_DOPPLER_NUM", None)

    def test_load_doppler_env_does_not_override_existing(self):
        """Test that existing env vars are not overwritten."""
        import json
        import os

        from src.config import _load_doppler_env

        # Set existing var
        os.environ["TEST_EXISTING_VAR"] = "original"
        os.environ["ENV"] = json.dumps({"TEST_EXISTING_VAR": "from_doppler"})

        try:
            _load_doppler_env()
            assert os.environ.get("TEST_EXISTING_VAR") == "original"
        finally:
            os.environ.pop("ENV", None)
            os.environ.pop("TEST_EXISTING_VAR", None)

    def test_load_doppler_env_ignores_invalid_json(self):
        """Test that invalid JSON is silently ignored."""
        import os

        from src.config import _load_doppler_env

        os.environ["ENV"] = "not valid json {"

        try:
            # Should not raise
            _load_doppler_env()
        finally:
            os.environ.pop("ENV", None)

    def test_load_doppler_env_handles_missing_env(self):
        """Test that missing ENV variable is handled gracefully."""
        import os

        from src.config import _load_doppler_env

        os.environ.pop("ENV", None)
        # Should not raise
        _load_doppler_env()


class TestChatRequestModel:
    """Tests for ChatRequest model."""

    def test_chat_request_basic(self):
        """Test ChatRequest model with basic query."""
        from src.web.models import ChatRequest

        request = ChatRequest(query="What are the latest episodes?")
        assert request.query == "What are the latest episodes?"
        assert request.podcast_id is None
        assert request.episode_id is None

    def test_chat_request_all_filters_together(self):
        """Test ChatRequest with all filter fields populated."""
        from src.web.models import ChatRequest

        request = ChatRequest(
            query="Complex query",
            podcast_id="123e4567-e89b-12d3-a456-426614174000",
            episode_id="episode-123",
        )
        assert request.query == "Complex query"
        assert request.podcast_id == "123e4567-e89b-12d3-a456-426614174000"
        assert request.episode_id == "episode-123"

    def test_chat_request_validation_empty_query(self):
        """Test that empty query is rejected."""
        from pydantic import ValidationError

        from src.web.models import ChatRequest

        with pytest.raises(ValidationError):
            ChatRequest(query="")

    def test_chat_request_validation_query_too_long(self):
        """Test that overly long queries are rejected."""
        from pydantic import ValidationError

        from src.web.models import ChatRequest

        long_query = "x" * 1001
        with pytest.raises(ValidationError):
            ChatRequest(query=long_query)

    def test_chat_request_with_podcast_id(self):
        """Test ChatRequest with podcast_id filter."""
        from src.web.models import ChatRequest

        request = ChatRequest(
            query="Test",
            podcast_id="podcast-123",
        )
        assert request.podcast_id == "podcast-123"
        assert request.episode_id is None


class TestGenerateAgenticResponseSignature:
    """Tests for generate_agentic_response function signature."""

    def test_generate_agentic_response_has_user_id_parameter(self):
        """Test that generate_agentic_response requires user_id."""
        import inspect

        from src.web.app import generate_agentic_response

        sig = inspect.signature(generate_agentic_response)
        params = list(sig.parameters.keys())

        assert "user_id" in params
        assert "session_id" in params
        assert "query" in params

    def test_generate_agentic_response_parameter_order(self):
        """Test parameter order in generate_agentic_response."""
        import inspect

        from src.web.app import generate_agentic_response

        sig = inspect.signature(generate_agentic_response)
        params = list(sig.parameters.keys())

        # Check required params come first
        assert params[0] == "query"
        assert params[1] == "session_id"
        assert params[2] == "user_id"

    def test_generate_agentic_response_is_async(self):
        """Test that generate_agentic_response is an async generator."""
        import inspect

        from src.web.app import generate_agentic_response

        assert inspect.isasyncgenfunction(generate_agentic_response)


class TestChatEndpointWithSubscribedOnly:
    """Tests for chat endpoint with subscribed_only parameter."""

    def test_chat_endpoint_accepts_subscribed_only_in_request(self, client):
        """Test that chat endpoint accepts subscribed_only in request body."""
        # Note: Will return 401 without auth, but validates request structure
        response = client.post(
            "/api/chat",
            json={
                "query": "What are the latest episodes?",
                "subscribed_only": True
            }
        )
        # Should fail auth, not request validation
        assert response.status_code == 401

    def test_chat_endpoint_accepts_subscribed_only_false(self, client):
        """Test that chat endpoint accepts subscribed_only=False."""
        response = client.post(
            "/api/chat",
            json={
                "query": "Search all podcasts",
                "subscribed_only": False
            }
        )
        assert response.status_code == 401  # Auth failure, not validation

    def test_chat_endpoint_validates_request_with_all_filters(self, client):
        """Test that chat endpoint accepts multiple filter parameters."""
        response = client.post(
            "/api/chat",
            json={
                "query": "Test query",
                "podcast_id": "123e4567-e89b-12d3-a456-426614174000",
                "subscribed_only": True
            }
        )
        # Should fail auth before processing filters
        assert response.status_code == 401


class TestValidatePodcastId:
    """Tests for _validate_podcast_id function."""

    def test_validate_podcast_id_valid_uuid(self):
        """Test that valid UUID passes validation."""
        import uuid

        from src.web.app import _validate_podcast_id

        valid_uuid = str(uuid.uuid4())
        result = _validate_podcast_id(valid_uuid)
        assert result == valid_uuid

    def test_validate_podcast_id_invalid_uuid_raises(self):
        """Test that invalid UUID raises HTTPException."""
        from fastapi import HTTPException

        from src.web.app import _validate_podcast_id

        with pytest.raises(HTTPException) as exc_info:
            _validate_podcast_id("not-a-uuid")

        assert exc_info.value.status_code == 422
        assert "Invalid podcast_id" in str(exc_info.value.detail)

    def test_validate_podcast_id_empty_string_raises(self):
        """Test that empty string raises HTTPException."""
        from fastapi import HTTPException

        from src.web.app import _validate_podcast_id

        with pytest.raises(HTTPException) as exc_info:
            _validate_podcast_id("")

        assert exc_info.value.status_code == 422

    def test_validate_podcast_id_sql_injection_attempt(self):
        """Test that SQL injection attempts are rejected."""
        from fastapi import HTTPException

        from src.web.app import _validate_podcast_id

        malicious_ids = [
            "1' OR '1'='1",
            "1; DROP TABLE podcasts--",
            "../../etc/passwd",
        ]

        for malicious_id in malicious_ids:
            with pytest.raises(HTTPException) as exc_info:
                _validate_podcast_id(malicious_id)
            assert exc_info.value.status_code == 422


class TestEscapeFilterValueIntegration:
    """Integration tests for escape_filter_value used in app.py."""

    def test_escape_filter_value_imported_correctly(self):
        """Test that escape_filter_value is available for import in app.py."""
        # This would be used in generate_streaming_response
        from src.agents.podcast_search import escape_filter_value

        result = escape_filter_value("Test Podcast")
        assert result == "Test Podcast"

    def test_escape_filter_value_handles_podcast_names_with_quotes(self):
        """Test escaping podcast names that might appear in filters."""
        from src.agents.podcast_search import escape_filter_value

        podcast_name = 'The "Tech" Podcast'
        result = escape_filter_value(podcast_name)
        assert result == 'The \\"Tech\\" Podcast'

    def test_escape_filter_value_or_condition_building(self):
        """Test building OR conditions for podcast list filtering."""
        from src.agents.podcast_search import escape_filter_value

        podcast_list = ["Podcast A", 'Podcast "B"', "Podcast\\C"]
        or_conditions = []

        for podcast_name in podcast_list:
            escaped = escape_filter_value(podcast_name)
            if escaped:
                or_conditions.append(f'podcast="{escaped}"')

        expected = [
            'podcast="Podcast A"',
            'podcast="Podcast \\"B\\""',
            'podcast="Podcast\\\\C"'
        ]
        assert or_conditions == expected

        # Build final OR filter
        filter_expr = f"({' OR '.join(or_conditions)})"
        assert "OR" in filter_expr
        assert filter_expr.startswith("(")
        assert filter_expr.endswith(")")


class TestSessionManagementRemovals:
    """Tests verifying removal of ADK session management code."""

    def test_no_session_service_global(self):
        """Test that _session_service global has been removed."""
        import src.web.app as app_module

        # Should not have _session_service anymore
        assert not hasattr(app_module, '_session_service')

    def test_no_session_runners_cache(self):
        """Test that _session_runners cache has been removed."""
        import src.web.app as app_module

        # Should not have _session_runners anymore
        assert not hasattr(app_module, '_session_runners')

    def test_no_get_session_service_function(self):
        """Test that _get_session_service helper has been removed."""
        import src.web.app as app_module

        # Should not have _get_session_service function
        assert not hasattr(app_module, '_get_session_service')

    def test_no_get_runner_for_session_function(self):
        """Test that _get_runner_for_session helper has been removed."""
        import src.web.app as app_module

        # Should not have _get_runner_for_session function
        assert not hasattr(app_module, '_get_runner_for_session')


class TestAgentsModuleExports:
    """Tests for updated agents module exports."""

    def test_agents_module_no_orchestrator_export(self):
        """Test that create_orchestrator is no longer exported."""
        from src import agents

        # Should not export create_orchestrator anymore
        assert not hasattr(agents, 'create_orchestrator')
        assert 'create_orchestrator' not in agents.__all__

    def test_agents_module_exports_podcast_search_functions(self):
        """Test that podcast search functions are still exported."""
        from src import agents

        expected_exports = [
            'get_podcast_citations',
            'set_podcast_citations',
            'clear_podcast_citations',
            'get_podcast_filter',
            'get_episode_filter',
            'set_podcast_filter',
        ]

        for export in expected_exports:
            assert hasattr(agents, export)
            assert export in agents.__all__

    def test_agents_module_imports_work(self):
        """Test that expected imports from agents module work."""
        from src.agents import (
            clear_podcast_citations,
            get_episode_filter,
            get_podcast_citations,
            get_podcast_filter,
            set_podcast_citations,
            set_podcast_filter,
        )

        # All should be callable
        assert callable(get_podcast_citations)
        assert callable(set_podcast_citations)
        assert callable(clear_podcast_citations)
        assert callable(get_podcast_filter)
        assert callable(get_episode_filter)
        assert callable(set_podcast_filter)


class TestValidateSessionId:
    """Tests for _validate_session_id function."""

    def test_validate_session_id_valid_uuid(self):
        """Test valid UUID passes validation."""
        import uuid

        from src.web.app import _validate_session_id

        valid_uuid = str(uuid.uuid4())
        result = _validate_session_id(valid_uuid)
        assert result == valid_uuid

    def test_validate_session_id_empty_generates_new(self):
        """Test empty session_id generates a new UUID."""
        from src.web.app import _validate_session_id

        result = _validate_session_id("")
        # Should be a valid UUID format
        import uuid
        uuid.UUID(result)  # Should not raise

    def test_validate_session_id_none_generates_new(self):
        """Test None session_id generates a new UUID."""
        from src.web.app import _validate_session_id

        result = _validate_session_id(None)
        import uuid
        uuid.UUID(result)  # Should not raise

    def test_validate_session_id_too_long_generates_new(self):
        """Test overly long session_id generates a new UUID."""
        from src.web.app import _validate_session_id

        long_id = "a" * 100
        result = _validate_session_id(long_id)
        assert result != long_id
        import uuid
        uuid.UUID(result)  # Should be valid UUID

    def test_validate_session_id_invalid_chars_generates_new(self):
        """Test session_id with invalid characters generates a new UUID."""
        from src.web.app import _validate_session_id

        invalid_ids = [
            "session<script>",
            "session id with spaces",
            "session;injection",
            "session\nid",
        ]

        for invalid_id in invalid_ids:
            result = _validate_session_id(invalid_id)
            assert result != invalid_id
            import uuid
            uuid.UUID(result)  # Should be valid UUID

    def test_validate_session_id_allows_alphanumeric(self):
        """Test session_id with alphanumeric characters passes."""
        from src.web.app import _validate_session_id

        valid_ids = [
            "abc123",
            "SESSION-123",
            "session_id_test",
            "test-session-123",
            "test_session-123",
        ]

        for valid_id in valid_ids:
            result = _validate_session_id(valid_id)
            assert result == valid_id


class TestLifespanContextManager:
    """Tests for the lifespan context manager."""

    def test_lifespan_exists(self):
        """Test that lifespan context manager is defined."""
        from src.web.app import lifespan

        assert lifespan is not None
        # Should be callable (async context manager wrapped with decorator)
        assert callable(lifespan)


class TestHealthEndpointExtended:
    """Extended tests for health endpoint."""

    def test_health_endpoint_returns_json(self, client):
        """Test health endpoint returns valid JSON."""
        response = client.get("/health")
        data = response.json()
        assert "status" in data
        assert "service" in data

    def test_health_endpoint_timing(self, client):
        """Test health endpoint responds quickly."""
        import time
        start = time.time()
        client.get("/health")
        elapsed = time.time() - start
        assert elapsed < 1.0  # Should respond in less than 1 second


class TestRootRedirect:
    """Tests for root URL redirect."""

    def test_root_redirects_to_podcasts(self, client):
        """Test root URL redirects to podcasts.html."""
        response = client.get("/", follow_redirects=False)
        assert response.status_code in [302, 307]
        assert "/podcasts.html" in response.headers.get("location", "")


class TestAPIRoutes:
    """Tests for API route registration."""

    def test_api_chat_route_exists(self, client):
        """Test that /api/chat route is registered."""
        # Will return 401 without auth, but route should exist
        response = client.post("/api/chat", json={"query": "test"})
        assert response.status_code != 404

    def test_api_conversations_route_exists(self, client):
        """Test that /api/conversations route is registered."""
        response = client.get("/api/conversations")
        assert response.status_code != 404

    def test_api_podcasts_route_exists(self, client):
        """Test that /api/podcasts route is registered."""
        response = client.get("/api/podcasts")
        assert response.status_code != 404

    def test_api_episodes_route_exists(self, client):
        """Test that /api/episodes route is registered."""
        response = client.get("/api/episodes/test-id")
        assert response.status_code != 404

    def test_api_search_route_exists(self, client):
        """Test that /api/search route is registered."""
        response = client.get("/api/search", params={"type": "keyword", "q": "test"})
        assert response.status_code != 404

    def test_admin_routes_exist(self, client):
        """Test that admin routes are registered."""
        response = client.get("/api/admin/users")
        # Will return 401/403, but route should exist
        assert response.status_code in [401, 403]


class TestMiddlewareConfiguration:
    """Tests for middleware configuration."""

    def test_session_middleware_configured(self):
        """Test that session middleware is configured."""
        from src.web.app import app

        # Check middleware stack - look at cls attribute of Middleware objects
        middleware_classes = [str(m) for m in app.user_middleware]
        # SessionMiddleware should be in the list
        assert any("Session" in name for name in middleware_classes)

    def test_cors_middleware_configured(self):
        """Test that CORS middleware is configured."""
        from src.web.app import app

        middleware_classes = [str(m) for m in app.user_middleware]
        assert any("CORS" in name for name in middleware_classes)

    def test_rate_limiter_in_state(self):
        """Test that rate limiter is in app state."""
        from src.web.app import app

        assert hasattr(app.state, "limiter")


class TestAppConfiguration:
    """Tests for app configuration."""

    def test_app_title(self):
        """Test app title is set."""
        from src.web.app import app

        assert app.title == "Podcast RAG Chat"

    def test_app_version(self):
        """Test app version is set."""
        from src.web.app import app

        assert app.version == "2.0.0"

    def test_config_in_state(self):
        """Test config is in app state."""
        from src.web.app import app

        assert hasattr(app.state, "config")

    def test_repository_in_state(self):
        """Test repository is in app state."""
        from src.web.app import app

        assert hasattr(app.state, "repository")


class TestAuthEndpoints:
    """Tests for auth endpoints."""

    def test_login_endpoint_exists(self, client):
        """Test that login endpoint is registered."""
        response = client.get("/auth/login")
        # Should redirect to Google OAuth, not return 404
        assert response.status_code != 404

    def test_logout_endpoint_exists(self, client):
        """Test that logout endpoint is registered."""
        response = client.post("/auth/logout")
        # Should work or redirect, not 404
        assert response.status_code != 404

    def test_me_endpoint_exists(self, client):
        """Test that /auth/me endpoint is registered."""
        response = client.get("/auth/me")
        # Will return 401 without auth, but should exist
        assert response.status_code != 404


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
