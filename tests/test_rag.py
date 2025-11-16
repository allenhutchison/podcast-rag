"""
Tests for RAG Manager with Gemini File Search.

These tests use dry_run mode and mocking to avoid requiring API credentials.
"""

import pytest
import sys
import os
from unittest.mock import patch, MagicMock

# Add the src directory to sys.path
sys.path.append(os.path.join(os.path.dirname(__file__), '../src'))

from config import Config
from rag import RagManager


def test_rag_manager_init():
    """Test that RagManager initializes properly."""
    config = Config()
    config.GEMINI_API_KEY = "test_api_key"

    with patch('rag.genai.Client'):
        manager = RagManager(config=config, dry_run=True)

        assert manager.config == config
        assert manager.dry_run is True
        assert manager.print_results is True


def test_rag_query_dry_run():
    """Test RAG query in dry_run mode."""
    config = Config()
    config.GEMINI_API_KEY = "test_api_key"

    with patch('rag.genai.Client'):
        manager = RagManager(config=config, dry_run=True)

        result = manager.query("What is this about?")

        # In dry_run mode, should return a simple response
        assert result == "This is a dry run response."


def test_rag_get_citations_empty():
    """Test getting citations when there are none."""
    config = Config()
    config.GEMINI_API_KEY = "test_api_key"

    with patch('rag.genai.Client'):
        manager = RagManager(config=config, dry_run=False)

        citations = manager.get_citations()

        # Should return empty list when no query has been made
        assert citations == []


def test_rag_search_snippets_no_query():
    """Test search_snippets when no query has been made."""
    config = Config()
    config.GEMINI_API_KEY = "test_api_key"

    with patch('rag.genai.Client'):
        manager = RagManager(config=config, dry_run=False)

        snippets_json = manager.search_snippets()

        # Should return empty JSON array
        assert snippets_json == "[]"


def test_rag_with_mocked_response():
    """Test RAG query with a mocked Gemini response."""
    config = Config()
    config.GEMINI_API_KEY = "test_api_key"

    # Create mock response with grounding metadata
    mock_citation = MagicMock()
    mock_citation.file_id = "files/test123"
    mock_citation.chunk_index = 5
    mock_citation.score = 0.95

    mock_grounding = MagicMock()
    mock_grounding.file_search_citations = [mock_citation]

    mock_candidate = MagicMock()
    mock_candidate.grounding_metadata = mock_grounding

    mock_response = MagicMock()
    mock_response.text = "This is a test response."
    mock_response.candidates = [mock_candidate]

    with patch('rag.genai.Client') as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.models.generate_content.return_value = mock_response

        manager = RagManager(config=config, dry_run=False)

        # Ensure store exists
        with patch.object(manager.file_search_manager, 'create_or_get_store',
                         return_value='fileSearchStores/test'):
            result = manager.query("Test query")

            # Should get the response text
            assert result == "This is a test response."

            # Should have grounding metadata
            citations = manager.get_citations()
            assert len(citations) == 1
            assert citations[0]['file_id'] == "files/test123"
            assert citations[0]['chunk_index'] == 5
            assert citations[0]['score'] == 0.95


def test_ensure_store_caching():
    """Test that store name is cached after first call."""
    config = Config()
    config.GEMINI_API_KEY = "test_api_key"

    with patch('rag.genai.Client'):
        manager = RagManager(config=config, dry_run=False)

        with patch.object(manager.file_search_manager, 'create_or_get_store',
                         return_value='fileSearchStores/test') as mock_create:
            # First call should create store
            store1 = manager._ensure_store()
            assert mock_create.call_count == 1

            # Second call should use cached value
            store2 = manager._ensure_store()
            assert mock_create.call_count == 1  # Not called again

            assert store1 == store2 == 'fileSearchStores/test'


def test_add_inline_citations_no_metadata():
    """Test inline citation when no grounding metadata exists."""
    config = Config()
    config.GEMINI_API_KEY = "test_api_key"

    with patch('rag.genai.Client'):
        manager = RagManager(config=config, dry_run=False)
        manager.last_grounding_metadata = None

        text = "This is a test response."
        result = manager._add_inline_citations(text)

        # Should return text unchanged when no metadata
        assert result == text


def test_add_inline_citations_with_supports():
    """Test inline citation insertion with grounding supports."""
    config = Config()
    config.GEMINI_API_KEY = "test_api_key"

    with patch('rag.genai.Client'):
        manager = RagManager(config=config, dry_run=False)

        # Create mock grounding supports
        mock_segment = MagicMock()
        mock_segment.start_index = 0
        mock_segment.end_index = 10

        mock_support = MagicMock()
        mock_support.segment = mock_segment
        mock_support.grounding_chunk_indices = [0, 1]

        mock_grounding = MagicMock()
        mock_grounding.grounding_supports = [mock_support]

        manager.last_grounding_metadata = mock_grounding

        text = "This is a test response."
        result = manager._add_inline_citations(text)

        # Should add citation markers
        assert '[1]' in result or '[2]' in result


def test_add_inline_citations_invalid_position():
    """Test inline citation with invalid position (should skip with warning)."""
    config = Config()
    config.GEMINI_API_KEY = "test_api_key"

    with patch('rag.genai.Client'):
        manager = RagManager(config=config, dry_run=False)

        # Create mock with invalid position
        mock_segment = MagicMock()
        mock_segment.start_index = 0
        mock_segment.end_index = 1000  # Beyond text length

        mock_support = MagicMock()
        mock_support.segment = mock_segment
        mock_support.grounding_chunk_indices = [0]

        mock_grounding = MagicMock()
        mock_grounding.grounding_supports = [mock_support]

        manager.last_grounding_metadata = mock_grounding

        text = "Short text."

        # Should handle invalid position gracefully
        with patch('rag.logging.warning') as mock_warning:
            result = manager._add_inline_citations(text)

            # Should log warning about invalid position
            mock_warning.assert_called_once()
            assert 'Invalid citation position' in str(mock_warning.call_args)


def test_add_inline_citations_negative_position():
    """Test inline citation with negative position (should skip with warning)."""
    config = Config()
    config.GEMINI_API_KEY = "test_api_key"

    with patch('rag.genai.Client'):
        manager = RagManager(config=config, dry_run=False)

        # Create mock with negative position
        mock_segment = MagicMock()
        mock_segment.start_index = 0
        mock_segment.end_index = -5  # Negative position

        mock_support = MagicMock()
        mock_support.segment = mock_segment
        mock_support.grounding_chunk_indices = [0]

        mock_grounding = MagicMock()
        mock_grounding.grounding_supports = [mock_support]

        manager.last_grounding_metadata = mock_grounding

        text = "Test text."

        # Should handle negative position gracefully
        with patch('rag.logging.warning') as mock_warning:
            result = manager._add_inline_citations(text)

            # Should log warning
            mock_warning.assert_called_once()


def test_get_citations_with_new_format():
    """Test getting citations with new grounding_chunks format."""
    config = Config()
    config.GEMINI_API_KEY = "test_api_key"

    with patch('rag.genai.Client'):
        manager = RagManager(config=config, dry_run=False)

        # Create mock grounding chunk
        mock_context = MagicMock()
        mock_context.title = "test_episode.txt"
        mock_context.text = "This is a test excerpt from the source document."
        mock_context.uri = None

        mock_chunk = MagicMock()
        mock_chunk.retrieved_context = mock_context

        mock_grounding = MagicMock(spec=['grounding_chunks', 'grounding_supports'])
        mock_grounding.grounding_chunks = [mock_chunk]
        mock_grounding.grounding_supports = []

        manager.last_grounding_metadata = mock_grounding

        citations = manager.get_citations()

        assert len(citations) == 1
        assert citations[0]['title'] == "test_episode.txt"
        assert 'text' in citations[0]


def test_get_citations_with_old_format():
    """Test getting citations with old file_search_citations format."""
    config = Config()
    config.GEMINI_API_KEY = "test_api_key"

    with patch('rag.genai.Client'):
        manager = RagManager(config=config, dry_run=False)

        # Create mock file search citation
        mock_citation = MagicMock()
        mock_citation.file_id = "files/test123"
        mock_citation.chunk_index = 5
        mock_citation.score = 0.95

        mock_grounding = MagicMock()
        mock_grounding.file_search_citations = [mock_citation]
        # No grounding_chunks attribute
        del mock_grounding.grounding_chunks

        manager.last_grounding_metadata = mock_grounding

        citations = manager.get_citations()

        assert len(citations) == 1
        assert citations[0]['file_id'] == "files/test123"
        assert citations[0]['chunk_index'] == 5


def test_citation_text_extraction():
    """Test that citation text is properly extracted."""
    config = Config()
    config.GEMINI_API_KEY = "test_api_key"

    with patch('rag.genai.Client'):
        manager = RagManager(config=config, dry_run=False)

        # Create mock with text
        test_text = "This is test text from the source document."
        mock_context = MagicMock()
        mock_context.title = "test.txt"
        mock_context.text = test_text
        mock_context.uri = None

        mock_chunk = MagicMock()
        mock_chunk.retrieved_context = mock_context

        mock_grounding = MagicMock(spec=['grounding_chunks', 'grounding_supports'])
        mock_grounding.grounding_chunks = [mock_chunk]
        mock_grounding.grounding_supports = []

        manager.last_grounding_metadata = mock_grounding

        citations = manager.get_citations()

        assert len(citations) == 1
        # Text should be extracted
        assert citations[0]['text'] == test_text
