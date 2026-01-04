"""Database factory for creating repository instances.

Automatically detects database type from URL and configures appropriately
for SQLite (local development) or PostgreSQL (Cloud SQL production).
"""

import logging
import os

from .models import Base
from .repository import PodcastRepositoryInterface, SQLAlchemyPodcastRepository

logger = logging.getLogger(__name__)

# Default database URL for local development
DEFAULT_DATABASE_URL = "sqlite:///./podcast_rag.db"


def create_repository(
    database_url: str | None = None,
    pool_size: int = 3,  # Supabase-optimized
    max_overflow: int = 2,  # Supabase-optimized
    echo: bool = False,
    create_tables: bool = False,
    pool_pre_ping: bool = True,  # Detect stale connections
    pool_recycle: int = 1800,  # Recycle connections after 30 minutes
) -> PodcastRepositoryInterface:
    """
    Create a PodcastRepositoryInterface configured from the provided or discovered database URL.

    If `database_url` is not provided, it is read from the `DATABASE_URL` environment variable; if that is unset, a local SQLite default is used. Logs the chosen database type and hides credentials when present. Pool settings apply to PostgreSQL and are ignored for SQLite.

    Parameters:
        database_url (Optional[str]): SQLAlchemy database URL to use; if None the environment or default is used.
        pool_size (int): Connection pool size for PostgreSQL (default 3 for Supabase); ignored for SQLite.
        max_overflow (int): Maximum overflow connections for PostgreSQL (default 2 for Supabase); ignored for SQLite.
        echo (bool): If true, enable SQL statement logging.
        create_tables (bool): If true, create database tables directly (for testing only;
            production should use Alembic migrations).
        pool_pre_ping (bool): Test connections for liveness before using (recommended for Supabase).
        pool_recycle (int): Seconds after which to recycle connections (default 1800 = 30 minutes).

    Returns:
        PodcastRepositoryInterface: A repository instance backed by the resolved database URL.
    """
    if database_url is None:
        database_url = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)

    # Detect if using Supabase and optimize settings
    is_supabase = "supabase.co" in database_url or "pooler.supabase" in database_url

    if is_supabase:
        logger.info("Detected Supabase PostgreSQL - using optimized pool settings")
        pool_size = min(pool_size, 3)
        max_overflow = min(max_overflow, 2)

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

    repo = SQLAlchemyPodcastRepository(
        database_url=database_url,
        pool_size=pool_size,
        max_overflow=max_overflow,
        echo=echo,
        pool_pre_ping=pool_pre_ping,
        pool_recycle=pool_recycle,
    )

    # Create tables directly for testing (production should use Alembic migrations)
    if create_tables:
        Base.metadata.create_all(repo.engine)
        logger.info("Created database tables (testing mode)")

    return repo


def get_database_url_from_config(config) -> str:
    """
    Retrieve the database URL from a configuration object, falling back to the environment and a default.

    Parameters:
        config: An object that may have a `DATABASE_URL` attribute.

    Returns:
        The resolved database URL string from `config.DATABASE_URL`, the `DATABASE_URL` environment variable, or `DEFAULT_DATABASE_URL`.
    """
    return getattr(config, "DATABASE_URL", None) or os.getenv(
        "DATABASE_URL", DEFAULT_DATABASE_URL
    )
