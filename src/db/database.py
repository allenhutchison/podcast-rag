
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# This module now expects the DATABASE_URL to be set in the environment.
# The responsibility of loading .env files and constructing the URL is
# moved to the application's entry points (e.g., main scripts, Config class).
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    print("Error: DATABASE_URL environment variable not set.")
    exit(1)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    """
    Provides a database session for use in a 'with' statement or as a dependency.
    Ensures the session is always closed.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
