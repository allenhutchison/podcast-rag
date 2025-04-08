#!/usr/bin/env python
import logging
import argparse
from typing import List

from argparse_shared import add_log_level_argument, get_base_parser
from config import Config
from db.database import DatabaseManager, JobType, Episode


def init_workflow_for_episode(db_manager: DatabaseManager, episode: Episode):
    """Initialize the workflow for an episode"""
    # Check if the episode has any jobs
    existing_jobs = db_manager.get_jobs_for_episode(episode.id)
    
    if existing_jobs:
        logging.info(f"Episode {episode.title} already has {len(existing_jobs)} jobs, skipping")
        return
        
    # Create download job
    download_job_id = db_manager.create_job(episode.id, JobType.DOWNLOAD)
    logging.info(f"Created download job {download_job_id} for episode {episode.title}")
    
    # If the episode is already downloaded, mark the download job as completed
    if episode.local_path and episode.download_date:
        db_manager.start_job(download_job_id)
        db_manager.complete_job(download_job_id)
        logging.info(f"Marked download job {download_job_id} as completed for episode {episode.title}")
        
        # Create metadata extraction job
        metadata_job_id = db_manager.create_job(episode.id, JobType.METADATA_EXTRACTION)
        logging.info(f"Created metadata extraction job {metadata_job_id} for episode {episode.title}")
        
        # Create transcription job
        transcription_job_id = db_manager.create_job(episode.id, JobType.TRANSCRIPTION)
        logging.info(f"Created transcription job {transcription_job_id} for episode {episode.title}")
        
        # Create embeddings creation job
        embeddings_job_id = db_manager.create_job(episode.id, JobType.EMBEDDINGS_CREATION)
        logging.info(f"Created embeddings creation job {embeddings_job_id} for episode {episode.title}")
        
        # Create MP3 deletion job
        mp3_deletion_job_id = db_manager.create_job(episode.id, JobType.MP3_DELETION)
        logging.info(f"Created MP3 deletion job {mp3_deletion_job_id} for episode {episode.title}")


def init_workflow_for_all_episodes(db_manager: DatabaseManager):
    """Initialize the workflow for all episodes"""
    # Get all episodes
    episodes = db_manager.get_all_episodes()
    logging.info(f"Found {len(episodes)} episodes")
    
    # Initialize workflow for each episode
    for episode in episodes:
        init_workflow_for_episode(db_manager, episode)


if __name__ == "__main__":
    parser = get_base_parser()
    add_log_level_argument(parser)
    parser.description = "Initialize workflow for podcast episodes"
    args = parser.parse_args()

    # Set up logging
    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler("init_workflow.log"),
            logging.StreamHandler()
        ],
    )
    
    # Set the log level for the httpx and httpcore libraries
    if args.log_level == "INFO":
        logging.getLogger('httpx').setLevel("WARNING")
        logging.getLogger('httpcore').setLevel("WARNING")

    # Load configuration
    config = Config(env_file=args.env_file)
    
    # Initialize database manager
    db_manager = DatabaseManager(config=config)
    
    try:
        # Initialize workflow for all episodes
        init_workflow_for_all_episodes(db_manager)
        logging.info("Workflow initialization completed successfully")
    finally:
        db_manager.close() 