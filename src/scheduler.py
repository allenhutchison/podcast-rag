import logging
import os
import time
from typing import List, Optional

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED
from apscheduler.schedulers.blocking import BlockingScheduler

from src.argparse_shared import add_log_level_argument, get_base_parser
from src.config import Config
from src.db.database import DatabaseManager, JobType, JobStatus, Job, Episode
from src.file_manager import FileManager


def job_listener(event):
    if event.exception:
        logging.error("Job failed: %s", event.exception)
    else:
        logging.info("Job completed successfully")


class Scheduler:
    """Handles scheduling and processing of podcast processing jobs"""
    
    def __init__(self, config: Config, db_manager: DatabaseManager, file_manager: FileManager, transcription_manager=None):
        self.config = config
        self.db_manager = db_manager
        self.file_manager = file_manager
        self.transcription_manager = transcription_manager
        
    def process_job(self, job, dry_run=False):
        """Process a single job of any type"""
        if dry_run:
            # Don't actually process the job in dry run mode
            return
        
        try:
            # Mark job as in progress
            job.status = JobStatus.IN_PROGRESS
            job.started_at = time.time()
            
            # Get the episode for this job
            episode_id = job.episode_id
            
            # Process the job based on its type
            if job.job_type == JobType.DOWNLOAD:
                success = self.file_manager.download_episode(episode_id)
            elif job.job_type == JobType.METADATA_EXTRACTION:
                success = self.file_manager.extract_metadata(episode_id)
            elif job.job_type == JobType.TRANSCRIPTION:
                if self.transcription_manager:
                    success = self.transcription_manager.transcribe_episode(episode_id)
                else:
                    raise Exception("TranscriptionManager not initialized")
            elif job.job_type == JobType.EMBEDDINGS_CREATION:
                success = self.file_manager.create_embeddings(episode_id)
            elif job.job_type == JobType.DELETE_MP3:
                success = self.file_manager.delete_mp3(episode_id)
            else:
                raise Exception(f"Unknown job type: {job.job_type}")
                
            # Update job status
            if success:
                job.status = JobStatus.COMPLETED
                job.completed_at = time.time()
            else:
                job.status = JobStatus.FAILED
                job.error_message = "Operation returned False"
                
        except Exception as e:
            # Mark job as failed
            job.status = JobStatus.FAILED
            job.error_message = str(e)
            logging.error(f"Error processing job {job.id}: {e}")
        
    def process_download_jobs(self):
        """Process pending download jobs"""
        pending_jobs = self.db_manager.get_pending_jobs(job_type=JobType.DOWNLOAD)
        logging.info(f"Found {len(pending_jobs)} pending download jobs")
        
        for job in pending_jobs:
            try:
                # Get the episode for this job
                episode = self.db_manager.get_episode_by_id(job.episode_id)
                if not episode:
                    logging.error(f"Episode {job.episode_id} not found for job {job.id}")
                    self.db_manager.fail_job(job.id, "Episode not found")
                    continue
                    
                # Mark job as in progress
                self.db_manager.start_job(job.id)
                
                # Download the episode
                success = self.file_manager.download_episode(episode)
                
                if success:
                    # Update episode with download information
                    episode.download_date = time.time()
                    self.db_manager.update_episode(episode)
                    
                    # Mark job as completed
                    self.db_manager.complete_job(job.id)
                    logging.info(f"Successfully downloaded episode {episode.title}")
                else:
                    # Mark job as failed
                    self.db_manager.fail_job(job.id, "Download failed")
                    logging.error(f"Failed to download episode {episode.title}")
                    
            except Exception as e:
                logging.error(f"Error processing download job {job.id}: {e}")
                self.db_manager.fail_job(job.id, str(e))

    def process_metadata_extraction_jobs(self):
        """Process pending metadata extraction jobs"""
        pending_jobs = self.db_manager.get_pending_jobs(job_type=JobType.METADATA_EXTRACTION)
        logging.info(f"Found {len(pending_jobs)} pending metadata extraction jobs")
        
        for job in pending_jobs:
            try:
                # Get the episode for this job
                episode = self.db_manager.get_episode_by_id(job.episode_id)
                if not episode:
                    logging.error(f"Episode {job.episode_id} not found for job {job.id}")
                    self.db_manager.fail_job(job.id, "Episode not found")
                    continue
                    
                # Mark job as in progress
                self.db_manager.start_job(job.id)
                
                # Extract metadata
                metadata = self.file_manager.extract_metadata(episode)
                
                if metadata:
                    # Mark job as completed with metadata result
                    self.db_manager.complete_job(job.id, result_data=str(metadata))
                    logging.info(f"Successfully extracted metadata for episode {episode.title}")
                else:
                    # Mark job as failed
                    self.db_manager.fail_job(job.id, "Metadata extraction failed")
                    logging.error(f"Failed to extract metadata for episode {episode.title}")
                    
            except Exception as e:
                logging.error(f"Error processing metadata extraction job {job.id}: {e}")
                self.db_manager.fail_job(job.id, str(e))

    def process_transcription_jobs(self):
        """Process pending transcription jobs"""
        pending_jobs = self.db_manager.get_pending_jobs(job_type=JobType.TRANSCRIPTION)
        logging.info(f"Found {len(pending_jobs)} pending transcription jobs")
        
        for job in pending_jobs:
            try:
                # Get the episode for this job
                episode = self.db_manager.get_episode_by_id(job.episode_id)
                if not episode:
                    logging.error(f"Episode {job.episode_id} not found for job {job.id}")
                    self.db_manager.fail_job(job.id, "Episode not found")
                    continue
                    
                # Mark job as in progress
                self.db_manager.start_job(job.id)
                
                # Transcribe the episode
                success = self.file_manager.transcribe_episode(episode)
                
                if success:
                    # Mark job as completed
                    self.db_manager.complete_job(job.id)
                    logging.info(f"Successfully transcribed episode {episode.title}")
                else:
                    # Mark job as failed
                    self.db_manager.fail_job(job.id, "Transcription failed")
                    logging.error(f"Failed to transcribe episode {episode.title}")
                    
            except Exception as e:
                logging.error(f"Error processing transcription job {job.id}: {e}")
                self.db_manager.fail_job(job.id, str(e))

    def process_embeddings_jobs(self):
        """Process pending embeddings creation jobs"""
        pending_jobs = self.db_manager.get_pending_jobs(job_type=JobType.EMBEDDINGS)
        logging.info(f"Found {len(pending_jobs)} pending embeddings creation jobs")
        
        for job in pending_jobs:
            try:
                # Get the episode for this job
                episode = self.db_manager.get_episode_by_id(job.episode_id)
                if not episode:
                    logging.error(f"Episode {job.episode_id} not found for job {job.id}")
                    self.db_manager.fail_job(job.id, "Episode not found")
                    continue
                    
                # Mark job as in progress
                self.db_manager.start_job(job.id)
                
                # Create embeddings
                success = self.file_manager.create_embeddings(episode)
                
                if success:
                    # Mark job as completed
                    self.db_manager.complete_job(job.id)
                    logging.info(f"Successfully created embeddings for episode {episode.title}")
                else:
                    # Mark job as failed
                    self.db_manager.fail_job(job.id, "Embeddings creation failed")
                    logging.error(f"Failed to create embeddings for episode {episode.title}")
                    
            except Exception as e:
                logging.error(f"Error processing embeddings job {job.id}: {e}")
                self.db_manager.fail_job(job.id, str(e))

    def process_mp3_deletion_jobs(self):
        """Process pending MP3 deletion jobs"""
        pending_jobs = self.db_manager.get_pending_jobs(job_type=JobType.MP3_DELETION)
        logging.info(f"Found {len(pending_jobs)} pending MP3 deletion jobs")
        
        for job in pending_jobs:
            try:
                # Get the episode for this job
                episode = self.db_manager.get_episode_by_id(job.episode_id)
                if not episode:
                    logging.error(f"Episode {job.episode_id} not found for job {job.id}")
                    self.db_manager.fail_job(job.id, "Episode not found")
                    continue
                    
                # Mark job as in progress
                self.db_manager.start_job(job.id)
                
                # Delete the MP3 file
                success = self.file_manager.delete_mp3(episode)
                
                if success:
                    # Mark job as completed
                    self.db_manager.complete_job(job.id)
                    logging.info(f"Successfully deleted MP3 for episode {episode.title}")
                else:
                    # Mark job as failed
                    self.db_manager.fail_job(job.id, "MP3 deletion failed")
                    logging.error(f"Failed to delete MP3 for episode {episode.title}")
                    
            except Exception as e:
                logging.error(f"Error processing MP3 deletion job {job.id}: {e}")
                self.db_manager.fail_job(job.id, str(e))

    def process_all_jobs(self):
        """Process all pending jobs in the workflow"""
        # Process each job type in sequence
        self.process_download_jobs()
        self.process_metadata_extraction_jobs()
        self.process_transcription_jobs()
        self.process_embeddings_jobs()
        self.process_mp3_deletion_jobs()


def process_all_jobs(env_file=None, dry_run=False):
    """Process all pending jobs in the workflow"""
    config = Config(env_file=env_file)
    db_manager = DatabaseManager(config=config)
    file_manager = FileManager(config=config, dry_run=dry_run)
    scheduler = Scheduler(config, db_manager, file_manager)
    
    try:
        scheduler.process_all_jobs()
    finally:
        db_manager.close()


def run_file_manager(env_file=None, dry_run=False):
    """Run the file manager with the given environment file."""
    config = Config(env_file=env_file)
    file_manager = FileManager(config=config, dry_run=dry_run)
    file_manager.process_directory()


if __name__ == "__main__":
    parser = get_base_parser()
    add_log_level_argument(parser)
    parser.description = "Scheduled podcast transcription."
    args = parser.parse_args()

    # Set up logging
    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler("scheduler.log"), 
        ],
    )
    # Set the log level for the httpx and httpcore libraries
    # because they are super chatty on INFO.
    if args.log_level == "INFO":
        logging.getLogger('httpx').setLevel("WARNING")
        logging.getLogger('httpcore').setLevel("WARNING")

    # Run the job processor once before starting the scheduler
    process_all_jobs(env_file=args.env_file, dry_run=False)

    scheduler = BlockingScheduler()
    scheduler.add_listener(job_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)
    scheduler.add_job(
        process_all_jobs,
        'interval',
        hours=1,
        kwargs={'env_file': args.env_file, 'dry_run': False}
    )

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        print("Scheduler stopped.")
