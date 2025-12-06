# Podcast Downloader & Database Abstraction Layer - Implementation Plan

**Status: IMPLEMENTED**

## Executive Summary

This document outlines the implementation of a podcast downloader system with a robust database abstraction layer. The system:

1. **Import OPML feeds** to discover podcast subscriptions
2. **Parse RSS feeds** to retrieve podcast and episode metadata
3. **Download episodes** with proper file management
4. **Store all data** in a database with cloud-agnostic abstraction
5. **Integrate** with existing transcription and RAG pipeline

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           User Interface                                 │
│                    (CLI commands / Scheduler)                           │
└─────────────────────────────┬───────────────────────────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────────────────┐
│                        Service Layer                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐  │
│  │ OPMLImporter │  │ FeedParser   │  │ Downloader   │  │FileManager  │  │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬──────┘  │
└─────────┼─────────────────┼─────────────────┼─────────────────┼─────────┘
          │                 │                 │                 │
┌─────────▼─────────────────▼─────────────────▼─────────────────▼─────────┐
│                      Repository Layer (Abstract)                         │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │                    PodcastRepository (Interface)                    │ │
│  │  - create_podcast() / get_podcast() / list_podcasts()              │ │
│  │  - create_episode() / get_episode() / list_episodes()              │ │
│  │  - update_download_status() / update_transcript_status()           │ │
│  └────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────┬───────────────────────────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────────────────┐
│                    Database Implementations                              │
│  ┌──────────────────────┐        ┌──────────────────────┐              │
│  │  SQLiteRepository    │        │  CloudSQLRepository  │              │
│  │  (Local Development) │        │  (Production)        │              │
│  └──────────────────────┘        └──────────────────────┘              │
└─────────────────────────────────────────────────────────────────────────┘
```

## Data Models

### 1. Podcast Model

Stores podcast-level metadata from RSS feeds.

```python
class Podcast(Base):
    __tablename__ = "podcasts"

    # Primary key
    id: str                          # UUID

    # Core identifiers
    feed_url: str                    # RSS feed URL (unique, indexed)
    website_url: Optional[str]       # Podcast website

    # Metadata from RSS feed
    title: str                       # Podcast title
    description: Optional[str]       # Podcast description
    author: Optional[str]            # Podcast author
    language: Optional[str]          # Language code (e.g., "en-us")

    # iTunes/Apple Podcasts specific
    itunes_id: Optional[str]         # Apple Podcasts ID
    itunes_author: Optional[str]     # iTunes author
    itunes_category: Optional[str]   # Primary category
    itunes_subcategory: Optional[str]
    itunes_explicit: Optional[bool]
    itunes_type: Optional[str]       # "episodic" or "serial"

    # Artwork
    image_url: Optional[str]         # Podcast cover art URL
    image_local_path: Optional[str]  # Local cached artwork path

    # Subscription management
    is_subscribed: bool = True       # Active subscription flag
    last_checked: Optional[datetime] # Last feed check timestamp
    last_new_episode: Optional[datetime]
    check_frequency_hours: int = 24  # How often to check for updates

    # File organization
    local_directory: Optional[str]   # Where episodes are stored

    # Timestamps
    created_at: datetime
    updated_at: datetime

    # Relationships
    episodes: List["Episode"]
```

### 2. Episode Model

Stores episode-level metadata, download status, and processing status.

```python
class Episode(Base):
    __tablename__ = "episodes"

    # Primary key
    id: str                          # UUID
    podcast_id: str                  # Foreign key to Podcast

    # Core identifiers
    guid: str                        # Globally unique ID from RSS (unique per podcast)

    # Metadata from RSS feed
    title: str                       # Episode title
    description: Optional[str]       # Episode description/show notes
    link: Optional[str]              # Episode webpage URL
    published_date: Optional[datetime]
    duration_seconds: Optional[int]  # Duration in seconds

    # Episode numbering
    episode_number: Optional[str]    # Episode number (e.g., "42", "S2E15")
    season_number: Optional[int]     # Season number
    episode_type: Optional[str]      # "full", "trailer", "bonus"

    # iTunes/Apple Podcasts specific
    itunes_title: Optional[str]      # iTunes-specific title
    itunes_episode: Optional[str]    # iTunes episode number
    itunes_season: Optional[int]     # iTunes season number
    itunes_explicit: Optional[bool]
    itunes_duration: Optional[str]   # Original duration string

    # Audio file info (from enclosure)
    enclosure_url: str               # Audio file URL
    enclosure_type: str              # MIME type (audio/mpeg, audio/mp4, etc.)
    enclosure_length: Optional[int]  # File size in bytes

    # Download status
    download_status: str = "pending" # pending, downloading, completed, failed, skipped
    download_error: Optional[str]    # Error message if failed
    downloaded_at: Optional[datetime]
    local_file_path: Optional[str]   # Path to downloaded file
    file_size_bytes: Optional[int]   # Actual file size after download
    file_hash: Optional[str]         # SHA256 hash for deduplication

    # Transcription status
    transcript_status: str = "pending"  # pending, processing, completed, failed, skipped
    transcript_error: Optional[str]
    transcript_path: Optional[str]   # Path to transcription file
    transcribed_at: Optional[datetime]

    # AI metadata extraction status
    metadata_status: str = "pending" # pending, processing, completed, failed, skipped
    metadata_error: Optional[str]
    metadata_path: Optional[str]     # Path to metadata JSON

    # AI-extracted metadata (from transcription)
    ai_summary: Optional[str]        # AI-generated summary
    ai_keywords: Optional[List[str]] # AI-extracted keywords (JSON)
    ai_hosts: Optional[List[str]]    # AI-extracted hosts (JSON)
    ai_guests: Optional[List[str]]   # AI-extracted guests (JSON)

    # File Search integration
    file_search_status: str = "pending"  # pending, uploading, indexed, failed, skipped
    file_search_error: Optional[str]
    file_search_resource_name: Optional[str]  # Gemini File Search resource name
    file_search_display_name: Optional[str]   # Display name in File Search
    file_search_uploaded_at: Optional[datetime]

    # Timestamps
    created_at: datetime
    updated_at: datetime

    # Relationships
    podcast: "Podcast"
```

### 3. OPMLImport Model (Optional - for tracking imports)

```python
class OPMLImport(Base):
    __tablename__ = "opml_imports"

    id: str
    filename: str
    imported_at: datetime
    podcasts_added: int
    podcasts_updated: int
    podcasts_skipped: int
```

## Repository Interface

### Abstract Repository Pattern

```python
from abc import ABC, abstractmethod
from typing import Optional, List
from datetime import datetime

class PodcastRepositoryInterface(ABC):
    """Abstract interface for podcast data persistence."""

    # --- Podcast Operations ---

    @abstractmethod
    def create_podcast(self, feed_url: str, **kwargs) -> Podcast:
        """Create a new podcast subscription."""
        pass

    @abstractmethod
    def get_podcast(self, podcast_id: str) -> Optional[Podcast]:
        """Get podcast by ID."""
        pass

    @abstractmethod
    def get_podcast_by_feed_url(self, feed_url: str) -> Optional[Podcast]:
        """Get podcast by feed URL."""
        pass

    @abstractmethod
    def list_podcasts(self, subscribed_only: bool = True) -> List[Podcast]:
        """List all podcasts, optionally filtering by subscription status."""
        pass

    @abstractmethod
    def update_podcast(self, podcast_id: str, **kwargs) -> Podcast:
        """Update podcast attributes."""
        pass

    @abstractmethod
    def delete_podcast(self, podcast_id: str, delete_files: bool = False) -> bool:
        """Delete a podcast and optionally its files."""
        pass

    # --- Episode Operations ---

    @abstractmethod
    def create_episode(self, podcast_id: str, guid: str, **kwargs) -> Episode:
        """Create a new episode."""
        pass

    @abstractmethod
    def get_episode(self, episode_id: str) -> Optional[Episode]:
        """Get episode by ID."""
        pass

    @abstractmethod
    def get_episode_by_guid(self, podcast_id: str, guid: str) -> Optional[Episode]:
        """Get episode by GUID within a podcast."""
        pass

    @abstractmethod
    def list_episodes(
        self,
        podcast_id: Optional[str] = None,
        download_status: Optional[str] = None,
        transcript_status: Optional[str] = None,
        limit: Optional[int] = None,
        offset: int = 0
    ) -> List[Episode]:
        """List episodes with optional filtering."""
        pass

    @abstractmethod
    def update_episode(self, episode_id: str, **kwargs) -> Episode:
        """Update episode attributes."""
        pass

    @abstractmethod
    def delete_episode(self, episode_id: str, delete_files: bool = False) -> bool:
        """Delete an episode and optionally its files."""
        pass

    # --- Batch Operations ---

    @abstractmethod
    def batch_create_episodes(self, podcast_id: str, episodes_data: List[dict]) -> List[Episode]:
        """Bulk create episodes (for feed sync)."""
        pass

    @abstractmethod
    def get_episodes_pending_download(self, limit: int = 10) -> List[Episode]:
        """Get episodes that need to be downloaded."""
        pass

    @abstractmethod
    def get_episodes_pending_transcription(self, limit: int = 10) -> List[Episode]:
        """Get downloaded episodes that need transcription."""
        pass

    @abstractmethod
    def get_episodes_pending_indexing(self, limit: int = 10) -> List[Episode]:
        """Get transcribed episodes that need File Search indexing."""
        pass

    # --- Status Update Helpers ---

    @abstractmethod
    def mark_download_started(self, episode_id: str) -> None:
        """Mark episode as currently downloading."""
        pass

    @abstractmethod
    def mark_download_complete(self, episode_id: str, local_path: str, file_size: int, file_hash: str) -> None:
        """Mark episode download as complete."""
        pass

    @abstractmethod
    def mark_download_failed(self, episode_id: str, error: str) -> None:
        """Mark episode download as failed."""
        pass

    # Similar methods for transcription and indexing...

    # --- Connection Management ---

    @abstractmethod
    def close(self) -> None:
        """Close database connection."""
        pass
```

## Implementation Components

### Phase 1: Database Foundation

**1.1 SQLAlchemy Models** (`src/db/models.py`)
- Define `Podcast` and `Episode` ORM models
- Support for both SQLite and PostgreSQL
- JSON column types for list fields (keywords, hosts, guests)

**1.2 Repository Implementation** (`src/db/repository.py`)
- `SQLAlchemyPodcastRepository` implementing the interface
- Connection pooling configuration
- Transaction management

**1.3 Database Factory** (`src/db/factory.py`)
- `create_repository(config)` factory function
- Auto-detect SQLite vs Cloud SQL based on `DATABASE_URL`
- Migration support with Alembic

**1.4 Configuration Updates** (`src/config.py`)
- Add `DATABASE_URL` environment variable
- Add `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_ECHO`
- Add podcast download directory config

### Phase 2: OPML Import

**2.1 OPML Parser** (`src/podcast/opml_parser.py`)
- Parse OPML XML files
- Extract podcast feed URLs and titles
- Handle nested outline structures
- Support various OPML flavors (Apple Podcasts, Overcast, etc.)

**2.2 OPML Import Service** (`src/podcast/opml_importer.py`)
- Import OPML file to database
- Skip duplicate feed URLs
- Report import statistics
- CLI command integration

### Phase 3: RSS Feed Parsing

**3.1 Feed Parser** (`src/podcast/feed_parser.py`)
- Parse RSS/Atom feeds using `feedparser` library
- Extract all podcast metadata (title, description, artwork, etc.)
- Extract all episode metadata (enclosure, duration, dates, etc.)
- Handle iTunes namespace extensions
- Normalize data formats (dates, durations)

**3.2 Feed Sync Service** (`src/podcast/feed_sync.py`)
- Sync podcast feed to database
- Detect new episodes
- Update changed episode metadata
- Track last sync timestamp

### Phase 4: Episode Downloader

**4.1 Download Manager** (`src/podcast/downloader.py`)
- Download audio files with progress tracking
- Resume interrupted downloads
- Verify file integrity (size, hash)
- Rate limiting and retry logic
- Concurrent download support

**4.2 File Organization**
- Organize files by podcast directory
- Filename normalization
- Handle duplicate prevention

### Phase 5: Integration

**5.1 Update FileManager** (`src/file_manager.py`)
- Integrate with repository for status tracking
- Update episode status after transcription
- Link File Search uploads to episode records

**5.2 Processing Pipeline**
- Queue-based processing workflow
- Status tracking at each stage
- Error handling and retry logic

**5.3 CLI Commands** (`src/cli.py` or scripts)
- `podcast import-opml <file>`
- `podcast add <feed_url>`
- `podcast sync [--podcast-id]`
- `podcast download [--podcast-id] [--limit]`
- `podcast status [--podcast-id]`
- `podcast list`

## File Structure

```
src/
├── db/
│   ├── __init__.py
│   ├── models.py              # SQLAlchemy ORM models
│   ├── repository.py          # Repository implementation
│   ├── factory.py             # Database factory
│   └── gemini_file_search.py  # Existing File Search manager
│
├── podcast/
│   ├── __init__.py
│   ├── opml_parser.py         # OPML parsing
│   ├── opml_importer.py       # OPML import service
│   ├── feed_parser.py         # RSS feed parsing
│   ├── feed_sync.py           # Feed synchronization
│   └── downloader.py          # Episode downloader
│
├── cli/
│   ├── __init__.py
│   └── podcast_commands.py    # CLI commands for podcast management
│
└── (existing files...)

alembic/
├── versions/
│   ├── 001_initial_schema.py  # Initial migration
│   └── ...
├── env.py
└── alembic.ini
```

## Configuration

### Environment Variables

```bash
# Database configuration
DATABASE_URL=sqlite:///./podcast_rag.db           # Local SQLite
# DATABASE_URL=postgresql://user:pass@host/db     # Cloud SQL

# Database pool settings (optional, for PostgreSQL)
DB_POOL_SIZE=5
DB_MAX_OVERFLOW=10
DB_ECHO=false                                     # SQL logging

# Podcast download settings
PODCAST_DOWNLOAD_DIRECTORY=/opt/podcasts          # Where to save episodes
PODCAST_MAX_CONCURRENT_DOWNLOADS=3
PODCAST_DOWNLOAD_RETRY_ATTEMPTS=3
PODCAST_DOWNLOAD_TIMEOUT=300                      # 5 minutes
```

## Migration Strategy

### For Existing Installations

1. **Generate migration from existing files**
   - Scan existing transcription files
   - Create episode records from metadata JSON files
   - Link to existing File Search uploads via cache

2. **Backwards compatibility**
   - Support running without database (file-based mode)
   - Gradual migration path

## Testing Strategy

### Unit Tests
- Repository CRUD operations
- OPML parsing edge cases
- RSS feed parsing with various formats
- Download manager retry logic

### Integration Tests
- End-to-end OPML import
- Feed sync with mock RSS server
- Download with mock file server
- Full pipeline from import to indexing

### Test Files Needed
- Sample OPML files (Apple Podcasts, Overcast, generic)
- Sample RSS feeds (various formats, iTunes extensions)
- Mock audio files for download testing

## Implementation Order

1. **Week 1: Database Foundation**
   - SQLAlchemy models
   - Repository interface and SQLite implementation
   - Configuration updates
   - Basic unit tests

2. **Week 2: OPML & Feed Parsing**
   - OPML parser
   - RSS feed parser
   - OPML import service
   - Feed sync service

3. **Week 3: Downloader**
   - Download manager
   - File organization
   - Status tracking
   - Retry logic

4. **Week 4: Integration**
   - FileManager integration
   - CLI commands
   - Migration script for existing data
   - Documentation

5. **Week 5: Production Readiness**
   - PostgreSQL/Cloud SQL testing
   - Alembic migrations
   - Error handling refinement
   - Performance optimization

## Dependencies to Add

```
# requirements.txt additions
sqlalchemy>=2.0
alembic>=1.13
feedparser>=6.0
aiohttp>=3.9        # For async downloads (optional)
python-magic>=0.4   # For file type detection
```

## Open Questions for User

1. **Download Strategy**: Should we download all episodes automatically, or only new episodes after subscription? Should there be a configurable retention policy?

2. **Episode Filtering**: Should we support filtering episodes by date range, keywords, or episode type during sync?

3. **Concurrent Downloads**: What's an acceptable default for concurrent downloads?

4. **Storage Limits**: Should we implement storage quotas or episode count limits per podcast?

5. **Cloud SQL Provider**: For production, are you planning to use Cloud SQL (PostgreSQL), Cloud Spanner, or another managed database?

6. **Existing Data Migration**: Do you want to migrate existing transcriptions/metadata from the file system into the database, or start fresh?
