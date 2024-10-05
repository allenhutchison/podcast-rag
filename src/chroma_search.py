
import os
import logging
from config import Config
import chromadb
from nltk.tokenize import sent_tokenize
import json

class VectorDbSearchManager:
    def __init__(self, config: Config, dry_run=False):
        self.config = config
        self.dry_run = dry_run
        logging.debug(f"Connecting to Chroma DB at {config.CHROMA_DB_HOST}:{config.CHROMA_DB_PORT}")
        self.client = chromadb.HttpClient(host=config.CHROMA_DB_HOST, port=config.CHROMA_DB_PORT, ssl=True)
        self.collection = self.client.get_collection(config.CHROMA_DB_COLLECTION)

    def pretty_print_chromadb_results(self, results):
        """
        Pretty print the ChromaDB search results.
        
        Args:
            results (list or dict): The search results from ChromaDB.
        """
        logging.debug(json.dumps(results, indent=4, sort_keys=True))

    # Function to search Chroma for relevant podcast transcriptions
    def search_transcriptions(self, query):
        # Query the collection using the query embeddings
        results = self.collection.query(
            query_texts=[query],  
            n_results=10  # Number of relevant chunks to return
        )
        self.pretty_print_chromadb_results(results)
        for document_list, metadata_list in zip(results['documents'], results['metadatas']):
            for document, metadata in zip(document_list, metadata_list):
                podcast = metadata.get('podcast', 'Unknown Podcast')
                episode = metadata.get('episode', 'Unknown Episode')
                transcription = document.strip()
                print(f"Relevant Episode: {podcast} Episode: {episode}\nTranscription Snippet: {transcription[:200]}...\n")
        return results


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Podcast Transcript Search with Chroma")
    parser.add_argument("-e", "--env-file", help="Path to a custom .env file", default=None)
    parser.add_argument("-l", "--log-level", help="Set log level (DEBUG, INFO, WARNING, ERROR)", default="INFO")
    parser.add_argument("-q", "--query", help="Query to search", required=True)
    args = parser.parse_args()

    # Configure logging based on command-line argument
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), "INFO"),  # Default to INFO if invalid log level
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler()]
    )

    config = Config(env_file=args.env_file)
    manager = VectorDbSearchManager(config)
    manager.search_transcriptions(args.query)
    

if __name__ == "__main__":
    main()
