#!/usr/bin/env python3
"""
Migration script to convert the keywords column from Text to ARRAY(String).

This script:
1. Checks the current type of the keywords column
2. If it's Text, converts comma-separated strings to PostgreSQL arrays
3. Alters the column type to ARRAY(String)

Usage:
    python scripts/migrate_keywords_to_array.py [--dry-run] [--env-file PATH]
"""

import os
import sys
import argparse
import logging
import traceback
from sqlalchemy import text, inspect

# Adjust path to import from src
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from src.config import Config

# Setup basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def migrate_keywords_to_array(db_url: str, dry_run: bool = False):
    """
    Migrate the keywords column from Text (comma-separated) to ARRAY(String).

    Args:
        db_url: Database URL connection string
        dry_run: If True, only shows what would be done without making changes
    """
    try:
        from src.db.database import engine

        logging.info("Connecting to database...")

        with engine.connect() as connection:
            # Check current column type
            inspector = inspect(engine)
            columns = inspector.get_columns('episodes')
            keywords_col = next((c for c in columns if c['name'] == 'keywords'), None)

            if not keywords_col:
                logging.error("Keywords column not found in episodes table!")
                return False

            current_type = str(keywords_col['type'])
            logging.info(f"Current keywords column type: {current_type}")

            # Check if already migrated
            if 'ARRAY' in current_type or '[]' in current_type:
                logging.info("Keywords column is already an ARRAY type. No migration needed.")
                return True

            if dry_run:
                logging.info("[DRY RUN] Would perform the following operations:")
                logging.info("[DRY RUN] 1. Create temporary column 'keywords_array' as ARRAY(String)")
                logging.info("[DRY RUN] 2. Convert comma-separated keywords to arrays")
                logging.info("[DRY RUN] 3. Drop old 'keywords' column")
                logging.info("[DRY RUN] 4. Rename 'keywords_array' to 'keywords'")
                return True

            logging.info("Starting keywords migration...")

            with connection.begin():
                # Step 1: Add temporary array column
                logging.info("Step 1/4: Creating temporary keywords_array column...")
                connection.execute(text("""
                    ALTER TABLE episodes
                    ADD COLUMN IF NOT EXISTS keywords_array TEXT[]
                """))

                # Step 2: Migrate data from comma-separated to array
                logging.info("Step 2/4: Migrating data from comma-separated to array...")
                # Use string_to_array to convert comma-separated strings to arrays
                # Trim whitespace from each element
                result = connection.execute(text("""
                    UPDATE episodes
                    SET keywords_array = string_to_array(
                        regexp_replace(keywords, '\\s*,\\s*', ',', 'g'),
                        ','
                    )
                    WHERE keywords IS NOT NULL AND keywords != ''
                """))
                logging.info(f"Migrated {result.rowcount} rows with keywords data")

                # Step 3: Drop old column
                logging.info("Step 3/4: Dropping old keywords column...")
                connection.execute(text("ALTER TABLE episodes DROP COLUMN keywords"))

                # Step 4: Rename new column
                logging.info("Step 4/4: Renaming keywords_array to keywords...")
                connection.execute(text("""
                    ALTER TABLE episodes
                    RENAME COLUMN keywords_array TO keywords
                """))

            logging.info("Keywords migration completed successfully!")
            return True

    except Exception as e:
        logging.error("An error occurred during keywords migration.")
        logging.error(traceback.format_exc())
        return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Migrate keywords column from Text to ARRAY(String)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes"
    )
    parser.add_argument(
        "--env-file",
        help="Path to a custom .env file",
        default=None
    )
    parser.add_argument(
        "--yes", "-y",
        action="store_true",
        help="Bypass confirmation prompt"
    )
    args = parser.parse_args()

    try:
        logging.info("Starting keywords migration script...")
        config = Config(env_file=args.env_file)

        # Log the configuration for debugging
        db_host = os.getenv("POSTGRES_HOST", "not_set")
        db_user = os.getenv("POSTGRES_USER", "not_set")
        logging.info(f"Database configuration: HOST={db_host}, USER={db_user}")

        if not config.DATABASE_URL:
            logging.error("DATABASE_URL is not set after config initialization. Exiting.")
            sys.exit(1)

        if args.dry_run:
            logging.info("Running in DRY RUN mode - no changes will be made")
        elif not args.yes:
            confirm = input(
                "This will migrate the keywords column to ARRAY type. "
                "Existing data will be converted. Continue? (y/n): "
            )
            if confirm.lower() != 'y':
                logging.info("Migration cancelled by user.")
                sys.exit(0)

        success = migrate_keywords_to_array(config.DATABASE_URL, dry_run=args.dry_run)
        sys.exit(0 if success else 1)

    except Exception as e:
        logging.error("A critical error occurred in the main execution block.")
        logging.error(traceback.format_exc())
        sys.exit(1)
