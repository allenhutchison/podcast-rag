import json
import logging
import os
from typing import Dict, Optional

import eyed3
import google.generativeai as genai
from ollama import Client

from config import Config


class MetadataExtractor:
    def __init__(self, config: Config, dry_run=False, ai_system="ollama"):
        self.config = config
        self.dry_run = dry_run
        self.ai_system = ai_system
        self.stats = {
            "already_processed": 0,
            "processed": 0,
            "failed": 0,
        }
        
        # Initialize AI client based on configuration
        if self.ai_system == "ollama":
            logging.info("Using Ollama for metadata extraction.")
            self.ai_client = Client(host=config.OLLAMA_HOST)
        elif self.ai_system == "gemini":
            logging.info("Using Gemini for metadata extraction.")
            genai.configure(api_key=self.config.GEMINI_API_KEY)
            self.ai_client = genai.GenerativeModel(model_name=self.config.GEMINI_MODEL)

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

    def extract_mp3_metadata(self, episode_path: str) -> Dict:
        """Extract metadata from MP3 file using eyed3."""
        try:
            audiofile = eyed3.load(episode_path)
            if audiofile and audiofile.tag:
                return {
                    "title": audiofile.tag.title or "",
                    "artist": audiofile.tag.artist or "",
                    "album": audiofile.tag.album or "",
                    "album_artist": audiofile.tag.album_artist or "",
                    "release_date": str(audiofile.tag.recording_date) if audiofile.tag.recording_date else "",
                    "comments": [c.text for c in audiofile.tag.comments] if audiofile.tag.comments else [],
                }
            return {}
        except Exception as e:
            logging.error(f"Error extracting MP3 metadata from {episode_path}: {e}")
            return {}

    def extract_metadata_from_transcript(self, transcript: str) -> Dict:
        """Extract metadata from transcript using AI."""
        prompt = """Based on the podcast transcript below, extract the following information in JSON format:
        {
            "podcast_title": "Name of the podcast series",
            "episode_title": "Title of this specific episode",
            "episode_number": "Episode number if mentioned (or null)",
            "date": "Recording or release date if mentioned (or null)",
            "hosts": ["List of host names"],
            "co_hosts": ["List of co-host names"],
            "guests": ["List of guest names"],
            "summary": "A concise but informative 2-3 paragraph summary of the episode",
            "keywords": ["List of 5-10 relevant keywords or topics discussed"]
        }

        Transcript:
        """
        prompt += transcript
        
        try:
            if self.ai_system == "ollama":
                response = self.ai_client.chat(
                    model=self.config.OLLAMA_MODEL,
                    messages=[{"role": "user", "content": prompt}]
                )
                result = response['message']['content']
            else:  # gemini
                response = self.ai_client.generate_content(prompt)
                result = response.text
            
            # Extract JSON from response
            start_idx = result.find('{')
            end_idx = result.rfind('}') + 1
            if start_idx >= 0 and end_idx > start_idx:
                json_str = result[start_idx:end_idx]
                return json.loads(json_str)
            else:
                logging.error("Could not find JSON in AI response")
                return {}
                
        except Exception as e:
            logging.error(f"Error extracting metadata from transcript: {e}")
            return {}

    def handle_metadata_extraction(self, episode_path: str) -> Optional[Dict]:
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
                    return json.load(f)
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
            
            transcript_metadata = self.extract_metadata_from_transcript(transcript)
            
            # Merge metadata, preferring MP3 metadata for overlapping fields
            metadata = {
                **transcript_metadata,
                "mp3_metadata": mp3_metadata
            }
            
            # Save metadata to file
            with open(metadata_file, 'w') as f:
                json.dump(metadata, f, indent=2)
            
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