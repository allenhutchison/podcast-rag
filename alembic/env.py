"""Alembic environment configuration for database migrations."""

import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.db.models import Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata


def get_url():
    """
    Determine the database URL for Alembic by checking environment variables and configuration.
    
    Checks the ALEMBIC_DATABASE_URL environment variable, then DATABASE_URL; if neither is set, returns the 'sqlalchemy.url' value from the Alembic configuration.
    
    Returns:
        str: The resolved database URL.
    """
    # Check environment variables first
    url = os.getenv("ALEMBIC_DATABASE_URL") or os.getenv("DATABASE_URL")
    if url:
        return url
    # Fall back to alembic.ini configuration
    return config.get_main_option("sqlalchemy.url")


def run_migrations_offline() -> None:
    """
    Execute database migrations using a URL without creating a live Engine.
    
    Configures the Alembic context with the resolved database URL and the module's
    target metadata, then runs migrations inside a transaction. This mode does not
    require a DBAPI or a live database connection.
    """
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Run migrations using a live database connection.

    Configure an Engine from the Alembic configuration, open a connection, configure the Alembic context with that connection and the module's target metadata, and execute migrations inside a transaction.
    """
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = get_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()