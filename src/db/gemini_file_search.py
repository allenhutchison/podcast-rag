"""
Gemini File Search Manager for podcast transcript indexing and search.

This module provides a wrapper around Google's Gemini File Search API,
enabling semantic search over podcast transcripts with automatic embedding,
chunking, and citation support.
"""

import logging
import os
import time
from typing import Dict, List, Optional

from google import genai
from google.genai import types

from src.utils.metadata_utils import flatten_episode_metadata


class GeminiFileSearchManager:
    """
    Manages Gemini File Search stores for podcast transcript indexing.

    Provides methods to:
    - Create and manage File Search stores
    - Upload transcripts with metadata
    - Monitor storage quotas
    - Batch upload existing transcripts
    """

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

        logging.info("Gemini File Search Manager initialized")

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

    def _prepare_metadata(self, metadata: Optional[Dict]) -> List[Dict]:
        """
        Convert metadata dictionary to File Search custom_metadata format.

        Handles both flat dictionaries and nested EpisodeMetadata structures.
        Converts lists to comma-separated strings, truncates long values, and ensures all
        values are strings. Returns a list of key-value pairs as required by the Gemini API.

        Args:
            metadata: Dictionary of metadata values (flat or nested EpisodeMetadata)

        Returns:
            List of dicts with 'key' and 'string_value' fields for File Search custom_metadata
        """
        MAX_VALUE_LENGTH = 255  # Gemini File Search limit (must be < 256)
        custom_metadata = []

        if not metadata:
            return custom_metadata

        # Flatten nested metadata structure using utility
        flattened = flatten_episode_metadata(metadata)

        # Convert flattened metadata to File Search format
        for key in ['podcast', 'episode', 'release_date', 'hosts', 'guests', 'keywords', 'summary']:
            if key in flattened and flattened[key]:
                value = flattened[key]
                # Convert lists to comma-separated strings
                if isinstance(value, list):
                    value = ', '.join(str(v) for v in value)

                # Convert to string and truncate if necessary
                value_str = str(value)
                if len(value_str) > MAX_VALUE_LENGTH:
                    # Truncate and add ellipsis (ensure total is <= 255)
                    value_str = value_str[:MAX_VALUE_LENGTH-3] + '...'
                    logging.debug(f"Truncated metadata '{key}' from {len(str(value))} to {len(value_str)} chars")

                custom_metadata.append({
                    'key': key,
                    'string_value': value_str
                })

        return custom_metadata

    def create_or_get_store(self, display_name: Optional[str] = None) -> str:
        """
        Create a new File Search store or get existing one.

        Args:
            display_name: Human-readable name for the store

        Returns:
            Store resource name (e.g., 'fileSearchStores/abc123')
        """
        if self._store_cache:
            logging.info(f"Using cached store: {self._store_cache}")
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
        metadata: Optional[Dict] = None,
        store_name: Optional[str] = None,
        existing_files: Optional[Dict[str, str]] = None,
        skip_existing: bool = True
    ) -> Optional[str]:
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
            logging.info(f"Skipping {display_name} - already exists as {existing_files[display_name]}")
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
                import tempfile
                import shutil

                # Create temp file with ASCII-safe name
                fd, tmp_path = tempfile.mkstemp(suffix='.txt', text=True)
                os.close(fd)  # Close the file descriptor

                try:
                    # Copy the original file to temp location
                    shutil.copy2(transcript_path, tmp_path)

                    # Upload the temp file
                    operation = self.client.file_search_stores.upload_to_file_search_store(
                        file=tmp_path,
                        file_search_store_name=store_name,
                        config={
                            'display_name': display_name,
                            'custom_metadata': custom_metadata
                        }
                    )

                    # Poll operation until complete
                    while not operation.done:
                        time.sleep(1)
                        operation = self.client.operations.get(operation)

                    logging.info(f"Successfully uploaded: {display_name}")
                    return operation.name
                finally:
                    # Clean up temp file
                    if os.path.exists(tmp_path):
                        os.unlink(tmp_path)
            else:
                # File path is ASCII-safe, upload directly
                operation = self.client.file_search_stores.upload_to_file_search_store(
                    file=transcript_path,
                    file_search_store_name=store_name,
                    config={
                        'display_name': display_name,
                        'custom_metadata': custom_metadata
                    }
                )

                # Poll operation until complete
                while not operation.done:
                    time.sleep(1)
                    operation = self.client.operations.get(operation)

                logging.info(f"Successfully uploaded: {display_name}")
                return operation.name

        except Exception as e:
            logging.error(f"Failed to upload transcript: {e}")
            raise

    def upload_transcript_text(
        self,
        text: str,
        display_name: str,
        metadata: Optional[Dict] = None,
        store_name: Optional[str] = None
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
            import tempfile
            # Create temp file, write content, and close it before reopening
            fd, tmp_path = tempfile.mkstemp(suffix='.txt', text=True)
            try:
                # Write text to file and close the file descriptor
                with os.fdopen(fd, 'w') as tmp_file:
                    tmp_file.write(text)

                # Now upload the closed temporary file
                operation = self.client.file_search_stores.upload_to_file_search_store(
                    file=tmp_path,
                    file_search_store_name=store_name,
                    config={
                        'display_name': sanitized_name,
                        'custom_metadata': custom_metadata
                    }
                )

                # Poll operation until complete
                while not operation.done:
                    time.sleep(1)
                    operation = self.client.operations.get(operation)

                logging.info(f"Successfully uploaded text as: {sanitized_name}")
                return operation.name
            finally:
                # Clean up temporary file
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)

        except Exception as e:
            logging.error(f"Failed to upload transcript text: {e}")
            raise

    def get_store_info(self, store_name: Optional[str] = None) -> Dict:
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

    def list_files(self, store_name: Optional[str] = None) -> List[str]:
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

    def get_existing_files(self, store_name: Optional[str] = None) -> Dict[str, str]:
        """
        Get a mapping of display names to document resource names for existing files.

        Args:
            store_name: Store to query (uses default if None)

        Returns:
            Dictionary mapping display_name -> document resource name
        """
        if store_name is None:
            store_name = self.create_or_get_store()

        if self.dry_run:
            return {}

        try:
            # List documents in the store and create mapping
            documents = self.client.file_search_stores.documents.list(parent=store_name)
            return {doc.display_name: doc.name for doc in documents}
        except Exception as e:
            logging.error(f"Failed to list documents: {e}")
            raise

    def get_document_by_name(self, display_name: str, store_name: Optional[str] = None) -> Optional[Dict]:
        """
        Get document metadata by display name.

        Args:
            display_name: Display name of the document (e.g., 'filename.txt')
            store_name: Store to query (uses default if None)

        Returns:
            Dictionary with document info including custom_metadata, or None if not found
        """
        if store_name is None:
            store_name = self.create_or_get_store()

        if self.dry_run:
            return None

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

                    return {
                        'name': doc.name,
                        'display_name': doc.display_name,
                        'metadata': metadata,
                        'create_time': getattr(doc, 'create_time', None),
                        'size_bytes': getattr(doc, 'size_bytes', None)
                    }

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
        metadata_pattern: str = "*_metadata.json"
    ) -> Dict[str, str]:
        """
        Batch upload all transcripts from a directory.

        Args:
            directory_path: Directory containing transcripts
            pattern: Glob pattern for transcript files
            metadata_pattern: Glob pattern for metadata files

        Returns:
            Dictionary mapping file paths to uploaded file names
        """
        import glob
        import json

        store_name = self.create_or_get_store()
        uploaded_files = {}

        # Find all transcript files
        transcript_files = glob.glob(os.path.join(directory_path, '**', pattern), recursive=True)

        logging.info(f"Found {len(transcript_files)} transcript files to upload")

        for transcript_path in transcript_files:
            # Try to find corresponding metadata file
            metadata = None
            base_path = transcript_path.replace('_transcription.txt', '')
            metadata_path = f"{base_path}_metadata.json"

            if os.path.exists(metadata_path):
                try:
                    with open(metadata_path, 'r') as f:
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
            except Exception as e:
                logging.error(f"Failed to upload {transcript_path}: {e}")

        logging.info(f"Batch upload complete: {len(uploaded_files)}/{len(transcript_files)} files uploaded")
        return uploaded_files
