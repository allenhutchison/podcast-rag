

import os
import sys
import argparse
from sqlalchemy import text

# Adjust path to import from src
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from src.config import Config

def initialize_database():
    """
    Connects to the database, creates the pgvector extension,
    and creates all tables defined in the models.
    """
    # The Config class now handles setting the DATABASE_URL environment variable
    # before other modules like 'database' are imported.
    from src.db.database import engine
    from src.db.models import Base

    print("Connecting to the database...")
    try:
        with engine.connect() as connection:
            print("Creating 'vector' extension if it doesn't exist...")
            connection.execute(text('CREATE EXTENSION IF NOT EXISTS vector;'))
            
            print("Creating tables if they don't exist...")
            Base.metadata.create_all(bind=engine)
            
            print("\nDatabase initialization complete.")
            print("All tables have been created successfully.")
            
    except Exception as e:
        print(f"\nAn error occurred during database initialization: {e}")
        print("Please ensure the PostgreSQL server is running and the environment variables are correct.")
        exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Initialize the database. Creates tables if they don't exist.")
    parser.add_argument("--yes", "-y", action="store_true", help="Bypass confirmation prompt.")
    parser.add_argument("--env-file", help="Path to a custom .env file", default=None)
    args = parser.parse_args()

    # Initialize config first to load and set up the environment
    config = Config(env_file=args.env_file)

    if not args.yes:
        confirm = input("Initialize the database? This will create tables but not delete existing data. (y/n): ")
        if confirm.lower() != 'y':
            print("Database initialization cancelled.")
            exit(0)
            
    initialize_database()

