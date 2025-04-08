import os
import sys
import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime
import time

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import directly from src to avoid circular imports
from src.scheduler import Scheduler

# Create mock classes for testing
class MockConfig:
    def __init__(self):
        self.BASE_DIRECTORY = "/tmp"

class MockJobType:
    DOWNLOAD = "download"
    METADATA_EXTRACTION = "metadata_extraction"
    TRANSCRIPTION = "transcription"
    EMBEDDINGS_CREATION = "embeddings_creation"
    DELETE_MP3 = "delete_mp3"

class MockJobStatus:
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"

class MockJob:
    def __init__(self, id, episode_id, job_type, status, created_at, started_at=None, completed_at=None, error_message=None, result_data=None):
        self.id = id
        self.episode_id = episode_id
        self.job_type = job_type
        self.status = status
        self.created_at = created_at
        self.started_at = started_at
        self.completed_at = completed_at
        self.error_message = error_message
        self.result_data = result_data

class MockDatabaseManager:
    def __init__(self, db_path=None):
        pass
        
    def close(self):
        pass
        
    def get_episode_by_id(self, episode_id):
        return MagicMock(id=episode_id)
        
    def get_job_by_id(self, job_id):
        return MagicMock(id=job_id)

class MockFileManager:
    def __init__(self, config=None, db_manager=None, dry_run=False):
        self.config = config
        self.db_manager = db_manager
        self.dry_run = dry_run
        
    def download_episode(self, episode_id):
        return True
        
    def extract_metadata(self, episode_id):
        return True
        
    def create_embeddings(self, episode_id):
        return True
        
    def delete_mp3(self, episode_id):
        return True

class MockTranscriptionManager:
    def __init__(self, config=None, dry_run=False):
        self.config = config
        self.dry_run = dry_run
        
    def transcribe_episode(self, episode_id):
        return True

class TestScheduler(unittest.TestCase):
    """Test the Scheduler class functionality"""

    @patch('src.db.database.DatabaseManager')
    @patch('src.file_manager.FileManager')
    @patch('src.transcribe_podcasts.TranscriptionManager')
    @patch('src.config.Config')
    def setUp(self, mock_config, mock_transcription_mgr, mock_file_mgr, mock_db_mgr):
        """Set up test fixtures"""
        self.mock_config = mock_config
        self.mock_db_manager = mock_db_mgr.return_value
        self.mock_file_manager = mock_file_mgr.return_value
        self.mock_transcription_manager = mock_transcription_mgr.return_value
        
        # Create the scheduler with mocked dependencies
        self.scheduler = Scheduler(
            self.mock_config,
            self.mock_db_manager,
            self.mock_file_manager,
            self.mock_transcription_manager
        )

    def tearDown(self):
        """Clean up after tests"""
        pass

    @patch('src.scheduler.JobType')
    @patch('src.scheduler.JobStatus')
    def test_process_download_job(self, mock_job_status, mock_job_type):
        """Test processing a download job"""
        # Set up mock job type and status 
        mock_job_type.DOWNLOAD = "download"
        mock_job_status.PENDING = "pending"
        mock_job_status.IN_PROGRESS = "in_progress"
        mock_job_status.COMPLETED = "completed"
        
        # Create a test job
        mock_job = MagicMock()
        mock_job.id = 1
        mock_job.episode_id = 2
        mock_job.job_type = mock_job_type.DOWNLOAD
        mock_job.status = mock_job_status.PENDING
        
        # Configure mock database manager
        self.mock_db_manager.get_pending_jobs.return_value = [mock_job]
        self.mock_db_manager.get_episode_by_id.return_value = MagicMock(id=2)
        
        # Configure mock file manager
        self.mock_file_manager.download_episode.return_value = True
        
        # Call the method under test
        with patch('src.scheduler.time.time', return_value=12345):
            self.scheduler.process_download_jobs()
            
        # Verify the correct methods were called
        self.mock_db_manager.get_pending_jobs.assert_called_once_with(job_type=mock_job_type.DOWNLOAD)
        self.mock_db_manager.start_job.assert_called_once()
        self.mock_db_manager.complete_job.assert_called_once()
        
    @patch('src.scheduler.JobType')
    @patch('src.scheduler.JobStatus')
    def test_process_metadata_extraction_job(self, mock_job_status, mock_job_type):
        """Test processing a metadata extraction job"""
        # Set up mock job type and status
        mock_job_type.METADATA_EXTRACTION = "metadata_extraction"
        mock_job_status.PENDING = "pending"
        mock_job_status.IN_PROGRESS = "in_progress"
        mock_job_status.COMPLETED = "completed"
        
        # Create a test job
        mock_job = MagicMock()
        mock_job.id = 1
        mock_job.episode_id = 2
        mock_job.job_type = mock_job_type.METADATA_EXTRACTION
        mock_job.status = mock_job_status.PENDING
        
        # Configure mock database manager
        self.mock_db_manager.get_pending_jobs.return_value = [mock_job]
        self.mock_db_manager.get_episode_by_id.return_value = MagicMock(id=2)
        
        # Configure mock file manager
        self.mock_file_manager.extract_metadata.return_value = {"title": "Test"}
        
        # Call the method under test
        self.scheduler.process_metadata_extraction_jobs()
        
        # Verify the correct methods were called
        self.mock_db_manager.get_pending_jobs.assert_called_once_with(job_type=mock_job_type.METADATA_EXTRACTION)
        self.mock_db_manager.start_job.assert_called_once()
        self.mock_db_manager.complete_job.assert_called_once()
        
    @patch('src.scheduler.JobType')
    @patch('src.scheduler.JobStatus')
    def test_process_transcription_job(self, mock_job_status, mock_job_type):
        """Test processing a transcription job"""
        # Set up mock job type and status
        mock_job_type.TRANSCRIPTION = "transcription"
        mock_job_status.PENDING = "pending"
        mock_job_status.IN_PROGRESS = "in_progress"
        mock_job_status.COMPLETED = "completed"
        
        # Create a test job
        mock_job = MagicMock()
        mock_job.id = 1
        mock_job.episode_id = 2
        mock_job.job_type = mock_job_type.TRANSCRIPTION
        mock_job.status = mock_job_status.PENDING
        
        # Configure mock database manager
        self.mock_db_manager.get_pending_jobs.return_value = [mock_job]
        self.mock_db_manager.get_episode_by_id.return_value = MagicMock(id=2)
        
        # Configure mock file manager - assuming transcribe_episode is on file_manager in the actual code
        self.mock_file_manager.transcribe_episode.return_value = True
        
        # Call the method under test
        self.scheduler.process_transcription_jobs()
        
        # Verify the correct methods were called
        self.mock_db_manager.get_pending_jobs.assert_called_once_with(job_type=mock_job_type.TRANSCRIPTION)
        self.mock_db_manager.start_job.assert_called_once()
        self.mock_db_manager.complete_job.assert_called_once()
        
    @patch('src.scheduler.JobType')
    @patch('src.scheduler.JobStatus')
    def test_process_embeddings_job(self, mock_job_status, mock_job_type):
        """Test processing an embeddings job"""
        # Set up mock job type and status
        mock_job_type.EMBEDDINGS = "embeddings"
        mock_job_status.PENDING = "pending"
        mock_job_status.IN_PROGRESS = "in_progress"
        mock_job_status.COMPLETED = "completed"
        
        # Create a test job
        mock_job = MagicMock()
        mock_job.id = 1
        mock_job.episode_id = 2
        mock_job.job_type = mock_job_type.EMBEDDINGS
        mock_job.status = mock_job_status.PENDING
        
        # Configure mock database manager
        self.mock_db_manager.get_pending_jobs.return_value = [mock_job]
        self.mock_db_manager.get_episode_by_id.return_value = MagicMock(id=2)
        
        # Configure mock file manager
        self.mock_file_manager.create_embeddings.return_value = True
        
        # Call the method under test
        self.scheduler.process_embeddings_jobs()
        
        # Verify the correct methods were called
        self.mock_db_manager.get_pending_jobs.assert_called_once_with(job_type=mock_job_type.EMBEDDINGS)
        self.mock_db_manager.start_job.assert_called_once()
        self.mock_db_manager.complete_job.assert_called_once()
        
    @patch('src.scheduler.JobType')
    @patch('src.scheduler.JobStatus')
    def test_process_mp3_deletion_job(self, mock_job_status, mock_job_type):
        """Test processing an MP3 deletion job"""
        # Set up mock job type and status
        mock_job_type.MP3_DELETION = "mp3_deletion"
        mock_job_status.PENDING = "pending"
        mock_job_status.IN_PROGRESS = "in_progress"
        mock_job_status.COMPLETED = "completed"
        
        # Create a test job
        mock_job = MagicMock()
        mock_job.id = 1
        mock_job.episode_id = 2
        mock_job.job_type = mock_job_type.MP3_DELETION
        mock_job.status = mock_job_status.PENDING
        
        # Configure mock database manager
        self.mock_db_manager.get_pending_jobs.return_value = [mock_job]
        self.mock_db_manager.get_episode_by_id.return_value = MagicMock(id=2)
        
        # Configure mock file manager
        self.mock_file_manager.delete_mp3.return_value = True
        
        # Call the method under test
        self.scheduler.process_mp3_deletion_jobs()
        
        # Verify the correct methods were called
        self.mock_db_manager.get_pending_jobs.assert_called_once_with(job_type=mock_job_type.MP3_DELETION)
        self.mock_db_manager.start_job.assert_called_once()
        self.mock_db_manager.complete_job.assert_called_once()
        
    @patch('src.scheduler.JobType')
    def test_process_all_jobs(self, mock_job_type):
        """Test processing all jobs"""
        # Set up mock job types
        mock_job_type.DOWNLOAD = "download"
        mock_job_type.METADATA_EXTRACTION = "metadata_extraction"
        mock_job_type.TRANSCRIPTION = "transcription"
        mock_job_type.EMBEDDINGS = "embeddings"
        mock_job_type.MP3_DELETION = "mp3_deletion"
        
        # Mock the individual job processing methods
        self.scheduler.process_download_jobs = MagicMock()
        self.scheduler.process_metadata_extraction_jobs = MagicMock()
        self.scheduler.process_transcription_jobs = MagicMock()
        self.scheduler.process_embeddings_jobs = MagicMock()
        self.scheduler.process_mp3_deletion_jobs = MagicMock()
        
        # Call the method under test
        self.scheduler.process_all_jobs()
        
        # Verify all job processing methods were called
        self.scheduler.process_download_jobs.assert_called_once()
        self.scheduler.process_metadata_extraction_jobs.assert_called_once()
        self.scheduler.process_transcription_jobs.assert_called_once() 
        self.scheduler.process_embeddings_jobs.assert_called_once()
        self.scheduler.process_mp3_deletion_jobs.assert_called_once()
        
    @patch('src.scheduler.JobType')
    @patch('src.scheduler.JobStatus')
    def test_job_failure(self, mock_job_status, mock_job_type):
        """Test handling of job failures"""
        # Set up mock job type and status
        mock_job_type.DOWNLOAD = "download"
        mock_job_status.PENDING = "pending"
        mock_job_status.IN_PROGRESS = "in_progress"
        mock_job_status.FAILED = "failed"
        
        # Create a test job
        mock_job = MagicMock()
        mock_job.id = 1
        mock_job.episode_id = 2
        mock_job.job_type = mock_job_type.DOWNLOAD
        mock_job.status = mock_job_status.PENDING
        
        # Configure mock database manager
        self.mock_db_manager.get_pending_jobs.return_value = [mock_job]
        self.mock_db_manager.get_episode_by_id.return_value = MagicMock(id=2)
        
        # Configure mock file manager to simulate failure
        self.mock_file_manager.download_episode.return_value = False
        
        # Call the method under test
        self.scheduler.process_download_jobs()
        
        # Verify failure was handled correctly
        self.mock_db_manager.start_job.assert_called_once()
        self.mock_db_manager.fail_job.assert_called_once()
        self.mock_db_manager.complete_job.assert_not_called()


if __name__ == "__main__":
    unittest.main() 