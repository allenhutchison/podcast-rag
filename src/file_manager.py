import logging
import os

from argparse_shared import (add_dry_run_argument, add_log_level_argument,
                             add_ai_system_argument, get_base_parser)
from db.chroma_vectordb import VectorDbManager
from config import Config
from metadata_extractor import MetadataExtractor
from transcribe_podcasts import TranscriptionManager


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
        # Release the model after processing is complete for the directory
        self.transcription_manager.release_model()

    def log_stats(self):
        '''Log transcription statistics.'''
        logging.info(f"Total MP3 files processed: {self.stats['total_mp3_files']}")
        self.transcription_manager.log_stats()
        self.metadata_extractor.log_stats()
        if not self.skip_vectordb:
            self.vector_db_manager.log_stats()

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
