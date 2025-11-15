import json
import logging
import os
import time
from functools import wraps
from typing import Optional
from threading import Lock

from pydantic import TypeAdapter

from src.config import Config
from src.prompt_manager import PromptManager
from src.schemas import EpisodeMetadata, MP3Metadata, PodcastMetadata


class RateLimiter:
    """Token bucket rate limiter for API requests."""
    def __init__(self, max_requests: int, time_window: int):
        self.max_requests = max_requests  # Maximum requests allowed in the time window
        self.time_window = time_window    # Time window in seconds
        self.tokens = max_requests        # Current token count
        self.last_update = time.time()    # Last token update timestamp
        self.lock = Lock()                # Thread safety lock

    def _update_tokens(self):
        """Update token count based on elapsed time."""
        now = time.time()
        time_passed = now - self.last_update
        self.tokens = min(
            self.max_requests,
            self.tokens + (time_passed * self.max_requests / self.time_window)
        )
        self.last_update = now

    def acquire(self):
        """Acquire a token, waiting if necessary."""
        with self.lock:
            self._update_tokens()
            while self.tokens < 1:
                # Calculate sleep time needed for at least one token
                sleep_time = (1 - self.tokens) * (self.time_window / self.max_requests)
                time.sleep(sleep_time)
                self._update_tokens()
            self.tokens -= 1
            return True


def retry_with_exponential_backoff(max_retries=5, base_delay=1, max_delay=32):
    """Decorator that implements exponential backoff for handling 429 errors."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            retries = 0
            while retries < max_retries:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    error_str = str(e).lower()
                    if "429" in error_str or "too many requests" in error_str:
                        if retries == max_retries - 1:
                            logging.error(f"Max retries ({max_retries}) reached. Last error: {e}")
                            raise
                        delay = min(base_delay * (2 ** retries), max_delay)
                        logging.warning(f"Rate limit hit. Retrying in {delay} seconds...")
                        time.sleep(delay)
                        retries += 1
                    else:
                        raise
            return func(*args, **kwargs)
        return wrapper
    return decorator


class MetadataExtractor:
    def __init__(self, config: Config, dry_run=False):
        self.config = config
        self.dry_run = dry_run
        self.prompt_manager = PromptManager(config=config, print_results=False)
        self.stats = {
            "already_processed": 0,
            "processed": 0,
            "failed": 0,
        }

        # Initialize AI client only when not in dry run mode
        self.ai_client = None
        self.rate_limiter = None
        if not dry_run:
            import google.genai as genai
            self.ai_client = genai.Client(api_key=self.config.GEMINI_API_KEY)
            # Initialize rate limiter for 10 requests per minute
            self.rate_limiter = RateLimiter(max_requests=9, time_window=60)

    def build_metadata_file(self, episode_path: str) -> str:
        """Build the path for the metadata file."""
        return os.path.splitext(episode_path)[0] + "_metadata.json"

    def build_temp_file(self, metadata_file: str) -> str:
        """Build the path for the temp file."""
        return metadata_file + ".metadata_in_progress"

    def metadata_exists(self, metadata_file: str) -> bool:
        """Check if metadata file exists and contains valid mp3 and transcript metadata."""
        if not os.path.exists(metadata_file) or os.path.getsize(metadata_file) == 0:
            return False
        try:
            with open(metadata_file, 'r') as f:
                metadata = json.loads(f.read())
                return (isinstance(metadata, dict) and 
                       'mp3_metadata' in metadata and
                       'transcript_metadata' in metadata)
        except (json.JSONDecodeError, IOError):
            return False

    def is_metadata_in_progress(self, temp_file: str) -> bool:
        """Check if metadata extraction is in progress."""
        return os.path.exists(temp_file)

    def handle_incomplete_metadata(self, episode_path: str, temp_file: str) -> None:
        """Handle incomplete metadata extraction by removing temp file."""
        logging.info(f"Detected unfinished metadata extraction for {episode_path}")
        os.remove(temp_file)

    def extract_mp3_metadata(self, episode_path: str) -> MP3Metadata:
        """Extract metadata from MP3 file using eyed3."""
        import eyed3
        try:
            audiofile = eyed3.load(episode_path)
            if audiofile and audiofile.tag:
                return MP3Metadata(
                    title=audiofile.tag.title or "",
                    artist=audiofile.tag.artist or "",
                    album=audiofile.tag.album or "",
                    album_artist=audiofile.tag.album_artist or "",
                    release_date=str(audiofile.tag.recording_date) if audiofile.tag.recording_date else "",
                    comments=[c.text for c in audiofile.tag.comments] if audiofile.tag.comments else [],
                )
            return MP3Metadata()
        except Exception as e:
            logging.error(f"Error extracting MP3 metadata from {episode_path}: {e}")
            return MP3Metadata()

    def sanitize_date(self, date_str: Optional[str]) -> Optional[str]:
        """Sanitize and validate a date string.
        
        Rules:
        1. If date contains 'BC' or 'BCE', return None (historical date)
        2. If date is None, return None
        3. If date doesn't match YYYY pattern at start, return None
        4. If year is before 2000, return None (too old for podcast)
        5. Otherwise return the date if it matches our pattern
        """
        if not date_str:
            return None
            
        if 'BC' in date_str.upper() or 'BCE' in date_str.upper():
            return None
            
        # Extract first year from date string
        import re
        year_match = re.match(r'^(\d{4})', date_str)
        if not year_match:
            return None
            
        year = int(year_match.group(1))
        if year < 2000:
            return None
            
        # Validate against our pattern
        pattern = r'^\d{4}(-\d{2}(-\d{2})?)?(-\d{4})?$'
        if not re.match(pattern, date_str):
            return None
            
        return date_str

    @retry_with_exponential_backoff()
    def extract_metadata_from_transcript(self, transcript: str, filename: str) -> Optional[PodcastMetadata]:
        """Extract metadata from transcript using AI."""
        prompt = self.prompt_manager.build_prompt(
            prompt_name="metadata_extraction",
            transcript=transcript,
            filename=filename
        )
        
        try:
            # Acquire rate limit token before making the request
            self.rate_limiter.acquire()
            logging.debug("Rate limit token acquired, making API request")
            
            response = self.ai_client.models.generate_content(
                model=self.config.GEMINI_MODEL,
                contents=prompt,
                config={
                    'response_mime_type': 'application/json',
                    'response_schema': PodcastMetadata,
                }
            )
            
            # Parse the response
            metadata_dict = response.parsed.model_dump()
            
            # Sanitize the date before creating final metadata
            metadata_dict['date'] = self.sanitize_date(metadata_dict.get('date'))
            
            return PodcastMetadata(**metadata_dict)
                
        except Exception as e:
            logging.error(f"Error extracting metadata from transcript: {e}")
            logging.error(f"Full error: {str(e)}")
            return None

    def handle_metadata_extraction(self, episode_path: str) -> Optional[EpisodeMetadata]:
        """Main method to handle metadata extraction for an episode."""
        metadata_file = self.build_metadata_file(episode_path)
        temp_file = self.build_temp_file(metadata_file)

        if self.is_metadata_in_progress(temp_file):
            self.handle_incomplete_metadata(episode_path, temp_file)
        elif self.metadata_exists(metadata_file):
            logging.debug(f"Skipping {episode_path}: metadata already exists")
            self.stats["already_processed"] += 1
            # Load and return existing metadata
            try:
                with open(metadata_file, 'r') as f:
                    json_data = json.load(f)
                    return EpisodeMetadata.model_validate(json_data)
            except Exception as e:
                logging.error(f"Error loading existing metadata for {episode_path}: {e}")
                return None
        
        if self.dry_run:
            logging.info(f"Dry run: would extract metadata for {episode_path}")
            return None
            
        # Only log when we're actually going to extract metadata
        logging.info(f"Extracting metadata for {episode_path}")
            
        try:
            # Create temp file to indicate processing
            logging.debug(f"Creating temp file: {temp_file}")
            open(temp_file, 'w').close()
            
            # Get MP3 metadata
            logging.debug(f"Extracting MP3 metadata from {episode_path}")
            mp3_metadata = self.extract_mp3_metadata(episode_path)
            logging.debug(f"MP3 metadata extracted: {mp3_metadata}")
            
            # Get transcript metadata
            transcript_file = self.config.build_transcription_file(episode_path)
            logging.debug(f"Looking for transcript file: {transcript_file}")
            if not os.path.exists(transcript_file):
                logging.error(f"Transcript file not found: {transcript_file}")
                self.stats["failed"] += 1  # Add failure stat here
                if os.path.exists(temp_file):
                    os.remove(temp_file)
                return None
                
            logging.debug(f"Reading transcript from {transcript_file}")
            with open(transcript_file, 'r') as f:
                transcript = f.read()
            
            filename = os.path.basename(episode_path)
            logging.debug(f"Extracting metadata from transcript using AI for {filename}")
            transcript_metadata = self.extract_metadata_from_transcript(transcript, filename)
            if transcript_metadata is None:
                logging.error("Failed to extract metadata from transcript")
                self.stats["failed"] += 1  # Add failure stat here
                if os.path.exists(temp_file):
                    os.remove(temp_file)
                return None
            
            logging.debug(f"Transcript metadata extracted: {transcript_metadata}")
            
            # Create combined metadata
            metadata = EpisodeMetadata(
                transcript_metadata=transcript_metadata,
                mp3_metadata=mp3_metadata
            )
            
            # Save metadata to file
            logging.debug(f"Saving metadata to {metadata_file}")
            with open(metadata_file, 'w') as f:
                json.dump(metadata.model_dump(), f, indent=2)
            
            # Remove temp file after successful completion
            logging.debug(f"Removing temp file: {temp_file}")
            os.remove(temp_file)
            
            self.stats["processed"] += 1
            return metadata
            
        except Exception as e:
            logging.error(f"Error processing metadata for {episode_path}: {e}")
            logging.exception("Full traceback:")  # This will log the full stack trace
            self.stats["failed"] += 1
            if os.path.exists(temp_file):
                os.remove(temp_file)
            return None

    def log_stats(self):
        """Log metadata extraction statistics."""
        logging.info(f"Metadata already processed: {self.stats['already_processed']}")
        logging.info(f"Metadata processed in this run: {self.stats['processed']}")
        logging.info(f"Metadata extraction failed: {self.stats['failed']}")


if __name__ == "__main__":
    from argparse_shared import (add_dry_run_argument,
                               add_episode_path_argument, add_log_level_argument,
                               get_base_parser)

    parser = get_base_parser()
    add_dry_run_argument(parser)
    add_log_level_argument(parser)
    add_episode_path_argument(parser)
    parser.description = "Extract metadata from podcast episodes"
    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), "INFO"),
        format="%(asctime)s - %(levelname)s - %(message)s"
    )

    # Load configuration
    config = Config(env_file=args.env_file)

    # Create metadata extractor
    extractor = MetadataExtractor(
        config=config,
        dry_run=args.dry_run
    )

    # Process single episode if specified
    if args.episode_path:
        extractor.handle_metadata_extraction(args.episode_path)
        extractor.log_stats() 