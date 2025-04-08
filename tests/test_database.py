import os
import tempfile
import unittest
from datetime import datetime, timedelta

from src.config import Config
from src.db.database import (
    DatabaseManager, Feed, Episode, Job, JobType, JobStatus
)


class TestDatabase(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory for the test database
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
        
    def tearDown(self):
        # Close the database connection
        self.db_manager.close()
        
        # Remove the temporary directory
        for file in os.listdir(self.temp_dir):
            os.remove(os.path.join(self.temp_dir, file))
        os.rmdir(self.temp_dir)
        
    def test_create_job(self):
        """Test creating a job"""
        job_id = self.db_manager.create_job(self.episode_id, JobType.DOWNLOAD)
        self.assertIsNotNone(job_id)
        
        # Get the job and verify its properties
        job = self.db_manager.get_job(job_id)
        self.assertEqual(job.episode_id, self.episode_id)
        self.assertEqual(job.job_type, JobType.DOWNLOAD)
        self.assertEqual(job.status, JobStatus.PENDING)
        self.assertIsNotNone(job.created_at)
        self.assertIsNone(job.started_at)
        self.assertIsNone(job.completed_at)
        self.assertIsNone(job.error_message)
        self.assertIsNone(job.result_data)
        
    def test_start_job(self):
        """Test starting a job"""
        job_id = self.db_manager.create_job(self.episode_id, JobType.DOWNLOAD)
        self.db_manager.start_job(job_id)
        
        # Get the job and verify its properties
        job = self.db_manager.get_job(job_id)
        self.assertEqual(job.status, JobStatus.IN_PROGRESS)
        self.assertIsNotNone(job.started_at)
        
    def test_complete_job(self):
        """Test completing a job"""
        job_id = self.db_manager.create_job(self.episode_id, JobType.DOWNLOAD)
        self.db_manager.start_job(job_id)
        self.db_manager.complete_job(job_id, result_data="Test result")
        
        # Get the job and verify its properties
        job = self.db_manager.get_job(job_id)
        self.assertEqual(job.status, JobStatus.COMPLETED)
        self.assertIsNotNone(job.completed_at)
        self.assertEqual(job.result_data, "Test result")
        
    def test_fail_job(self):
        """Test failing a job"""
        job_id = self.db_manager.create_job(self.episode_id, JobType.DOWNLOAD)
        self.db_manager.start_job(job_id)
        self.db_manager.fail_job(job_id, "Test error")
        
        # Get the job and verify its properties
        job = self.db_manager.get_job(job_id)
        self.assertEqual(job.status, JobStatus.FAILED)
        self.assertIsNotNone(job.completed_at)
        self.assertEqual(job.error_message, "Test error")
        
    def test_get_pending_jobs(self):
        """Test getting pending jobs"""
        # Create jobs of different types
        download_job_id = self.db_manager.create_job(self.episode_id, JobType.DOWNLOAD)
        metadata_job_id = self.db_manager.create_job(self.episode_id, JobType.METADATA_EXTRACTION)
        
        # Start one job
        self.db_manager.start_job(download_job_id)
        
        # Get all pending jobs
        pending_jobs = self.db_manager.get_pending_jobs()
        self.assertEqual(len(pending_jobs), 1)
        self.assertEqual(pending_jobs[0].id, metadata_job_id)
        
        # Get pending jobs of a specific type
        pending_download_jobs = self.db_manager.get_pending_jobs(job_type=JobType.DOWNLOAD)
        self.assertEqual(len(pending_download_jobs), 0)
        
        pending_metadata_jobs = self.db_manager.get_pending_jobs(job_type=JobType.METADATA_EXTRACTION)
        self.assertEqual(len(pending_metadata_jobs), 1)
        self.assertEqual(pending_metadata_jobs[0].id, metadata_job_id)
        
    def test_get_jobs_for_episode(self):
        """Test getting jobs for an episode"""
        # Create jobs for the episode
        download_job_id = self.db_manager.create_job(self.episode_id, JobType.DOWNLOAD)
        metadata_job_id = self.db_manager.create_job(self.episode_id, JobType.METADATA_EXTRACTION)
        
        # Create another episode and job
        another_episode = Episode(
            id=0,
            feed_id=self.feed_id,
            title="Another Episode",
            guid="test-episode-2",
            url="https://example.com/episode2.mp3",
            published_date=datetime.now(),
            description="Another test episode",
            duration="00:30:00",
            file_size=1024 * 1024,
            local_path=None,
            download_date=None
        )
        another_episode_id = self.db_manager.add_episode(another_episode)
        another_job_id = self.db_manager.create_job(another_episode_id, JobType.DOWNLOAD)
        
        # Get jobs for the first episode
        jobs = self.db_manager.get_jobs_for_episode(self.episode_id)
        self.assertEqual(len(jobs), 2)
        job_ids = [job.id for job in jobs]
        self.assertIn(download_job_id, job_ids)
        self.assertIn(metadata_job_id, job_ids)
        self.assertNotIn(another_job_id, job_ids)
        
    def test_get_downloaded_episodes(self):
        """Test getting downloaded episodes"""
        # Create a download job and mark it as completed
        job_id = self.db_manager.create_job(self.episode_id, JobType.DOWNLOAD)
        self.db_manager.start_job(job_id)
        self.db_manager.complete_job(job_id)
        
        # Get downloaded episodes
        downloaded_episodes = self.db_manager.get_downloaded_episodes()
        self.assertEqual(len(downloaded_episodes), 1)
        self.assertEqual(downloaded_episodes[0].id, self.episode_id)
        
        # Create another episode with a failed download job
        another_episode = Episode(
            id=0,
            feed_id=self.feed_id,
            title="Another Episode",
            guid="test-episode-2",
            url="https://example.com/episode2.mp3",
            published_date=datetime.now(),
            description="Another test episode",
            duration="00:30:00",
            file_size=1024 * 1024,
            local_path=None,
            download_date=None
        )
        another_episode_id = self.db_manager.add_episode(another_episode)
        another_job_id = self.db_manager.create_job(another_episode_id, JobType.DOWNLOAD)
        self.db_manager.start_job(another_job_id)
        self.db_manager.fail_job(another_job_id, "Download failed")
        
        # Get downloaded episodes again
        downloaded_episodes = self.db_manager.get_downloaded_episodes()
        self.assertEqual(len(downloaded_episodes), 1)
        self.assertEqual(downloaded_episodes[0].id, self.episode_id)
        
    def test_workflow_sequence(self):
        """Test the complete workflow sequence for an episode"""
        # Create download job
        download_job_id = self.db_manager.create_job(self.episode_id, JobType.DOWNLOAD)
        
        # Start and complete download job
        self.db_manager.start_job(download_job_id)
        self.db_manager.complete_job(download_job_id)
        
        # Create metadata extraction job
        metadata_job_id = self.db_manager.create_job(self.episode_id, JobType.METADATA_EXTRACTION)
        
        # Start and complete metadata extraction job
        self.db_manager.start_job(metadata_job_id)
        self.db_manager.complete_job(metadata_job_id, result_data="Test metadata")
        
        # Create transcription job
        transcription_job_id = self.db_manager.create_job(self.episode_id, JobType.TRANSCRIPTION)
        
        # Start and complete transcription job
        self.db_manager.start_job(transcription_job_id)
        self.db_manager.complete_job(transcription_job_id)
        
        # Create embeddings creation job
        embeddings_job_id = self.db_manager.create_job(self.episode_id, JobType.EMBEDDINGS_CREATION)
        
        # Start and complete embeddings creation job
        self.db_manager.start_job(embeddings_job_id)
        self.db_manager.complete_job(embeddings_job_id)
        
        # Create MP3 deletion job
        mp3_deletion_job_id = self.db_manager.create_job(self.episode_id, JobType.MP3_DELETION)
        
        # Start and complete MP3 deletion job
        self.db_manager.start_job(mp3_deletion_job_id)
        self.db_manager.complete_job(mp3_deletion_job_id)
        
        # Get all jobs for the episode
        jobs = self.db_manager.get_jobs_for_episode(self.episode_id)
        self.assertEqual(len(jobs), 5)
        
        # Verify job types and statuses
        job_types = [job.job_type for job in jobs]
        job_statuses = [job.status for job in jobs]
        
        self.assertIn(JobType.DOWNLOAD, job_types)
        self.assertIn(JobType.METADATA_EXTRACTION, job_types)
        self.assertIn(JobType.TRANSCRIPTION, job_types)
        self.assertIn(JobType.EMBEDDINGS_CREATION, job_types)
        self.assertIn(JobType.MP3_DELETION, job_types)
        
        self.assertEqual(job_statuses.count(JobStatus.COMPLETED), 5)


if __name__ == "__main__":
    unittest.main() 