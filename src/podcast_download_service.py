
import os
import sys
import logging
import requests
import boto3
import feedparser
import time
from apscheduler.schedulers.blocking import BlockingScheduler
from sqlalchemy.orm import Session
from dateutil import parser as date_parser

# Adjust path to import from src
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from config import Config
from db.database import get_db
from db.models import Podcast, Episode

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_r2_client(config: Config):
    """Initializes a boto3 client for Cloudflare R2."""
    return boto3.client(
        's3',
        endpoint_url=config.S3_ENDPOINT_URL,
        aws_access_key_id=config.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=config.AWS_SECRET_ACCESS_KEY,
        region_name='auto'
    )

def poll_all_feeds(config: Config, r2_client):
    """The main job function that polls all podcast feeds."""
    logging.info("Starting new polling cycle for all podcast feeds...")
    db_session: Session = next(get_db())
    
    try:
        podcasts = db_session.query(Podcast).all()
        if not podcasts:
            logging.info("No podcasts found in the database to poll. Add some via a client or direct DB insertion.")
            return

        logging.info(f"Found {len(podcasts)} podcasts to check.")

        for podcast in podcasts:
            logging.info(f"Checking feed for '{podcast.title}': {podcast.feed_url}")
            try:
                feed = feedparser.parse(podcast.feed_url)
                if feed.bozo:
                    logging.warning(f"Feed for '{podcast.title}' may not be well-formed. Reason: {feed.bozo_exception}")

                for entry in feed.entries:
                    guid = entry.get('guid')
                    if not guid:
                        logging.warning(f"Skipping entry in '{podcast.title}' due to missing GUID.")
                        continue

                    if db_session.query(Episode).filter(Episode.guid == guid).first():
                        continue
                    
                    logging.info(f"New episode found for '{podcast.title}': '{entry.title}'")
                    
                    audio_url = next((link.get('href') for link in entry.get('links', []) if link.get('rel') == 'enclosure' and 'audio' in link.get('type', '')), None)
                    if not audio_url:
                        logging.warning(f"Could not find audio enclosure for '{entry.title}'. Skipping.")
                        continue

                    try:
                        file_extension = os.path.splitext(audio_url.split('?')[0])[-1] or '.mp3'
                        object_key = f"podcasts/{podcast.id}/{guid}{file_extension}"
                        
                        logging.info(f"Downloading audio from {audio_url}")
                        with requests.get(audio_url, stream=True) as r:
                            r.raise_for_status()
                            logging.info(f"Uploading to R2 with key: {object_key}")
                            r2_client.upload_fileobj(r.raw, config.S3_BUCKET_NAME, object_key)
                        
                        r2_object_url = f"{config.S3_ENDPOINT_URL}/{config.S3_BUCKET_NAME}/{object_key}"
                        
                        published_date = date_parser.parse(entry.get('published')) if entry.get('published') else None

                        new_episode = Episode(
                            podcast_id=podcast.id,
                            guid=guid,
                            title=entry.get('title', 'No Title'),
                            published_date=published_date,
                            audio_url=r2_object_url,
                            summary=entry.get('summary')
                        )
                        db_session.add(new_episode)
                        db_session.commit()
                        logging.info(f"Successfully added '{entry.title}' to the database.")

                    except requests.exceptions.RequestException as e:
                        logging.error(f"Failed to download audio for '{entry.title}': {e}")
                        db_session.rollback()
                    except Exception as e:
                        logging.error(f"Failed to upload or process '{entry.title}': {e}")
                        db_session.rollback()

            except Exception as e:
                logging.error(f"Failed to process feed for '{podcast.title}': {e}")

    finally:
        db_session.close()
        logging.info("Polling cycle finished.")

if __name__ == "__main__":
    config = Config()
    
    if not all([config.DATABASE_URL, config.S3_BUCKET_NAME, config.S3_ENDPOINT_URL, config.AWS_ACCESS_KEY_ID, config.AWS_SECRET_ACCESS_KEY]):
        logging.critical("FATAL: Database or S3/R2 configuration is missing. Please check your .env file.")
        exit(1)

    r2_client = get_r2_client(config)
    poll_interval = int(os.getenv("DOWNLOAD_POLL_INTERVAL_MINUTES", 60))

    scheduler = BlockingScheduler()
    
    logging.info("Scheduler starting. Triggering immediate first run.")
    scheduler.add_job(poll_all_feeds, 'date', args=[config, r2_client], misfire_grace_time=600)
    scheduler.add_job(poll_all_feeds, 'interval', minutes=poll_interval, args=[config, r2_client], misfire_grace_time=600)

    logging.info(f"Podcast Download Service started. Polling every {poll_interval} minutes.")
    print("Press Ctrl+C to exit.")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logging.info("Scheduler stopped.")
