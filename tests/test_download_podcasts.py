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
        
    def create_mock_entry(self, title, guid, description, published_date, duration="30:00", url="https://example.com/episode.mp3", file_size="1000000"):
        mock_entry = MagicMock()
        mock_entry.title = title
        mock_entry.id = guid
        mock_entry.description = description
        mock_entry.published_parsed = published_date.timetuple()[:9]
        mock_entry.itunes_duration = duration
        
        mock_link = MagicMock()
        mock_link.type = "audio/mpeg"
        mock_link.rel = "enclosure"
        mock_link.href = url
        mock_link.length = file_size
        mock_link.get = lambda key, default=None: {
            "type": "audio/mpeg",
            "href": url,
            "length": file_size
        }.get(key, default)
        
        mock_entry.links = [mock_link]
        return mock_entry
        
    @patch('feedparser.parse')
    def test_parse_feed(self, mock_parse):
        # Create mock feed with one entry
        mock_feed = self.create_mock_feed()
        mock_entry = self.create_mock_entry(
            title="Test Episode",
            guid="episode1",
            description="A test episode",
            published_date=datetime(2023, 1, 1, 12, 0, 0),
            url="https://example.com/episode1.mp3"
        )
        mock_feed.entries = [mock_entry]
        mock_parse.return_value = mock_feed
        
        # Parse the feed
        episodes = self.download_manager.parse_feed(self.sample_feed)
        
        # Check that the feed was updated
        updated_feed = self.db_manager.get_feed_by_url(self.sample_feed.url)
        self.assertEqual(updated_feed.title, "Test Podcast")
        
        # Check that the episode was added to the database
        db_episode = self.db_manager.get_episode_by_guid("episode1")
        self.assertIsNotNone(db_episode)
        self.assertEqual(db_episode.title, "Test Episode")
        self.assertEqual(db_episode.url, "https://example.com/episode1.mp3")
        self.assertEqual(db_episode.file_size, 1000000)
        self.assertEqual(db_episode.duration, "30:00")
        
        # Check that the episode was returned
        self.assertEqual(len(episodes), 1)
        self.assertEqual(episodes[0].title, "Test Episode")
        self.assertEqual(episodes[0].url, "https://example.com/episode1.mp3")
        self.assertEqual(episodes[0].guid, "episode1")
        self.assertEqual(episodes[0].file_size, 1000000)
        self.assertEqual(episodes[0].duration, "30:00")
        
        # Check that the stats were updated
        self.assertEqual(self.download_manager.stats["feeds_processed"], 1)
        self.assertEqual(self.download_manager.stats["episodes_found"], 1)
        self.assertEqual(self.download_manager.stats["episodes_added"], 1)
        
    @patch('feedparser.parse')
    def test_parse_feed_update_existing_episode(self, mock_parse):
        # Add an existing episode to the database
        existing_episode = Episode(
            id=1,
            feed_id=self.sample_feed.id,
            title="Old Title",
            guid="episode1",
            url="https://example.com/old.mp3",
            published_date=datetime.now() - timedelta(days=1),
            description="Old description",
            duration="15:00",
            file_size=500000,
            local_path=None,
            downloaded=False,
            download_date=None
        )
        self.db_manager.add_episode(existing_episode)
        
        # Create mock feed with updated entry
        mock_feed = self.create_mock_feed()
        mock_entry = self.create_mock_entry(
            title="Test Episode",
            guid="episode1",
            description="A test episode",
            published_date=datetime(2023, 1, 1, 12, 0, 0),
            url="https://example.com/episode1.mp3"
        )
        mock_feed.entries = [mock_entry]
        mock_parse.return_value = mock_feed
        
        # Parse the feed
        episodes = self.download_manager.parse_feed(self.sample_feed)
        
        # Check that the episode was updated in the database
        db_episode = self.db_manager.get_episode_by_guid("episode1")
        self.assertIsNotNone(db_episode)
        self.assertEqual(db_episode.title, "Test Episode")
        self.assertEqual(db_episode.url, "https://example.com/episode1.mp3")
        self.assertEqual(db_episode.file_size, 1000000)
        self.assertEqual(db_episode.duration, "30:00")
        
        # Check that the stats were updated
        self.assertEqual(self.download_manager.stats["feeds_processed"], 1)
        self.assertEqual(self.download_manager.stats["episodes_found"], 1)
        self.assertEqual(self.download_manager.stats["episodes_updated"], 1)
        
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