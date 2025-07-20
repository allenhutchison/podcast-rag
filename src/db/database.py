
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# Load environment variables to get the database URL
# This allows the module to be self-contained for scripts that might import it.
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    # A fallback for local development could be added here if desired
    print("Error: DATABASE_URL environment variable not set.")
    # Forcing an exit if the DB URL isn't set is safer for a DB-dependent app
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
