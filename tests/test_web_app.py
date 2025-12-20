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




class TestChatRequestModel:
    """Tests for updated ChatRequest model with subscribed_only field."""

    def test_chat_request_with_subscribed_only_true(self):
        """Test ChatRequest model accepts subscribed_only=True."""
        from src.web.models import ChatRequest

        request = ChatRequest(
            query="What are the latest episodes?",
            subscribed_only=True
        )
        assert request.query == "What are the latest episodes?"
        assert request.subscribed_only is True
        assert request.podcast_id is None
        assert request.episode_id is None

    def test_chat_request_with_subscribed_only_false(self):
        """Test ChatRequest model accepts subscribed_only=False."""
        from src.web.models import ChatRequest

        request = ChatRequest(
            query="Search all podcasts",
            subscribed_only=False
        )
        assert request.subscribed_only is False

    def test_chat_request_subscribed_only_optional(self):
        """Test that subscribed_only field is optional."""
        from src.web.models import ChatRequest

        request = ChatRequest(query="Test query")
        assert request.subscribed_only is None

    def test_chat_request_all_filters_together(self):
        """Test ChatRequest with all filter fields populated."""
        from src.web.models import ChatRequest

        request = ChatRequest(
            query="Complex query",
            podcast_id="123e4567-e89b-12d3-a456-426614174000",
            episode_id="episode-123",
            subscribed_only=True
        )
        assert request.query == "Complex query"
        assert request.podcast_id == "123e4567-e89b-12d3-a456-426614174000"
        assert request.episode_id == "episode-123"
        assert request.subscribed_only is True

    def test_chat_request_validation_empty_query(self):
        """Test that empty query is rejected."""
        from src.web.models import ChatRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ChatRequest(query="")

    def test_chat_request_validation_query_too_long(self):
        """Test that overly long queries are rejected."""
        from src.web.models import ChatRequest
        from pydantic import ValidationError

        long_query = "x" * 1001
        with pytest.raises(ValidationError):
            ChatRequest(query=long_query)

    def test_chat_request_mutually_exclusive_filters(self):
        """Test that multiple filters can coexist (validation happens at endpoint level)."""
        from src.web.models import ChatRequest

        # Model allows all filters - logic validation is in the endpoint
        request = ChatRequest(
            query="Test",
            podcast_id="podcast-123",
            subscribed_only=True
        )
        assert request.podcast_id is not None
        assert request.subscribed_only is True


class TestGenerateStreamingResponseSignature:
    """Tests for updated generate_streaming_response function signature."""

    def test_generate_streaming_response_has_user_id_parameter(self):
        """Test that generate_streaming_response now requires user_id."""
        from src.web.app import generate_streaming_response
        import inspect

        sig = inspect.signature(generate_streaming_response)
        params = list(sig.parameters.keys())

        assert "user_id" in params
        assert "session_id" in params
        assert "query" in params

    def test_generate_streaming_response_has_subscribed_only_parameter(self):
        """Test that generate_streaming_response accepts subscribed_only parameter."""
        from src.web.app import generate_streaming_response
        import inspect

        sig = inspect.signature(generate_streaming_response)
        params = list(sig.parameters.keys())

        assert "subscribed_only" in params
        # Verify it's optional with default None
        param = sig.parameters["subscribed_only"]
        assert param.default is None

    def test_generate_streaming_response_parameter_order(self):
        """Test parameter order in generate_streaming_response."""
        from src.web.app import generate_streaming_response
        import inspect

        sig = inspect.signature(generate_streaming_response)
        params = list(sig.parameters.keys())

        # Check required params come first
        assert params[0] == "query"
        assert params[1] == "session_id"
        assert params[2] == "user_id"

    def test_generate_streaming_response_is_async(self):
        """Test that generate_streaming_response is an async generator."""
        from src.web.app import generate_streaming_response
        import inspect

        assert inspect.isasyncgenfunction(generate_streaming_response)


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
        from src.web.app import _validate_podcast_id
        import uuid

        valid_uuid = str(uuid.uuid4())
        result = _validate_podcast_id(valid_uuid)
        assert result == valid_uuid

    def test_validate_podcast_id_invalid_uuid_raises(self):
        """Test that invalid UUID raises HTTPException."""
        from src.web.app import _validate_podcast_id
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            _validate_podcast_id("not-a-uuid")

        assert exc_info.value.status_code == 400
        assert "Invalid podcast_id format" in str(exc_info.value.detail)

    def test_validate_podcast_id_empty_string_raises(self):
        """Test that empty string raises HTTPException."""
        from src.web.app import _validate_podcast_id
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            _validate_podcast_id("")

        assert exc_info.value.status_code == 400

    def test_validate_podcast_id_sql_injection_attempt(self):
        """Test that SQL injection attempts are rejected."""
        from src.web.app import _validate_podcast_id
        from fastapi import HTTPException

        malicious_ids = [
            "1' OR '1'='1",
            "1; DROP TABLE podcasts--",
            "../../etc/passwd",
        ]

        for malicious_id in malicious_ids:
            with pytest.raises(HTTPException) as exc_info:
                _validate_podcast_id(malicious_id)
            assert exc_info.value.status_code == 400


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
            get_podcast_citations,
            set_podcast_citations,
            clear_podcast_citations,
            get_podcast_filter,
            get_episode_filter,
            set_podcast_filter,
        )

        # All should be callable
        assert callable(get_podcast_citations)
        assert callable(set_podcast_citations)
        assert callable(clear_podcast_citations)
        assert callable(get_podcast_filter)
        assert callable(get_episode_filter)
        assert callable(set_podcast_filter)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
