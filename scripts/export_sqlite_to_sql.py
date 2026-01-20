#!/usr/bin/env python3
"""Export SQLite database to PostgreSQL-compatible SQL dump.

This script exports data from the SQLite database to a SQL file that can be
imported into Supabase PostgreSQL. It handles proper escaping and data type
conversions between SQLite and PostgreSQL.

Usage:
    python scripts/export_sqlite_to_sql.py

Output:
    Creates supabase_data_import.sql in the current directory
"""

import sqlite3
import sys
from pathlib import Path
from datetime import datetime

def escape_value(val):
    """Escape value for PostgreSQL compatibility.

    Args:
        val: Value to escape (can be None, str, bool, int, float, datetime, or other)

    Returns:
        str: PostgreSQL-compatible escaped value
    """
    if val is None:
        return 'NULL'
    elif isinstance(val, str):
        # Escape single quotes and backslashes for PostgreSQL
        escaped = val.replace("\\", "\\\\").replace("'", "''")
        return f"'{escaped}'"
    elif isinstance(val, bool):
        # PostgreSQL uses lowercase true/false
        return 'true' if val else 'false'
    elif isinstance(val, (int, float)):
        return str(val)
    elif isinstance(val, datetime):
        return f"'{val.isoformat()}'"
    else:
        # Fallback for other types - convert to string and escape
        escaped = str(val).replace("\\", "\\\\").replace("'", "''")
        return f"'{escaped}'"


def export_table_data(cursor, table_name, output_file):
    """Export table data as INSERT statements.

    Args:
        cursor: SQLite database cursor
        table_name: Name of table to export
        output_file: File object to write INSERT statements to
    """
    # Columns to exclude (removed from schema)
    excluded_columns = {'is_subscribed'}

    # Boolean columns (SQLite stores as INTEGER 0/1, PostgreSQL needs true/false)
    # These are known boolean columns in our schema
    boolean_columns = {
        'itunes_explicit', 'is_active', 'is_admin',
        'email_digest_enabled', 'smtp_use_tls'
    }

    # JSON/JSONB columns that should not be escaped
    # Use dollar-quoted strings to preserve JSON syntax
    json_columns = {
        'ai_keywords', 'ai_hosts', 'ai_guests'
    }

    cursor.execute(f"SELECT * FROM {table_name}")
    rows = cursor.fetchall()

    if not rows:
        output_file.write(f"-- No data in {table_name}\n")
        return

    # Get column names from cursor description, excluding removed columns
    all_columns = [desc[0] for desc in cursor.description]
    columns = [col for col in all_columns if col not in excluded_columns]
    keep_indices = [i for i, col in enumerate(all_columns) if col not in excluded_columns]
    col_list = ", ".join(columns)

    output_file.write(f"-- Inserting {len(rows)} rows into {table_name}\n")

    for row in rows:
        values = []
        for idx in keep_indices:
            col_name = all_columns[idx]
            val = row[idx]
            # Handle JSON columns - keep as-is, just wrap in single quotes
            if col_name in json_columns:
                if val is None:
                    values.append('NULL')
                else:
                    # JSON is already properly formatted, just wrap in quotes
                    # Use dollar-quoted strings for JSON to avoid escaping issues
                    values.append(f"$${val}$$")
            # Convert 0/1 to true/false for known boolean columns
            elif col_name in boolean_columns and isinstance(val, int) and val in (0, 1):
                values.append('true' if val == 1 else 'false')
            else:
                values.append(escape_value(val))

        value_list = ", ".join(values)
        output_file.write(f"INSERT INTO {table_name} ({col_list}) VALUES ({value_list});\n")


def main():
    """Main function to export SQLite database to SQL dump."""
    db_path = Path("podcast_rag.db")

    if not db_path.exists():
        print(f"❌ Database not found: {db_path}")
        print("Please ensure podcast_rag.db is in the current directory")
        print(f"Current directory: {Path.cwd()}")
        sys.exit(1)

    try:
        # Connect to SQLite database
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Export tables in dependency order (parent tables before child tables)
        # This ensures foreign key constraints are satisfied during import
        tables = ['podcasts', 'users', 'episodes', 'user_subscriptions']

        output_file_path = Path('supabase_data_import.sql')

        with open(output_file_path, 'w', encoding='utf-8') as f:
            # Write header
            f.write("-- Podcast RAG Data Import for Supabase\n")
            f.write(f"-- Generated: {datetime.now().isoformat()}\n")
            f.write(f"-- Source: {db_path}\n")
            f.write("--\n")
            f.write("-- Import this file into Supabase via:\n")
            f.write("--   1. Supabase Dashboard → SQL Editor → New Query → Paste & Run\n")
            f.write("--   2. psql command: psql 'postgresql://...' < supabase_data_import.sql\n")
            f.write("--\n\n")

            # Begin transaction
            f.write("BEGIN;\n\n")

            # Export each table
            for table in tables:
                try:
                    f.write(f"\n-- ====================================================\n")
                    f.write(f"-- Table: {table}\n")
                    f.write(f"-- ====================================================\n")
                    export_table_data(cursor, table, f)
                    f.write("\n")
                except sqlite3.Error as e:
                    print(f"⚠️  Warning: Could not export {table}: {e}")
                    f.write(f"-- Error exporting {table}: {e}\n\n")

            # Commit transaction
            f.write("COMMIT;\n")

        conn.close()

        # Print summary
        print(f"✅ Data exported successfully to {output_file_path}")
        print()
        print("Next steps:")
        print("1. Review the generated supabase_data_import.sql file")
        print("2. Import to Supabase using one of these methods:")
        print("   - Supabase Dashboard → SQL Editor → New Query → Paste contents and run")
        print("   - Command line: psql 'postgresql://postgres:[PASSWORD]@db.[PROJECT-REF].supabase.co:5432/postgres' < supabase_data_import.sql")
        print("3. Verify row counts match after import")

    except Exception as e:
        print(f"❌ Error during export: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
