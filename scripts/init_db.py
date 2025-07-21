

import os
import sys
import argparse
import logging
import traceback
from sqlalchemy import text

# Adjust path to import from src
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from src.config import Config

# Setup basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def initialize_database(db_url: str):
    """
    Connects to the database, creates the pgvector extension,
    and creates all tables defined in the models.
    """
    try:
        from src.db.database import engine
        from src.db.models import Base

        logging.info("Attempting to connect to the database...")
        with engine.connect() as connection:
            logging.info("Database connection successful.")
            
            logging.info("Creating 'vector' extension if it doesn't exist...")
            connection.execute(text('CREATE EXTENSION IF NOT EXISTS vector;'))
            
            logging.info("Creating tables if they don't exist...")
            Base.metadata.create_all(bind=engine)
            
            logging.info("Database initialization complete. All tables created successfully.")
            
    except Exception as e:
        logging.error("An error occurred during database initialization.")
        logging.error(traceback.format_exc()) # Log the full traceback
        exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Initialize the database. Creates tables if they don't exist.")
    parser.add_argument("--yes", "-y", action="store_true", help="Bypass confirmation prompt.")
    parser.add_argument("--env-file", help="Path to a custom .env file", default=None)
    args = parser.parse_args()

    try:
        logging.info("Starting database initialization script.")
        config = Config(env_file=args.env_file)
        
        # Log the configuration for debugging
        db_host = os.getenv("POSTGRES_HOST", "not_set")
        db_user = os.getenv("POSTGRES_USER", "not_set")
        logging.info(f"Attempting to use database configuration: HOST={db_host}, USER={db_user}")

        if not config.DATABASE_URL:
            logging.error("DATABASE_URL is not set after config initialization. Exiting.")
            exit(1)

        if not args.yes:
            confirm = input("Initialize the database? This will create tables but not delete existing data. (y/n): ")
            if confirm.lower() != 'y':
                logging.info("Database initialization cancelled by user.")
                exit(0)
        
        initialize_database(config.DATABASE_URL)

    except Exception as e:
        logging.error("A critical error occurred in the main execution block.")
        logging.error(traceback.format_exc())
        exit(1)

