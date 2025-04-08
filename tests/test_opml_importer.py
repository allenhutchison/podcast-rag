#!/usr/bin/env python
import os
import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch, mock_open

from src.config import Config
from src.db import Feed, DatabaseManager
from src.opml_importer import OPMLImporter


@pytest.fixture
def mock_config():
    """Create a mock config with a test database path"""
    config = MagicMock(spec=Config)
    config.BASE_DIRECTORY = "./test_data"
    return config


@pytest.fixture
def sample_opml_content():
    """Sample OPML content for testing"""
    return '''<?xml version="1.0" encoding="UTF-8"?>
<opml version="1.0">
    <head>
        <title>My Podcasts</title>
    </head>
    <body>
        <outline text="Tech News Today" type="rss" xmlUrl="https://example.com/tech-news" />
        <outline text="Science Friday" type="rss" xmlUrl="https://example.com/science-friday" />
        <outline text="Le Journal de la Science" type="rss" xmlUrl="https://example.com/journal-science" />
    </body>
</opml>'''


def test_parse_opml(mock_config, sample_opml_content):
    """Test parsing OPML content"""
    # Create a temporary OPML file
    with patch("builtins.open", mock_open(read_data=sample_opml_content)):
        importer = OPMLImporter(mock_config, dry_run=True)
        feeds = importer.parse_opml("test.opml")
        
        # Verify the parsed feeds
        assert len(feeds) == 3
        assert feeds[0]["title"] == "Tech News Today"
        assert feeds[0]["url"] == "https://example.com/tech-news"
        assert feeds[1]["title"] == "Science Friday"
        assert feeds[2]["title"] == "Le Journal de la Science"


def test_import_feeds_new(mock_config, sample_opml_content):
    """Test importing new feeds from OPML"""
    # Mock the database manager
    with patch('src.opml_importer.DatabaseManager') as mock_db_manager, \
         patch("builtins.open", mock_open(read_data=sample_opml_content)):
        
        # Set up the mock
        mock_db = MagicMock()
        mock_db.get_feed_by_url.return_value = None  # No existing feeds
        mock_db.add_feed.return_value = 1  # Return feed ID
        mock_db_manager.return_value = mock_db
        
        # Create importer and import feeds
        importer = OPMLImporter(mock_config, dry_run=False)
        count = importer.import_feeds("test.opml")
        
        # Verify the results
        assert count == 3
        assert importer.stats["feeds_found"] == 3
        assert importer.stats["feeds_added"] == 3
        assert importer.stats["feeds_updated"] == 0
        
        # Verify database calls
        assert mock_db.add_feed.call_count == 3
        assert mock_db.update_feed.call_count == 0


def test_import_feeds_existing(mock_config, sample_opml_content):
    """Test importing feeds that already exist in the database"""
    # Create an existing feed
    existing_feed = Feed(
        id=1,
        title="Tech News Today",
        url="https://example.com/tech-news",
        last_updated=datetime.now(),
        description="Old description",
        language="en",
        image_url=None
    )
    
    # Mock the database manager
    with patch('src.opml_importer.DatabaseManager') as mock_db_manager, \
         patch("builtins.open", mock_open(read_data=sample_opml_content)):
        
        # Set up the mock
        mock_db = MagicMock()
        mock_db.get_feed_by_url.return_value = existing_feed
        mock_db_manager.return_value = mock_db
        
        # Create importer and import feeds
        importer = OPMLImporter(mock_config, dry_run=False)
        count = importer.import_feeds("test.opml")
        
        # Verify the results
        assert count == 3
        assert importer.stats["feeds_found"] == 3
        assert importer.stats["feeds_added"] == 0
        assert importer.stats["feeds_updated"] == 3
        
        # Verify database calls
        assert mock_db.add_feed.call_count == 0
        assert mock_db.update_feed.call_count == 3


def test_import_feeds_dry_run(mock_config, sample_opml_content):
    """Test importing feeds in dry run mode"""
    # Mock the database manager
    with patch('src.opml_importer.DatabaseManager') as mock_db_manager, \
         patch("builtins.open", mock_open(read_data=sample_opml_content)):
        
        # Set up the mock
        mock_db = MagicMock()
        mock_db.get_feed_by_url.return_value = None
        mock_db_manager.return_value = mock_db
        
        # Create importer and import feeds
        importer = OPMLImporter(mock_config, dry_run=True)
        count = importer.import_feeds("test.opml")
        
        # Verify the results
        assert count == 3
        assert importer.stats["feeds_found"] == 3
        assert importer.stats["feeds_added"] == 3
        assert importer.stats["feeds_updated"] == 0
        
        # Verify no database changes were made
        assert mock_db.add_feed.call_count == 0
        assert mock_db.update_feed.call_count == 0


def test_import_feeds_invalid_opml(mock_config):
    """Test importing from an invalid OPML file"""
    # Create invalid OPML content
    invalid_opml = "This is not valid OPML content"
    
    # Mock the database manager
    with patch('src.opml_importer.DatabaseManager') as mock_db_manager, \
         patch("builtins.open", mock_open(read_data=invalid_opml)):
        
        # Set up the mock
        mock_db = MagicMock()
        mock_db_manager.return_value = mock_db
        
        # Create importer and import feeds
        importer = OPMLImporter(mock_config, dry_run=False)
        count = importer.import_feeds("test.opml")
        
        # Verify the results
        assert count == 0
        assert importer.stats["feeds_found"] == 0
        assert importer.stats["import_errors"] == 1 