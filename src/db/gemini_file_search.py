"""
Gemini File Search Manager for podcast transcript indexing and search.

This module provides a wrapper around Google's Gemini File Search API,
enabling semantic search over podcast transcripts with automatic embedding,
chunking, and citation support.
"""

import logging
import os
from typing import Dict, List, Optional

from google import genai
from google.genai import types


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

    def _prepare_metadata(self, metadata: Optional[Dict]) -> Dict:
        """
        Convert metadata dictionary to File Search custom_metadata format.

        Converts lists to comma-separated strings and ensures all values are strings.

        Args:
            metadata: Dictionary of metadata values

        Returns:
            Dictionary suitable for File Search custom_metadata
        """
        custom_metadata = {}
        if metadata:
            for key in ['podcast', 'episode', 'release_date', 'hosts', 'guests', 'keywords', 'summary']:
                if key in metadata and metadata[key]:
                    value = metadata[key]
                    # Convert lists to comma-separated strings
                    if isinstance(value, list):
                        value = ', '.join(str(v) for v in value)
                    custom_metadata[key] = str(value)
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
        store_name: Optional[str] = None
    ) -> str:
        """
        Upload a transcript file to the File Search store.

        Args:
            transcript_path: Path to the transcript text file
            metadata: Dictionary of metadata to attach (podcast, episode, etc.)
            store_name: Store to upload to (uses default if None)

        Returns:
            File resource name
        """
        # Check file exists first before making any API calls
        if not os.path.exists(transcript_path):
            raise FileNotFoundError(f"Transcript file not found: {transcript_path}")

        if store_name is None:
            store_name = self.create_or_get_store()

        # Prepare metadata
        custom_metadata = self._prepare_metadata(metadata)

        if self.dry_run:
            logging.info(f"[DRY RUN] Would upload {transcript_path} to {store_name}")
            logging.info(f"[DRY RUN] Metadata: {custom_metadata}")
            return f"files/dry-run-{os.path.basename(transcript_path)}"

        try:
            # Upload file with metadata
            logging.info(f"Uploading {transcript_path} to File Search store...")

            operation = self.client.file_search_stores.upload_to_file_search_store(
                file=transcript_path,
                file_search_store_name=store_name,
                config={
                    'display_name': os.path.basename(transcript_path),
                    'custom_metadata': custom_metadata
                }
            )

            # Wait for operation to complete and get file name
            result = operation.result()
            logging.info(f"Successfully uploaded: {result.name}")
            return result.name

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

        # Prepare metadata
        custom_metadata = self._prepare_metadata(metadata)

        if self.dry_run:
            logging.info(f"[DRY RUN] Would upload text as {display_name} to {store_name}")
            logging.info(f"[DRY RUN] Text length: {len(text)} characters")
            logging.info(f"[DRY RUN] Metadata: {custom_metadata}")
            return f"files/dry-run-{display_name}"

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
                        'display_name': display_name,
                        'custom_metadata': custom_metadata
                    }
                )

                # Wait for operation to complete and get file name
                result = operation.result()
                logging.info(f"Successfully uploaded text as: {result.name}")
                return result.name
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
        List all files in a File Search store.

        Args:
            store_name: Store to query (uses default if None)

        Returns:
            List of file resource names
        """
        if store_name is None:
            store_name = self.create_or_get_store()

        if self.dry_run:
            return []

        try:
            # List files in the store
            files = self.client.files.list(
                config={'file_search_store_name': store_name}
            )
            return [file.name for file in files]
        except Exception as e:
            logging.error(f"Failed to list files: {e}")
            raise

    def delete_file(self, file_name: str):
        """
        Delete a file from the File Search store.

        Args:
            file_name: File resource name to delete
        """
        if self.dry_run:
            logging.info(f"[DRY RUN] Would delete file: {file_name}")
            return

        try:
            self.client.files.delete(name=file_name)
            logging.info(f"Deleted file: {file_name}")
        except Exception as e:
            logging.error(f"Failed to delete file: {e}")
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
