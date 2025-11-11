
import os
import sys
import logging
import boto3
import whisper
import torch
import gc
import tempfile
from apscheduler.schedulers.blocking import BlockingScheduler
from sqlalchemy.orm import Session
from botocore.exceptions import ClientError

from src.config import Config
from src.db.database import get_db
from src.db.models import Episode, ProcessingStatus

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class TranscriptionService:
    def __init__(self, config: Config):
        self.config = config
        self.whisper_model = None
        self.r2_client = self._get_r2_client()

    def _get_r2_client(self):
        """Initializes a boto3 client for Cloudflare R2."""
        return boto3.client(
            's3',
            endpoint_url=self.config.S3_ENDPOINT_URL,
            aws_access_key_id=self.config.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=self.config.AWS_SECRET_ACCESS_KEY,
            region_name='auto'
        )

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
        temp_audio_path = None
        try:
            # 1. Download audio from R2 to a temporary file
            object_key = episode.audio_url.replace(f"{self.config.S3_ENDPOINT_URL}/{self.config.S3_BUCKET_NAME}/", "")
            
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as temp_file:
                temp_audio_path = temp_file.name

            logging.info(f"Downloading audio for episode {episode.id} from R2 key: {object_key}")
            self.r2_client.download_file(self.config.S3_BUCKET_NAME, object_key, temp_audio_path)
            logging.info(f"Successfully downloaded to temporary file: {temp_audio_path}")

            # 2. Transcribe using Whisper
            model = self._get_whisper_model()
            logging.info(f"Starting Whisper transcription for episode {episode.id}...")
            result = model.transcribe(audio=temp_audio_path, language="en", verbose=False)
            transcript_text = result["text"]
            logging.info(f"Transcription complete for episode {episode.id}. Transcript length: {len(transcript_text)}")

            # 3. Update database
            episode.full_transcript = transcript_text
            episode.transcription_status = ProcessingStatus.COMPLETED
            db_session.commit()
            logging.info(f"Successfully saved transcript for episode {episode.id} to the database.")

        except ClientError as e:
            logging.error(f"Failed to download audio for episode {episode.id} from R2: {e}")
            episode.transcription_status = ProcessingStatus.FAILED
            db_session.commit()
        except Exception as e:
            logging.error(f"An error occurred while transcribing episode {episode.id}: {e}")
            episode.transcription_status = ProcessingStatus.FAILED
            db_session.commit()
        finally:
            # 4. Cleanup temporary file
            if temp_audio_path and os.path.exists(temp_audio_path):
                os.remove(temp_audio_path)
                logging.info(f"Cleaned up temporary file: {temp_audio_path}")

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
