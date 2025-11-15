"""
RAG Manager using Gemini File Search for podcast transcript queries.

This module provides a simplified RAG interface that leverages Google's
hosted File Search solution for automatic semantic search with citations.
"""

import logging
import json
from typing import Dict, List, Optional

from google import genai
from google.genai import types

from src.argparse_shared import (
    add_dry_run_argument,
    add_log_level_argument,
    add_query_argument,
    get_base_parser
)
from src.config import Config
from src.db.gemini_file_search import GeminiFileSearchManager


class RagManager:
    """
    Manages RAG queries using Gemini File Search.

    Uses Google's hosted File Search to automatically retrieve relevant
    transcript chunks and generate responses with proper citations.
    """

    def __init__(self, config: Config, dry_run=False, print_results=True):
        """
        Initialize the RAG manager.

        Args:
            config: Configuration object
            dry_run: If True, log operations without executing
            print_results: If True, log detailed results
        """
        self.config = config
        self.dry_run = dry_run
        self.print_results = print_results

        # Validate model compatibility with File Search
        if not dry_run:
            config.validate_file_search_model()

        # Initialize Gemini client (newer SDK)
        self.client = genai.Client(api_key=config.GEMINI_API_KEY)

        # Initialize File Search manager
        self.file_search_manager = GeminiFileSearchManager(config=config, dry_run=dry_run)
        self.store_name = None

        # Cache for last query results
        self.last_query = None
        self.last_response = None
        self.last_grounding_metadata = None

        logging.info("RAG Manager initialized with Gemini File Search")

    def _ensure_store(self):
        """Ensure File Search store is created and cached."""
        if self.store_name is None:
            self.store_name = self.file_search_manager.create_or_get_store()
        return self.store_name

    def query(self, query: str) -> str:
        """
        Query the podcast archive using File Search.

        Args:
            query: User's question

        Returns:
            Generated response text
        """
        self.last_query = query
        logging.info(f"Processing query: {query}")

        store_name = self._ensure_store()

        if self.dry_run:
            logging.info(f"[DRY RUN] Would query File Search with: {query}")
            return "This is a dry run response."

        try:
            # Query using File Search tool
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

            # Cache the response and grounding metadata
            self.last_response = response

            # Extract grounding metadata if available
            if hasattr(response, 'candidates') and len(response.candidates) > 0:
                candidate = response.candidates[0]
                if hasattr(candidate, 'grounding_metadata'):
                    self.last_grounding_metadata = candidate.grounding_metadata

            # Get response text
            response_text = response.text if hasattr(response, 'text') else str(response)

            if self.print_results:
                logging.info(f"Response: {response_text}")
                if self.last_grounding_metadata:
                    logging.info(f"Grounding metadata: {self.last_grounding_metadata}")

            return response_text

        except Exception as e:
            logging.error(f"Query failed: {e}")
            raise

    def get_citations(self) -> List[Dict]:
        """
        Get citations from the last query's grounding metadata.

        Returns:
            List of citation dictionaries with file and chunk information
        """
        if not self.last_grounding_metadata:
            return []

        citations = []

        # Parse grounding metadata structure
        if hasattr(self.last_grounding_metadata, 'file_search_citations'):
            for citation in self.last_grounding_metadata.file_search_citations:
                citations.append({
                    'file_id': getattr(citation, 'file_id', None),
                    'chunk_index': getattr(citation, 'chunk_index', None),
                    'score': getattr(citation, 'score', None)
                })

        return citations

    def search_snippets(self, query: Optional[str] = None) -> str:
        """
        Get search snippets with citations for the last query.

        Args:
            query: Optional query (uses last query if None)

        Returns:
            JSON string of snippets with metadata
        """
        if query and query != self.last_query:
            logging.warning("Query differs from last cached query")
            # Re-run query to get fresh results
            self.query(query)

        citations = self.get_citations()

        # Convert citations to snippet format
        snippets = []
        for i, citation in enumerate(citations):
            snippets.append({
                'index': i + 1,
                'file_id': citation.get('file_id', ''),
                'chunk_index': citation.get('chunk_index', 0),
                'score': citation.get('score', 0.0)
            })

        return json.dumps(snippets, indent=2)


if __name__ == "__main__":
    import argparse

    parser = get_base_parser()
    parser.description = "Query podcast transcriptions using Gemini File Search"

    add_dry_run_argument(parser)
    add_log_level_argument(parser)
    add_query_argument(parser)

    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), "INFO"),
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler()]
    )

    config = Config(env_file=args.env_file)
    rag_manager = RagManager(config=config, print_results=True)

    result = rag_manager.query(args.query)
    print("\n" + "="*80)
    print("ANSWER:")
    print("="*80)
    print(result)
    print("="*80)

    # Show citations if available
    citations = rag_manager.get_citations()
    if citations:
        print("\nCITATIONS:")
        print("="*80)
        for i, citation in enumerate(citations, 1):
            print(f"{i}. File: {citation.get('file_id', 'N/A')}, "
                  f"Chunk: {citation.get('chunk_index', 'N/A')}, "
                  f"Score: {citation.get('score', 'N/A'):.3f}")
        print("="*80)
