#!/usr/bin/env python
import os
import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch

from src.config import Config
from src.db import Feed, DatabaseManager
from src.list_feeds import list_feeds


@pytest.fixture
def mock_config():
    """Create a mock config with a test database path"""
    config = MagicMock(spec=Config)
    config.BASE_DIRECTORY = "./test_data"
    return config


@pytest.fixture
def mock_args():
    """Create mock command line arguments"""
    args = MagicMock()
    args.language = None
    args.has_image = False
    return args


@pytest.fixture
def sample_feeds():
    """Create sample feed data for testing"""
    return [
        Feed(
            id=1,
            title="Tech News Today",
            url="https://example.com/tech-news",
            last_updated=datetime.now(),
            description="Tech news podcast",
            language="en",
            image_url="https://example.com/image.jpg"
        ),
        Feed(
            id=2,
            title="Science Friday",
            url="https://example.com/science-friday",
            last_updated=datetime.now(),
            description="Science podcast",
            language="en",
            image_url=None
        ),
        Feed(
            id=3,
            title="Le Journal de la Science",
            url="https://example.com/journal-science",
            last_updated=datetime.now(),
            description="Science podcast in French",
            language="fr",
            image_url="https://example.com/fr-image.jpg"
        )
    ]


def test_list_feeds_no_filter(mock_config, mock_args, sample_feeds, capsys):
    """Test listing all feeds without filters"""
    # Mock the database manager
    with patch('src.list_feeds.DatabaseManager') as mock_db_manager:
        # Set up the mock
        mock_db = MagicMock()
        mock_db.get_all_feeds.return_value = sample_feeds
        mock_db_manager.return_value = mock_db
        
        # Call the function
        list_feeds(mock_config, mock_args)
        
        # Capture the output
        captured = capsys.readouterr()
        
        # Verify the output contains all feeds
        assert "Tech News Today" in captured.out
        assert "Science Friday" in captured.out
        assert "Le Journal de la Science" in captured.out
        assert "Total feeds: 3" in captured.out
        
        # Verify database was closed
        mock_db.close.assert_called_once()


def test_list_feeds_filter_by_language(mock_config, mock_args, sample_feeds, capsys):
    """Test listing feeds filtered by language"""
    # Set language filter
    mock_args.language = "en"
    
    # Mock the database manager
    with patch('src.list_feeds.DatabaseManager') as mock_db_manager:
        # Set up the mock
        mock_db = MagicMock()
        mock_db.get_all_feeds.return_value = sample_feeds
        mock_db_manager.return_value = mock_db
        
        # Call the function
        list_feeds(mock_config, mock_args)
        
        # Capture the output
        captured = capsys.readouterr()
        
        # Verify only English feeds are shown
        assert "Tech News Today" in captured.out
        assert "Science Friday" in captured.out
        assert "Le Journal de la Science" not in captured.out
        assert "Total feeds: 2" in captured.out


def test_list_feeds_filter_by_image(mock_config, mock_args, sample_feeds, capsys):
    """Test listing feeds filtered by image presence"""
    # Set image filter
    mock_args.has_image = True
    
    # Mock the database manager
    with patch('src.list_feeds.DatabaseManager') as mock_db_manager:
        # Set up the mock
        mock_db = MagicMock()
        mock_db.get_all_feeds.return_value = sample_feeds
        mock_db_manager.return_value = mock_db
        
        # Call the function
        list_feeds(mock_config, mock_args)
        
        # Capture the output
        captured = capsys.readouterr()
        
        # Verify only feeds with images are shown
        assert "Tech News Today" in captured.out
        assert "Science Friday" not in captured.out
        assert "Le Journal de la Science" in captured.out
        assert "Total feeds: 2" in captured.out


def test_list_feeds_no_feeds(mock_config, mock_args, capsys):
    """Test listing feeds when database is empty"""
    # Mock the database manager
    with patch('src.list_feeds.DatabaseManager') as mock_db_manager:
        # Set up the mock
        mock_db = MagicMock()
        mock_db.get_all_feeds.return_value = []
        mock_db_manager.return_value = mock_db
        
        # Call the function
        list_feeds(mock_config, mock_args)
        
        # Capture the output
        captured = capsys.readouterr()
        
        # Verify the output
        assert "No feeds found matching the criteria." in captured.out 