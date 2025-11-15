import logging
import os

from src.argparse_shared import (add_dry_run_argument, add_log_level_argument,
                             get_base_parser)
from src.db.gemini_file_search import GeminiFileSearchManager
from src.config import Config
from src.metadata_extractor import MetadataExtractor
from src.transcribe_podcasts import TranscriptionManager


class FileManager:
    def __init__(self, config: Config, dry_run=False, skip_vectordb=False):
        self.config = config
        self.dry_run = dry_run
        self.skip_vectordb = skip_vectordb
        self.transcription_manager = TranscriptionManager(config=config, dry_run=dry_run)
        self.metadata_extractor = MetadataExtractor(config=config, dry_run=dry_run)

        # Initialize File Search manager only if not skipping indexing operations
        self.existing_files_cache = None
        if not skip_vectordb:
            try:
                self.file_search_manager = GeminiFileSearchManager(config=config, dry_run=dry_run)
                # Ensure store is created
                store_name = self.file_search_manager.create_or_get_store()
                # Cache existing files for idempotency
                self.existing_files_cache = self.file_search_manager.get_existing_files(store_name)
                logging.info(f"Found {len(self.existing_files_cache)} existing documents in File Search store")
            except (ValueError, KeyError) as e:
                # Configuration errors (missing API key, etc.) should fail loudly
                logging.error(f"Configuration error initializing File Search: {e}")
                logging.error("Please check your GEMINI_API_KEY and configuration.")
                raise
            except Exception as e:
                # Network or other transient errors can be skipped with warning
                logging.warning(f"Could not initialize GeminiFileSearchManager: {e}")
                logging.warning("File Search operations will be skipped. Use --skip-vectordb to suppress this warning.")
                self.skip_vectordb = True

        self.stats = {
            "total_mp3_files": 0,
            "total_uploaded": 0,
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
                # Upload transcript to File Search store
                if not self.skip_vectordb:
                    try:
                        transcript_path = self.config.build_transcription_file(episode_path)
                        if os.path.exists(transcript_path):
                            file_name = self.file_search_manager.upload_transcript(
                                transcript_path=transcript_path,
                                metadata=metadata,
                                existing_files=self.existing_files_cache
                            )
                            if file_name:
                                self.stats["total_uploaded"] += 1
                                logging.info(f"Uploaded transcript to File Search: {transcript_path}")
                            else:
                                logging.debug(f"Skipped upload (already exists): {transcript_path}")
                    except Exception as e:
                        logging.error(f"Failed to upload transcript for {episode_path}: {e}")

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
        '''Log processing statistics.'''
        logging.info(f"Total MP3 files processed: {self.stats['total_mp3_files']}")
        logging.info(f"Total transcripts uploaded to File Search: {self.stats['total_uploaded']}")
        self.transcription_manager.log_stats()
        self.metadata_extractor.log_stats()

if __name__ == "__main__":
    parser = get_base_parser()
    add_dry_run_argument(parser)
    add_log_level_argument(parser)
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
    file_manager = FileManager(config=config, dry_run=args.dry_run)

    file_manager.process_directory()
