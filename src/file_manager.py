
import os
import subprocess
import logging
from config import Config
from transcribe_podcasts import TranscriptionManager

class FileManager:
    def __init__(self, config: Config, dry_run=False, transcription_manager=None):
        self.config = config
        self.dry_run = dry_run
        self.transcription_manager = transcription_manager
        self.stats = {
            "total_mp3_files": 0,
        }

    def process_podcast(self, podcast_dir):
        '''Process all podcast files in a directory.'''
        for episode_file in os.listdir(podcast_dir):
            episode_path = os.path.join(podcast_dir, episode_file)
            if self.config.is_mp3_file(episode_path):
                self.stats["total_mp3_files"] += 1
                # Handle transcription for MP3 files, then summary and embedding
                self.transcription_manager.handle_transcription(episode_path)
                #self.handle_summary(episode_path)
                #self.handle_embedding(episode_path)

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

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Transcribe podcasts using Whisper")
    parser.add_argument("-d", "--dry-run", action="store_true", help="Perform a dry run without actual transcription")
    parser.add_argument("-e", "--env-file", help="Path to a custom .env file", default=None)
    parser.add_argument("-l", "--log-level", help="Set log level (DEBUG, INFO, WARNING, ERROR)", default="INFO")
    args = parser.parse_args()

    # Configure logging based on command-line argument
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), "INFO"),  # Default to INFO if invalid log level
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler()]
    )

    # Load configuration, passing the env file if provided
    config = Config(env_file=args.env_file)

    # Instantiate the TranscriptionManager with the loaded configuration
    transcription_manager = TranscriptionManager(config=config, dry_run=args.dry_run)

    # Instantiate the FileManager with the loaded configuration
    file_manager = FileManager(config=config, dry_run=args.dry_run, transcription_manager=transcription_manager)

    file_manager.process_directory()