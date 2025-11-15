
import os
import sys
import logging
import whisper
import torch
import gc
from apscheduler.schedulers.blocking import BlockingScheduler
from sqlalchemy.orm import Session

from src.config import Config
from src.db.database import get_db
from src.db.models import Episode, ProcessingStatus

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class TranscriptionService:
    def __init__(self, config: Config):
        self.config = config
        self.whisper_model = None

    def _get_whisper_model(self):
        """Lazy loads the Whisper model to conserve memory."""
        if self.whisper_model is None:
            logging.info("Loading Whisper model (large-v3)...")
            self.whisper_model = whisper.load_model("large-v3")
        return self.whisper_model

    def _release_whisper_model(self):
        """Releases the Whisper model from memory."""
        if self.whisper_model is not None:
            logging.info("Releasing Whisper model from memory.")
            del self.whisper_model
            self.whisper_model = None
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            gc.collect()

    def process_pending_episodes(self):
        """The main job function that finds and transcribes pending episodes."""
        logging.info("Starting new transcription cycle...")
        db_session: Session = next(get_db())
        
        try:
            pending_episode = db_session.query(Episode).filter(
                Episode.transcription_status == ProcessingStatus.PENDING
            ).first()

            if not pending_episode:
                logging.info("No pending episodes to transcribe.")
                return

            logging.info(f"Found pending episode to process: '{pending_episode.title}' (ID: {pending_episode.id})")
            
            # Mark as in_progress
            pending_episode.transcription_status = ProcessingStatus.IN_PROGRESS
            db_session.commit()

            self._transcribe_episode(db_session, pending_episode)

        except Exception as e:
            logging.error(f"An error occurred during the transcription cycle: {e}")
            db_session.rollback()
        finally:
            db_session.close()
            # Release model memory after each cycle to be efficient
            self._release_whisper_model()
            logging.info("Transcription cycle finished.")

    def _transcribe_episode(self, db_session: Session, episode: Episode):
        """Handles the transcription for a single episode."""
        try:
            # 1. Get local audio file path
            audio_path = episode.audio_url

            if not os.path.exists(audio_path):
                logging.error(f"Audio file not found for episode {episode.id}: {audio_path}")
                episode.transcription_status = ProcessingStatus.FAILED
                db_session.commit()
                return

            logging.info(f"Processing audio file for episode {episode.id}: {audio_path}")

            # 2. Transcribe using Whisper
            model = self._get_whisper_model()
            logging.info(f"Starting Whisper transcription for episode {episode.id}...")
            result = model.transcribe(audio=audio_path, language="en", verbose=False)
            transcript_text = result["text"]
            logging.info(f"Transcription complete for episode {episode.id}. Transcript length: {len(transcript_text)}")

            # 3. Update database
            episode.full_transcript = transcript_text
            episode.transcription_status = ProcessingStatus.COMPLETED
            db_session.commit()
            logging.info(f"Successfully saved transcript for episode {episode.id} to the database.")

        except Exception as e:
            logging.error(f"An error occurred while transcribing episode {episode.id}: {e}")
            episode.transcription_status = ProcessingStatus.FAILED
            db_session.commit()

if __name__ == "__main__":
    config = Config()
    service = TranscriptionService(config)
    
    poll_interval = int(os.getenv("TRANSCRIPTION_POLL_INTERVAL_MINUTES", 5))

    scheduler = BlockingScheduler()
    
    logging.info("Scheduler starting. Triggering immediate first run.")
    scheduler.add_job(service.process_pending_episodes, 'date', misfire_grace_time=600)
    scheduler.add_job(service.process_pending_episodes, 'interval', minutes=poll_interval, misfire_grace_time=600)

    logging.info(f"Transcription Service started. Polling every {poll_interval} minutes.")
    print("Press Ctrl+C to exit.")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logging.info("Scheduler stopped.")
