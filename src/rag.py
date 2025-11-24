"""
RAG Manager using Gemini File Search for podcast transcript queries.

This module provides a simplified RAG interface that leverages Google's
hosted File Search solution for automatic semantic search with citations.
"""

import logging
import json
from typing import Dict, List, Optional, TypedDict

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


# Citation type definitions
class LegacyCitation(TypedDict):
    """Legacy citation format from file_search_citations."""
    file_id: Optional[str]
    chunk_index: Optional[int]
    score: Optional[float]


class GroundingCitation(TypedDict):
    """Modern citation format from grounding_chunks."""
    index: int
    title: str
    text: str
    uri: Optional[str]


# Union type for citations (can be either format)
Citation = LegacyCitation | GroundingCitation


class RagManager:
    """
    Manages RAG queries using Gemini File Search.

    Uses Google's hosted File Search to automatically retrieve relevant
    transcript chunks and generate responses with proper citations.
    """

    # Maximum length for citation excerpts displayed in CLI
    MAX_EXCERPT_LENGTH = 300

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
            Generated response text with inline citations
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

            # Add inline citations
            response_text = self._add_inline_citations(response_text)

            if self.print_results:
                logging.info(f"Response: {response_text}")
                if self.last_grounding_metadata:
                    logging.info(f"Grounding metadata: {self.last_grounding_metadata}")

            return response_text

        except Exception as e:
            logging.error(f"Query failed: {e}")
            raise

    def _add_inline_citations(self, text: str) -> str:
        """
        Add inline citation markers to the response text.

        Args:
            text: Original response text

        Returns:
            Text with inline citations like [1], [2], etc.
        """
        if not self.last_grounding_metadata:
            return text

        if not hasattr(self.last_grounding_metadata, 'grounding_supports'):
            return text

        grounding_supports = self.last_grounding_metadata.grounding_supports
        if grounding_supports is None:
            return text

        # Build a map of text positions to citation indices
        # We'll insert citations after segments they support
        citation_inserts = []

        for support in grounding_supports:
            if hasattr(support, 'segment') and hasattr(support, 'grounding_chunk_indices'):
                segment = support.segment
                chunk_indices = support.grounding_chunk_indices

                if hasattr(segment, 'end_index') and chunk_indices:
                    # Convert chunk indices to citation numbers (1-based)
                    citation_nums = [idx + 1 for idx in chunk_indices]
                    citation_text = ''.join(f'[{num}]' for num in citation_nums)

                    citation_inserts.append({
                        'position': segment.end_index,
                        'text': citation_text
                    })

        # Sort by position in reverse order so we can insert without messing up indices
        citation_inserts.sort(key=lambda x: x['position'], reverse=True)

        # Insert citations with position validation
        result = text
        for insert in citation_inserts:
            pos = insert['position']
            cite = insert['text']
            # Validate position is within valid range
            if 0 <= pos <= len(result):
                result = result[:pos] + cite + result[pos:]
            else:
                logging.warning(
                    f"Invalid citation position {pos} for text length {len(result)}, skipping"
                )

        return result

    def get_citations(self) -> List[Citation]:
        """
        Get citations from the last query's grounding metadata.

        Returns:
            List of citation dictionaries with file and chunk information.
            Can be either LegacyCitation or GroundingCitation format depending
            on the API response structure.

        Examples:
            >>> rag = RagManager(config=Config(), dry_run=True)
            >>> response = rag.query("What is discussed in episode 5?")
            >>> citations = rag.get_citations()
            >>> len(citations)  # Number of source chunks
            3
            >>> citations[0].keys()
            dict_keys(['index', 'title', 'text', 'uri'])
            >>> citations[0]['title']
            'episode5_transcription.txt'
            >>> citations[0]['text'][:50]  # Preview of source text
            'In this episode, we discuss the fundamentals of...'

            >>> # Citations are empty before first query
            >>> rag = RagManager(config=Config(), dry_run=True)
            >>> rag.get_citations()
            []
        """
        if not self.last_grounding_metadata:
            return []

        citations = []

        # Parse grounding metadata structure - try both old and new formats
        if hasattr(self.last_grounding_metadata, 'file_search_citations'):
            # Old format
            file_search_citations = self.last_grounding_metadata.file_search_citations
            if file_search_citations is not None:
                for citation in file_search_citations:
                    citations.append({
                        'file_id': getattr(citation, 'file_id', None),
                        'chunk_index': getattr(citation, 'chunk_index', None),
                        'score': getattr(citation, 'score', None)
                    })
        elif hasattr(self.last_grounding_metadata, 'grounding_chunks'):
            # New format with grounding_chunks
            grounding_chunks = self.last_grounding_metadata.grounding_chunks
            if grounding_chunks is not None:
                for i, chunk in enumerate(grounding_chunks):
                    if hasattr(chunk, 'retrieved_context'):
                        context = chunk.retrieved_context
                        title = getattr(context, 'title', 'Unknown')
                        logging.debug(f"Citation {i}: title='{title}'")
                        citations.append({
                            'index': i,
                            'title': title,
                            'text': getattr(context, 'text', ''),
                            'uri': getattr(context, 'uri', None)
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
        print("\n" + "="*80)
        print("SOURCES & CITATIONS:")
        print("="*80)

        for i, citation in enumerate(citations, 1):
            # Handle both old and new citation formats
            if 'title' in citation:
                # New format with grounding chunks
                title = citation.get('title', 'Unknown')
                text = citation.get('text', '')

                # Fetch document metadata from cache (instant - no API calls!)
                doc_info = rag_manager.file_search_manager.get_document_metadata_from_cache(title)

                print(f"\n[{i}]", end='')

                # Display metadata if available
                if doc_info and doc_info.get('metadata'):
                    metadata = doc_info['metadata']

                    # Format: Podcast - Episode (Year) - Host
                    parts = []
                    if metadata.get('podcast'):
                        parts.append(metadata['podcast'])
                    if metadata.get('episode'):
                        parts.append(metadata['episode'])

                    if parts:
                        print(f" {' - '.join(parts)}", end='')

                    if metadata.get('release_date'):
                        print(f" ({metadata['release_date']})", end='')

                    if metadata.get('hosts'):
                        print(f" - Host: {metadata['hosts']}", end='')

                    print()  # Newline after metadata
                else:
                    # Fallback to filename if no metadata
                    print(f" {title}")

                print("-" * 80)

                # Show text excerpt (truncate if too long)
                if text:
                    excerpt = text.strip()
                    if len(excerpt) > RagManager.MAX_EXCERPT_LENGTH:
                        excerpt = excerpt[:RagManager.MAX_EXCERPT_LENGTH - 3] + "..."
                    print(excerpt)
                else:
                    print("(No text preview available)")

            else:
                # Old format
                print(f"\n[{i}] File: {citation.get('file_id', 'N/A')}, "
                      f"Chunk: {citation.get('chunk_index', 'N/A')}, "
                      f"Score: {citation.get('score', 'N/A'):.3f}")

        print("\n" + "="*80)
