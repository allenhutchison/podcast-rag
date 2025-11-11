import logging
import os

import chromadb
from nltk.tokenize import sent_tokenize

from src.config import Config


class VectorDbManager:
    def __init__(self, config: Config, dry_run=False):
        self.config = config
        self.dry_run = dry_run
        self.client = chromadb.HttpClient(host=config.CHROMA_DB_HOST, port=config.CHROMA_DB_PORT, ssl=True)
        self.collection = self.client.get_or_create_collection(config.CHROMA_DB_COLLECTION)
        self.stats = {
            "already_indexed": 0,
            "waiting_for_indexing": 0,
            "indexed_now": 0,
        }

    def split_transcript_into_chunks(self, transcript, max_chunk_size=500, overlap_size=50):
        """
        Splits a transcript into chunks with a specified maximum size and overlap.

        Parameters:
            transcript (str): The full text of the transcript.
            max_chunk_size (int): Maximum number of words per chunk.
            overlap_size (int): Number of words to overlap between chunks.

        Returns:
            list of str: A list containing the transcript chunks.
        """
        sentences = sent_tokenize(transcript)
        chunks = []
        current_chunk = []
        current_length = 0

        for sentence in sentences:
            sentence_words = sentence.split()
            sentence_length = len(sentence_words)

            if current_length + sentence_length > max_chunk_size:
                # Add the current chunk to the list
                chunks.append(' '.join(current_chunk))
                
                # Start a new chunk with overlap
                if overlap_size > 0:
                    # Get the last 'overlap_size' words
                    overlap_words = current_chunk[-overlap_size:]
                    current_chunk = overlap_words.copy()
                    current_length = len(' '.join(current_chunk).split())
                else:
                    current_chunk = []
                    current_length = 0

            current_chunk.append(sentence)
            current_length += sentence_length

        # Add any remaining sentences as the last chunk
        if current_chunk:
            chunks.append(' '.join(current_chunk))

        return chunks

    def handle_indexing(self, episode_path, metadata=None):
        '''Handle indexing for a given episode file.'''
        index_file = self.build_index_file(episode_path)
        temp_file = self.build_temp_file(index_file)

        if self.is_indexing_in_progress(temp_file):
            self.handle_incomplete_indexing(episode_path, temp_file)
        elif self.index_exists(index_file):
            logging.debug(f"Skipping {episode_path}: index already exists.")
            self.stats["already_indexed"] += 1
        else:
            if self.dry_run:
                logging.debug(f"Dry run: Would index {episode_path}")
                self.stats["waiting_for_indexing"] += 1
            else:
                self.start_indexing(episode_path, index_file, temp_file, metadata)

    def start_indexing(self, episode_path, index_file, temp_file, metadata=None):
        '''Run the indexing process using ChromaDB.'''
        logging.info(f"Starting indexing for {episode_path}")

        podcast_name = os.path.basename(os.path.dirname(episode_path))
        file_name = os.path.basename(episode_path)

        transcription_file = self.config.build_transcription_file(episode_path)
        with open(transcription_file, 'r') as f:
            transcript = f.read()
        
        chunks = self.split_transcript_into_chunks(transcript)
        logging.debug(f"Split transcript into {len(chunks)} chunks.")

        if self.dry_run:
            logging.debug(f"Dry run: Would add embeddings for {len(chunks)} chunks of {podcast_name} - {file_name}")
        else:
            open(temp_file, 'w').close()
            index_file_handle = open(index_file, 'w')
            
            # Prepare base metadata with preference for MP3 metadata
            episode_title = file_name
            if metadata:
                if metadata.mp3_metadata and metadata.mp3_metadata.title:
                    episode_title = metadata.mp3_metadata.title
                elif metadata.transcript_metadata and metadata.transcript_metadata.episode_title:
                    episode_title = metadata.transcript_metadata.episode_title

            base_metadata = {
                "podcast": metadata.transcript_metadata.podcast_title if metadata else podcast_name,
                "episode": episode_title,
                "release_date": metadata.mp3_metadata.release_date if metadata and metadata.mp3_metadata else "",
                "hosts": ", ".join(metadata.transcript_metadata.hosts) if metadata else "",
                "co_hosts": ", ".join(metadata.transcript_metadata.co_hosts) if metadata else "",
                "guests": ", ".join(metadata.transcript_metadata.guests) if metadata else "",
                "keywords": ", ".join(metadata.transcript_metadata.keywords) if metadata else "",
                "episode_number": str(metadata.transcript_metadata.episode_number) if metadata and metadata.transcript_metadata.episode_number else "",
                "summary": metadata.transcript_metadata.summary if metadata else ""
            }
            
            for i, chunk in enumerate(chunks):
                chunk_id = f"{podcast_name}-{file_name}-chunk-{i}"
                chunk_metadata = {
                    **base_metadata,
                    "chunk": i,
                }
                self.collection.upsert(
                    documents=[chunk],  # Add the chunk text
                    ids=[chunk_id],     # Unique ID for the chunk
                    metadatas=[chunk_metadata]  # Metadata for later querying
                )
                index_file_handle.write(f"{chunk_id}\n")
                index_file_handle.write(f"{chunk}\n")
            
            index_file_handle.close()
            os.remove(temp_file)  # Remove the temp file to indicate indexing is complete
            self.stats["indexed_now"] += 1
            logging.debug(f"Successfully indexed {len(chunks)} chunks for {podcast_name} - {file_name}")

    def index_exists(self, index_file):
        '''Check if the index file already exists.'''
        return os.path.exists(index_file) and os.path.getsize(index_file) > 0

    def is_indexing_in_progress(self, temp_file):
        '''Check if indexing is in progress.'''
        return os.path.exists(temp_file)

    def handle_incomplete_indexing(self, episode_path, temp_file):
        '''Handle incomplete indexing by removing temp file.'''
        logging.info(f"Detected unfinished indexing for {episode_path}.")
        os.remove(temp_file)

    def build_index_file(self, episode_path):
        '''Build the path for the index file.'''
        return os.path.splitext(episode_path)[0] + self.config.INDEX_OUTPUT_SUFFIX

    def build_temp_file(self, index_file):
        '''Build the path for the temp file.'''
        return index_file + self.config.INDEX_TEMP_FILE_SUFFIX

    def log_stats(self):
        '''Log indexing statistics.'''
        logging.info(f"Already indexed: {self.stats['already_indexed']}")
        if self.dry_run:
            logging.info(f"Waiting for indexing: {self.stats['waiting_for_indexing']}")
        else:
            logging.info(f"Indexed during this run: {self.stats['indexed_now']}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Podcast Transcript Indexer with Chroma")
    parser.add_argument("-d", "--dry-run", action="store_true", help="Perform a dry run without actual indexing")
    parser.add_argument("-e", "--env-file", help="Path to a custom .env file", default=None)
    parser.add_argument("-l", "--log-level", help="Set log level (DEBUG, INFO, WARNING, ERROR)", default="INFO")
    parser.add_argument("-p", "--episode-path", help="Path to an MP3 file", default=None)
    args = parser.parse_args()

    # Configure logging based on command-line argument
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), "INFO"),  # Default to INFO if invalid log level
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler()]
    )

    config = Config()  # Initialize config
    manager = VectorDbManager(config, dry_run=args.dry_run)
    manager.handle_indexing(args.episode_path)
    manager.log_stats()

if __name__ == "__main__":
    main()
