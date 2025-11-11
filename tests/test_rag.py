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
