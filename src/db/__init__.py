"""Database module for podcast data persistence.

Provides:
- SQLAlchemy ORM models (Podcast, Episode)
- Repository interface and implementation
- Factory function for creating repositories
"""

from .factory import create_repository, get_database_url_from_config
from .models import Base, Episode, Podcast
from .repository import PodcastRepositoryInterface, SQLAlchemyPodcastRepository

__all__ = [
    "Base",
    "Podcast",
    "Episode",
    "PodcastRepositoryInterface",
    "SQLAlchemyPodcastRepository",
    "create_repository",
    "get_database_url_from_config",
]
