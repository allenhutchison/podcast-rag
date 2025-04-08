import pytest
import sys
import os
from unittest.mock import patch
import tempfile
import unittest
from unittest.mock import MagicMock
from datetime import datetime
import json

# Add the src directory to sys.path so that Config and TranscriptionManager can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.config import Config
from src.transcribe_podcasts import TranscriptionManager
from src.file_manager import FileManager
from src.db.database import (
    DatabaseManager, Feed, Episode, Job, JobType, JobStatus
)

# Test for process_directory with a dry-run mode (mocked transcription process)
def test_process_podcasts_dry_run(monkeypatch, tmpdir):
    config = Config()
    config.BASE_DIRECTORY = str(tmpdir.mkdir("podcasts"))

    # Mock the BASE_DIRECTORY and whisper path in the TranscriptionManager
    mock_podcast_dir = os.path.join(config.BASE_DIRECTORY, "SamplePodcast")
    os.makedirs(mock_podcast_dir)
    mock_podcast_file = os.path.join(mock_podcast_dir, "episode1.mp3")
    with open(mock_podcast_file, 'w') as f:
        f.write("Fake MP3 content")

    transcription_manager = TranscriptionManager(config=config, dry_run=True)

    # Instantiate TranscriptionManager
    manager = FileManager(config=config, dry_run=True, transcription_manager=transcription_manager)
    
    # Mock start_transcription method so that it doesn't actually run
    with patch.object(transcription_manager, 'handle_transcription') as mock_transcribe:
        manager.process_directory()

        # Check that start_transcription was not called in dry-run mode
        mock_transcribe.assert_called()

class TestFileManager(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory for testing
        self.temp_dir = tempfile.mkdtemp()
        self.config = Config()
        self.config.BASE_DIRECTORY = self.temp_dir
        
        # Initialize the database manager
        self.db_manager = DatabaseManager(self.config)
        
        # Create a test feed
        self.test_feed = Feed(
            id=0,  # Will be set by the database
            title="Test Podcast",
            url="https://example.com/feed.xml",
            last_updated=datetime.now(),
            description="A test podcast feed",
            language="en",
            image_url="https://example.com/image.jpg"
        )
        self.feed_id = self.db_manager.add_feed(self.test_feed)
        self.test_feed.id = self.feed_id
        
        # Create a test episode
        self.test_episode = Episode(
            id=0,  # Will be set by the database
            feed_id=self.feed_id,
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
        self.episode_id = self.db_manager.add_episode(self.test_episode)
        self.test_episode.id = self.episode_id
        
        # Initialize the file manager
        self.file_manager = FileManager(self.config, self.db_manager)
        
    def tearDown(self):
        # Close the database connection
        self.db_manager.close()
        
        # Remove the temporary directory and its contents
        for root, dirs, files in os.walk(self.temp_dir, topdown=False):
            for name in files:
                try:
                    os.remove(os.path.join(root, name))
                except PermissionError:
                    pass
            for name in dirs:
                try:
                    os.rmdir(os.path.join(root, name))
                except PermissionError:
                    pass
        try:
            os.rmdir(self.temp_dir)
        except PermissionError:
            pass
        
    def test_download_episode(self):
        """Test downloading an episode"""
        # Mock the HTTP response
        with patch('requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.content = b"fake mp3 content"
            mock_response.status_code = 200
            mock_get.return_value = mock_response
            
            # Download the episode
            result = self.file_manager.download_episode(self.test_episode)
            
            # Verify the download was successful
            self.assertTrue(result)
            
            # Verify the episode was updated
            updated_episode = self.db_manager.get_episode_by_id(self.episode_id)
            self.assertIsNotNone(updated_episode.local_path)
            self.assertIsNotNone(updated_episode.download_date)
            
            # Verify the file was created
            self.assertTrue(os.path.exists(updated_episode.local_path))
            
    def test_download_episode_dry_run(self):
        """Test downloading an episode in dry run mode"""
        # Set dry run mode
        self.file_manager.dry_run = True
        
        # Mock the HTTP response
        with patch('requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.content = b"fake mp3 content"
            mock_response.status_code = 200
            mock_get.return_value = mock_response
            
            # Download the episode
            result = self.file_manager.download_episode(self.test_episode)
            
            # Reset dry run mode
            self.file_manager.dry_run = False
            
            # Verify the download was successful
            self.assertTrue(result)
            
            # Verify the episode was not updated
            updated_episode = self.db_manager.get_episode_by_id(self.episode_id)
            self.assertIsNone(updated_episode.local_path)
            self.assertIsNone(updated_episode.download_date)
            
            # Verify no file was created
            episode_dir = os.path.join(self.temp_dir, str(self.test_feed.id))
            self.assertFalse(os.path.exists(episode_dir))
            
    def test_download_episode_failure(self):
        """Test handling download failures"""
        # Mock the HTTP response to simulate a failure
        with patch('requests.get') as mock_get:
            mock_get.side_effect = Exception("Download failed")
            
            # Attempt to download the episode
            result = self.file_manager.download_episode(self.test_episode)
            
            # Verify the download failed
            self.assertFalse(result)
            
            # Verify the episode was not updated
            updated_episode = self.db_manager.get_episode_by_id(self.episode_id)
            self.assertIsNone(updated_episode.local_path)
            self.assertIsNone(updated_episode.download_date)
            
    def test_extract_metadata(self):
        """Test extracting metadata from an episode"""
        # Create a test MP3 file
        test_mp3_path = os.path.join(self.temp_dir, str(self.test_feed.id), "test.mp3")
        os.makedirs(os.path.dirname(test_mp3_path), exist_ok=True)
        with open(test_mp3_path, "wb") as f:
            f.write(b"fake mp3 content")
            
        # Update the episode with the test file path
        self.test_episode.local_path = test_mp3_path
        self.db_manager.update_episode(self.test_episode)
        
        # Mock the mutagen library
        with patch('mutagen.File') as mock_mutagen:
            # Set up the mock to return test metadata
            mock_file = MagicMock()
            mock_file.tags = {
                'TIT2': ['Test Episode'],
                'TLEN': ['1800000'],  # 30 minutes in milliseconds
                'TRCK': ['1'],
                'TPE1': ['Test Artist'],
                'TALB': ['Test Album']
            }
            mock_mutagen.return_value = mock_file
            
            # Extract metadata
            metadata = self.file_manager.extract_metadata(self.test_episode)
            
            # Verify the metadata was extracted
            self.assertIsNotNone(metadata)
            self.assertEqual(metadata.get('title'), 'Test Episode')
            self.assertEqual(metadata.get('duration'), '00:30:00')
            
    def test_extract_metadata_no_file(self):
        """Test extracting metadata when file doesn't exist"""
        # Set a non-existent file path
        self.test_episode.local_path = os.path.join(self.temp_dir, "nonexistent.mp3")
        
        # Attempt to extract metadata
        metadata = self.file_manager.extract_metadata(self.test_episode)
        
        # Verify no metadata was extracted
        self.assertIsNone(metadata)
        
    def test_transcribe_episode(self):
        """Test transcribing an episode"""
        # Create a test MP3 file
        test_mp3_path = os.path.join(self.temp_dir, str(self.test_feed.id), "test.mp3")
        os.makedirs(os.path.dirname(test_mp3_path), exist_ok=True)
        with open(test_mp3_path, "wb") as f:
            f.write(b"fake mp3 content")
            
        # Update the episode with the test file path
        self.test_episode.local_path = test_mp3_path
        self.db_manager.update_episode(self.test_episode)
        
        # Create transcriptions directory
        transcription_dir = os.path.join(self.temp_dir, "transcriptions")
        os.makedirs(transcription_dir, exist_ok=True)
        
        # Mock the Whisper model
        with patch('whisper.load_model') as mock_whisper:
            mock_model = MagicMock()
            mock_model.transcribe.return_value = {
                'text': 'This is a test transcription.',
                'segments': [
                    {'text': 'This is a test transcription.', 'start': 0, 'end': 2}
                ]
            }
            mock_whisper.return_value = mock_model
            
            # Transcribe the episode
            result = self.file_manager.transcribe_episode(self.test_episode)
            
            # Verify the transcription was successful
            self.assertTrue(result)
            
            # Verify the transcription file was created
            transcription_path = os.path.join(
                transcription_dir, f"{self.test_episode.guid}.json"
            )
            self.assertTrue(os.path.exists(transcription_path))
            
            # Verify the transcription content
            with open(transcription_path, 'r') as f:
                transcription_data = json.load(f)
                self.assertEqual(transcription_data['text'], 'This is a test transcription.')
                
    def test_delete_mp3(self):
        """Test deleting an MP3 file"""
        # Create a test MP3 file
        test_mp3_path = os.path.join(self.temp_dir, str(self.test_feed.id), "test.mp3")
        os.makedirs(os.path.dirname(test_mp3_path), exist_ok=True)
        with open(test_mp3_path, "wb") as f:
            f.write(b"fake mp3 content")
            
        # Update the episode with the test file path
        self.test_episode.local_path = test_mp3_path
        self.db_manager.update_episode(self.test_episode)
        
        # Delete the MP3 file
        result = self.file_manager.delete_mp3(self.test_episode)
        
        # Verify the deletion was successful
        self.assertTrue(result)
        
        # Verify the file was deleted
        self.assertFalse(os.path.exists(test_mp3_path))
        
        # Verify the episode was updated
        updated_episode = self.db_manager.get_episode_by_id(self.episode_id)
        self.assertIsNone(updated_episode.local_path)
        
    def test_delete_mp3_dry_run(self):
        """Test deleting an MP3 file in dry run mode"""
        # Create a test MP3 file
        test_mp3_path = os.path.join(self.temp_dir, str(self.test_feed.id), "test.mp3")
        os.makedirs(os.path.dirname(test_mp3_path), exist_ok=True)
        with open(test_mp3_path, "wb") as f:
            f.write(b"fake mp3 content")
            
        # Update the episode with the test file path
        self.test_episode.local_path = test_mp3_path
        self.db_manager.update_episode(self.test_episode)
        
        # Set dry run mode
        self.file_manager.dry_run = True
        
        # Delete the MP3 file
        result = self.file_manager.delete_mp3(self.test_episode)
        
        # Reset dry run mode
        self.file_manager.dry_run = False
        
        # Verify the deletion was successful (in dry run mode)
        self.assertTrue(result)
        
        # Verify the file was not deleted
        self.assertTrue(os.path.exists(test_mp3_path))
        
        # Verify the episode was not updated
        updated_episode = self.db_manager.get_episode_by_id(self.episode_id)
        self.assertEqual(updated_episode.local_path, test_mp3_path)


if __name__ == "__main__":
    unittest.main()
