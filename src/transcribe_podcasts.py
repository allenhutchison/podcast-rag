import logging
import os
import whisper
import torch
import gc

from argparse_shared import (add_dry_run_argument, add_episode_path_argument,
                             add_log_level_argument, get_base_parser)
from config import Config


class TranscriptionManager:
    def __init__(self, config: Config, dry_run=False):
        self.config = config
        self.dry_run = dry_run
        self.stats = {
            "already_transcribed": 0,
            "waiting_for_transcription": 0,
            "transcribed_now": 0,
        }
        # Load the whisper model once during initialization
        self.model = None

    def get_model(self):
        """Lazy load the whisper model when needed"""
        if self.model is None:
            logging.info("Loading Whisper model (large-v3)...")
            self.model = whisper.load_model("large-v3")
        return self.model

    def handle_transcription(self, episode_path):
        transcription_file = self.config.build_transcription_file(episode_path)
        temp_file = self.config.build_temp_file(transcription_file)

        if self.config.is_transcription_in_progress(temp_file):
            self.handle_incomplete_transcription(episode_path, temp_file)
        elif self.config.transcription_exists(transcription_file):
            logging.debug(f"Skipping {episode_path}: transcription already exists.")
            self.stats["already_transcribed"] += 1
        else:
            if self.dry_run:
                logging.debug(f"Dry run: would transcribe {episode_path}")
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
            # Get the model and transcribe the audio
            model = self.get_model()
            result = model.transcribe(
                audio=episode_path,
                language="en",
                verbose=False
            )
            
            # Write the transcription to the file
            with open(transcription_file, 'w', encoding='utf-8') as f:
                f.write(result["text"])
                
            logging.debug(f"Transcription complete for {episode_path}")
            self.stats["transcribed_now"] += 1
        except Exception as e:
            logging.error(f"Unexpected error during transcription for {episode_path}: {e}")
        finally:
            if os.path.exists(temp_file):
                os.remove(temp_file)

    def release_model(self):
        if self.model is not None:
            logging.info("Releasing Whisper model from memory.")
            del self.model
            self.model = None # Ensure it's None so get_model reloads if needed
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            gc.collect()

    def log_stats(self):
        '''Log transcription statistics.'''
        logging.info(f"Already transcribed: {self.stats['already_transcribed']}")
        if self.dry_run:
            logging.info(f"Waiting for transcription: {self.stats['waiting_for_transcription']}")
        else:
            logging.info(f"Transcribed during this run: {self.stats['transcribed_now']}")

if __name__ == "__main__":
    parser = get_base_parser()
    parser.description = "Transcribe podcasts using Whisper"
    add_dry_run_argument(parser)
    add_log_level_argument(parser)
    add_episode_path_argument(parser)
    
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
    manager.handle_transcription(args.episode_path)
    manager.log_stats()
