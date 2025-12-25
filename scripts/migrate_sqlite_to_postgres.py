#!/usr/bin/env python3
"""Migrate data from SQLite backup to PostgreSQL (Supabase).

This script exports data from the SQLite backup database and imports it
into the PostgreSQL database. It handles:
- Proper ordering to respect foreign key constraints
- JSON column serialization
- Boolean value conversion

Usage:
    doppler run -- python scripts/migrate_sqlite_to_postgres.py

    # Dry run (show what would be migrated)
    doppler run -- python scripts/migrate_sqlite_to_postgres.py --dry-run
"""

import argparse
import json
import logging
import os
import sqlite3
from datetime import datetime

import psycopg2
from psycopg2.extras import execute_values, Json

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

SQLITE_PATH = "podcast_rag.db"


def clean_string(val):
    """Remove NUL characters from strings (PostgreSQL doesn't allow them)."""
    if isinstance(val, str):
        return val.replace('\x00', '')
    return val


def get_postgres_connection():
    """Get PostgreSQL connection from DATABASE_URL environment variable."""
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL environment variable not set")
    return psycopg2.connect(database_url)


def get_sqlite_connection():
    """Get SQLite connection."""
    if not os.path.exists(SQLITE_PATH):
        raise FileNotFoundError(f"SQLite database not found: {SQLITE_PATH}")
    return sqlite3.connect(SQLITE_PATH)


def migrate_podcasts(sqlite_conn, pg_conn, dry_run=False):
    """Migrate podcasts table."""
    sqlite_cur = sqlite_conn.cursor()
    sqlite_cur.execute("SELECT * FROM podcasts")
    columns = [description[0] for description in sqlite_cur.description]
    rows = sqlite_cur.fetchall()

    logger.info(f"Found {len(rows)} podcasts to migrate")

    if dry_run or not rows:
        return len(rows)

    pg_cur = pg_conn.cursor()

    # Build INSERT statement
    placeholders = ", ".join(["%s"] * len(columns))
    columns_str = ", ".join(f'"{col}"' for col in columns)
    insert_sql = f'INSERT INTO podcasts ({columns_str}) VALUES ({placeholders}) ON CONFLICT (id) DO NOTHING'

    for row in rows:
        # Convert SQLite booleans (0/1) to Python booleans
        converted_row = []
        for i, val in enumerate(row):
            col_name = columns[i]
            if col_name in ('is_subscribed', 'itunes_explicit') and val is not None:
                converted_row.append(bool(val))
            else:
                converted_row.append(val)
        pg_cur.execute(insert_sql, converted_row)

    pg_conn.commit()
    logger.info(f"Migrated {len(rows)} podcasts")
    return len(rows)


def migrate_episodes(sqlite_conn, pg_conn, dry_run=False):
    """Migrate episodes table."""
    sqlite_cur = sqlite_conn.cursor()
    sqlite_cur.execute("SELECT * FROM episodes")
    columns = [description[0] for description in sqlite_cur.description]
    rows = sqlite_cur.fetchall()

    logger.info(f"Found {len(rows)} episodes to migrate")

    if dry_run or not rows:
        return len(rows)

    pg_cur = pg_conn.cursor()

    # Build INSERT statement
    placeholders = ", ".join(["%s"] * len(columns))
    columns_str = ", ".join(f'"{col}"' for col in columns)
    insert_sql = f'INSERT INTO episodes ({columns_str}) VALUES ({placeholders}) ON CONFLICT (id) DO NOTHING'

    # JSON columns in episodes
    json_columns = {'ai_keywords', 'ai_hosts', 'ai_guests', 'ai_email_content'}
    boolean_columns = {'itunes_explicit'}

    batch_size = 500
    migrated = 0

    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]

        for row in batch:
            converted_row = []
            for j, val in enumerate(row):
                col_name = columns[j]
                if col_name in json_columns and val is not None:
                    # Parse JSON string from SQLite, wrap with Json adapter for PostgreSQL
                    try:
                        parsed = json.loads(val) if isinstance(val, str) else val
                        converted_row.append(Json(parsed))
                    except (json.JSONDecodeError, TypeError):
                        converted_row.append(Json(val) if val else None)
                elif col_name in boolean_columns and val is not None:
                    converted_row.append(bool(val))
                else:
                    # Clean string values to remove NUL characters
                    converted_row.append(clean_string(val))

            try:
                pg_cur.execute(insert_sql, converted_row)
            except Exception as e:
                logger.error(f"Failed to insert episode: {e}")
                pg_conn.rollback()
                raise

        pg_conn.commit()
        migrated += len(batch)
        logger.info(f"Migrated {migrated}/{len(rows)} episodes...")

    logger.info(f"Migrated {len(rows)} episodes")
    return len(rows)


def migrate_users(sqlite_conn, pg_conn, dry_run=False):
    """Migrate users table."""
    sqlite_cur = sqlite_conn.cursor()
    sqlite_cur.execute("SELECT * FROM users")
    columns = [description[0] for description in sqlite_cur.description]
    rows = sqlite_cur.fetchall()

    logger.info(f"Found {len(rows)} users to migrate")

    if dry_run or not rows:
        return len(rows)

    pg_cur = pg_conn.cursor()

    # Build INSERT statement
    placeholders = ", ".join(["%s"] * len(columns))
    columns_str = ", ".join(f'"{col}"' for col in columns)
    insert_sql = f'INSERT INTO users ({columns_str}) VALUES ({placeholders}) ON CONFLICT DO NOTHING'

    boolean_columns = {'is_active', 'is_admin', 'email_digest_enabled'}

    for row in rows:
        converted_row = []
        for i, val in enumerate(row):
            col_name = columns[i]
            if col_name in boolean_columns and val is not None:
                converted_row.append(bool(val))
            else:
                converted_row.append(val)
        pg_cur.execute(insert_sql, converted_row)

    pg_conn.commit()
    logger.info(f"Migrated {len(rows)} users")
    return len(rows)


def migrate_user_subscriptions(sqlite_conn, pg_conn, dry_run=False):
    """Migrate user_subscriptions table."""
    sqlite_cur = sqlite_conn.cursor()
    sqlite_cur.execute("SELECT * FROM user_subscriptions")
    columns = [description[0] for description in sqlite_cur.description]
    rows = sqlite_cur.fetchall()

    logger.info(f"Found {len(rows)} user_subscriptions to migrate")

    if dry_run or not rows:
        return len(rows)

    pg_cur = pg_conn.cursor()

    # Build INSERT statement
    placeholders = ", ".join(["%s"] * len(columns))
    columns_str = ", ".join(f'"{col}"' for col in columns)
    insert_sql = f'INSERT INTO user_subscriptions ({columns_str}) VALUES ({placeholders}) ON CONFLICT DO NOTHING'

    for row in rows:
        pg_cur.execute(insert_sql, row)

    pg_conn.commit()
    logger.info(f"Migrated {len(rows)} user_subscriptions")
    return len(rows)


def main():
    parser = argparse.ArgumentParser(
        description="Migrate data from SQLite backup to PostgreSQL"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be migrated without making changes",
    )
    args = parser.parse_args()

    logger.info("Connecting to databases...")

    sqlite_conn = get_sqlite_connection()
    pg_conn = get_postgres_connection()

    try:
        if args.dry_run:
            logger.info("DRY RUN - no changes will be made")

        # Migrate in order respecting foreign keys
        podcasts_count = migrate_podcasts(sqlite_conn, pg_conn, args.dry_run)
        episodes_count = migrate_episodes(sqlite_conn, pg_conn, args.dry_run)
        users_count = migrate_users(sqlite_conn, pg_conn, args.dry_run)
        subscriptions_count = migrate_user_subscriptions(sqlite_conn, pg_conn, args.dry_run)

        logger.info("=" * 50)
        logger.info("Migration complete!")
        logger.info(f"  Podcasts: {podcasts_count}")
        logger.info(f"  Episodes: {episodes_count}")
        logger.info(f"  Users: {users_count}")
        logger.info(f"  Subscriptions: {subscriptions_count}")

    finally:
        sqlite_conn.close()
        pg_conn.close()


if __name__ == "__main__":
    main()
