from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
import os

from core.config import settings
from db.models import Base  # Import Base from models instead of creating a new one

# Get database URL from environment variable or use default SQLite
DATABASE_URL = os.getenv("DATABASE_URL", settings.DATABASE_URL)

# Create engine
engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    """Dependency for getting database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    """Initialize the database, creating all tables"""
    Base.metadata.create_all(bind=engine) 