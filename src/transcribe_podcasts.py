
import os
import subprocess
import logging
from config import Config

class TranscriptionManager:
    def __init__(self, config: Config, dry_run=False):
        self.config = config
        self.dry_run = dry_run
        self.stats = {
            "total_mp3_files": 0,
            "already_transcribed": 0,
            "waiting_for_transcription": 0,
            "transcribed_now": 0,
        }

    def process_podcast(self, podcast_dir):
        '''Process all podcast files in a directory.'''
        for episode_file in os.listdir(podcast_dir):
            episode_path = os.path.join(podcast_dir, episode_file)
            if self.config.is_mp3_file(episode_path):
                self.handle_transcription(episode_path)

    def handle_transcription(self, episode_path):
        transcription_file = self.config.build_transcription_file(episode_path)
        temp_file = self.config.build_temp_file(transcription_file)

        if self.config.is_transcription_in_progress(temp_file):
            self.handle_incomplete_transcription(episode_path, temp_file)
        elif self.config.transcription_exists(transcription_file):
            logging.info(f"Skipping {episode_path}: transcription already exists.")
            self.stats["already_transcribed"] += 1
        else:
            if self.dry_run:
                logging.info(f"Dry run: would transcribe {episode_path}")
                self.stats["waiting_for_transcription"] += 1
            else:
                self.start_transcription(episode_path, transcription_file, temp_file)

    def handle_incomplete_transcription(self, episode_path, temp_file):
        '''Handle incomplete transcription by removing temp file.'''
        logging.info(f"Detected unfinished transcription for {episode_path}.")
        os.remove(temp_file)

    def start_transcription(self, episode_path, transcription_file, temp_file):
        '''Run the transcription process using Whisper.'''
        logging.info(f"Starting transcription for {episode_path}")
        try:
            result = subprocess.run([self.config.WHISPER_PATH, episode_path, 
                                     '--output_dir', os.path.dirname(transcription_file), 
                                     '--output_format', 'txt',
                                     '--language', 'en'], capture_output=True, text=True)
            result.check_returncode()  # Raises an error if returncode != 0
            logging.info(f"Transcription complete for {episode_path}")
            self.stats["transcribed_now"] += 1
        except subprocess.CalledProcessError as e:
            logging.error(f"Transcription failed for {episode_path}: {e}")
        except Exception as e:
            logging.error(f"Unexpected error during transcription for {episode_path}: {e}")
        finally:
            if os.path.exists(temp_file):
                os.remove(temp_file)
            # Move the output file to the final transcription file
            output_file = os.path.splitext(episode_path)[0] + ".txt"
            if os.path.exists(output_file):
                os.rename(output_file, transcription_file)            

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
        logging.info("\n--- Transcription Statistics ---")
        logging.info(f"Total MP3 files processed: {self.stats['total_mp3_files']}")
        logging.info(f"Already transcribed: {self.stats['already_transcribed']}")
        if self.dry_run:
            logging.info(f"Waiting for transcription: {self.stats['waiting_for_transcription']}")
        else:
            logging.info(f"Transcribed during this run: {self.stats['transcribed_now']}")

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
    manager = TranscriptionManager(config=config, dry_run=args.dry_run)
    manager.process_directory()
