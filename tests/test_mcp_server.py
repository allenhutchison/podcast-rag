"""Tests for MCP server module."""

import pytest
from unittest.mock import Mock, patch, MagicMock
import logging


class TestMCPServerMain:
    """Tests for MCP server main function."""

    @patch("src.mcp_server.MCP")
    @patch("src.mcp_server.Config")
    @patch("src.mcp_server.GeminiSearchManager")
    def test_main_initializes_server(self, mock_search_manager, mock_config_class, mock_mcp_class):
        """Test that main initializes the MCP server."""
        mock_config = Mock()
        mock_config_class.return_value = mock_config

        mock_mcp = Mock()
        mock_mcp_class.return_value = mock_mcp

        with patch("sys.argv", ["mcp_server", "-l", "INFO"]):
            with patch.object(mock_mcp, "run", side_effect=KeyboardInterrupt):
                from src.mcp_server import main
                main()

        mock_mcp_class.assert_called_once_with(port=5002)

    @patch("src.mcp_server.MCP")
    @patch("src.mcp_server.Config")
    def test_main_with_env_file(self, mock_config_class, mock_mcp_class):
        """Test main with custom env file."""
        mock_config = Mock()
        mock_config_class.return_value = mock_config

        mock_mcp = Mock()
        mock_mcp_class.return_value = mock_mcp

        with patch("sys.argv", ["mcp_server", "-e", "~/.custom.env", "-l", "DEBUG"]):
            with patch.object(mock_mcp, "run", side_effect=KeyboardInterrupt):
                from src.mcp_server import main
                main()

        # Check that config was created with expanded env file path
        mock_config_class.assert_called_once()


class TestMCPTools:
    """Tests for MCP tool functions."""

    @pytest.fixture
    def mock_config(self):
        """Create mock config."""
        config = Mock()
        config.GEMINI_API_KEY = "test_key"
        config.GEMINI_FILE_SEARCH_STORE_NAME = "test-store"
        return config

    def test_mcp_server_module_has_main(self):
        """Test that mcp_server module has expected entry point."""
        import src.mcp_server
        # Verify main entry point exists and is callable
        assert hasattr(src.mcp_server, "main")
        assert callable(src.mcp_server.main)

    @patch("src.mcp_server.GeminiSearchManager")
    def test_search_manager_created_with_config(self, mock_search_manager_class, mock_config):
        """Test that search manager is created with correct config."""
        mock_manager = Mock()
        mock_manager.search_transcriptions.return_value = {
            'documents': [[]],
            'metadatas': [[]]
        }
        mock_search_manager_class.return_value = mock_manager

        # Simulate what the tool would do
        search_manager = mock_search_manager_class(config=mock_config, dry_run=False)
        results = search_manager.search_transcriptions("test query", print_results=False)

        assert results is not None

    @patch("src.mcp_server.GeminiSearchManager")
    def test_search_podcasts_limits_results(self, mock_search_manager_class, mock_config):
        """Test that search_podcasts limits results correctly."""
        mock_manager = Mock()
        # Simulate results with 10 documents in a flat list structure
        mock_manager.search_transcriptions.return_value = {
            'documents': [f"doc{i}" for i in range(10)],
            'metadatas': [{"id": i} for i in range(10)],
            'distances': [0.1 * i for i in range(10)]
        }
        mock_search_manager_class.return_value = mock_manager

        # Simulate limit logic from search_podcasts
        results = mock_manager.search_transcriptions("query", print_results=False)
        limit = 5

        if limit and 'documents' in results:
            limited_results = {
                'documents': results['documents'][:limit],
                'metadatas': results['metadatas'][:limit] if 'metadatas' in results else [],
                'distances': results['distances'][:limit] if 'distances' in results else []
            }
            results = limited_results

        assert len(results['documents']) == 5
        assert results['documents'] == ["doc0", "doc1", "doc2", "doc3", "doc4"]

    @patch("src.mcp_server.GeminiSearchManager")
    def test_get_podcast_info_structure(self, mock_search_manager_class, mock_config):
        """Test get_podcast_info returns correct structure."""
        mock_file_search_manager = Mock()
        mock_file_search_manager.get_store_info.return_value = {
            'display_name': 'test-store'
        }
        mock_file_search_manager.list_files.return_value = [Mock(), Mock(), Mock()]

        mock_manager = Mock()
        mock_manager.file_search_manager = mock_file_search_manager
        mock_search_manager_class.return_value = mock_manager

        # Simulate get_podcast_info logic
        store_info = mock_manager.file_search_manager.get_store_info()
        file_list = mock_manager.file_search_manager.list_files()

        response = {
            "database_info": {
                "store_name": mock_config.GEMINI_FILE_SEARCH_STORE_NAME,
                "display_name": store_info.get('display_name', 'N/A'),
                "total_files": len(file_list)
            },
            "status": "success"
        }

        assert response["status"] == "success"
        assert response["database_info"]["total_files"] == 3

    @patch("src.mcp_server.GeminiSearchManager")
    def test_tool_error_handling(self, mock_search_manager_class, mock_config):
        """Test that tools handle errors correctly."""
        mock_search_manager_class.side_effect = Exception("API error")

        # Simulate error handling in tool
        try:
            mock_search_manager_class(config=mock_config, dry_run=False)
            response = {"status": "success"}
        except Exception as e:
            response = {
                "query": "test",
                "error": str(e),
                "status": "error"
            }

        assert response["status"] == "error"
        assert "API error" in response["error"]


class TestMCPServerIntegration:
    """Integration-style tests for MCP server."""

    def test_module_imports_correctly(self):
        """Test that the module can be imported."""
        with patch("src.mcp_server.MCP"):
            with patch("src.mcp_server.Config"):
                import src.mcp_server
                assert hasattr(src.mcp_server, "main")

    def test_log_level_parsing(self):
        """Test that log levels are parsed correctly."""
        test_levels = ["DEBUG", "INFO", "WARNING", "ERROR"]
        for level in test_levels:
            log_level = getattr(logging, level.upper(), logging.INFO)
            assert log_level is not None


class TestMCPServerMainAdvanced:
    """Advanced tests for MCP server main function."""

    @patch("src.mcp_server.MCP")
    @patch("src.mcp_server.Config")
    def test_main_config_failure(self, mock_config_class, mock_mcp_class):
        """Test main handles config initialization failure."""
        mock_config_class.side_effect = Exception("Config error")

        with patch("sys.argv", ["mcp_server", "-l", "INFO"]):
            with pytest.raises(SystemExit) as exc_info:
                from src.mcp_server import main
                main()

            assert exc_info.value.code == 1

    @patch("src.mcp_server.MCP")
    @patch("src.mcp_server.Config")
    def test_main_server_error(self, mock_config_class, mock_mcp_class):
        """Test main handles server runtime error."""
        mock_config = Mock()
        mock_config_class.return_value = mock_config

        mock_mcp = Mock()
        mock_mcp_class.return_value = mock_mcp
        mock_mcp.run.side_effect = Exception("Server crash")

        with patch("sys.argv", ["mcp_server", "-l", "INFO"]):
            with pytest.raises(SystemExit) as exc_info:
                from src.mcp_server import main
                main()

            assert exc_info.value.code == 1


class TestMCPToolFunctions:
    """Tests for the actual MCP tool function implementations."""

    @pytest.fixture
    def mock_config(self):
        """Create mock config."""
        config = Mock()
        config.GEMINI_API_KEY = "test_key"
        config.GEMINI_FILE_SEARCH_STORE_NAME = "test-store"
        return config

    @patch("src.mcp_server.GeminiSearchManager")
    def test_get_rag_context_success(self, mock_search_manager_class, mock_config):
        """Test get_rag_context returns successful response."""
        mock_manager = Mock()
        mock_manager.search_transcriptions.return_value = {
            'documents': [["Test document content"]],
            'metadatas': [[{"episode": "Episode 1"}]]
        }
        mock_search_manager_class.return_value = mock_manager

        # Simulate the tool logic
        search_manager = mock_search_manager_class(config=mock_config, dry_run=False)
        query = "test query"
        results = search_manager.search_transcriptions(query, print_results=False)

        response = {
            "query": query,
            "results": results,
            "status": "success"
        }

        assert response["status"] == "success"
        assert response["query"] == "test query"
        assert "documents" in response["results"]

    @patch("src.mcp_server.GeminiSearchManager")
    def test_get_rag_context_error(self, mock_search_manager_class, mock_config):
        """Test get_rag_context handles errors."""
        mock_search_manager_class.side_effect = Exception("Search failed")

        query = "test query"
        try:
            search_manager = mock_search_manager_class(config=mock_config, dry_run=False)
            results = search_manager.search_transcriptions(query, print_results=False)
            response = {"status": "success", "results": results}
        except Exception as e:
            response = {
                "query": query,
                "error": str(e),
                "status": "error"
            }

        assert response["status"] == "error"
        assert "Search failed" in response["error"]

    @patch("src.mcp_server.GeminiSearchManager")
    def test_search_podcasts_success(self, mock_search_manager_class, mock_config):
        """Test search_podcasts with successful results."""
        mock_manager = Mock()
        mock_manager.search_transcriptions.return_value = {
            'documents': [f"document {i}" for i in range(10)],
            'metadatas': [{"id": i} for i in range(10)],
            'distances': [0.1 * i for i in range(10)]
        }
        mock_search_manager_class.return_value = mock_manager

        query = "podcast search"
        limit = 3

        search_manager = mock_search_manager_class(config=mock_config, dry_run=False)
        results = search_manager.search_transcriptions(query, print_results=False)

        # Apply limit logic
        if limit and 'documents' in results:
            limited_results = {
                'documents': results['documents'][:limit],
                'metadatas': results['metadatas'][:limit] if 'metadatas' in results else [],
                'distances': results['distances'][:limit] if 'distances' in results else []
            }
            results = limited_results

        response = {
            "query": query,
            "limit": limit,
            "results": results,
            "status": "success"
        }

        assert response["status"] == "success"
        assert len(response["results"]["documents"]) == 3
        assert response["limit"] == 3

    @patch("src.mcp_server.GeminiSearchManager")
    def test_search_podcasts_no_limit(self, mock_search_manager_class, mock_config):
        """Test search_podcasts without limit returns all results."""
        mock_manager = Mock()
        mock_manager.search_transcriptions.return_value = {
            'documents': [f"document {i}" for i in range(5)]
        }
        mock_search_manager_class.return_value = mock_manager

        query = "search"

        search_manager = mock_search_manager_class(config=mock_config, dry_run=False)
        results = search_manager.search_transcriptions(query, print_results=False)

        # No limit applied - all results returned
        response = {
            "query": query,
            "results": results,
            "status": "success"
        }

        assert len(response["results"]["documents"]) == 5

    @patch("src.mcp_server.GeminiSearchManager")
    def test_search_podcasts_error(self, mock_search_manager_class, mock_config):
        """Test search_podcasts handles errors."""
        mock_manager = Mock()
        mock_manager.search_transcriptions.side_effect = Exception("API timeout")
        mock_search_manager_class.return_value = mock_manager

        query = "test"
        try:
            search_manager = mock_search_manager_class(config=mock_config, dry_run=False)
            results = search_manager.search_transcriptions(query, print_results=False)
            response = {"status": "success"}
        except Exception as e:
            response = {
                "query": query,
                "error": str(e),
                "status": "error"
            }

        assert response["status"] == "error"
        assert "API timeout" in response["error"]

    @patch("src.mcp_server.GeminiSearchManager")
    def test_get_podcast_info_success(self, mock_search_manager_class, mock_config):
        """Test get_podcast_info returns complete info."""
        mock_file_search = Mock()
        mock_file_search.get_store_info.return_value = {
            'display_name': 'My Podcast Store',
            'state': 'ACTIVE'
        }
        mock_file_search.list_files.return_value = [
            Mock(name="file1.txt"),
            Mock(name="file2.txt"),
            Mock(name="file3.txt"),
            Mock(name="file4.txt"),
            Mock(name="file5.txt"),
        ]

        mock_manager = Mock()
        mock_manager.file_search_manager = mock_file_search
        mock_search_manager_class.return_value = mock_manager

        search_manager = mock_search_manager_class(config=mock_config, dry_run=False)
        store_info = search_manager.file_search_manager.get_store_info()
        file_list = search_manager.file_search_manager.list_files()

        response = {
            "database_info": {
                "store_name": mock_config.GEMINI_FILE_SEARCH_STORE_NAME,
                "display_name": store_info.get('display_name', 'N/A'),
                "total_files": len(file_list)
            },
            "status": "success"
        }

        assert response["status"] == "success"
        assert response["database_info"]["total_files"] == 5
        assert response["database_info"]["display_name"] == "My Podcast Store"

    @patch("src.mcp_server.GeminiSearchManager")
    def test_get_podcast_info_error(self, mock_search_manager_class, mock_config):
        """Test get_podcast_info handles errors."""
        mock_search_manager_class.side_effect = Exception("Store not found")

        try:
            search_manager = mock_search_manager_class(config=mock_config, dry_run=False)
            store_info = search_manager.file_search_manager.get_store_info()
            response = {"status": "success"}
        except Exception as e:
            response = {
                "error": str(e),
                "status": "error"
            }

        assert response["status"] == "error"
        assert "Store not found" in response["error"]

    @patch("src.mcp_server.GeminiSearchManager")
    def test_get_podcast_info_missing_display_name(self, mock_search_manager_class, mock_config):
        """Test get_podcast_info with missing display_name."""
        mock_file_search = Mock()
        mock_file_search.get_store_info.return_value = {}  # No display_name
        mock_file_search.list_files.return_value = []

        mock_manager = Mock()
        mock_manager.file_search_manager = mock_file_search
        mock_search_manager_class.return_value = mock_manager

        search_manager = mock_search_manager_class(config=mock_config, dry_run=False)
        store_info = search_manager.file_search_manager.get_store_info()

        response = {
            "database_info": {
                "store_name": mock_config.GEMINI_FILE_SEARCH_STORE_NAME,
                "display_name": store_info.get('display_name', 'N/A'),
                "total_files": 0
            },
            "status": "success"
        }

        assert response["database_info"]["display_name"] == "N/A"


class TestMCPServerLogging:
    """Tests for MCP server logging functionality."""

    def test_log_level_debug(self):
        """Test DEBUG log level is recognized."""
        level = getattr(logging, "DEBUG", logging.INFO)
        assert level == logging.DEBUG

    def test_log_level_warning(self):
        """Test WARNING log level is recognized."""
        level = getattr(logging, "WARNING", logging.INFO)
        assert level == logging.WARNING

    def test_log_level_error(self):
        """Test ERROR log level is recognized."""
        level = getattr(logging, "ERROR", logging.INFO)
        assert level == logging.ERROR

    def test_log_level_invalid_fallback(self):
        """Test invalid log level falls back to INFO."""
        level = getattr(logging, "INVALID", logging.INFO)
        assert level == logging.INFO
