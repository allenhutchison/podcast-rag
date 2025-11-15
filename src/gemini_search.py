"""
Gemini File Search-based search manager for podcast transcripts.

This module provides a search interface compatible with the old ChromaDB-based
VectorDbSearchManager, but uses Google's Gemini File Search under the hood.
"""

import json
import logging
from typing import Dict, List

from google import genai
from google.genai import types

from src.config import Config
from src.db.gemini_file_search import GeminiFileSearchManager


class GeminiSearchManager:
    """
    Search manager using Gemini File Search.

    Provides a compatible interface with VectorDbSearchManager for backward
    compatibility with existing code (e.g., MCP server).
    """

    def __init__(self, config: Config, dry_run=False):
        """
        Initialize the Gemini search manager.

        Args:
            config: Configuration object
            dry_run: If True, log operations without executing
        """
        self.config = config
        self.dry_run = dry_run

        # Validate model compatibility with File Search
        if not dry_run:
            config.validate_file_search_model()

        # Initialize Gemini client
        self.client = genai.Client(api_key=config.GEMINI_API_KEY)
        self.store_name = None

        # Initialize file search manager for compatibility
        self.file_search_manager = GeminiFileSearchManager(config=config, dry_run=dry_run)

        logging.debug(f"Initialized Gemini File Search Manager")

    def _ensure_store(self):
        """Ensure File Search store is available."""
        if self.store_name is None:
            try:
                # Try to find existing store
                stores = self.client.file_search_stores.list()
                for store in stores:
                    if store.display_name == self.config.GEMINI_FILE_SEARCH_STORE_NAME:
                        self.store_name = store.name
                        logging.info(f"Using existing File Search store: {self.store_name}")
                        return self.store_name
            except Exception as e:
                logging.warning(f"Could not list stores: {e}")

            # Create new store if not found
            try:
                store = self.client.file_search_stores.create(
                    config={'display_name': self.config.GEMINI_FILE_SEARCH_STORE_NAME}
                )
                self.store_name = store.name
                logging.info(f"Created new File Search store: {self.store_name}")
            except Exception as e:
                logging.error(f"Failed to create File Search store: {e}")
                raise

        return self.store_name

    def search_transcriptions(self, query: str, print_results=True) -> Dict:
        """
        Search podcast transcriptions using Gemini File Search.

        Args:
            query: Search query string
            print_results: If True, print results to console

        Returns:
            Dictionary with 'documents' and 'metadatas' keys (compatible format)
        """
        if self.dry_run:
            logging.info(f"[DRY RUN] Would search for: {query}")
            return {
                'documents': [[]],
                'metadatas': [[]]
            }

        try:
            store_name = self._ensure_store()

            # Perform File Search query
            response = self.client.models.generate_content(
                model=self.config.GEMINI_MODEL,
                contents=query,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(
                        file_search=types.FileSearch(
                            file_search_store_names=[store_name]
                        )
                    )],
                    response_modalities=["TEXT"]
                )
            )

            # Extract grounding metadata
            grounding_metadata = None
            if hasattr(response, 'candidates') and len(response.candidates) > 0:
                candidate = response.candidates[0]
                if hasattr(candidate, 'grounding_metadata'):
                    grounding_metadata = candidate.grounding_metadata

            # Convert grounding metadata to compatible format
            documents = []
            metadatas = []

            if grounding_metadata and hasattr(grounding_metadata, 'file_search_citations'):
                for citation in grounding_metadata.file_search_citations:
                    # Each citation represents a relevant chunk
                    # Note: We don't get the actual text content in the same way
                    # but we can provide the citation info
                    chunk_text = f"[File: {citation.file_id}, Chunk: {citation.chunk_index}]"
                    documents.append(chunk_text)

                    # Build metadata from citation
                    metadata = {
                        'file_id': citation.file_id,
                        'chunk_index': getattr(citation, 'chunk_index', 0),
                        'score': getattr(citation, 'score', 0.0),
                        # We don't have the original metadata here, would need file lookup
                        'source': 'file_search'
                    }
                    metadatas.append(metadata)

            if print_results:
                self.pretty_print_results({'documents': [documents], 'metadatas': [metadatas]})

            # Return in compatible format
            return {
                'documents': [documents],
                'metadatas': [metadatas],
                'response_text': response.text if hasattr(response, 'text') else ''
            }

        except Exception as e:
            logging.error(f"Search failed: {e}")
            raise

    def pretty_print_results(self, results: Dict):
        """
        Pretty print the search results.

        Args:
            results: Search results dictionary
        """
        logging.debug(json.dumps(results, indent=4, sort_keys=True))

        for document_list, metadata_list in zip(results['documents'], results['metadatas']):
            for document, metadata in zip(document_list, metadata_list):
                file_id = metadata.get('file_id', 'Unknown')
                chunk_idx = metadata.get('chunk_index', 'Unknown')
                score = metadata.get('score', 0.0)
                print(f"File: {file_id}, Chunk: {chunk_idx}, Score: {score:.3f}")
                print(f"Content: {document[:200]}...\n")


# Backward compatibility alias
VectorDbSearchManager = GeminiSearchManager


def main():
    """Command-line interface for Gemini search."""
    import argparse

    parser = argparse.ArgumentParser(description="Podcast Transcript Search with Gemini File Search")
    parser.add_argument("-e", "--env-file", help="Path to a custom .env file", default=None)
    parser.add_argument("-l", "--log-level", help="Set log level (DEBUG, INFO, WARNING, ERROR)", default="INFO")
    parser.add_argument("-q", "--query", help="Query to search", required=True)
    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), "INFO"),
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler()]
    )

    config = Config(env_file=args.env_file)
    manager = GeminiSearchManager(config)
    results = manager.search_transcriptions(args.query, print_results=True)

    print("\n" + "="*80)
    print("SEARCH RESULTS:")
    print("="*80)
    if 'response_text' in results and results['response_text']:
        print(results['response_text'])
    print("="*80)


if __name__ == "__main__":
    main()
