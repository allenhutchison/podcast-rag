"""
Tests for the chat tools module.

These tests cover the tool creation and citation extraction functionality
used by the chat agent.
"""

import pytest
from unittest.mock import MagicMock, patch


class TestExtractCitationsFromResponse:
    """Tests for _extract_citations_from_response function."""

    def test_extract_citations_empty_response(self):
        """Test extraction with no candidates in response."""
        from src.agents.chat_tools import _extract_citations_from_response

        mock_response = MagicMock()
        mock_response.candidates = []

        mock_repo = MagicMock()

        citations = _extract_citations_from_response(mock_response, mock_repo)
        assert citations == []

    def test_extract_citations_no_candidates_attribute(self):
        """Test extraction when response has no candidates attribute."""
        from src.agents.chat_tools import _extract_citations_from_response

        mock_response = MagicMock(spec=[])  # No attributes

        mock_repo = MagicMock()

        citations = _extract_citations_from_response(mock_response, mock_repo)
        assert citations == []

    def test_extract_citations_no_grounding_metadata(self):
        """Test extraction when candidate has no grounding_metadata."""
        from src.agents.chat_tools import _extract_citations_from_response

        mock_candidate = MagicMock(spec=['content'])  # No grounding_metadata
        mock_response = MagicMock()
        mock_response.candidates = [mock_candidate]

        mock_repo = MagicMock()

        citations = _extract_citations_from_response(mock_response, mock_repo)
        assert citations == []

    def test_extract_citations_empty_grounding_chunks(self):
        """Test extraction when grounding_chunks is empty."""
        from src.agents.chat_tools import _extract_citations_from_response

        mock_grounding = MagicMock()
        mock_grounding.grounding_chunks = []

        mock_candidate = MagicMock()
        mock_candidate.grounding_metadata = mock_grounding

        mock_response = MagicMock()
        mock_response.candidates = [mock_candidate]

        mock_repo = MagicMock()

        citations = _extract_citations_from_response(mock_response, mock_repo)
        assert citations == []

    def test_extract_citations_invalid_source_type(self):
        """Test extraction with invalid source_type defaults to transcript."""
        from src.agents.chat_tools import _extract_citations_from_response

        mock_response = MagicMock()
        mock_response.candidates = []

        mock_repo = MagicMock()

        # Should not raise, just log warning and return empty
        citations = _extract_citations_from_response(
            mock_response, mock_repo, source_type="invalid"
        )
        assert citations == []

    def test_extract_citations_transcript_source(self):
        """Test extraction for transcript source type."""
        from src.agents.chat_tools import _extract_citations_from_response

        # Create mock episode
        mock_episode = MagicMock()
        mock_episode.id = "episode-123"
        mock_episode.title = "Test Episode"
        mock_episode.published_date = None
        mock_episode.ai_hosts = ["Host 1"]
        mock_podcast = MagicMock()
        mock_podcast.id = "podcast-123"
        mock_podcast.title = "Test Podcast"
        mock_episode.podcast = mock_podcast

        # Create mock grounding chunk
        mock_ctx = MagicMock()
        mock_ctx.title = "episode_transcript.txt"
        mock_ctx.text = "Some transcript text"

        mock_chunk = MagicMock()
        mock_chunk.retrieved_context = mock_ctx

        mock_grounding = MagicMock()
        mock_grounding.grounding_chunks = [mock_chunk]

        mock_candidate = MagicMock()
        mock_candidate.grounding_metadata = mock_grounding

        mock_response = MagicMock()
        mock_response.candidates = [mock_candidate]

        mock_repo = MagicMock()
        mock_repo.get_episode_by_file_search_display_name.return_value = mock_episode

        citations = _extract_citations_from_response(
            mock_response, mock_repo, source_type="transcript"
        )

        assert len(citations) == 1
        assert citations[0]['source_type'] == 'transcript'
        assert citations[0]['title'] == "episode_transcript.txt"
        assert citations[0]['episode_id'] == "episode-123"
        assert citations[0]['podcast_id'] == "podcast-123"

    def test_extract_citations_description_source(self):
        """Test extraction for description source type."""
        from src.agents.chat_tools import _extract_citations_from_response

        # Create mock podcast
        mock_podcast = MagicMock()
        mock_podcast.id = "podcast-456"
        mock_podcast.title = "Test Podcast"
        mock_podcast.description = "A test podcast"
        mock_podcast.itunes_author = "Author Name"
        mock_podcast.author = None
        mock_podcast.image_url = "https://example.com/image.jpg"

        # Create mock grounding chunk
        mock_ctx = MagicMock()
        mock_ctx.title = "podcast_description.txt"
        mock_ctx.text = "Podcast description text"

        mock_chunk = MagicMock()
        mock_chunk.retrieved_context = mock_ctx

        mock_grounding = MagicMock()
        mock_grounding.grounding_chunks = [mock_chunk]

        mock_candidate = MagicMock()
        mock_candidate.grounding_metadata = mock_grounding

        mock_response = MagicMock()
        mock_response.candidates = [mock_candidate]

        mock_repo = MagicMock()
        mock_repo.get_podcast_by_description_display_name.return_value = mock_podcast

        citations = _extract_citations_from_response(
            mock_response, mock_repo, source_type="description"
        )

        assert len(citations) == 1
        assert citations[0]['source_type'] == 'description'
        assert citations[0]['podcast_id'] == "podcast-456"
        assert citations[0]['metadata']['podcast'] == "Test Podcast"
        assert citations[0]['metadata']['author'] == "Author Name"

    def test_extract_citations_skips_duplicates(self):
        """Test that duplicate titles are skipped."""
        from src.agents.chat_tools import _extract_citations_from_response

        mock_episode = MagicMock()
        mock_episode.id = "episode-123"
        mock_episode.title = "Episode"
        mock_episode.published_date = None
        mock_episode.ai_hosts = []
        mock_episode.podcast = MagicMock(id="podcast-123", title="Podcast")

        # Create two chunks with same title
        mock_ctx1 = MagicMock()
        mock_ctx1.title = "same_title.txt"
        mock_ctx1.text = "Text 1"
        mock_chunk1 = MagicMock()
        mock_chunk1.retrieved_context = mock_ctx1

        mock_ctx2 = MagicMock()
        mock_ctx2.title = "same_title.txt"
        mock_ctx2.text = "Text 2"
        mock_chunk2 = MagicMock()
        mock_chunk2.retrieved_context = mock_ctx2

        mock_grounding = MagicMock()
        mock_grounding.grounding_chunks = [mock_chunk1, mock_chunk2]

        mock_candidate = MagicMock()
        mock_candidate.grounding_metadata = mock_grounding

        mock_response = MagicMock()
        mock_response.candidates = [mock_candidate]

        mock_repo = MagicMock()
        mock_repo.get_episode_by_file_search_display_name.return_value = mock_episode

        citations = _extract_citations_from_response(mock_response, mock_repo)

        # Should only have one citation due to deduplication
        assert len(citations) == 1

    def test_extract_citations_handles_db_error(self):
        """Test that database errors are handled gracefully."""
        from src.agents.chat_tools import _extract_citations_from_response

        mock_ctx = MagicMock()
        mock_ctx.title = "episode.txt"
        mock_ctx.text = "Text"
        mock_chunk = MagicMock()
        mock_chunk.retrieved_context = mock_ctx

        mock_grounding = MagicMock()
        mock_grounding.grounding_chunks = [mock_chunk]

        mock_candidate = MagicMock()
        mock_candidate.grounding_metadata = mock_grounding

        mock_response = MagicMock()
        mock_response.candidates = [mock_candidate]

        mock_repo = MagicMock()
        mock_repo.get_episode_by_file_search_display_name.side_effect = Exception("DB error")

        citations = _extract_citations_from_response(mock_response, mock_repo)

        # Should return empty citations on error, not raise
        assert len(citations) == 0

    def test_extract_citations_skips_missing_episode(self):
        """Test that citations are skipped when episode not found."""
        from src.agents.chat_tools import _extract_citations_from_response

        mock_ctx = MagicMock()
        mock_ctx.title = "unknown_episode.txt"
        mock_ctx.text = "Text"
        mock_chunk = MagicMock()
        mock_chunk.retrieved_context = mock_ctx

        mock_grounding = MagicMock()
        mock_grounding.grounding_chunks = [mock_chunk]

        mock_candidate = MagicMock()
        mock_candidate.grounding_metadata = mock_grounding

        mock_response = MagicMock()
        mock_response.candidates = [mock_candidate]

        mock_repo = MagicMock()
        mock_repo.get_episode_by_file_search_display_name.return_value = None

        citations = _extract_citations_from_response(mock_response, mock_repo)

        # Should skip citation when episode not found
        assert len(citations) == 0


class TestCreateChatTools:
    """Tests for create_chat_tools function."""

    def test_create_chat_tools_returns_list(self):
        """Test that create_chat_tools returns a list of callables."""
        from src.agents.chat_tools import create_chat_tools

        mock_config = MagicMock()
        mock_config.GEMINI_API_KEY = "test-key"
        mock_config.GEMINI_MODEL_FLASH = "gemini-2.0-flash"

        mock_repo = MagicMock()
        mock_repo.get_podcast.return_value = None
        mock_repo.get_episode.return_value = None

        mock_file_search = MagicMock()
        mock_file_search.create_or_get_store.return_value = "stores/test-store"

        with patch('src.agents.chat_tools.genai.Client'):
            tools = create_chat_tools(
                config=mock_config,
                repository=mock_repo,
                file_search_manager=mock_file_search,
                user_id="user-123",
            )

        assert isinstance(tools, list)
        assert len(tools) > 0
        for tool in tools:
            assert callable(tool)

    def test_create_chat_tools_handles_podcast_scope(self):
        """Test tools created with podcast scope."""
        from src.agents.chat_tools import create_chat_tools

        mock_config = MagicMock()
        mock_config.GEMINI_API_KEY = "test-key"
        mock_config.GEMINI_MODEL_FLASH = "gemini-2.0-flash"

        mock_podcast = MagicMock()
        mock_podcast.title = "Test Podcast"

        mock_repo = MagicMock()
        mock_repo.get_podcast.return_value = mock_podcast
        mock_repo.get_episode.return_value = None

        mock_file_search = MagicMock()
        mock_file_search.create_or_get_store.return_value = "stores/test-store"

        with patch('src.agents.chat_tools.genai.Client'):
            tools = create_chat_tools(
                config=mock_config,
                repository=mock_repo,
                file_search_manager=mock_file_search,
                user_id="user-123",
                podcast_id="podcast-456",
            )

        assert len(tools) > 0
        # Verify podcast was fetched
        mock_repo.get_podcast.assert_called_once_with("podcast-456")

    def test_create_chat_tools_handles_episode_scope(self):
        """Test tools created with episode scope."""
        from src.agents.chat_tools import create_chat_tools

        mock_config = MagicMock()
        mock_config.GEMINI_API_KEY = "test-key"
        mock_config.GEMINI_MODEL_FLASH = "gemini-2.0-flash"

        mock_episode = MagicMock()
        mock_episode.title = "Test Episode"

        mock_repo = MagicMock()
        mock_repo.get_podcast.return_value = None
        mock_repo.get_episode.return_value = mock_episode

        mock_file_search = MagicMock()
        mock_file_search.create_or_get_store.return_value = "stores/test-store"

        with patch('src.agents.chat_tools.genai.Client'):
            tools = create_chat_tools(
                config=mock_config,
                repository=mock_repo,
                file_search_manager=mock_file_search,
                user_id="user-123",
                episode_id="episode-789",
            )

        assert len(tools) > 0
        # Verify episode was fetched
        mock_repo.get_episode.assert_called_once_with("episode-789")

    def test_create_chat_tools_handles_failed_podcast_fetch(self):
        """Test that failed podcast fetch doesn't break tool creation."""
        from src.agents.chat_tools import create_chat_tools

        mock_config = MagicMock()
        mock_config.GEMINI_API_KEY = "test-key"
        mock_config.GEMINI_MODEL_FLASH = "gemini-2.0-flash"

        mock_repo = MagicMock()
        mock_repo.get_podcast.side_effect = Exception("DB error")
        mock_repo.get_episode.return_value = None

        mock_file_search = MagicMock()
        mock_file_search.create_or_get_store.return_value = "stores/test-store"

        with patch('src.agents.chat_tools.genai.Client'):
            # Should not raise
            tools = create_chat_tools(
                config=mock_config,
                repository=mock_repo,
                file_search_manager=mock_file_search,
                user_id="user-123",
                podcast_id="podcast-456",
            )

        assert len(tools) > 0

    def test_create_chat_tools_handles_failed_store_fetch(self):
        """Test that failed store fetch doesn't break tool creation."""
        from src.agents.chat_tools import create_chat_tools

        mock_config = MagicMock()
        mock_config.GEMINI_API_KEY = "test-key"
        mock_config.GEMINI_MODEL_FLASH = "gemini-2.0-flash"

        mock_repo = MagicMock()
        mock_repo.get_podcast.return_value = None
        mock_repo.get_episode.return_value = None

        mock_file_search = MagicMock()
        mock_file_search.create_or_get_store.side_effect = Exception("API error")

        with patch('src.agents.chat_tools.genai.Client'):
            # Should not raise
            tools = create_chat_tools(
                config=mock_config,
                repository=mock_repo,
                file_search_manager=mock_file_search,
                user_id="user-123",
            )

        assert len(tools) > 0


class TestToolFunctionNames:
    """Tests for verifying tool function names and docstrings."""

    def test_search_transcripts_tool_exists(self):
        """Test that search_transcripts tool is created."""
        from src.agents.chat_tools import create_chat_tools

        mock_config = MagicMock()
        mock_config.GEMINI_API_KEY = "test-key"
        mock_config.GEMINI_MODEL_FLASH = "gemini-2.0-flash"

        mock_repo = MagicMock()
        mock_repo.get_podcast.return_value = None
        mock_repo.get_episode.return_value = None

        mock_file_search = MagicMock()
        mock_file_search.create_or_get_store.return_value = "stores/test-store"

        with patch('src.agents.chat_tools.genai.Client'):
            tools = create_chat_tools(
                config=mock_config,
                repository=mock_repo,
                file_search_manager=mock_file_search,
                user_id="user-123",
            )

        tool_names = [t.__name__ for t in tools]
        assert 'search_transcripts' in tool_names

    def test_search_podcast_descriptions_tool_exists(self):
        """Test that search_podcast_descriptions tool is created."""
        from src.agents.chat_tools import create_chat_tools

        mock_config = MagicMock()
        mock_config.GEMINI_API_KEY = "test-key"
        mock_config.GEMINI_MODEL_FLASH = "gemini-2.0-flash"

        mock_repo = MagicMock()
        mock_repo.get_podcast.return_value = None
        mock_repo.get_episode.return_value = None

        mock_file_search = MagicMock()
        mock_file_search.create_or_get_store.return_value = "stores/test-store"

        with patch('src.agents.chat_tools.genai.Client'):
            tools = create_chat_tools(
                config=mock_config,
                repository=mock_repo,
                file_search_manager=mock_file_search,
                user_id="user-123",
            )

        tool_names = [t.__name__ for t in tools]
        assert 'search_podcast_descriptions' in tool_names

    def test_tools_have_docstrings(self):
        """Test that all tools have docstrings."""
        from src.agents.chat_tools import create_chat_tools

        mock_config = MagicMock()
        mock_config.GEMINI_API_KEY = "test-key"
        mock_config.GEMINI_MODEL_FLASH = "gemini-2.0-flash"

        mock_repo = MagicMock()
        mock_repo.get_podcast.return_value = None
        mock_repo.get_episode.return_value = None

        mock_file_search = MagicMock()
        mock_file_search.create_or_get_store.return_value = "stores/test-store"

        with patch('src.agents.chat_tools.genai.Client'):
            tools = create_chat_tools(
                config=mock_config,
                repository=mock_repo,
                file_search_manager=mock_file_search,
                user_id="user-123",
            )

        for tool in tools:
            assert tool.__doc__ is not None, f"Tool {tool.__name__} missing docstring"
            assert len(tool.__doc__) > 10, f"Tool {tool.__name__} has short docstring"


class TestSearchTranscriptsTool:
    """Tests for the search_transcripts tool function."""

    def test_search_transcripts_no_store(self):
        """Test search_transcripts returns error when store unavailable."""
        from src.agents.chat_tools import create_chat_tools

        mock_config = MagicMock()
        mock_config.GEMINI_API_KEY = "test-key"
        mock_config.GEMINI_MODEL_FLASH = "gemini-2.0-flash"

        mock_repo = MagicMock()
        mock_repo.get_podcast.return_value = None
        mock_repo.get_episode.return_value = None

        mock_file_search = MagicMock()
        mock_file_search.create_or_get_store.side_effect = Exception("Store error")

        with patch('src.agents.chat_tools.genai.Client'):
            tools = create_chat_tools(
                config=mock_config,
                repository=mock_repo,
                file_search_manager=mock_file_search,
                user_id="user-123",
            )

        # Get search_transcripts tool
        search_tool = next(t for t in tools if t.__name__ == 'search_transcripts')

        result = search_tool("test query")

        assert 'error' in result
        assert 'unavailable' in result['response_text'].lower()
        assert result['citations'] == []


class TestSearchPodcastDescriptionsTool:
    """Tests for the search_podcast_descriptions tool function."""

    def test_search_descriptions_no_store(self):
        """Test search_podcast_descriptions returns error when store unavailable."""
        from src.agents.chat_tools import create_chat_tools

        mock_config = MagicMock()
        mock_config.GEMINI_API_KEY = "test-key"
        mock_config.GEMINI_MODEL_FLASH = "gemini-2.0-flash"

        mock_repo = MagicMock()
        mock_repo.get_podcast.return_value = None
        mock_repo.get_episode.return_value = None

        mock_file_search = MagicMock()
        mock_file_search.create_or_get_store.side_effect = Exception("Store error")

        with patch('src.agents.chat_tools.genai.Client'):
            tools = create_chat_tools(
                config=mock_config,
                repository=mock_repo,
                file_search_manager=mock_file_search,
                user_id="user-123",
            )

        # Get search_podcast_descriptions tool
        search_tool = next(t for t in tools if t.__name__ == 'search_podcast_descriptions')

        result = search_tool("test query")

        assert 'error' in result
        assert 'unavailable' in result['response_text'].lower()
        assert result['citations'] == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
