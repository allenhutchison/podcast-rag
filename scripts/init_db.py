

import os
import sys
import argparse
from sqlalchemy import text

# Adjust path to import from src
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from src.db.database import engine
from src.db.models import Base

def initialize_database():
    """
    Connects to the database, creates the pgvector extension,
    and creates all tables defined in the models.
    """
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
        print("Please ensure the PostgreSQL server is running and the DATABASE_URL in your .env file is correct.")
        exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Initialize the database. Drops and recreates all tables.")
    parser.add_argument("--yes", "-y", action="store_true", help="Bypass confirmation prompt.")
    args = parser.parse_args()

    if not args.yes:
        confirm = input("Are you sure you want to initialize the database? This will drop all existing tables. (y/n): ")
        if confirm.lower() != 'y':
            print("Database initialization cancelled.")
            exit(0)
            
    initialize_database()

