import logging
import os
import sys
from pathlib import Path

# Add parent directory to path to import from src
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.argparse_shared import (add_dry_run_argument, add_log_level_argument,
                             add_skip_vectordb_argument, add_sync_remote_argument,
                             get_base_parser)
from src.db.gemini_file_search import GeminiFileSearchManager
from src.config import Config
from src.metadata_extractor import MetadataExtractor
from src.transcribe_podcasts import TranscriptionManager


class FileManager:
    def __init__(self, config: Config, dry_run=False, skip_vectordb=False, sync_remote=False):
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
                # Cache existing files for idempotency (use_cache=False if sync_remote is True)
                use_cache = not sync_remote
                self.existing_files_cache = self.file_search_manager.get_existing_files(
                    store_name, use_cache=use_cache, show_progress=sync_remote
                )
                logging.info(f"Found {len(self.existing_files_cache)} existing documents in File Search store")
            except (ValueError, KeyError) as e:
                # Configuration errors (missing API key, etc.) should fail loudly
                logging.error(f"Configuration error initializing File Search: {e}")
                logging.error("Please check your GEMINI_API_KEY and configuration.")
                raise
            except Exception as e:
                # Network errors, API errors, or other transient issues during initialization
                # Note: This does NOT catch KeyboardInterrupt or SystemExit (they inherit from BaseException, not Exception)
                # File Search is an optional feature, so we gracefully degrade rather than failing completely
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

        # Print error report if there were any errors
        self.print_error_report()

    def print_error_report(self):
        '''Print a detailed error report with file paths.'''
        transcription_errors = self.transcription_manager.errors
        metadata_errors = self.metadata_extractor.errors

        if not transcription_errors and not metadata_errors:
            return

        print("\n" + "=" * 80)
        print("ERROR REPORT")
        print("=" * 80)

        # Transcription errors
        if transcription_errors:
            print(f"\n{len(transcription_errors)} Transcription Error(s):")
            print("-" * 80)
            for file_path, error_msg in transcription_errors:
                # Extract just the first line of error for cleaner output
                error_summary = error_msg.split('\n')[0][:100]
                print(f"\n  File: {file_path}")
                print(f"  Error: {error_summary}")
                # Check if it looks like an ffmpeg error (common for corrupt files)
                if "ffmpeg" in error_msg.lower() or "failed to load audio" in error_msg.lower():
                    print(f"  Action: Check if file is corrupt. May need to re-download.")

        # Metadata errors
        if metadata_errors:
            # Group by error type
            errors_by_type = {}
            for file_path, error_type, error_msg in metadata_errors:
                if error_type not in errors_by_type:
                    errors_by_type[error_type] = []
                errors_by_type[error_type].append((file_path, error_msg))

            print(f"\n{len(metadata_errors)} Metadata Extraction Error(s):")
            print("-" * 80)

            # Missing transcript errors (usually caused by transcription failures)
            if "missing_transcript" in errors_by_type:
                errors = errors_by_type["missing_transcript"]
                print(f"\n  Missing Transcript ({len(errors)} file(s)):")
                print("  These files failed to transcribe (see transcription errors above)")
                for file_path, _ in errors:
                    print(f"    - {file_path}")

            # AI extraction failures
            if "ai_extraction_failed" in errors_by_type:
                errors = errors_by_type["ai_extraction_failed"]
                print(f"\n  AI Metadata Extraction Failed ({len(errors)} file(s)):")
                print("  The transcript exists but metadata extraction failed")
                for file_path, error_msg in errors:
                    print(f"    - {file_path}")

            # Unexpected errors
            if "unexpected_error" in errors_by_type:
                errors = errors_by_type["unexpected_error"]
                print(f"\n  Unexpected Errors ({len(errors)} file(s)):")
                for file_path, error_msg in errors:
                    error_summary = error_msg.split('\n')[0][:100]
                    print(f"    - {file_path}")
                    print(f"      {error_summary}")

        print("\n" + "=" * 80)
        print("RECOMMENDED ACTIONS:")
        print("=" * 80)
        if transcription_errors:
            print("\nFor transcription errors:")
            print("  1. Check if the MP3 files are corrupt (use ffmpeg or media player)")
            print("  2. If corrupt, re-download the files from the source")
            print("  3. If files are valid, this may be an ffmpeg compatibility issue")
        if metadata_errors:
            print("\nFor metadata errors:")
            print("  1. Missing transcript: Fix transcription errors first")
            print("  2. AI extraction failed: Check Gemini API connectivity and quota")
            print("  3. For persistent issues, inspect individual files manually")
        print("=" * 80 + "\n")

if __name__ == "__main__":
    parser = get_base_parser()
    add_dry_run_argument(parser)
    add_log_level_argument(parser)
    add_skip_vectordb_argument(parser)
    add_sync_remote_argument(parser)
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
    logger.addHandler(console_handler)

    # Load configuration, passing the env file if provided
    config = Config(env_file=args.env_file)

    # Instantiate the FileManager with the loaded configuration
    file_manager = FileManager(
        config=config,
        dry_run=args.dry_run,
        skip_vectordb=args.skip_vectordb,
        sync_remote=args.sync_remote
    )

    file_manager.process_directory()
