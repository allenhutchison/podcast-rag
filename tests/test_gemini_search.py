"""Tests for gemini_search module."""

import pytest
from unittest.mock import Mock, patch, MagicMock
import logging

from src.gemini_search import GeminiSearchManager, VectorDbSearchManager


class TestGeminiSearchManager:
    """Tests for GeminiSearchManager class."""

    @pytest.fixture
    def mock_config(self):
        """Create a mock config."""
        config = Mock()
        config.GEMINI_API_KEY = "test_api_key"
        config.GEMINI_MODEL_FLASH = "gemini-2.0-flash"
        config.GEMINI_FILE_SEARCH_STORE_NAME = "test-store"
        config.validate_file_search_model = Mock()
        return config

    def test_init_dry_run(self, mock_config):
        """Test initialization in dry run mode."""
        with patch("src.gemini_search.genai") as mock_genai, \
             patch("src.gemini_search.GeminiFileSearchManager"):
            manager = GeminiSearchManager(config=mock_config, dry_run=True)

            assert manager.config == mock_config
            assert manager.dry_run is True
            assert manager.store_name is None
            # In dry run mode, validate_file_search_model should not be called
            mock_config.validate_file_search_model.assert_not_called()

    def test_init_validates_model(self, mock_config):
        """Test initialization validates model when not in dry run."""
        with patch("src.gemini_search.genai") as mock_genai, \
             patch("src.gemini_search.GeminiFileSearchManager"):
            manager = GeminiSearchManager(config=mock_config, dry_run=False)

            mock_config.validate_file_search_model.assert_called_once()

    def test_ensure_store_finds_existing(self, mock_config):
        """Test _ensure_store finds existing store."""
        with patch("src.gemini_search.genai") as mock_genai, \
             patch("src.gemini_search.GeminiFileSearchManager"):

            mock_store = Mock()
            mock_store.name = "stores/12345"
            mock_store.display_name = "test-store"

            mock_client = Mock()
            mock_client.file_search_stores.list.return_value = [mock_store]
            mock_genai.Client.return_value = mock_client

            manager = GeminiSearchManager(config=mock_config, dry_run=False)
            store_name = manager._ensure_store()

            assert store_name == "stores/12345"
            assert manager.store_name == "stores/12345"

    def test_ensure_store_creates_new(self, mock_config):
        """Test _ensure_store creates new store when not found."""
        with patch("src.gemini_search.genai") as mock_genai, \
             patch("src.gemini_search.GeminiFileSearchManager"):

            mock_client = Mock()
            mock_client.file_search_stores.list.return_value = []

            new_store = Mock()
            new_store.name = "stores/new-12345"
            mock_client.file_search_stores.create.return_value = new_store

            mock_genai.Client.return_value = mock_client

            manager = GeminiSearchManager(config=mock_config, dry_run=False)
            store_name = manager._ensure_store()

            assert store_name == "stores/new-12345"

    def test_ensure_store_caching(self, mock_config):
        """Test _ensure_store caches the store name."""
        with patch("src.gemini_search.genai") as mock_genai, \
             patch("src.gemini_search.GeminiFileSearchManager"):

            mock_store = Mock()
            mock_store.name = "stores/cached"
            mock_store.display_name = "test-store"

            mock_client = Mock()
            mock_client.file_search_stores.list.return_value = [mock_store]
            mock_genai.Client.return_value = mock_client

            manager = GeminiSearchManager(config=mock_config, dry_run=False)

            # Call twice
            store_name1 = manager._ensure_store()
            store_name2 = manager._ensure_store()

            # list should only be called once due to caching
            assert mock_client.file_search_stores.list.call_count == 1
            assert store_name1 == store_name2

    def test_search_transcriptions_dry_run(self, mock_config):
        """Test search_transcriptions in dry run mode."""
        with patch("src.gemini_search.genai"), \
             patch("src.gemini_search.GeminiFileSearchManager"):

            manager = GeminiSearchManager(config=mock_config, dry_run=True)
            result = manager.search_transcriptions("test query", print_results=False)

            assert result == {
                'documents': [[]],
                'metadatas': [[]]
            }

    def test_search_transcriptions_with_results(self, mock_config):
        """Test search_transcriptions with actual results."""
        with patch("src.gemini_search.genai") as mock_genai, \
             patch("src.gemini_search.GeminiFileSearchManager"):

            # Set up mock response
            mock_citation = Mock()
            mock_citation.file_id = "file123"
            mock_citation.chunk_index = 0
            mock_citation.score = 0.95

            mock_grounding = Mock()
            mock_grounding.file_search_citations = [mock_citation]

            mock_candidate = Mock()
            mock_candidate.grounding_metadata = mock_grounding

            mock_response = Mock()
            mock_response.candidates = [mock_candidate]
            mock_response.text = "Search result text"

            mock_store = Mock()
            mock_store.name = "stores/test"
            mock_store.display_name = "test-store"

            mock_client = Mock()
            mock_client.file_search_stores.list.return_value = [mock_store]
            mock_client.models.generate_content.return_value = mock_response

            mock_genai.Client.return_value = mock_client

            manager = GeminiSearchManager(config=mock_config, dry_run=False)
            result = manager.search_transcriptions("test query", print_results=False)

            assert 'documents' in result
            assert 'metadatas' in result
            assert 'response_text' in result
            assert result['response_text'] == "Search result text"

    def test_search_transcriptions_no_grounding_metadata(self, mock_config):
        """Test search_transcriptions when response has no grounding metadata."""
        with patch("src.gemini_search.genai") as mock_genai, \
             patch("src.gemini_search.GeminiFileSearchManager"):

            mock_candidate = Mock(spec=[])  # No grounding_metadata attribute

            mock_response = Mock()
            mock_response.candidates = [mock_candidate]
            mock_response.text = "Response without grounding"

            mock_store = Mock()
            mock_store.name = "stores/test"
            mock_store.display_name = "test-store"

            mock_client = Mock()
            mock_client.file_search_stores.list.return_value = [mock_store]
            mock_client.models.generate_content.return_value = mock_response

            mock_genai.Client.return_value = mock_client

            manager = GeminiSearchManager(config=mock_config, dry_run=False)
            result = manager.search_transcriptions("test query", print_results=False)

            assert result['documents'] == [[]]
            assert result['metadatas'] == [[]]

    def test_search_transcriptions_exception(self, mock_config):
        """Test search_transcriptions handles exceptions."""
        with patch("src.gemini_search.genai") as mock_genai, \
             patch("src.gemini_search.GeminiFileSearchManager"):

            mock_store = Mock()
            mock_store.name = "stores/test"
            mock_store.display_name = "test-store"

            mock_client = Mock()
            mock_client.file_search_stores.list.return_value = [mock_store]
            mock_client.models.generate_content.side_effect = Exception("API error")

            mock_genai.Client.return_value = mock_client

            manager = GeminiSearchManager(config=mock_config, dry_run=False)

            with pytest.raises(Exception) as exc_info:
                manager.search_transcriptions("test query", print_results=False)

            assert "API error" in str(exc_info.value)

    def test_pretty_print_results(self, mock_config, capsys):
        """Test pretty_print_results output."""
        with patch("src.gemini_search.genai"), \
             patch("src.gemini_search.GeminiFileSearchManager"):

            manager = GeminiSearchManager(config=mock_config, dry_run=True)

            results = {
                'documents': [["Document content here" + "x" * 200]],
                'metadatas': [[{
                    'file_id': 'file123',
                    'chunk_index': 0,
                    'score': 0.85
                }]]
            }

            manager.pretty_print_results(results)

            captured = capsys.readouterr()
            assert "file123" in captured.out
            assert "0.85" in captured.out

    def test_backward_compatibility_alias(self):
        """Test VectorDbSearchManager is an alias for GeminiSearchManager."""
        assert VectorDbSearchManager is GeminiSearchManager

    def test_ensure_store_handles_list_exception(self, mock_config):
        """Test _ensure_store handles exception from list call."""
        with patch("src.gemini_search.genai") as mock_genai, \
             patch("src.gemini_search.GeminiFileSearchManager"):

            mock_client = Mock()
            mock_client.file_search_stores.list.side_effect = Exception("List error")

            new_store = Mock()
            new_store.name = "stores/fallback"
            mock_client.file_search_stores.create.return_value = new_store

            mock_genai.Client.return_value = mock_client

            manager = GeminiSearchManager(config=mock_config, dry_run=False)
            store_name = manager._ensure_store()

            # Should fall back to creating new store
            assert store_name == "stores/fallback"

    def test_ensure_store_create_failure(self, mock_config):
        """Test _ensure_store raises when create fails."""
        with patch("src.gemini_search.genai") as mock_genai, \
             patch("src.gemini_search.GeminiFileSearchManager"):

            mock_client = Mock()
            mock_client.file_search_stores.list.return_value = []
            mock_client.file_search_stores.create.side_effect = Exception("Create error")

            mock_genai.Client.return_value = mock_client

            manager = GeminiSearchManager(config=mock_config, dry_run=False)

            with pytest.raises(Exception) as exc_info:
                manager._ensure_store()

            assert "Create error" in str(exc_info.value)


class TestGeminiSearchMain:
    """Tests for the main function."""

    def test_main_function_exists(self):
        """Test that main function exists."""
        from src.gemini_search import main
        assert callable(main)

    @patch("src.gemini_search.GeminiSearchManager")
    @patch("src.gemini_search.Config")
    def test_main_parses_arguments(self, mock_config_class, mock_manager_class, capsys):
        """Test main function parses command line arguments."""
        mock_config = Mock()
        mock_config_class.return_value = mock_config

        mock_manager = Mock()
        mock_manager.search_transcriptions.return_value = {
            'documents': [[]],
            'metadatas': [[]],
            'response_text': 'Test response'
        }
        mock_manager_class.return_value = mock_manager

        with patch("sys.argv", ["gemini_search", "-q", "test query"]):
            from src.gemini_search import main
            main()

        mock_manager.search_transcriptions.assert_called_once()
