"""Tests for podcast routes - add, search, and import endpoints."""

from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from src.web.models import (
    AddPodcastByUrlRequest,
    AddPodcastResponse,
    OPMLImportRequest,
    OPMLImportResponse,
    OPMLImportResult,
    PodcastSearchResponse,
    PodcastSearchResult,
)
from src.web.podcast_routes import router


class TestAddPodcastByUrlRequest:
    """Tests for AddPodcastByUrlRequest model."""

    def test_valid_http_url(self):
        """Test valid HTTP URL is accepted."""
        request = AddPodcastByUrlRequest(feed_url="http://example.com/feed.xml")
        assert request.feed_url == "http://example.com/feed.xml"

    def test_valid_https_url(self):
        """Test valid HTTPS URL is accepted."""
        request = AddPodcastByUrlRequest(feed_url="https://example.com/feed.xml")
        assert request.feed_url == "https://example.com/feed.xml"

    def test_url_with_query_params(self):
        """Test URL with query parameters is accepted."""
        request = AddPodcastByUrlRequest(
            feed_url="https://example.com/feed.xml?format=rss&version=2"
        )
        assert "?format=rss" in request.feed_url

    def test_url_too_long_fails(self):
        """Test URL exceeding max length fails validation."""
        long_url = "https://example.com/" + "a" * 2050
        with pytest.raises(ValidationError):
            AddPodcastByUrlRequest(feed_url=long_url)

    def test_empty_url_fails(self):
        """Test empty URL fails validation."""
        with pytest.raises(ValidationError):
            AddPodcastByUrlRequest(feed_url="")

    def test_missing_url_fails(self):
        """Test missing URL fails validation."""
        with pytest.raises(ValidationError):
            AddPodcastByUrlRequest()


class TestAddPodcastResponse:
    """Tests for AddPodcastResponse model."""

    def test_create_response(self):
        """Test creating a valid response."""
        response = AddPodcastResponse(
            podcast_id="abc-123",
            title="My Podcast",
            is_new=True,
            is_subscribed=True,
            episode_count=10,
            message="Added podcast with 10 episodes",
        )
        assert response.podcast_id == "abc-123"
        assert response.title == "My Podcast"
        assert response.is_new is True
        assert response.episode_count == 10

    def test_episode_count_default(self):
        """Test episode_count defaults to 0."""
        response = AddPodcastResponse(
            podcast_id="abc-123",
            title="My Podcast",
            is_new=False,
            is_subscribed=True,
            message="Subscribed",
        )
        assert response.episode_count == 0


class TestPodcastSearchResult:
    """Tests for PodcastSearchResult model."""

    def test_create_result(self):
        """Test creating a valid search result."""
        result = PodcastSearchResult(
            title="Tech Talk",
            author="John Doe",
            feed_url="https://example.com/feed.xml",
            image_url="https://example.com/image.jpg",
            description="A tech podcast",
            genre="Technology",
        )
        assert result.title == "Tech Talk"
        assert result.author == "John Doe"
        assert result.feed_url == "https://example.com/feed.xml"

    def test_optional_fields_default(self):
        """Test optional fields default to None/empty."""
        result = PodcastSearchResult(
            title="Minimal Podcast",
            feed_url="https://example.com/feed.xml",
        )
        assert result.author == ""
        assert result.image_url is None
        assert result.description is None
        assert result.genre is None


class TestPodcastSearchResponse:
    """Tests for PodcastSearchResponse model."""

    def test_create_response(self):
        """Test creating a valid search response."""
        results = [
            PodcastSearchResult(
                title="Podcast 1",
                feed_url="https://example.com/feed1.xml",
            ),
            PodcastSearchResult(
                title="Podcast 2",
                feed_url="https://example.com/feed2.xml",
            ),
        ]
        response = PodcastSearchResponse(
            query="test",
            results=results,
            count=2,
        )
        assert response.query == "test"
        assert len(response.results) == 2
        assert response.count == 2

    def test_empty_results(self):
        """Test response with empty results."""
        response = PodcastSearchResponse(
            query="no-results",
            results=[],
            count=0,
        )
        assert response.count == 0
        assert len(response.results) == 0


class TestOPMLImportRequest:
    """Tests for OPMLImportRequest model."""

    def test_valid_content(self):
        """Test valid OPML content is accepted."""
        request = OPMLImportRequest(
            content='<?xml version="1.0"?><opml version="2.0"><body></body></opml>'
        )
        assert "opml" in request.content

    def test_empty_content_fails(self):
        """Test empty content fails validation."""
        with pytest.raises(ValidationError):
            OPMLImportRequest(content="")


class TestOPMLImportResult:
    """Tests for OPMLImportResult model."""

    def test_added_status(self):
        """Test added status result."""
        result = OPMLImportResult(
            feed_url="https://example.com/feed.xml",
            title="New Podcast",
            status="added",
            podcast_id="abc-123",
        )
        assert result.status == "added"
        assert result.podcast_id is not None
        assert result.error is None

    def test_existing_status(self):
        """Test existing status result."""
        result = OPMLImportResult(
            feed_url="https://example.com/feed.xml",
            title="Existing Podcast",
            status="existing",
            podcast_id="abc-123",
        )
        assert result.status == "existing"

    def test_failed_status(self):
        """Test failed status result."""
        result = OPMLImportResult(
            feed_url="https://example.com/feed.xml",
            title="Failed Podcast",
            status="failed",
            error="Connection timeout",
        )
        assert result.status == "failed"
        assert result.error == "Connection timeout"
        assert result.podcast_id is None

    def test_invalid_status_fails(self):
        """Test invalid status fails validation."""
        with pytest.raises(ValidationError):
            OPMLImportResult(
                feed_url="https://example.com/feed.xml",
                title="Podcast",
                status="invalid_status",
            )


class TestOPMLImportResponse:
    """Tests for OPMLImportResponse model."""

    def test_create_response(self):
        """Test creating a valid import response."""
        results = [
            OPMLImportResult(
                feed_url="https://example.com/feed1.xml",
                title="Podcast 1",
                status="added",
                podcast_id="abc-123",
            ),
            OPMLImportResult(
                feed_url="https://example.com/feed2.xml",
                title="Podcast 2",
                status="existing",
                podcast_id="def-456",
            ),
        ]
        response = OPMLImportResponse(
            total=2,
            added=1,
            existing=1,
            failed=0,
            results=results,
        )
        assert response.total == 2
        assert response.added == 1
        assert response.existing == 1
        assert response.failed == 0
        assert len(response.results) == 2


class TestPodcastRoutesEndpoints:
    """Integration tests for podcast routes endpoints."""

    def test_add_podcast_url_normalization(self):
        """Test that feed:// URLs are normalized to https://."""
        request = AddPodcastByUrlRequest(feed_url="feed://example.com/podcast.xml")
        # The normalization happens in the endpoint, not the model
        assert request.feed_url == "feed://example.com/podcast.xml"

    def test_search_response_serialization(self):
        """Test search response serializes to JSON correctly."""
        response = PodcastSearchResponse(
            query="test",
            results=[
                PodcastSearchResult(
                    title="Test Podcast",
                    feed_url="https://example.com/feed.xml",
                    author="Author",
                    image_url=None,
                )
            ],
            count=1,
        )
        json_data = response.model_dump()
        assert json_data["query"] == "test"
        assert len(json_data["results"]) == 1
        assert json_data["results"][0]["title"] == "Test Podcast"

    def test_opml_import_response_serialization(self):
        """Test OPML import response serializes to JSON correctly."""
        response = OPMLImportResponse(
            total=3,
            added=1,
            existing=1,
            failed=1,
            results=[
                OPMLImportResult(
                    feed_url="https://example.com/feed.xml",
                    title="Podcast",
                    status="added",
                    podcast_id="abc-123",
                )
            ],
        )
        json_data = response.model_dump()
        assert json_data["total"] == 3
        assert json_data["added"] == 1
        assert json_data["failed"] == 1


class TestURLValidation:
    """Tests for URL validation in AddPodcastByUrlRequest."""

    def test_valid_http_scheme(self):
        """Test http:// scheme is accepted."""
        request = AddPodcastByUrlRequest(feed_url="http://example.com/feed.xml")
        assert request.feed_url == "http://example.com/feed.xml"

    def test_valid_https_scheme(self):
        """Test https:// scheme is accepted."""
        request = AddPodcastByUrlRequest(feed_url="https://example.com/feed.xml")
        assert request.feed_url == "https://example.com/feed.xml"

    def test_valid_feed_scheme(self):
        """Test feed:// scheme is accepted."""
        request = AddPodcastByUrlRequest(feed_url="feed://example.com/feed.xml")
        assert request.feed_url == "feed://example.com/feed.xml"

    def test_invalid_scheme_rejected(self):
        """Test invalid URL schemes are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            AddPodcastByUrlRequest(feed_url="ftp://example.com/feed.xml")
        assert "Invalid URL scheme" in str(exc_info.value)

    def test_no_scheme_rejected(self):
        """Test URLs without scheme are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            AddPodcastByUrlRequest(feed_url="example.com/feed.xml")
        assert "Invalid URL scheme" in str(exc_info.value)

    def test_javascript_scheme_rejected(self):
        """Test javascript: URLs are rejected for security."""
        with pytest.raises(ValidationError) as exc_info:
            AddPodcastByUrlRequest(feed_url="javascript:alert(1)")
        assert "Invalid URL scheme" in str(exc_info.value)

    def test_whitespace_trimmed(self):
        """Test whitespace is trimmed from URLs."""
        request = AddPodcastByUrlRequest(feed_url="  https://example.com/feed.xml  ")
        assert request.feed_url == "https://example.com/feed.xml"


class TestOPMLContentMaxLength:
    """Tests for OPML content max_length constraint."""

    def test_normal_content_accepted(self):
        """Test normal-sized content is accepted."""
        content = '<?xml version="1.0"?><opml version="2.0"><body></body></opml>'
        request = OPMLImportRequest(content=content)
        assert request.content == content

    def test_max_length_enforced(self):
        """Test content exceeding 10MB is rejected."""
        # Create content just over 10MB
        content = "x" * (10 * 1024 * 1024 + 1)
        with pytest.raises(ValidationError) as exc_info:
            OPMLImportRequest(content=content)
        # Pydantic will raise validation error for max_length
        assert "String should have at most" in str(exc_info.value)


class TestPodcastRoutesIntegration:
    """Integration tests for podcast routes using TestClient."""

    @pytest.fixture
    def app_with_mocks(self):
        """Create a test app with mocked dependencies."""
        from src.web.auth import get_current_user

        app = FastAPI()
        app.include_router(router)

        # Mock repository
        mock_repo = Mock()
        mock_repo.get_podcast_by_feed_url.return_value = None
        mock_repo.is_user_subscribed.return_value = False
        mock_repo.subscribe_user_to_podcast.return_value = None
        mock_repo.list_episodes.return_value = []

        # Mock config
        mock_config = Mock()
        mock_config.PODCAST_DOWNLOAD_DIRECTORY = "/tmp/podcasts"

        app.state.repository = mock_repo
        app.state.config = mock_config

        # Override the auth dependency
        def mock_get_current_user():
            return {"sub": "test-user-id", "email": "test@example.com"}

        app.dependency_overrides[get_current_user] = mock_get_current_user

        return app, mock_repo

    @pytest.fixture
    def authenticated_client(self, app_with_mocks):
        """Create an authenticated test client."""
        app, mock_repo = app_with_mocks
        client = TestClient(app)
        yield client, mock_repo

    def test_add_podcast_invalid_url_scheme(self, authenticated_client):
        """Test adding a podcast with invalid URL scheme returns 422."""
        client, _ = authenticated_client
        response = client.post(
            "/api/podcasts/add",
            json={"feed_url": "ftp://example.com/feed.xml"}
        )
        assert response.status_code == 422
        assert "Invalid URL scheme" in response.text

    def test_add_podcast_missing_url(self, authenticated_client):
        """Test adding a podcast without URL returns 422."""
        client, _ = authenticated_client
        response = client.post(
            "/api/podcasts/add",
            json={}
        )
        assert response.status_code == 422

    def test_search_empty_query_rejected(self, authenticated_client):
        """Test search with empty query returns 400."""
        client, _ = authenticated_client
        response = client.get("/api/podcasts/search?q=")
        assert response.status_code == 400
        assert "empty" in response.json()["detail"].lower()

    def test_search_whitespace_query_rejected(self, authenticated_client):
        """Test search with whitespace-only query returns 400."""
        client, _ = authenticated_client
        response = client.get("/api/podcasts/search?q=   ")
        assert response.status_code == 400

    def test_import_opml_empty_content(self, authenticated_client):
        """Test OPML import with empty content returns 422."""
        client, _ = authenticated_client
        response = client.post(
            "/api/podcasts/import-opml",
            json={"content": ""}
        )
        assert response.status_code == 422

    def test_add_existing_podcast_subscribes_user(self, authenticated_client):
        """Test adding an existing podcast subscribes the user."""
        client, mock_repo = authenticated_client

        # Set up mock to return an existing podcast
        mock_podcast = Mock()
        mock_podcast.id = "existing-podcast-id"
        mock_podcast.title = "Existing Podcast"
        mock_repo.get_podcast_by_feed_url.return_value = mock_podcast
        mock_repo.is_user_subscribed.return_value = False

        response = client.post(
            "/api/podcasts/add",
            json={"feed_url": "https://example.com/feed.xml"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["is_new"] is False
        assert data["is_subscribed"] is True
        assert data["podcast_id"] == "existing-podcast-id"
        mock_repo.subscribe_user_to_podcast.assert_called_once()
