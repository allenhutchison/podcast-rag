"""Tests for web chat routes module."""

import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, patch, MagicMock, AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.web.chat_routes import router


@pytest.fixture
def mock_current_user():
    """Create mock current user."""
    return {
        "sub": "user-123",
        "email": "test@example.com",
        "name": "Test User",
    }


@pytest.fixture
def mock_repository():
    """Create mock repository."""
    return Mock()


@pytest.fixture
def app(mock_repository, mock_current_user):
    """Create FastAPI test app."""
    app = FastAPI()
    app.include_router(router)
    app.state.repository = mock_repository

    # Override the dependency
    from src.web.auth import get_current_user
    app.dependency_overrides[get_current_user] = lambda: mock_current_user

    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app, raise_server_exceptions=False)


class TestListConversations:
    """Tests for GET /api/conversations endpoint."""

    def test_list_conversations_success(self, client, mock_repository):
        """Test listing conversations."""
        mock_conv = Mock()
        mock_conv.id = "conv-1"
        mock_conv.title = "Test Conversation"
        mock_conv.scope = "library"
        mock_conv.podcast_id = None
        mock_conv.podcast = None
        mock_conv.episode_id = None
        mock_conv.episode = None
        mock_conv.message_count = 5
        mock_conv.created_at = datetime(2024, 1, 15, tzinfo=timezone.utc)
        mock_conv.updated_at = datetime(2024, 1, 15, tzinfo=timezone.utc)

        mock_repository.list_conversations.return_value = [mock_conv]
        mock_repository.count_conversations.return_value = 1

        response = client.get("/api/conversations")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["conversations"]) == 1
        assert data["conversations"][0]["id"] == "conv-1"

    def test_list_conversations_empty(self, client, mock_repository):
        """Test listing when no conversations exist."""
        mock_repository.list_conversations.return_value = []
        mock_repository.count_conversations.return_value = 0

        response = client.get("/api/conversations")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert len(data["conversations"]) == 0

    def test_list_conversations_with_pagination(self, client, mock_repository):
        """Test listing with limit and offset."""
        mock_repository.list_conversations.return_value = []
        mock_repository.count_conversations.return_value = 0

        response = client.get("/api/conversations?limit=10&offset=5")

        assert response.status_code == 200
        mock_repository.list_conversations.assert_called_with(
            "user-123", limit=10, offset=5
        )


class TestCreateConversation:
    """Tests for POST /api/conversations endpoint."""

    def test_create_conversation_all_scope(self, client, mock_repository):
        """Test creating an all-scoped conversation."""
        mock_conv = Mock()
        mock_conv.id = "conv-new"
        mock_conv.title = None
        mock_conv.scope = "all"
        mock_conv.podcast_id = None
        mock_conv.episode_id = None
        mock_conv.created_at = datetime.now(timezone.utc)
        mock_conv.updated_at = datetime.now(timezone.utc)

        mock_repository.create_conversation.return_value = mock_conv

        response = client.post(
            "/api/conversations",
            json={"scope": "all"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "conv-new"
        assert data["scope"] == "all"

    def test_create_conversation_podcast_scope_missing_id(self, client, mock_repository):
        """Test creating podcast-scoped conversation without podcast_id."""
        response = client.post(
            "/api/conversations",
            json={"scope": "podcast"}
        )

        assert response.status_code == 400
        assert "podcast_id is required" in response.json()["detail"]

    def test_create_conversation_episode_scope_missing_id(self, client, mock_repository):
        """Test creating episode-scoped conversation without episode_id."""
        response = client.post(
            "/api/conversations",
            json={"scope": "episode"}
        )

        assert response.status_code == 400
        assert "episode_id is required" in response.json()["detail"]

    def test_create_conversation_podcast_not_found(self, client, mock_repository):
        """Test creating conversation with non-existent podcast."""
        mock_repository.get_podcast.return_value = None

        response = client.post(
            "/api/conversations",
            json={"scope": "podcast", "podcast_id": "non-existent"}
        )

        assert response.status_code == 404
        assert "Podcast not found" in response.json()["detail"]

    def test_create_conversation_episode_not_found(self, client, mock_repository):
        """Test creating conversation with non-existent episode."""
        mock_repository.get_episode.return_value = None

        response = client.post(
            "/api/conversations",
            json={"scope": "episode", "episode_id": "non-existent"}
        )

        assert response.status_code == 404
        assert "Episode not found" in response.json()["detail"]

    def test_create_conversation_with_podcast(self, client, mock_repository):
        """Test creating podcast-scoped conversation."""
        mock_podcast = Mock()
        mock_podcast.title = "Test Podcast"
        mock_repository.get_podcast.return_value = mock_podcast

        mock_conv = Mock()
        mock_conv.id = "conv-new"
        mock_conv.title = None
        mock_conv.scope = "podcast"
        mock_conv.podcast_id = "pod-1"
        mock_conv.episode_id = None
        mock_conv.created_at = datetime.now(timezone.utc)
        mock_conv.updated_at = datetime.now(timezone.utc)
        mock_repository.create_conversation.return_value = mock_conv

        response = client.post(
            "/api/conversations",
            json={"scope": "podcast", "podcast_id": "pod-1"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["podcast_title"] == "Test Podcast"


class TestGetConversation:
    """Tests for GET /api/conversations/{id} endpoint."""

    def test_get_conversation_success(self, client, mock_repository, mock_current_user):
        """Test getting a conversation."""
        mock_conv = Mock()
        mock_conv.id = "conv-1"
        mock_conv.user_id = mock_current_user["sub"]
        mock_conv.title = "Test Conversation"
        mock_conv.scope = "library"
        mock_conv.podcast_id = None
        mock_conv.podcast = None
        mock_conv.episode_id = None
        mock_conv.episode = None
        mock_conv.messages = []
        mock_conv.created_at = datetime.now(timezone.utc)
        mock_conv.updated_at = datetime.now(timezone.utc)

        mock_repository.get_conversation.return_value = mock_conv

        response = client.get("/api/conversations/conv-1")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "conv-1"

    def test_get_conversation_not_found(self, client, mock_repository):
        """Test getting non-existent conversation."""
        mock_repository.get_conversation.return_value = None

        response = client.get("/api/conversations/non-existent")

        assert response.status_code == 404

    def test_get_conversation_wrong_user(self, client, mock_repository):
        """Test getting another user's conversation."""
        mock_conv = Mock()
        mock_conv.user_id = "other-user"

        mock_repository.get_conversation.return_value = mock_conv

        response = client.get("/api/conversations/conv-1")

        assert response.status_code == 404

    def test_get_conversation_with_messages(self, client, mock_repository, mock_current_user):
        """Test getting conversation with messages."""
        mock_msg = Mock()
        mock_msg.id = "msg-1"
        mock_msg.role = "user"
        mock_msg.content = "Hello"
        mock_msg.citations = None
        mock_msg.created_at = datetime.now(timezone.utc)

        mock_conv = Mock()
        mock_conv.id = "conv-1"
        mock_conv.user_id = mock_current_user["sub"]
        mock_conv.title = "Test"
        mock_conv.scope = "library"
        mock_conv.podcast_id = None
        mock_conv.podcast = None
        mock_conv.episode_id = None
        mock_conv.episode = None
        mock_conv.messages = [mock_msg]
        mock_conv.created_at = datetime.now(timezone.utc)
        mock_conv.updated_at = datetime.now(timezone.utc)

        mock_repository.get_conversation.return_value = mock_conv

        response = client.get("/api/conversations/conv-1")

        assert response.status_code == 200
        data = response.json()
        assert len(data["messages"]) == 1
        assert data["messages"][0]["content"] == "Hello"

    def test_get_conversation_with_citations(self, client, mock_repository, mock_current_user):
        """Test getting conversation with citations."""
        mock_msg = Mock()
        mock_msg.id = "msg-1"
        mock_msg.role = "assistant"
        mock_msg.content = "Response"
        mock_msg.citations = [
            {
                "index": 0,
                "metadata": {
                    "podcast": "Test Podcast",
                    "episode": "Episode 1",
                    "release_date": "2024-01-15",
                }
            }
        ]
        mock_msg.created_at = datetime.now(timezone.utc)

        mock_conv = Mock()
        mock_conv.id = "conv-1"
        mock_conv.user_id = mock_current_user["sub"]
        mock_conv.title = "Test"
        mock_conv.scope = "library"
        mock_conv.podcast_id = None
        mock_conv.podcast = None
        mock_conv.episode_id = None
        mock_conv.episode = None
        mock_conv.messages = [mock_msg]
        mock_conv.created_at = datetime.now(timezone.utc)
        mock_conv.updated_at = datetime.now(timezone.utc)

        mock_repository.get_conversation.return_value = mock_conv

        response = client.get("/api/conversations/conv-1")

        assert response.status_code == 200
        data = response.json()
        assert data["messages"][0]["citations"] is not None
        assert data["messages"][0]["citations"][0]["metadata"]["podcast"] == "Test Podcast"


class TestUpdateConversation:
    """Tests for PATCH /api/conversations/{id} endpoint."""

    def test_update_conversation_success(self, client, mock_repository, mock_current_user):
        """Test updating a conversation."""
        mock_conv = Mock()
        mock_conv.id = "conv-1"
        mock_conv.user_id = mock_current_user["sub"]

        mock_updated = Mock()
        mock_updated.id = "conv-1"
        mock_updated.title = "New Title"
        mock_updated.scope = "library"
        mock_updated.podcast_id = None
        mock_updated.podcast = None
        mock_updated.episode_id = None
        mock_updated.episode = None
        mock_updated.message_count = 0
        mock_updated.created_at = datetime.now(timezone.utc)
        mock_updated.updated_at = datetime.now(timezone.utc)

        mock_repository.get_conversation.return_value = mock_conv
        mock_repository.update_conversation.return_value = mock_updated

        response = client.patch(
            "/api/conversations/conv-1",
            json={"title": "New Title"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "New Title"

    def test_update_conversation_not_found(self, client, mock_repository):
        """Test updating non-existent conversation."""
        mock_repository.get_conversation.return_value = None

        response = client.patch(
            "/api/conversations/non-existent",
            json={"title": "New Title"}
        )

        assert response.status_code == 404

    def test_update_conversation_wrong_user(self, client, mock_repository):
        """Test updating another user's conversation."""
        mock_conv = Mock()
        mock_conv.user_id = "other-user"

        mock_repository.get_conversation.return_value = mock_conv

        response = client.patch(
            "/api/conversations/conv-1",
            json={"title": "New Title"}
        )

        assert response.status_code == 404


class TestDeleteConversation:
    """Tests for DELETE /api/conversations/{id} endpoint."""

    def test_delete_conversation_success(self, client, mock_repository, mock_current_user):
        """Test deleting a conversation."""
        mock_conv = Mock()
        mock_conv.id = "conv-1"
        mock_conv.user_id = mock_current_user["sub"]

        mock_repository.get_conversation.return_value = mock_conv

        response = client.delete("/api/conversations/conv-1")

        assert response.status_code == 200
        data = response.json()
        assert data["deleted"] is True
        mock_repository.delete_conversation.assert_called_with("conv-1")

    def test_delete_conversation_not_found(self, client, mock_repository):
        """Test deleting non-existent conversation."""
        mock_repository.get_conversation.return_value = None

        response = client.delete("/api/conversations/non-existent")

        assert response.status_code == 404

    def test_delete_conversation_wrong_user(self, client, mock_repository):
        """Test deleting another user's conversation."""
        mock_conv = Mock()
        mock_conv.user_id = "other-user"

        mock_repository.get_conversation.return_value = mock_conv

        response = client.delete("/api/conversations/conv-1")

        assert response.status_code == 404


class TestSendMessage:
    """Tests for POST /api/conversations/{id}/messages endpoint."""

    def test_send_message_conversation_not_found(self, client, mock_repository):
        """Test sending message to non-existent conversation."""
        mock_repository.get_conversation.return_value = None

        response = client.post(
            "/api/conversations/non-existent/messages",
            json={"content": "Hello"}
        )

        assert response.status_code == 404

    def test_send_message_wrong_user(self, client, mock_repository):
        """Test sending message to another user's conversation."""
        mock_conv = Mock()
        mock_conv.user_id = "other-user"

        mock_repository.get_conversation.return_value = mock_conv

        response = client.post(
            "/api/conversations/conv-1/messages",
            json={"content": "Hello"}
        )

        assert response.status_code == 404

    @patch("src.web.chat_routes.generate_streaming_response", create=True)
    def test_send_message_success(
        self, mock_generate, client, mock_repository, mock_current_user
    ):
        """Test successful message sending."""
        mock_conv = Mock()
        mock_conv.id = "conv-1"
        mock_conv.user_id = mock_current_user["sub"]
        mock_conv.title = "Test"
        mock_conv.podcast_id = None
        mock_conv.episode_id = None
        mock_conv.scope = "library"
        mock_conv.messages = []

        mock_repository.get_conversation.return_value = mock_conv

        response = client.post(
            "/api/conversations/conv-1/messages",
            json={"content": "Hello"}
        )

        # Should return streaming response
        assert response.status_code == 200
        assert response.headers.get("content-type").startswith("text/event-stream")

    @patch("src.web.chat_routes.generate_streaming_response", create=True)
    def test_send_message_auto_title(
        self, mock_generate, client, mock_repository, mock_current_user
    ):
        """Test auto-title generation on first message."""
        mock_conv = Mock()
        mock_conv.id = "conv-1"
        mock_conv.user_id = mock_current_user["sub"]
        mock_conv.title = None  # No title yet
        mock_conv.podcast_id = None
        mock_conv.episode_id = None
        mock_conv.scope = "library"
        mock_conv.messages = []

        mock_repository.get_conversation.return_value = mock_conv

        response = client.post(
            "/api/conversations/conv-1/messages",
            json={"content": "This is my first message in the conversation"}
        )

        # Title should have been set
        mock_repository.update_conversation.assert_called()
