
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# Load environment variables from a .env file if it exists.
# This is useful for local development.
load_dotenv()

# Build the database URL from individual components, providing sensible defaults
# for a Docker Compose environment.
DB_USER = os.getenv("POSTGRES_USER", "podcast_rag_user")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "insecure_password_change_me")
DB_HOST = os.getenv("POSTGRES_HOST", "postgres") # 'postgres' is the service name in docker-compose
DB_PORT = os.getenv("POSTGRES_PORT", "5432")
DB_NAME = os.getenv("POSTGRES_DB", "podcast_rag_db")

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

if not all([DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME]):
    print("Error: One or more PostgreSQL environment variables are missing.")
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
