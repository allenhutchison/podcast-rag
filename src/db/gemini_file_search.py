"""
Gemini File Search Manager for podcast transcript indexing and search.

This module provides a wrapper around Google's Gemini File Search API,
enabling semantic search over podcast transcripts with automatic embedding,
chunking, and citation support.
"""

import json
import logging
import os
import shutil
import tempfile
import time
from collections.abc import Callable
from typing import Literal, TypedDict, TypeVar

from google import genai
from google.genai.errors import APIError, ClientError

from src.utils.metadata_utils import flatten_episode_metadata

T = TypeVar('T')


# Progress callback type definition
class ProgressInfo(TypedDict, total=False):
    """Progress information passed to progress callbacks during batch operations."""
    status: Literal['start', 'progress', 'complete', 'error']
    current: int  # Current file index (0-based for start, 1-based for progress)
    total: int  # Total number of files to process
    file_path: str  # Path to current file being processed
    file_name: str  # Name of uploaded file (present on success)
    error: str  # Error message (present on error)
    uploaded_count: int  # Number of successfully uploaded files


class GeminiFileSearchManager:
    """
    Manages Gemini File Search stores for podcast transcript indexing.

    Provides methods to:
    - Create and manage File Search stores
    - Upload transcripts with metadata
    - Monitor storage quotas
    - Batch upload existing transcripts
    """

    # Gemini API maximum documents per page for list operations
    MAX_PAGE_SIZE = 20

    def __init__(self, config, dry_run=False):
        """
        Initialize the File Search manager.

        Args:
            config: Configuration object with Gemini API settings
            dry_run: If True, log operations without executing them
        """
        self.config = config
        self.dry_run = dry_run
        self.client = genai.Client(api_key=config.GEMINI_API_KEY)
        self.store_name = None
        self._store_cache = None
        self._document_metadata_cache = {}  # Cache for document metadata lookups

        logging.info("Gemini File Search Manager initialized")

    def _retry_with_backoff(
        self,
        func: Callable[[], T],
        max_retries: int = 3,
        initial_delay: float = 1.0,
        max_delay: float = 60.0,
        backoff_factor: float = 2.0
    ) -> T:
        """
        Retry a function with exponential backoff for transient errors.

        Args:
            func: Function to retry (should take no arguments)
            max_retries: Maximum number of retry attempts (default: 3)
            initial_delay: Initial delay between retries in seconds (default: 1.0)
            max_delay: Maximum delay between retries in seconds (default: 60.0)
            backoff_factor: Multiplier for delay after each retry (default: 2.0)

        Returns:
            Result of the function call

        Raises:
            The last exception if all retries are exhausted
        """
        delay = initial_delay
        last_exception = None

        for attempt in range(max_retries + 1):
            try:
                return func()
            except (APIError, ClientError) as e:
                last_exception = e

                # Don't retry on client errors (4xx) except rate limiting (429)
                if hasattr(e, 'status_code'):
                    if 400 <= e.status_code < 500 and e.status_code != 429:
                        logging.error(f"Client error (non-retryable): {e}")
                        raise

                if attempt < max_retries:
                    logging.warning(
                        f"API error on attempt {attempt + 1}/{max_retries + 1}: {e}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    time.sleep(delay)
                    delay = min(delay * backoff_factor, max_delay)
                else:
                    logging.error(f"All {max_retries + 1} attempts failed. Last error: {e}")

        raise last_exception

    def _poll_operation(self, operation, timeout: int = 300) -> None:
        """
        Poll a long-running operation until completion with timeout and error handling.

        Args:
            operation: The operation object to poll
            timeout: Maximum time to wait in seconds (default: 300 = 5 minutes)

        Raises:
            TimeoutError: If operation doesn't complete within timeout
            RuntimeError: If operation fails with an error
        """
        start_time = time.time()
        sleep_time = 0.5  # Start with 0.5 second polling

        while not operation.done:
            elapsed = time.time() - start_time

            # Check timeout
            if elapsed > timeout:
                raise TimeoutError(
                    f"Operation timed out after {timeout}s. "
                    f"Operation: {getattr(operation, 'name', 'unknown')}"
                )

            # Exponential backoff with max 5 seconds
            time.sleep(min(sleep_time, 5.0))
            sleep_time *= 1.5

            # Refresh operation status
            operation = self.client.operations.get(operation)

            # Check for operation errors
            if hasattr(operation, 'error') and operation.error:
                error_msg = str(operation.error)
                raise RuntimeError(f"Operation failed: {error_msg}")

        logging.debug(f"Operation completed in {time.time() - start_time:.2f}s")

    def _sanitize_display_name(self, name: str) -> str:
        """
        Sanitize display name to ASCII-safe characters.

        Replaces common unicode punctuation with ASCII equivalents to avoid
        encoding errors in the Gemini File Search API.

        Args:
            name: Original filename

        Returns:
            ASCII-safe filename
        """
        # Replace common unicode characters with ASCII equivalents
        replacements = {
            '\u2019': "'",  # Right single quotation mark
            '\u2018': "'",  # Left single quotation mark
            '\u201c': '"',  # Left double quotation mark
            '\u201d': '"',  # Right double quotation mark
            '\u2013': '-',  # En dash
            '\u2014': '--', # Em dash
            '\u2026': '...', # Horizontal ellipsis
        }
        result = name
        for unicode_char, ascii_char in replacements.items():
            result = result.replace(unicode_char, ascii_char)

        # Ensure the result is ASCII-encodable, replacing any remaining non-ASCII
        try:
            result.encode('ascii')
            return result
        except UnicodeEncodeError:
            # Fall back to ASCII with replacement
            return result.encode('ascii', 'replace').decode('ascii')

    def _prepare_metadata(self, metadata: dict | None) -> list[dict]:
        """
        Convert metadata dictionary to File Search custom_metadata format.

        Handles both flat dictionaries and nested EpisodeMetadata structures.
        Converts lists to comma-separated strings, truncates long values, and ensures all
        values are strings. Returns a list of key-value pairs as required by the Gemini API.

        Args:
            metadata: Dictionary of metadata values (flat or nested EpisodeMetadata)

        Returns:
            List of dicts with 'key' and 'string_value' fields for File Search custom_metadata

        Examples:
            >>> manager = GeminiFileSearchManager(config=Config(), dry_run=True)
            >>> metadata = {
            ...     'podcast': 'Tech Talk',
            ...     'episode': 'AI Episode',
            ...     'hosts': ['Alice', 'Bob'],
            ...     'release_date': '2024-01-15'
            ... }
            >>> result = manager._prepare_metadata(metadata)
            >>> len(result)
            4
            >>> result[0]
            {'key': 'podcast', 'string_value': 'Tech Talk'}
            >>> result[2]  # hosts list becomes comma-separated
            {'key': 'hosts', 'string_value': 'Alice, Bob'}

            >>> # Long values are truncated to 256 bytes (UTF-8)
            >>> long_summary = 'x' * 300
            >>> metadata = {'summary': long_summary}
            >>> result = manager._prepare_metadata(metadata)
            >>> len(result[0]['string_value'].encode('utf-8')) <= 256
            True
            >>> result[0]['string_value'].endswith('...')
            True
        """
        MAX_VALUE_BYTES = 256  # Gemini File Search limit (256 bytes in UTF-8, not characters)
        custom_metadata = []

        if not metadata:
            return custom_metadata

        # Flatten nested metadata structure using utility
        flattened = flatten_episode_metadata(metadata)

        # Convert flattened metadata to File Search format
        # 'type' field distinguishes document types: 'transcript' or 'description'
        for key in ['type', 'podcast', 'episode', 'release_date', 'hosts', 'guests', 'keywords', 'summary']:
            if key in flattened and flattened[key]:
                value = flattened[key]
                # Convert lists to comma-separated strings
                if isinstance(value, list):
                    value = ', '.join(str(v) for v in value)

                # Convert to string and truncate if necessary (based on BYTE length, not char length)
                value_str = str(value)
                value_bytes = value_str.encode('utf-8')

                if len(value_bytes) > MAX_VALUE_BYTES:
                    # Log before truncation to avoid storing original length
                    logging.warning(
                        f"Metadata field '{key}' truncated from {len(value_bytes)} bytes "
                        f"({len(value_str)} chars) to {MAX_VALUE_BYTES} bytes. "
                        f"Data loss occurred. Consider storing full metadata separately."
                    )

                    # Truncate to MAX_VALUE_BYTES - 3 bytes (for '...')
                    # Then decode, ignoring incomplete multi-byte sequences at the end
                    truncated_bytes = value_bytes[:MAX_VALUE_BYTES - 3]
                    value_str = truncated_bytes.decode('utf-8', errors='ignore') + '...'

                    # Verify final byte length is within limit
                    final_bytes = len(value_str.encode('utf-8'))
                    assert final_bytes <= MAX_VALUE_BYTES, \
                        f"Truncation error: expected <= {MAX_VALUE_BYTES} bytes, got {final_bytes}"

                custom_metadata.append({
                    'key': key,
                    'string_value': value_str
                })

        return custom_metadata

    def create_or_get_store(self, display_name: str | None = None) -> str:
        """
        Create a new File Search store or get existing one.

        Args:
            display_name: Human-readable name for the store

        Returns:
            Store resource name (e.g., 'fileSearchStores/abc123')
        """
        if self._store_cache:
            logging.debug(f"Using cached store: {self._store_cache}")
            return self._store_cache

        if display_name is None:
            display_name = self.config.GEMINI_FILE_SEARCH_STORE_NAME

        if self.dry_run:
            logging.info(f"[DRY RUN] Would create File Search store: {display_name}")
            self._store_cache = f"fileSearchStores/dry-run-{display_name}"
            return self._store_cache

        try:
            # Try to list existing stores to find one with matching display name
            stores = self.client.file_search_stores.list()
            for store in stores:
                if store.display_name == display_name:
                    logging.info(f"Found existing store: {store.name}")
                    self._store_cache = store.name
                    self.store_name = store.name
                    return store.name
        except Exception as e:
            logging.warning(f"Could not list existing stores: {e}")

        # Create new store
        try:
            store = self.client.file_search_stores.create(
                config={'display_name': display_name}
            )
            logging.info(f"Created new File Search store: {store.name}")
            self._store_cache = store.name
            self.store_name = store.name
            return store.name
        except Exception as e:
            logging.error(f"Failed to create File Search store: {e}")
            raise

    def upload_transcript(
        self,
        transcript_path: str,
        metadata: dict | None = None,
        store_name: str | None = None,
        existing_files: dict[str, str] | None = None,
        skip_existing: bool = True
    ) -> str | None:
        """
        Upload a transcript file to the File Search store.

        Args:
            transcript_path: Path to the transcript text file
            metadata: Dictionary of metadata to attach (podcast, episode, etc.)
            store_name: Store to upload to (uses default if None)
            existing_files: Dict of display_name -> file_name for existing files (to skip duplicates)
            skip_existing: If True, skip files that already exist

        Returns:
            File resource name, or None if skipped

        Examples:
            >>> manager = GeminiFileSearchManager(config=Config(), dry_run=True)
            >>> metadata = {
            ...     'podcast': 'Tech Talk',
            ...     'episode': 'Episode 1',
            ...     'hosts': ['Alice'],
            ...     'release_date': '2024-01-15'
            ... }
            >>> # Upload new file
            >>> file_name = manager.upload_transcript(
            ...     transcript_path='/path/to/episode_transcription.txt',
            ...     metadata=metadata
            ... )
            >>> file_name
            'files/dry-run-episode_transcription.txt'

            >>> # Skip existing file
            >>> existing = {'episode_transcription.txt': 'files/existing123'}
            >>> result = manager.upload_transcript(
            ...     transcript_path='/path/to/episode_transcription.txt',
            ...     existing_files=existing,
            ...     skip_existing=True
            ... )
            >>> result is None  # File was skipped
            True
        """
        # Check file exists first before making any API calls
        if not os.path.exists(transcript_path):
            raise FileNotFoundError(f"Transcript file not found: {transcript_path}")

        if store_name is None:
            store_name = self.create_or_get_store()

        # Get basename and sanitize for ASCII compatibility
        original_name = os.path.basename(transcript_path)
        display_name = self._sanitize_display_name(original_name)

        # Log if sanitization changed the name
        if display_name != original_name:
            logging.debug(f"Sanitized display name: '{original_name}' -> '{display_name}'")

        # Check if file already exists (use sanitized name for lookup)
        if skip_existing and existing_files and display_name in existing_files:
            logging.debug(f"Skipping {display_name} - already exists as {existing_files[display_name]}")
            return None

        # Prepare metadata
        custom_metadata = self._prepare_metadata(metadata)

        if self.dry_run:
            logging.info(f"[DRY RUN] Would upload {transcript_path} to {store_name}")
            logging.info(f"[DRY RUN] Metadata: {custom_metadata}")
            return f"files/dry-run-{os.path.basename(transcript_path)}"

        try:
            # Upload file with metadata
            logging.info(f"Uploading {transcript_path} to File Search store...")

            # Check if the file path contains non-ASCII characters
            # If so, copy to a temp file with ASCII-safe name to avoid SDK encoding issues
            needs_temp_file = False
            try:
                transcript_path.encode('ascii')
            except UnicodeEncodeError:
                needs_temp_file = True

            if needs_temp_file:
                # Create temp file with ASCII-safe name
                fd, tmp_path = tempfile.mkstemp(suffix='.txt', text=True)
                fd_closed = False
                try:
                    os.close(fd)  # Close the file descriptor immediately
                    fd_closed = True

                    # Copy the original file to temp location
                    shutil.copy2(transcript_path, tmp_path)

                    # Upload the temp file with retry logic
                    def _upload():
                        return self.client.file_search_stores.upload_to_file_search_store(
                            file=tmp_path,
                            file_search_store_name=store_name,
                            config={
                                'display_name': display_name,
                                'custom_metadata': custom_metadata
                            }
                        )

                    operation = self._retry_with_backoff(_upload)

                    # Poll operation until complete with timeout
                    self._poll_operation(operation)

                    logging.info(f"Successfully uploaded: {display_name}")

                    return operation.name
                except Exception:
                    # Ensure FD is closed even if an error occurred before os.close
                    if not fd_closed:
                        try:
                            os.close(fd)
                        except OSError:
                            pass  # FD already closed or invalid
                    raise
                finally:
                    # Clean up temp file
                    if os.path.exists(tmp_path):
                        os.unlink(tmp_path)
            else:
                # File path is ASCII-safe, upload directly with retry logic
                def _upload():
                    return self.client.file_search_stores.upload_to_file_search_store(
                        file=transcript_path,
                        file_search_store_name=store_name,
                        config={
                            'display_name': display_name,
                            'custom_metadata': custom_metadata
                        }
                    )

                operation = self._retry_with_backoff(_upload)

                # Poll operation until complete with timeout
                self._poll_operation(operation)

                logging.info(f"Successfully uploaded: {display_name}")

                return operation.name

        except Exception as e:
            logging.error(f"Failed to upload transcript: {e}")
            raise

    def upload_transcript_text(
        self,
        text: str,
        display_name: str,
        metadata: dict | None = None,
        store_name: str | None = None
    ) -> str:
        """
        Upload transcript text directly (without file path).

        Args:
            text: Transcript text content
            display_name: Name for the file
            metadata: Dictionary of metadata to attach
            store_name: Store to upload to (uses default if None)

        Returns:
            File resource name
        """
        if store_name is None:
            store_name = self.create_or_get_store()

        # Sanitize display name for ASCII compatibility
        sanitized_name = self._sanitize_display_name(display_name)
        if sanitized_name != display_name:
            logging.debug(f"Sanitized display name: '{display_name}' -> '{sanitized_name}'")

        # Prepare metadata
        custom_metadata = self._prepare_metadata(metadata)

        if self.dry_run:
            logging.info(f"[DRY RUN] Would upload text as {sanitized_name} to {store_name}")
            logging.info(f"[DRY RUN] Text length: {len(text)} characters")
            logging.info(f"[DRY RUN] Metadata: {custom_metadata}")
            return f"files/dry-run-{sanitized_name}"

        try:
            # Create temporary file with text content
            # Create temp file, write content, and close it before reopening
            fd, tmp_path = tempfile.mkstemp(suffix='.txt', text=True)
            try:
                # Write text to file and close the file descriptor
                with os.fdopen(fd, 'w') as tmp_file:
                    tmp_file.write(text)

                # Now upload the closed temporary file with retry logic
                def _upload():
                    return self.client.file_search_stores.upload_to_file_search_store(
                        file=tmp_path,
                        file_search_store_name=store_name,
                        config={
                            'display_name': sanitized_name,
                            'custom_metadata': custom_metadata
                        }
                    )

                operation = self._retry_with_backoff(_upload)

                # Poll operation until complete with timeout
                self._poll_operation(operation)

                logging.info(f"Successfully uploaded text as: {sanitized_name}")
                return operation.name
            finally:
                # Clean up temporary file
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)

        except Exception as e:
            logging.error(f"Failed to upload transcript text: {e}")
            raise

    def upload_description_document(
        self,
        podcast_name: str,
        description: str,
        metadata: dict | None = None,
        store_name: str | None = None
    ) -> tuple[str, str]:
        """
        Upload a podcast description document to File Search.

        Creates a text document containing the podcast description with
        type="description" metadata for filtering.

        Args:
            podcast_name: Name of the podcast
            description: Full podcast description text
            metadata: Additional metadata (will be merged with defaults)
            store_name: Store to upload to (uses default if None)

        Returns:
            Tuple of (resource_name, display_name)
        """
        # Build display name: "PodcastName_description.txt"
        safe_name = "".join(c if c.isalnum() or c in " -_" else "_" for c in podcast_name)
        safe_name = safe_name.strip()[:100]
        display_name = f"{safe_name}_description.txt"

        # Ensure type="description" is in metadata
        full_metadata = metadata.copy() if metadata else {}
        full_metadata['type'] = 'description'
        full_metadata['podcast'] = podcast_name

        resource_name = self.upload_transcript_text(
            text=description,
            display_name=display_name,
            metadata=full_metadata,
            store_name=store_name
        )

        return resource_name, display_name

    def get_store_info(self, store_name: str | None = None) -> dict:
        """
        Get information about a File Search store.

        Args:
            store_name: Store to query (uses default if None)

        Returns:
            Dictionary with store information
        """
        if store_name is None:
            store_name = self.create_or_get_store()

        if self.dry_run:
            return {
                'name': store_name,
                'display_name': 'Dry Run Store',
                'file_count': 0,
                'storage_bytes': 0
            }

        try:
            store = self.client.file_search_stores.get(name=store_name)
            return {
                'name': store.name,
                'display_name': store.display_name,
                'create_time': store.create_time,
                'update_time': store.update_time
            }
        except Exception as e:
            logging.error(f"Failed to get store info: {e}")
            raise

    def list_files(self, store_name: str | None = None) -> list[str]:
        """
        List all documents in a File Search store.

        Args:
            store_name: Store to query (uses default if None)

        Returns:
            List of document resource names
        """
        if store_name is None:
            store_name = self.create_or_get_store()

        if self.dry_run:
            return []

        try:
            # List documents in the store
            documents = self.client.file_search_stores.documents.list(parent=store_name)
            return [doc.name for doc in documents]
        except Exception as e:
            logging.error(f"Failed to list documents: {e}")
            raise

    def get_existing_files(
        self,
        store_name: str | None = None,
        show_progress: bool = False
    ) -> dict[str, str]:
        """
        Get a mapping of display names to document resource names for existing files.

        Args:
            store_name: Store to query (uses default if None)
            show_progress: If True, show progress bar during fetch (default: False)

        Returns:
            Dictionary mapping display_name -> document resource name
        """
        if store_name is None:
            store_name = self.create_or_get_store()

        if self.dry_run:
            return {}

        logging.info("Fetching file list from remote File Search store...")
        try:
            return self._fetch_files_sync(store_name, show_progress)
        except Exception as e:
            logging.error(f"Failed to list documents: {e}")
            raise

    def _extract_doc_metadata(self, doc) -> dict:
        """Extract metadata from a document object."""
        metadata = {}
        if hasattr(doc, 'custom_metadata') and doc.custom_metadata:
            for meta in doc.custom_metadata:
                if hasattr(meta, 'key') and hasattr(meta, 'string_value'):
                    metadata[meta.key] = meta.string_value
        return metadata

    def _fetch_files_sync(
        self,
        store_name: str,
        show_progress: bool = False
    ) -> dict[str, str]:
        """
        Fetch files from remote store using synchronous iteration.

        Args:
            store_name: Store to fetch from
            show_progress: Show progress bar

        Returns:
            Dictionary mapping display_name -> document resource name
        """
        files = {}

        # List documents from the store with max page size
        documents = self.client.file_search_stores.documents.list(
            parent=store_name,
            config={'page_size': self.MAX_PAGE_SIZE}
        )

        # Check for tqdm availability before starting iteration
        tqdm_module = None
        if show_progress:
            try:
                import tqdm as tqdm_module
            except ImportError:
                logging.info("Fetching files (install tqdm for progress bar)...")

        if tqdm_module:
            print("Fetching files from remote File Search store...")

            with tqdm_module.tqdm(desc="Fetching files", unit=" files") as pbar:
                for doc in documents:
                    files[doc.display_name] = doc.name
                    pbar.update(1)

            print(f"✓ Fetched {len(files)} files from remote")
        else:
            # No progress bar or tqdm not available
            count = 0
            for doc in documents:
                files[doc.display_name] = doc.name
                count += 1
                if count % 1000 == 0:
                    logging.info(f"  Fetched {count} files...")

            logging.info(f"Fetched {len(files)} files from remote")

        return files

    async def _fetch_files_async(
        self,
        store_name: str,
        show_progress: bool = False
    ) -> dict[str, str]:
        """
        Fetch files from remote store using async API.

        Uses the native async SDK support for faster iteration through
        paginated results.

        Args:
            store_name: Store to fetch from
            show_progress: Show progress bar

        Returns:
            Dictionary mapping display_name -> document resource name
        """
        files = {}

        # Use async client with max page size
        documents = await self.client.aio.file_search_stores.documents.list(
            parent=store_name,
            config={'page_size': self.MAX_PAGE_SIZE}
        )

        # Check for tqdm availability before starting iteration
        tqdm_module = None
        if show_progress:
            try:
                import tqdm as tqdm_module
            except ImportError:
                logging.info("Fetching files (install tqdm for progress bar)...")

        if tqdm_module:
            print("Fetching files from remote File Search store (async)...")

            with tqdm_module.tqdm(desc="Fetching files", unit=" files") as pbar:
                async for doc in documents:
                    files[doc.display_name] = doc.name
                    pbar.update(1)

            print(f"✓ Fetched {len(files)} files from remote")

        elif show_progress:
            # No tqdm, but progress requested - log periodically
            count = 0
            async for doc in documents:
                files[doc.display_name] = doc.name
                count += 1
                if count % 1000 == 0:
                    logging.info(f"  Fetched {count} files...")
            logging.info(f"Fetched {len(files)} files from remote")
        else:
            async for doc in documents:
                files[doc.display_name] = doc.name
            logging.info(f"Fetched {len(files)} files from remote")

        return files

    def get_existing_files_async(
        self,
        store_name: str | None = None,
        show_progress: bool = False
    ) -> dict[str, str]:
        """
        Get existing files using async API for faster fetching.

        This is a synchronous wrapper that runs the async fetch internally.

        Note: This method creates a new event loop with asyncio.run(). It will
        fail if called from within an existing async context. For async contexts,
        use _fetch_files_async() directly with await.

        Args:
            store_name: Store to query (uses default if None)
            show_progress: If True, show progress bar during fetch (default: False)

        Returns:
            Dictionary mapping display_name -> document resource name

        Raises:
            RuntimeError: If called from within an existing async event loop.
                Use the sync get_existing_files() method instead in async contexts,
                or await _fetch_files_async() directly.
        """
        import asyncio

        if store_name is None:
            store_name = self.create_or_get_store()

        if self.dry_run:
            return {}

        # Check for existing event loop to provide helpful error message
        try:
            asyncio.get_running_loop()
            # If we get here, there IS a running loop - can't use asyncio.run()
            raise RuntimeError(
                "get_existing_files_async() cannot be called from within an async context. "
                "Use get_existing_files() (sync) instead, or await _fetch_files_async() directly."
            )
        except RuntimeError as e:
            # Only proceed if it's the "no running loop" error
            if "cannot be called from within an async context" in str(e):
                raise  # Re-raise our custom error
            # Otherwise it's the expected "no running loop" case, proceed

        logging.info("Fetching file list using async API...")
        try:
            return asyncio.run(self._fetch_files_async(store_name, show_progress))
        except Exception as e:
            logging.error(f"Failed to list documents: {e}")
            raise

    def _prefetch_metadata_for_documents(self, display_names: list[str], store_name: str | None = None) -> None:
        """
        Pre-fetch and cache metadata for multiple documents in one API call.

        Args:
            display_names: List of display names to fetch
            store_name: Store to query (uses default if None)
        """
        if store_name is None:
            store_name = self.create_or_get_store()

        if self.dry_run:
            return

        # Filter out already-cached documents
        cache_keys = [f"{store_name}:{name}" for name in display_names]
        uncached_names = [
            name for name, key in zip(display_names, cache_keys, strict=False)
            if key not in self._document_metadata_cache
        ]

        if not uncached_names:
            logging.debug("All requested documents already cached")
            return

        logging.info(f"Pre-fetching metadata for {len(uncached_names)} documents...")

        try:
            # List all documents once
            documents = self.client.file_search_stores.documents.list(parent=store_name)
            uncached_set = set(uncached_names)

            for doc in documents:
                # Only process documents we're looking for
                if doc.display_name in uncached_set:
                    # Extract metadata
                    metadata = {}
                    if hasattr(doc, 'custom_metadata') and doc.custom_metadata:
                        for meta in doc.custom_metadata:
                            if hasattr(meta, 'key') and hasattr(meta, 'string_value'):
                                metadata[meta.key] = meta.string_value

                    result = {
                        'name': doc.name,
                        'display_name': doc.display_name,
                        'metadata': metadata,
                        'create_time': getattr(doc, 'create_time', None),
                        'size_bytes': getattr(doc, 'size_bytes', None)
                    }

                    # Cache the result
                    cache_key = f"{store_name}:{doc.display_name}"
                    self._document_metadata_cache[cache_key] = result

                    # Remove from set for early exit
                    uncached_set.remove(doc.display_name)

                    # Early exit if we found all requested documents
                    if not uncached_set:
                        break

            # Cache None for any documents that weren't found
            for name in uncached_set:
                cache_key = f"{store_name}:{name}"
                self._document_metadata_cache[cache_key] = None

            logging.info(f"Pre-fetched {len(uncached_names) - len(uncached_set)} documents, "
                        f"{len(uncached_set)} not found")

        except Exception as e:
            logging.error(f"Failed to pre-fetch document metadata: {e}")

    def get_document_by_resource_name(self, resource_name: str) -> dict | None:
        """
        Get document metadata by resource name (direct O(1) lookup).

        Args:
            resource_name: Full document resource name (e.g., 'fileSearchStores/.../documents/...')

        Returns:
            Dictionary with document information, or None if not found
        """
        if self.dry_run:
            return None

        # Check cache first
        cache_key = f"resource:{resource_name}"
        if cache_key in self._document_metadata_cache:
            logging.debug(f"Cache hit for resource: {resource_name}")
            return self._document_metadata_cache[cache_key]

        try:
            # Direct get by resource name - O(1) lookup!
            doc = self.client.file_search_stores.documents.get(name=resource_name)

            # Extract metadata
            metadata = {}
            if hasattr(doc, 'custom_metadata') and doc.custom_metadata:
                for meta in doc.custom_metadata:
                    if hasattr(meta, 'key') and hasattr(meta, 'string_value'):
                        metadata[meta.key] = meta.string_value

            result = {
                'name': doc.name,
                'display_name': doc.display_name,
                'metadata': metadata,
                'create_time': getattr(doc, 'create_time', None),
                'size_bytes': getattr(doc, 'size_bytes', None)
            }

            # Cache the result
            self._document_metadata_cache[cache_key] = result
            logging.debug(f"Cached document metadata for resource: {resource_name}")

            return result

        except Exception as e:
            logging.debug(f"Failed to get document by resource name {resource_name}: {e}")
            # Cache the None result to avoid repeated lookups
            self._document_metadata_cache[cache_key] = None
            return None

    def get_document_by_name(self, display_name: str, store_name: str | None = None) -> dict | None:
        """
        Get document metadata by display name.

        Uses in-memory cache to avoid expensive API calls for repeated lookups.

        Args:
            display_name: Display name of the document (e.g., 'filename.txt')
            store_name: Store to query (uses default if None)

        Returns:
            Dictionary with document information, or None if not found:
            {
                'name': str,           # Full resource name (e.g., 'fileSearchStores/.../documents/...')
                'display_name': str,   # Display name (e.g., 'episode_transcription.txt')
                'metadata': dict,      # Custom metadata as key-value pairs
                'create_time': str,    # ISO timestamp of creation
                'size_bytes': int      # Document size in bytes
            }
        """
        if store_name is None:
            store_name = self.create_or_get_store()

        if self.dry_run:
            return None

        # Check cache first
        cache_key = f"{store_name}:{display_name}"
        if cache_key in self._document_metadata_cache:
            logging.debug(f"Cache hit for document: {display_name}")
            return self._document_metadata_cache[cache_key]

        logging.debug(f"Cache miss for document: {display_name}, fetching from API...")

        try:
            # List documents and find the matching one
            documents = self.client.file_search_stores.documents.list(parent=store_name)

            for doc in documents:
                if doc.display_name == display_name:
                    # Extract metadata
                    metadata = {}
                    if hasattr(doc, 'custom_metadata') and doc.custom_metadata:
                        for meta in doc.custom_metadata:
                            if hasattr(meta, 'key') and hasattr(meta, 'string_value'):
                                metadata[meta.key] = meta.string_value

                    result = {
                        'name': doc.name,
                        'display_name': doc.display_name,
                        'metadata': metadata,
                        'create_time': getattr(doc, 'create_time', None),
                        'size_bytes': getattr(doc, 'size_bytes', None)
                    }

                    # Cache the result
                    self._document_metadata_cache[cache_key] = result
                    logging.debug(f"Cached document metadata for: {display_name}")

                    return result

            # Document not found - cache the None result to avoid repeated lookups
            self._document_metadata_cache[cache_key] = None
            return None
        except Exception as e:
            logging.error(f"Failed to get document {display_name}: {e}")
            return None

    def delete_file(self, file_name: str, force: bool = True):
        """
        Delete a document from the File Search store.

        Args:
            file_name: Document resource name to delete
            force: If True, delete the document and all its chunks (default: True)
        """
        if self.dry_run:
            logging.info(f"[DRY RUN] Would delete document: {file_name}")
            return

        try:
            self.client.file_search_stores.documents.delete(
                name=file_name,
                config={'force': force}
            )
            logging.info(f"Deleted document: {file_name}")
        except Exception as e:
            logging.error(f"Failed to delete document: {e}")
            raise

    def batch_upload_directory(
        self,
        directory_path: str,
        pattern: str = "*_transcription.txt",
        metadata_pattern: str = "*_metadata.json",
        progress_callback: Callable[[ProgressInfo], None] | None = None
    ) -> dict[str, str]:
        """
        Batch upload all transcripts from a directory.

        Args:
            directory_path: Directory containing transcripts
            pattern: Glob pattern for transcript files
            metadata_pattern: Glob pattern for metadata files
            progress_callback: Optional callback function that receives ProgressInfo
                with status, progress counts, file paths, and error information.
                See ProgressInfo TypedDict for full structure.

        Returns:
            Dictionary mapping file paths to uploaded file names
        """
        import glob

        store_name = self.create_or_get_store()
        uploaded_files = {}

        # Find all transcript files
        transcript_files = glob.glob(os.path.join(directory_path, '**', pattern), recursive=True)

        logging.info(f"Found {len(transcript_files)} transcript files to upload")

        # Notify start of batch operation
        if progress_callback:
            progress_callback({
                'status': 'start',
                'current': 0,
                'total': len(transcript_files),
                'file_path': '',
                'uploaded_count': 0
            })

        for idx, transcript_path in enumerate(transcript_files):
            # Try to find corresponding metadata file
            metadata = None
            base_path = transcript_path.replace('_transcription.txt', '')
            metadata_path = f"{base_path}_metadata.json"

            if os.path.exists(metadata_path):
                try:
                    with open(metadata_path) as f:
                        metadata = json.load(f)
                except Exception as e:
                    logging.warning(f"Failed to load metadata from {metadata_path}: {e}")

            try:
                file_name = self.upload_transcript(
                    transcript_path=transcript_path,
                    metadata=metadata,
                    store_name=store_name
                )
                uploaded_files[transcript_path] = file_name
                logging.info(f"Uploaded {transcript_path} → {file_name}")

                # Notify progress - successful upload
                if progress_callback:
                    progress_callback({
                        'status': 'progress',
                        'current': idx + 1,
                        'total': len(transcript_files),
                        'file_path': transcript_path,
                        'file_name': file_name,
                        'uploaded_count': len(uploaded_files)
                    })
            except Exception as e:
                logging.error(f"Failed to upload {transcript_path}: {e}")

                # Notify progress - failed upload
                if progress_callback:
                    progress_callback({
                        'status': 'error',
                        'current': idx + 1,
                        'total': len(transcript_files),
                        'file_path': transcript_path,
                        'error': str(e),
                        'uploaded_count': len(uploaded_files)
                    })

        logging.info(f"Batch upload complete: {len(uploaded_files)}/{len(transcript_files)} files uploaded")

        # Notify completion
        if progress_callback:
            progress_callback({
                'status': 'complete',
                'current': len(transcript_files),
                'total': len(transcript_files),
                'file_path': '',
                'uploaded_count': len(uploaded_files)
            })

        return uploaded_files
