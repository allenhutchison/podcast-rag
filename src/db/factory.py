"""Database factory for creating repository instances.

Automatically detects database type from URL and configures appropriately
for SQLite (local development) or PostgreSQL (Cloud SQL production).
"""

import logging
import os
from typing import Optional

from .repository import PodcastRepositoryInterface, SQLAlchemyPodcastRepository

logger = logging.getLogger(__name__)

# Default database URL for local development
DEFAULT_DATABASE_URL = "sqlite:///./podcast_rag.db"


def create_repository(
    database_url: Optional[str] = None,
    pool_size: int = 5,
    max_overflow: int = 10,
    echo: bool = False,
) -> PodcastRepositoryInterface:
    """Create a podcast repository instance based on configuration.

    Args:
        database_url: SQLAlchemy database URL. If not provided, uses
                     DATABASE_URL environment variable or defaults to SQLite.
        pool_size: Connection pool size for PostgreSQL (ignored for SQLite)
        max_overflow: Maximum overflow connections for PostgreSQL
        echo: Whether to log SQL statements

    Returns:
        PodcastRepositoryInterface implementation

    Examples:
        # SQLite (local development)
        repo = create_repository("sqlite:///./podcast_rag.db")

        # PostgreSQL (Cloud SQL)
        repo = create_repository("postgresql://user:pass@host/dbname")

        # Using environment variable
        os.environ["DATABASE_URL"] = "postgresql://..."
        repo = create_repository()
    """
    if database_url is None:
        database_url = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)

    # Log database type (without credentials)
    if "://" in database_url:
        db_type = database_url.split("://")[0]
        if "@" in database_url:
            # Hide credentials in log
            db_location = database_url.split("@")[-1]
            logger.info(f"Creating {db_type} repository: ...@{db_location}")
        else:
            logger.info(f"Creating {db_type} repository: {database_url}")
    else:
        logger.info(f"Creating repository with URL: {database_url}")

    return SQLAlchemyPodcastRepository(
        database_url=database_url,
        pool_size=pool_size,
        max_overflow=max_overflow,
        echo=echo,
    )


def get_database_url_from_config(config) -> str:
    """Extract database URL from Config object.

    Args:
        config: Config instance with database settings

    Returns:
        Database URL string
    """
    return getattr(config, "DATABASE_URL", None) or os.getenv(
        "DATABASE_URL", DEFAULT_DATABASE_URL
    )
