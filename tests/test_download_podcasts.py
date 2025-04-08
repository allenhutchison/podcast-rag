#!/usr/bin/env python
import unittest
import os
import tempfile
import shutil
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
import feedparser
import sys
import time

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.config import Config
from src.db.database import DatabaseManager, Feed, Episode
from src.download_podcasts import DownloadManager, PodcastEpisode


class TestDownloadManager(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory for testing
        self.temp_dir = tempfile.mkdtemp()
        
        # Create a config with the temporary directory
        self.config = Config()
        self.config.BASE_DIRECTORY = self.temp_dir
        
        # Create a database manager
        self.db_manager = DatabaseManager(self.config)
        
        # Create a download manager
        self.download_manager = DownloadManager(self.config, dry_run=True)
        
        # Sample feed data
        self.sample_feed = Feed(
            id=1,
            title="Test Podcast",
            url="https://example.com/feed.xml",
            last_updated=datetime.now(),
            description="A test podcast",
            language="en",
            image_url="https://example.com/image.jpg"
        )
        
        # Add the sample feed to the database
        self.db_manager.add_feed(self.sample_feed)
        
    def tearDown(self):
        # Clean up the temporary directory
        shutil.rmtree(self.temp_dir)
        
    def create_mock_feed(self, title="Test Podcast", description="A test podcast", language="en", image_url="https://example.com/image.jpg"):
        mock_feed = MagicMock()
        mock_feed.feed = MagicMock()
        mock_feed.feed.title = title
        mock_feed.feed.description = description
        mock_feed.feed.language = language
        mock_feed.feed.image = {"href": image_url}
        mock_feed.feed.get = lambda key, default=None: {
            "description": description,
            "language": language,
            "image": {"href": image_url}
        }.get(key, default)
        return mock_feed
        
    def create_mock_entry(self, title="Test Episode", guid="test-episode-1",
                         description="A test episode", published_date=None,
                         url="https://example.com/episode1.mp3"):
        """Create a mock feed entry"""
        if published_date is None:
            published_date = datetime.now()
            
        entry = MagicMock()
        entry.title = title
        entry.id = guid
        entry.link = url
        entry.published = published_date
        entry.description = description
        entry.enclosures = [MagicMock(length='1000000', type='audio/mpeg')]
        entry.itunes_duration = "30:00"
        return entry
        
    @patch('feedparser.parse')
    def test_parse_feed(self, mock_parse):
        """Test parsing a feed"""
        # Create mock feed
        mock_feed = self.create_mock_feed()
        mock_entry = self.create_mock_entry()
        mock_feed.entries = [mock_entry]
        mock_parse.return_value = mock_feed
        
        # Parse the feed
        episodes = self.download_manager.parse_feed(self.sample_feed)
        
        # Check that the episode was added to the database
        db_episode = self.db_manager.get_episode_by_guid("test-episode-1")
        self.assertIsNotNone(db_episode)
        self.assertEqual(db_episode.title, "Test Episode")
        self.assertEqual(db_episode.url, "https://example.com/episode1.mp3")
        self.assertEqual(db_episode.file_size, 1000000)
        self.assertEqual(db_episode.duration, "30:00")
        self.assertIsNone(db_episode.download_date)
        
        # Check that the stats were updated
        self.assertEqual(self.download_manager.stats["feeds_processed"], 1)
        self.assertEqual(self.download_manager.stats["episodes_found"], 1)
        self.assertEqual(self.download_manager.stats["episodes_added"], 1)
        
    @patch('feedparser.parse')
    def test_parse_feed_update_existing_episode(self, mock_parse):
        """Test updating an existing episode when parsing a feed"""
        # Create an existing episode
        existing_episode = Episode(
            id=1,
            feed_id=1,
            title="Test Episode",
            guid="test-episode-1",
            url="https://example.com/episode1.mp3",
            published_date=datetime.now(),
            description="A test episode",
            duration="00:30:00",
            file_size=1024 * 1024,  # 1 MB
            local_path=None,
            download_date=None
        )
        self.db_manager.add_episode(existing_episode)

        # Create a mock feed with updated episode info
        mock_feed = {
            'entries': [{
                'title': "Updated Test Episode",
                'id': "test-episode-1",  # Same GUID
                'link': "https://example.com/episode1.mp3",
                'published': datetime.now(),
                'description': "Updated description",
                'duration': "00:45:00",  # Updated duration
                'length': str(2 * 1024 * 1024),  # Updated size
            }]
        }

        # Parse the feed
        self.download_manager.parse_feed(mock_feed, feed_id=1)

        # Get the updated episode
        updated_episode = self.db_manager.get_episode_by_id(1)

        # Verify the episode was updated
        self.assertEqual(updated_episode.title, "Updated Test Episode")
        self.assertEqual(updated_episode.description, "Updated description")
        self.assertEqual(updated_episode.duration, "00:45:00")
        self.assertEqual(updated_episode.file_size, 2 * 1024 * 1024)
        
    @patch('feedparser.parse')
    def test_process_feed(self, mock_parse):
        # Reset the stats before this test
        self.download_manager.stats = {
            "feeds_processed": 0,
            "episodes_found": 0,
            "episodes_added": 0,
            "episodes_updated": 0,
            "download_errors": 0
        }
        
        # Create mock feed with multiple entries
        mock_feed = self.create_mock_feed()
        mock_entries = []
        for i in range(10):
            mock_entry = self.create_mock_entry(
                title=f"Test Episode {i}",
                guid=f"episode{i}",
                description=f"A test episode {i}",
                published_date=datetime(2023, 1, 1, 12, 0, 0),
                url=f"https://example.com/episode{i}.mp3"
            )
            mock_entries.append(mock_entry)
        mock_feed.entries = mock_entries
        mock_parse.return_value = mock_feed
        
        # Process the feed with a limit of 5 episodes
        self.download_manager.process_feed(self.sample_feed, limit=5)
        
        # Check that only 5 episodes were added to the database
        episodes = self.db_manager.get_episodes_by_feed(self.sample_feed.id)
        self.assertEqual(len(episodes), 5)
        
        # Check that the stats were updated
        self.assertEqual(self.download_manager.stats["feeds_processed"], 1)
        self.assertEqual(self.download_manager.stats["episodes_found"], 10)
        self.assertEqual(self.download_manager.stats["episodes_added"], 5)
        
    @patch('feedparser.parse')
    def test_process_feed_with_age_filter(self, mock_parse):
        # Reset the stats before this test
        self.download_manager.stats = {
            "feeds_processed": 0,
            "episodes_found": 0,
            "episodes_added": 0,
            "episodes_updated": 0,
            "download_errors": 0
        }
        
        # Create mock feed with entries of different ages
        mock_feed = self.create_mock_feed()
        mock_entries = []
        base_date = datetime.now()
        for i in range(10):
            mock_entry = self.create_mock_entry(
                title=f"Test Episode {i}",
                guid=f"episode{i}",
                description=f"A test episode {i}",
                published_date=base_date - timedelta(days=i*2),
                url=f"https://example.com/episode{i}.mp3"
            )
            mock_entries.append(mock_entry)
        mock_feed.entries = mock_entries
        mock_parse.return_value = mock_feed
        
        # Process the feed with a min_age_days of 5
        self.download_manager.process_feed(self.sample_feed, min_age_days=5)
        
        # Check that only episodes newer than 5 days were added to the database
        episodes = self.db_manager.get_episodes_by_feed(self.sample_feed.id)
        self.assertEqual(len(episodes), 3)  # Episodes 0, 1, 2 (0, 2, 4 days old)
        
        # Check that the stats were updated
        self.assertEqual(self.download_manager.stats["feeds_processed"], 1)
        self.assertEqual(self.download_manager.stats["episodes_found"], 10)
        self.assertEqual(self.download_manager.stats["episodes_added"], 3)
        
    @patch('feedparser.parse')
    def test_process_all_feeds(self, mock_parse):
        # Reset the stats before this test
        self.download_manager.stats = {
            "feeds_processed": 0,
            "episodes_found": 0,
            "episodes_added": 0,
            "episodes_updated": 0,
            "download_errors": 0
        }
        
        # Remove the sample feed from setUp
        self.db_manager.cursor.execute('DELETE FROM feeds')
        self.db_manager.conn.commit()
        
        # Add multiple feeds to the database
        feeds = []
        for i in range(3):
            feed = Feed(
                id=i+1,
                title=f"Test Podcast {i}",
                url=f"https://example.com/feed{i}.xml",
                last_updated=datetime.now(),
                description=f"A test podcast {i}",
                language="en",
                image_url=f"https://example.com/image{i}.jpg"
            )
            self.db_manager.add_feed(feed)
            feeds.append(feed)
        
        # Mock the feedparser.parse function
        def mock_parse_side_effect(url):
            feed_num = url.split('feed')[1].split('.')[0]
            mock_feed = self.create_mock_feed(
                title=f"Test Podcast {feed_num}",
                description=f"A test podcast {feed_num}",
                image_url=f"https://example.com/image{feed_num}.jpg"
            )
            mock_entry = self.create_mock_entry(
                title=f"Test Episode for {url}",
                guid=f"episode{url}",
                description=f"A test episode for {url}",
                published_date=datetime(2023, 1, 1, 12, 0, 0),
                url=f"https://example.com/episode{url}.mp3"
            )
            mock_feed.entries = [mock_entry]
            return mock_feed
        
        mock_parse.side_effect = mock_parse_side_effect
        
        # Process all feeds
        self.download_manager.process_all_feeds()
        
        # Check that all feeds were processed
        self.assertEqual(self.download_manager.stats["feeds_processed"], 3)
        self.assertEqual(self.download_manager.stats["episodes_found"], 3)
        self.assertEqual(self.download_manager.stats["episodes_added"], 3)
        
        # Check that all episodes were added to the database
        for feed in feeds:
            episodes = self.db_manager.get_episodes_by_feed(feed.id)
            self.assertEqual(len(episodes), 1)
            self.assertEqual(episodes[0].title, f"Test Episode for {feed.url}")


if __name__ == '__main__':
    unittest.main() 