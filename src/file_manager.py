import logging
import os
import requests
import json
import time
from typing import Dict, Optional, Any

from src.argparse_shared import (add_dry_run_argument, add_log_level_argument,
                             add_ai_system_argument, get_base_parser)
from src.config import Config
from src.metadata_extractor import MetadataExtractor
from src.transcribe_podcasts import TranscriptionManager
from src.db.database import DatabaseManager, Job, JobType, JobStatus, Episode
from src.chroma_vectordb import VectorDbManager


class FileManager:
    def __init__(self, config: Config, dry_run=False, ai_system="gemini", skip_vectordb=False):
        self.config = config
        self.dry_run = dry_run
        self.skip_vectordb = skip_vectordb
        self.transcription_manager = TranscriptionManager(config=config, dry_run=dry_run)
        self.metadata_extractor = MetadataExtractor(config=config, dry_run=dry_run, ai_system=ai_system)
        
        # Initialize vector_db_manager only if not skipping vectordb operations
        if not skip_vectordb:
            try:
                self.vector_db_manager = VectorDbManager(config=config, dry_run=dry_run)
            except Exception as e:
                logging.warning(f"Could not initialize VectorDbManager: {e}")
                logging.warning("Vector database operations will be skipped. Use --skip-vectordb to suppress this warning.")
                self.skip_vectordb = True
        
        self.stats = {
            "total_mp3_files": 0,
        }

    def process_podcast(self, podcast_dir):
        '''Process all podcast files in a directory.'''
        for episode_file in os.listdir(podcast_dir):
            episode_path = os.path.join(podcast_dir, episode_file)
            if self.config.is_mp3_file(episode_path):
                self.stats["total_mp3_files"] += 1
                # Handle transcription for MP3 files
                self.transcription_manager.handle_transcription(episode_path)
                # Extract metadata from transcript and MP3
                metadata = self.metadata_extractor.handle_metadata_extraction(episode_path)
                # Handle indexing for transcripts with embedding and metadata
                if not self.skip_vectordb:
                    self.vector_db_manager.handle_indexing(episode_path, metadata=metadata)

    def process_directory(self):
        '''Main function to start processing podcasts.'''
        if not os.path.isdir(self.config.BASE_DIRECTORY):
            logging.error(f"Directory {self.config.BASE_DIRECTORY} does not exist.")
            return

        for podcast_name in os.listdir(self.config.BASE_DIRECTORY):
            podcast_dir = os.path.join(self.config.BASE_DIRECTORY, podcast_name)

            if os.path.isdir(podcast_dir):
                self.process_podcast(podcast_dir)

        self.log_stats()

    def log_stats(self):
        '''Log transcription statistics.'''
        logging.info(f"Total MP3 files processed: {self.stats['total_mp3_files']}")
        self.transcription_manager.log_stats()
        self.metadata_extractor.log_stats()
        if not self.skip_vectordb:
            self.vector_db_manager.log_stats()
            
    # New methods for workflow-based processing
    
    def download_episode(self, episode: Episode) -> bool:
        """Download an episode to the local filesystem"""
        try:
            if self.dry_run:
                logging.info(f"[DRY RUN] Would download episode: {episode.title} from {episode.url}")
                return True
                
            # Create podcast directory if it doesn't exist
            podcast_dir = os.path.join(self.config.BASE_DIRECTORY, f"podcast_{episode.feed_id}")
            os.makedirs(podcast_dir, exist_ok=True)
            
            # Determine the local file path
            file_name = f"{episode.id}_{episode.title.replace(' ', '_')}.mp3"
            local_path = os.path.join(podcast_dir, file_name)
            
            # Download the file
            logging.info(f"Downloading episode: {episode.title} from {episode.url}")
            response = requests.get(episode.url, stream=True)
            response.raise_for_status()
            
            # Save the file
            with open(local_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
                    
            # Update the episode with the local path
            episode.local_path = local_path
            episode.download_date = time.time()
            
            logging.info(f"Successfully downloaded episode: {episode.title} to {local_path}")
            return True
            
        except Exception as e:
            logging.error(f"Error downloading episode {episode.title}: {e}")
            return False
            
    def extract_metadata(self, episode: Episode) -> Optional[Dict[str, Any]]:
        """Extract metadata from an episode"""
        try:
            if self.dry_run:
                logging.info(f"[DRY RUN] Would extract metadata for episode: {episode.title}")
                return {"title": episode.title, "duration": "00:00:00"}
                
            if not episode.local_path or not os.path.exists(episode.local_path):
                logging.error(f"Episode file not found: {episode.local_path}")
                return None
                
            # Extract metadata using the metadata extractor
            metadata = self.metadata_extractor.handle_metadata_extraction(episode.local_path)
            
            if metadata:
                logging.info(f"Successfully extracted metadata for episode: {episode.title}")
                return metadata
            else:
                logging.error(f"Failed to extract metadata for episode: {episode.title}")
                return None
                
        except Exception as e:
            logging.error(f"Error extracting metadata for episode {episode.title}: {e}")
            return None
            
    def transcribe_episode(self, episode: Episode) -> bool:
        """Transcribe an episode"""
        try:
            if self.dry_run:
                logging.info(f"[DRY RUN] Would transcribe episode: {episode.title}")
                return True
                
            if not episode.local_path or not os.path.exists(episode.local_path):
                logging.error(f"Episode file not found: {episode.local_path}")
                return False
                
            # Transcribe the episode
            success = self.transcription_manager.handle_transcription(episode.local_path)
            
            if success:
                logging.info(f"Successfully transcribed episode: {episode.title}")
                return True
            else:
                logging.error(f"Failed to transcribe episode: {episode.title}")
                return False
                
        except Exception as e:
            logging.error(f"Error transcribing episode {episode.title}: {e}")
            return False
            
    def create_embeddings(self, episode: Episode) -> bool:
        """Create embeddings for an episode"""
        try:
            if self.dry_run:
                logging.info(f"[DRY RUN] Would create embeddings for episode: {episode.title}")
                return True
                
            if self.skip_vectordb:
                logging.warning("Skipping embeddings creation as vectordb is disabled")
                return True
                
            # Get the transcript file path
            transcript_path = self.transcription_manager.get_transcript_path(episode.local_path)
            if not transcript_path or not os.path.exists(transcript_path):
                logging.error(f"Transcript file not found for episode: {episode.title}")
                return False
                
            # Create embeddings
            success = self.vector_db_manager.handle_indexing(transcript_path)
            
            if success:
                logging.info(f"Successfully created embeddings for episode: {episode.title}")
                return True
            else:
                logging.error(f"Failed to create embeddings for episode: {episode.title}")
                return False
                
        except Exception as e:
            logging.error(f"Error creating embeddings for episode {episode.title}: {e}")
            return False
            
    def delete_mp3(self, episode: Episode) -> bool:
        """Delete the MP3 file for an episode"""
        try:
            if self.dry_run:
                logging.info(f"[DRY RUN] Would delete MP3 for episode: {episode.title}")
                return True
                
            if not episode.local_path or not os.path.exists(episode.local_path):
                logging.error(f"Episode file not found: {episode.local_path}")
                return False
                
            # Delete the file
            os.remove(episode.local_path)
            logging.info(f"Successfully deleted MP3 for episode: {episode.title}")
            return True
            
        except Exception as e:
            logging.error(f"Error deleting MP3 for episode {episode.title}: {e}")
            return False


if __name__ == "__main__":
    parser = get_base_parser()
    add_dry_run_argument(parser)
    add_log_level_argument(parser)
    add_ai_system_argument(parser)
    parser.description = "Process podcast files with transcription, metadata extraction, and indexing"
    args = parser.parse_args()

    # Configure logging based on command-line argument
    logger = logging.getLogger()
    log_level = getattr(logging, args.log_level.upper(), "INFO")
    logger.setLevel(log_level)
    logging.getLogger('httpx').setLevel("WARNING")
    logging.getLogger('httpcore').setLevel("WARNING")
    # Console handler for logging to the console
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(console_formatter)

    # Load configuration, passing the env file if provided
    config = Config(env_file=args.env_file)

    # Instantiate the FileManager with the loaded configuration
    file_manager = FileManager(config=config, dry_run=args.dry_run, ai_system=args.ai_system)

    file_manager.process_directory()
