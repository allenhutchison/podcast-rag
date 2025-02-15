import json
import logging
import os
from typing import Optional

import eyed3
import google.genai as genai
from ollama import Client
from pydantic import TypeAdapter

from config import Config
from prompt_manager import PromptManager
from schemas import EpisodeMetadata, MP3Metadata, PodcastMetadata


class MetadataExtractor:
    def __init__(self, config: Config, dry_run=False, ai_system="gemini"):
        self.config = config
        self.dry_run = dry_run
        self.ai_system = ai_system
        self.prompt_manager = PromptManager(config=config, print_results=False)
        self.stats = {
            "already_processed": 0,
            "processed": 0,
            "failed": 0,
        }
        
        # Initialize AI client
        if self.ai_system != "gemini":
            logging.error("Metadata extraction requires Gemini. Please set ai_system to 'gemini'.")
            self.ai_client = None
            return
            
        logging.info("Using Gemini for metadata extraction.")
        self.ai_client = genai.Client(api_key=self.config.GEMINI_API_KEY)

    def build_metadata_file(self, episode_path: str) -> str:
        """Build the path for the metadata file."""
        return os.path.splitext(episode_path)[0] + "_metadata.json"

    def build_temp_file(self, metadata_file: str) -> str:
        """Build the path for the temp file."""
        return metadata_file + ".metadata_in_progress"

    def metadata_exists(self, metadata_file: str) -> bool:
        """Check if metadata file exists and is not empty."""
        return os.path.exists(metadata_file) and os.path.getsize(metadata_file) > 0

    def is_metadata_in_progress(self, temp_file: str) -> bool:
        """Check if metadata extraction is in progress."""
        return os.path.exists(temp_file)

    def handle_incomplete_metadata(self, episode_path: str, temp_file: str) -> None:
        """Handle incomplete metadata extraction by removing temp file."""
        logging.info(f"Detected unfinished metadata extraction for {episode_path}")
        os.remove(temp_file)

    def extract_mp3_metadata(self, episode_path: str) -> MP3Metadata:
        """Extract metadata from MP3 file using eyed3."""
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

    def extract_metadata_from_transcript(self, transcript: str, filename: str) -> Optional[PodcastMetadata]:
        """Extract metadata from transcript using AI."""
        if self.ai_system != "gemini":
            logging.error("Metadata extraction requires Gemini. Please set ai_system to 'gemini'.")
            return None
            
        prompt = self.prompt_manager.build_prompt(
            prompt_name="metadata_extraction",
            transcript=transcript,
            filename=filename
        )
        
        try:
            response = self.ai_client.models.generate_content(
                model=self.config.GEMINI_MODEL,
                contents=prompt,
                config={
                    'response_mime_type': 'application/json',
                    'response_schema': PodcastMetadata,
                }
            )
            return response.parsed
                
        except Exception as e:
            logging.error(f"Error extracting metadata from transcript: {e}")
            logging.error(f"Full error: {str(e)}")
            return None

    def handle_metadata_extraction(self, episode_path: str) -> Optional[EpisodeMetadata]:
        """Main method to handle metadata extraction for an episode."""
        logging.info(f"Extracting metadata for {episode_path}")
        
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
            
        try:
            # Create temp file to indicate processing
            open(temp_file, 'w').close()
            
            # Get MP3 metadata
            mp3_metadata = self.extract_mp3_metadata(episode_path)
            
            # Get transcript metadata
            transcript_file = self.config.build_transcription_file(episode_path)
            if not os.path.exists(transcript_file):
                logging.error(f"Transcript file not found: {transcript_file}")
                return None
                
            with open(transcript_file, 'r') as f:
                transcript = f.read()
            
            filename = os.path.basename(episode_path)
            transcript_metadata = self.extract_metadata_from_transcript(transcript, filename)
            if transcript_metadata is None:
                return None
            
            # Create combined metadata
            metadata = EpisodeMetadata(
                transcript_metadata=transcript_metadata,
                mp3_metadata=mp3_metadata
            )
            
            # Save metadata to file
            with open(metadata_file, 'w') as f:
                json.dump(metadata.model_dump(), f, indent=2)
            
            # Remove temp file after successful completion
            os.remove(temp_file)
            
            self.stats["processed"] += 1
            return metadata
            
        except Exception as e:
            logging.error(f"Error processing metadata for {episode_path}: {e}")
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
    from argparse_shared import (add_ai_system_argument, add_dry_run_argument,
                               add_episode_path_argument, add_log_level_argument,
                               get_base_parser)
    
    parser = get_base_parser()
    add_dry_run_argument(parser)
    add_log_level_argument(parser)
    add_episode_path_argument(parser)
    add_ai_system_argument(parser)
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
        dry_run=args.dry_run,
        ai_system=args.ai_system
    )

    # Process single episode if specified
    if args.episode_path:
        extractor.handle_metadata_extraction(args.episode_path)
        extractor.log_stats() 