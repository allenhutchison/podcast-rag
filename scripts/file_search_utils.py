#!/usr/bin/env python3
"""
Utility script for managing Gemini File Search store.

This script helps manage documents in the File Search store by:
- Listing all documents with metadata
- Identifying duplicates
- Deleting documents (all or duplicates only)
"""

import argparse
import logging
import sys
from pathlib import Path
from collections import defaultdict

# Add parent directory to path to import from src
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import Config
from src.db.gemini_file_search import GeminiFileSearchManager


def list_files(file_search_manager: GeminiFileSearchManager, store_name: str):
    """List all documents in the store with details including metadata."""
    logging.info(f"Listing documents in store: {store_name}")

    try:
        # List documents in the store
        documents = file_search_manager.client.file_search_stores.documents.list(parent=store_name)
        files_list = list(documents)

        logging.info(f"Found {len(files_list)} documents")

        for i, doc in enumerate(files_list, 1):
            print(f"\n{'='*80}")
            print(f"{i}. {doc.display_name}")
            print(f"{'='*80}")
            print(f"Resource name: {doc.name}")

            if hasattr(doc, 'create_time'):
                print(f"Created:       {doc.create_time}")
            if hasattr(doc, 'update_time'):
                print(f"Updated:       {doc.update_time}")
            if hasattr(doc, 'size_bytes'):
                print(f"Size:          {doc.size_bytes:,} bytes")
            if hasattr(doc, 'mime_type'):
                print(f"MIME type:     {doc.mime_type}")
            if hasattr(doc, 'state'):
                print(f"State:         {doc.state}")

            # Display custom metadata
            if hasattr(doc, 'custom_metadata') and doc.custom_metadata:
                print(f"\nMetadata:")
                for meta in doc.custom_metadata:
                    if hasattr(meta, 'key'):
                        value = ''
                        if hasattr(meta, 'string_value'):
                            value = meta.string_value
                        elif hasattr(meta, 'numeric_value'):
                            value = str(meta.numeric_value)
                        print(f"  {meta.key}: {value}")
            else:
                print(f"\nMetadata:      None")

        return files_list
    except Exception as e:
        logging.error(f"Failed to list documents: {e}")
        raise


def find_duplicates(file_search_manager: GeminiFileSearchManager, store_name: str):
    """Find duplicate documents based on display_name."""
    logging.info(f"Finding duplicates in store: {store_name}")

    try:
        # List documents in the store
        documents = file_search_manager.client.file_search_stores.documents.list(parent=store_name)

        # Group documents by display_name
        by_name = defaultdict(list)
        for doc in documents:
            by_name[doc.display_name].append(doc)

        # Find duplicates
        duplicates = {name: files for name, files in by_name.items() if len(files) > 1}

        if duplicates:
            logging.info(f"Found {len(duplicates)} files with duplicates")
            total_duplicate_files = sum(len(files) - 1 for files in duplicates.values())
            logging.info(f"Total duplicate copies: {total_duplicate_files}")

            print("\n" + "="*80)
            print("DUPLICATE FILES")
            print("="*80)

            for name, files in duplicates.items():
                print(f"\n{name} ({len(files)} copies):")
                for i, file in enumerate(files, 1):
                    created = file.create_time if hasattr(file, 'create_time') else 'N/A'
                    print(f"  {i}. {file.name} (created: {created})")

            return duplicates
        else:
            logging.info("No duplicates found!")
            return {}

    except Exception as e:
        logging.error(f"Failed to find duplicates: {e}")
        raise


def delete_all_files(file_search_manager: GeminiFileSearchManager, store_name: str, confirm: bool = True):
    """Delete all documents from the store."""
    logging.info(f"Deleting all documents from store: {store_name}")

    if confirm:
        response = input("Are you sure you want to delete ALL documents? (yes/no): ")
        if response.lower() != 'yes':
            logging.info("Deletion cancelled")
            return 0

    try:
        # List documents in the store
        documents = file_search_manager.client.file_search_stores.documents.list(parent=store_name)
        files_list = list(documents)
        total = len(files_list)

        logging.info(f"Deleting {total} files...")

        deleted = 0
        for i, file in enumerate(files_list, 1):
            try:
                logging.info(f"[{i}/{total}] Deleting: {file.display_name}")
                file_search_manager.delete_file(file.name)
                deleted += 1
            except Exception as e:
                logging.error(f"Failed to delete {file.display_name}: {e}")

        logging.info(f"Deleted {deleted}/{total} files")
        return deleted

    except Exception as e:
        logging.error(f"Failed to delete files: {e}")
        raise


def delete_duplicates(file_search_manager: GeminiFileSearchManager, store_name: str, keep: str = 'oldest', confirm: bool = True):
    """
    Delete duplicate files, keeping only one copy.

    Args:
        file_search_manager: File search manager instance
        store_name: Store name
        keep: Which copy to keep - 'oldest' or 'newest'
        confirm: Ask for confirmation before deleting
    """
    duplicates = find_duplicates(file_search_manager, store_name)

    if not duplicates:
        logging.info("No duplicates to delete")
        return 0

    total_to_delete = sum(len(files) - 1 for files in duplicates.values())

    if confirm:
        print(f"\nThis will delete {total_to_delete} duplicate files, keeping the {keep} copy of each.")
        response = input("Proceed? (yes/no): ")
        if response.lower() != 'yes':
            logging.info("Deletion cancelled")
            return 0

    deleted = 0
    for name, files in duplicates.items():
        # Sort by creation time
        sorted_files = sorted(files, key=lambda f: f.create_time if hasattr(f, 'create_time') else '')

        # Keep oldest or newest
        if keep == 'oldest':
            to_keep = sorted_files[0]
            to_delete = sorted_files[1:]
        else:  # newest
            to_keep = sorted_files[-1]
            to_delete = sorted_files[:-1]

        logging.info(f"Keeping {to_keep.name}, deleting {len(to_delete)} duplicates")

        for file in to_delete:
            try:
                logging.info(f"  Deleting: {file.name}")
                file_search_manager.delete_file(file.name)
                deleted += 1
            except Exception as e:
                logging.error(f"  Failed to delete {file.name}: {e}")

    logging.info(f"Deleted {deleted} duplicate files")
    return deleted


def main():
    """Main entry point for File Search utility script."""
    parser = argparse.ArgumentParser(
        description="Utility for managing Gemini File Search store"
    )
    parser.add_argument(
        "-e", "--env-file",
        help="Path to .env file",
        default=None
    )
    parser.add_argument(
        "-l", "--log-level",
        help="Log level (DEBUG, INFO, WARNING, ERROR)",
        default="INFO"
    )
    parser.add_argument(
        "--action",
        choices=['list', 'find-duplicates', 'delete-all', 'delete-duplicates'],
        required=True,
        help="Action to perform"
    )
    parser.add_argument(
        "--keep",
        choices=['oldest', 'newest'],
        default='oldest',
        help="Which copy to keep when deleting duplicates (default: oldest)"
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip confirmation prompts"
    )

    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), "INFO"),
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler()]
    )

    # Load configuration
    logging.info("Loading configuration...")
    config = Config(env_file=args.env_file)
    logging.info(f"File Search store: {config.GEMINI_FILE_SEARCH_STORE_NAME}")

    # Initialize File Search manager
    file_search_manager = GeminiFileSearchManager(config=config)
    store_name = file_search_manager.create_or_get_store()

    # Perform action
    try:
        if args.action == 'list':
            files = list_files(file_search_manager, store_name)
            print(f"\n{'='*80}")
            print(f"TOTAL FILES: {len(files)}")
            print(f"{'='*80}")

        elif args.action == 'find-duplicates':
            duplicates = find_duplicates(file_search_manager, store_name)
            if duplicates:
                print(f"\n{'='*80}")
                print(f"Found {len(duplicates)} files with duplicates")
                print(f"Total duplicate copies: {sum(len(files) - 1 for files in duplicates.values())}")
                print(f"{'='*80}")

        elif args.action == 'delete-all':
            deleted = delete_all_files(file_search_manager, store_name, confirm=not args.yes)
            print(f"\n{'='*80}")
            print(f"DELETED {deleted} FILES")
            print(f"{'='*80}")

        elif args.action == 'delete-duplicates':
            deleted = delete_duplicates(file_search_manager, store_name, keep=args.keep, confirm=not args.yes)
            print(f"\n{'='*80}")
            print(f"DELETED {deleted} DUPLICATE FILES")
            print(f"{'='*80}")

    except Exception as e:
        logging.error(f"Operation failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
