# RSS/Atom Article Feed Support - Implementation Plan

## Overview

Add support for RSS/Atom article feeds (blogs, news sites, newsletters) as a
first-class content type alongside podcasts. Article feeds go through the same
subscription, search, email digest, and RAG query features but with an
article-appropriate processing pipeline (fetch article text instead of
download + transcribe audio).

## Design Decision: Extend Existing Models vs. New Models

**Decision: Extend the existing `Podcast` and `Episode` models with a
`content_type` discriminator.**

Rationale:
- `Podcast` is structurally a "feed source" and `Episode` is a "feed item" -
  the naming is podcast-centric but the shape is general.
- `UserSubscription` already links users to `Podcast` - no schema changes
  needed for subscriptions.
- The email digest system queries by subscription - works unchanged.
- Gemini File Search is content-agnostic - uploads text with metadata.
- The RAG query system doesn't care about content origin.
- Creating parallel `Feed`/`FeedItem` models would duplicate ~40 repository
  methods, subscription logic, email digest queries, web routes, agent tools,
  and test infrastructure for very little structural benefit.

---

## Phase 1: Database & Model Changes

### 1.1 Add `content_type` to `Podcast` model

```python
# src/db/models.py - Podcast class
content_type: Mapped[str] = mapped_column(
    String(32), default="podcast", nullable=False, server_default="podcast"
)  # "podcast" or "feed"
```

Add index: `Index("ix_podcasts_content_type", "content_type")`

### 1.2 Make audio-specific Episode fields nullable

Currently `enclosure_url` and `enclosure_type` are `nullable=False`. Article
feed items have no audio enclosure. These need to become nullable:

```python
enclosure_url: Mapped[str | None] = mapped_column(String(2048))
enclosure_type: Mapped[str | None] = mapped_column(String(64))
```

### 1.3 Add article-specific fields to `Episode`

```python
# Article content
article_url: Mapped[str | None] = mapped_column(String(2048))
article_content: Mapped[str | None] = mapped_column(Text)
article_author: Mapped[str | None] = mapped_column(String(512))

# Article fetch status (parallel to download_status for podcasts)
article_fetch_status: Mapped[str] = mapped_column(
    String(32), default="pending", server_default="pending"
)  # pending, fetching, completed, failed, skipped
article_fetch_error: Mapped[str | None] = mapped_column(Text)
article_fetched_at: Mapped[datetime | None] = mapped_column(DateTime)
article_fetch_retry_count: Mapped[int] = mapped_column(Integer, default=0)
```

Add index: `Index("ix_episodes_article_fetch_status", "article_fetch_status")`

### 1.4 Update `Episode.is_fully_processed`

```python
@property
def is_fully_processed(self) -> bool:
    if self.podcast and self.podcast.content_type == "feed":
        return (
            self.article_fetch_status == "completed"
            and self.metadata_status == "completed"
            and self.file_search_status == "indexed"
        )
    return (
        self.transcript_status == "completed"
        and self.metadata_status == "completed"
        and self.file_search_status == "indexed"
    )
```

### 1.5 Alembic migration

Create migration:
- Add `content_type` column to `podcasts` with server_default `"podcast"`
- Make `enclosure_url` and `enclosure_type` nullable
- Add `article_url`, `article_content`, `article_author`,
  `article_fetch_status`, `article_fetch_error`, `article_fetched_at`,
  `article_fetch_retry_count` to `episodes`
- Add indexes

### Files changed
- `src/db/models.py`
- `alembic/versions/<new>_add_article_feed_support.py`

---

## Phase 2: Feed Detection & Parsing

### 2.1 Extend `FeedParser` for article detection

The current `_parse_episode()` returns `None` for entries without audio
enclosures, which means article feeds would yield zero episodes. We need a
parallel path:

```python
# src/podcast/feed_parser.py

@dataclass
class ParsedFeedItem:
    """Parsed item from an article feed (no audio enclosure)."""
    guid: str
    title: str
    link: str | None = None
    description: str | None = None
    published_date: datetime | None = None
    author: str | None = None
    content: str | None = None  # Full content from <content:encoded> or <description>
```

Add to `ParsedPodcast`:
```python
content_type: str = "podcast"  # "podcast" or "feed"
feed_items: list[ParsedFeedItem] = field(default_factory=list)
```

### 2.2 Detection logic

In `_parse_feed()`, after parsing episodes:
- If `len(podcast.episodes) == 0` and there are entries in the feed, parse
  them as article items into `feed_items` and set `content_type = "feed"`.
- A feed entry is an article if it has a `<link>` or `<content:encoded>` but
  no audio enclosure.
- Some feeds have both articles and audio (e.g., show notes + episode). In
  this case, keep `content_type = "podcast"` since the audio episodes are
  the primary content. The article content from `<description>` is already
  captured in the episode's `description` field.

### 2.3 Extract article content from feed

For article feeds, extract the full text from:
1. `content:encoded` (richest source, common in WordPress feeds)
2. `content[0].value` (Atom feeds)
3. `description` / `summary` (fallback, may be truncated)

Strip HTML tags and store as plain text in `ParsedFeedItem.content`.

### Files changed
- `src/podcast/feed_parser.py`
- `tests/test_feed_parser.py`

---

## Phase 3: Feed Sync Updates

### 3.1 Extend `FeedSyncService`

Update `add_podcast_from_url()` to handle article feeds:
- Set `content_type` on the Podcast record based on `ParsedPodcast.content_type`
- For article feeds, create episodes from `parsed.feed_items` instead of
  `parsed.episodes`

Update `_add_new_episodes()` (or add `_add_new_articles()`):
- For article items, set `article_url = item.link`,
  `article_content = item.content`, `article_author = item.author`
- Set `enclosure_url = None`, `enclosure_type = None`
- Set `download_status = "skipped"`, `transcript_status = "skipped"`
- Set `article_fetch_status = "completed"` if feed content is available,
  otherwise `"pending"` (will be fetched later)

### 3.2 Extend `SyncWorker`

The sync worker currently only syncs podcasts with subscribers. It should also
sync article feeds with subscribers. Since article feeds use the same
`Podcast` model, `list_podcasts_with_subscribers()` already returns them.
The `FeedSyncService.sync_podcast()` method needs to handle both types.

### Files changed
- `src/podcast/feed_sync.py`
- `src/workflow/workers/sync.py`
- `tests/test_feed_sync.py`

---

## Phase 4: Article Content Fetching

### 4.1 New `ArticleFetchWorker`

Create `src/workflow/workers/article_fetch.py`:

This worker fetches the full text of articles when the feed only provides a
summary/excerpt. Many RSS feeds only include the first paragraph - the full
article lives at the `link` URL.

```python
class ArticleFetchWorker(WorkerInterface):
    """Fetches full article content from URLs for article feed items."""

    def process_batch(self, limit: int) -> WorkerResult:
        """Fetch articles pending content retrieval."""
        episodes = self.repository.get_articles_pending_fetch(limit=limit)
        for episode in episodes:
            html = self._fetch_url(episode.article_url)
            text = self._extract_text(html)
            self.repository.mark_article_fetch_complete(episode.id, text)
```

Content extraction options (in order of preference):
1. **`trafilatura`** - purpose-built for web article extraction, handles
   boilerplate removal well, pure Python, already widely used. Add as
   dependency via `uv add trafilatura`.
2. **`readability-lxml`** - Mozilla Readability port, good at finding the
   main content block.
3. **`beautifulsoup4`** - manual extraction as fallback.

If the feed already provides full content (detected by content length > some
threshold, e.g., 500 chars), skip fetching and use the feed content directly.

### 4.2 Repository methods

Add to `PodcastRepositoryInterface`:
```python
def get_articles_pending_fetch(self, limit: int) -> list[Episode]
def mark_article_fetch_started(self, episode_id: str) -> None
def mark_article_fetch_complete(self, episode_id: str, content: str) -> None
def mark_article_fetch_failed(self, episode_id: str, error: str) -> None
```

### Files changed
- `src/workflow/workers/article_fetch.py` (new)
- `src/db/repository.py`
- `pyproject.toml` (add `trafilatura` dependency)
- `tests/test_article_fetch_worker.py` (new)

---

## Phase 5: Pipeline Orchestrator Changes

### 5.1 Dual-track pipeline

The current pipeline is structured as:
```
Sync → Download → Transcribe → [Post-process: Metadata → Index → Cleanup]
```

For article feeds, the pipeline becomes:
```
Sync → Fetch Article Content → [Post-process: Metadata → Index]
```

The orchestrator needs to handle both tracks. The simplest approach:

In `_pipeline_iteration()`:
1. After checking sync and email timers, check for pending article fetches
2. Article fetching is I/O-bound (not GPU-bound), so it can run in the
   post-processor thread pool alongside metadata and indexing
3. The transcription loop continues to only handle podcast episodes

```python
def _pipeline_iteration(self) -> bool:
    self._maybe_run_sync()
    self._maybe_run_email_digests()
    self._maybe_fetch_articles()       # NEW
    self._maintain_download_buffer()

    episode = self.repository.get_next_for_transcription()
    # ... existing transcription logic
```

### 5.2 Post-processor changes

The `PostProcessor` currently runs: Metadata → Indexing → Description Indexing
→ Cleanup for each episode.

For article episodes, the sequence is: Metadata → Indexing (no cleanup needed
since there are no audio files).

The post-processor should check the episode's parent podcast `content_type`
and skip irrelevant steps.

### Files changed
- `src/workflow/orchestrator.py`
- `src/workflow/post_processor.py`
- `tests/test_orchestrator.py`

---

## Phase 6: Metadata Extraction for Articles

### 6.1 Article metadata prompt

Create `prompts/article_metadata_extraction.txt` - a prompt tailored for
article content (no hosts/guests, instead extract author, publication, topic
category).

### 6.2 Article-specific Pydantic schema

```python
# src/schemas.py
class ArticleMetadata(BaseModel):
    title: str
    author: str | None
    source: str | None  # Publication name
    summary: str
    keywords: list[str]
    email_content: EmailContent | None  # Reuse the existing schema
```

### 6.3 MetadataWorker changes

Extend `_process_episode()` to detect content type:
- If podcast `content_type == "feed"`, use `article_content` instead of
  `transcript_text`
- Use the article metadata prompt instead of the podcast prompt
- Skip MP3 tag reading
- Use `ArticleMetadata` schema for structured output

### Files changed
- `src/schemas.py`
- `src/workflow/workers/metadata.py`
- `prompts/article_metadata_extraction.txt` (new)
- `tests/test_metadata_worker.py`

---

## Phase 7: Indexing Changes

### 7.1 IndexingWorker for articles

Extend `_index_episode()` to handle articles:
- Use `article_content` instead of `transcript_text`
- Set metadata `type` to `"article"` instead of `"transcript"`
- Include `author` and `source` in metadata
- Build display name from article title (not transcript filename)

```python
def _build_metadata(self, episode: Episode) -> dict[str, Any]:
    podcast = episode.podcast
    if podcast and podcast.content_type == "feed":
        return {
            "type": "article",
            "source": podcast.title,
            "article_title": episode.title,
            "author": episode.article_author,
            "release_date": ...,
            "keywords": episode.ai_keywords,
            "summary": episode.ai_summary,
        }
    # existing podcast metadata
    return { ... }
```

### 7.2 IndexingWorker text source

```python
def _get_content_text(self, episode: Episode) -> str:
    if episode.podcast and episode.podcast.content_type == "feed":
        return episode.article_content
    return self.repository.get_transcript_text(episode.id)
```

### Files changed
- `src/workflow/workers/indexing.py`
- `tests/test_indexing_worker.py`

---

## Phase 8: Search & RAG

### 8.1 File Search metadata filtering

Gemini File Search supports metadata filtering. The `type` field already
distinguishes `"transcript"` vs `"description"`. Adding `"article"` is
seamless - articles will appear in search results alongside transcripts.

### 8.2 RAG query system

`src/rag.py` uses Gemini's File Search tool which automatically searches
across all documents in the store. Articles will be returned alongside
podcast transcripts based on semantic relevance. No code changes needed for
basic functionality.

Optional enhancement: add a `content_type` filter parameter to `RagManager.query()`
so users can search only articles or only podcasts.

### 8.3 Agent tools

Update `src/agents/chat_tools.py` to include content type in search context
so the synthesizer agent can distinguish sources:

```python
# In podcast_search tool response, include content type
"type": "article" or "podcast_transcript"
```

### Files changed
- `src/rag.py` (optional filter parameter)
- `src/agents/chat_tools.py`
- `src/agents/podcast_search.py`

---

## Phase 9: Email Digest Integration

### 9.1 Email digest content for articles

The `EmailDigestWorker` queries `get_new_episodes_for_user_since()` which
returns episodes from subscribed podcasts. Since article feeds use the same
`Podcast`/`Episode`/`UserSubscription` models, articles will automatically
be included in digest queries.

### 9.2 Email renderer changes

Update `render_digest_html()` and `render_digest_text()` to:
- Group by content type (podcast episodes first, then articles, or
  interleaved by recency)
- Use appropriate section headers ("New Episodes" vs "New Articles")
- For articles, link to the article URL instead of the episode page
- Skip "View episode" link for articles; use "Read article" instead

The `EmailContent` schema (`teaser_summary`, `key_takeaways`,
`highlight_moment`) works for articles too - the AI metadata extraction
will populate these fields from article content.

### 9.3 Email subject line

Update subject to reflect mixed content:
```python
# Current
f"Your Daily Podcast Digest - {len(episodes)} new episode{'s'...}"

# Updated
f"Your Daily Digest - {n_episodes} episode{'s'...}, {n_articles} article{'s'...}"
```

### Files changed
- `src/services/email_renderer.py`
- `src/workflow/workers/email_digest.py`
- `tests/test_email_renderer.py`

---

## Phase 10: Web App & API

### 10.1 Add feed by URL

Extend `POST /api/podcasts/add` to detect and handle article feeds:
- The existing endpoint calls `FeedSyncService.add_podcast_from_url()` which
  will now handle both types after Phase 3 changes
- Return `content_type` in the response so the UI can display appropriately

### 10.2 Subscription management

Update `GET /api/users/subscriptions` (or equivalent) to include
`content_type` so the UI can show podcast and feed subscriptions separately
or with different icons.

### 10.3 Web models

Add `content_type` field to relevant Pydantic response models:
```python
class AddPodcastResponse(BaseModel):
    # ... existing fields
    content_type: str = "podcast"  # "podcast" or "feed"
```

### 10.4 Frontend changes

Update the static frontend to:
- Show a feed icon vs podcast icon based on `content_type`
- Display article items differently (link to article URL, no audio player)
- Update "Add Podcast" UI to also say "or RSS/Atom feed"
- Episode detail page: show article content for feeds, transcript for podcasts

### Files changed
- `src/web/podcast_routes.py`
- `src/web/models.py`
- `src/web/user_routes.py`
- `src/web/static/` (frontend JS/HTML)

---

## Phase 11: CLI Updates

### 11.1 Add feed command

Extend `add-podcast` CLI command (or add `add-feed` alias):
```bash
doppler run -- python -m src.cli podcast add-feed https://example.com/rss
```

The existing `add-podcast` command should work for both since feed detection
is automatic. An alias improves discoverability.

### 11.2 Status command

Update `status` to show article feed stats:
```
Podcasts: 12 (45 episodes indexed)
Feeds: 3 (127 articles indexed)
  - Pending article fetch: 5
```

### Files changed
- `src/cli/podcast_commands.py`

---

## Phase 12: MCP Server

Update `src/mcp_server.py` tools to include content type information:
- `get_rag_context()` - no changes needed (searches all content)
- `search_podcasts()` - include content_type in results

### Files changed
- `src/mcp_server.py`

---

## Phase 13: Configuration

### 13.1 New config options

```python
# src/config.py
ARTICLE_FETCH_TIMEOUT: int = 30  # seconds
ARTICLE_FETCH_MAX_RETRIES: int = 3
ARTICLE_FETCH_USER_AGENT: str = "PodcastRAG/1.0"
ARTICLE_MAX_CONTENT_LENGTH: int = 500_000  # chars, ~500KB
```

### Files changed
- `src/config.py`

---

## Implementation Order

Recommended order to allow incremental development and testing:

1. **Phase 1** - Database & models (foundation, everything depends on this)
2. **Phase 2** - Feed parser updates (can test parsing independently)
3. **Phase 3** - Feed sync updates (enables adding article feeds to DB)
4. **Phase 4** - Article content fetching (core new worker)
5. **Phase 6** - Metadata extraction for articles
6. **Phase 7** - Indexing changes
7. **Phase 5** - Pipeline orchestrator integration (ties workers together)
8. **Phase 8** - Search & RAG (enable querying articles)
9. **Phase 9** - Email digest (include articles in digests)
10. **Phase 10** - Web app & API
11. **Phase 11** - CLI updates
12. **Phase 12** - MCP server
13. **Phase 13** - Configuration

Each phase can be developed and tested independently with its own PR.

---

## New Dependencies

| Package | Purpose | Size |
|---------|---------|------|
| `trafilatura` | Article text extraction from HTML | ~5MB |

Install: `uv add trafilatura`

---

## Test Plan

### New test files
- `tests/test_article_feed_parser.py` - Article feed detection and parsing
- `tests/test_article_fetch_worker.py` - Content fetching and extraction
- `tests/test_article_metadata.py` - Article metadata extraction
- `tests/test_article_indexing.py` - Article indexing to File Search
- `tests/test_article_email_digest.py` - Articles in email digests
- `tests/test_article_pipeline.py` - End-to-end article pipeline

### Updated test files
- `tests/test_feed_parser.py` - Existing podcast parsing still works
- `tests/test_feed_sync.py` - Sync handles both content types
- `tests/test_workflow.py` - Pipeline handles both content types
- `tests/test_repository.py` - New repository methods
- `tests/test_web_app.py` - API returns content_type
- `tests/test_email_renderer.py` - Mixed content digests

### Test data
- Sample RSS 2.0 article feed (blog-style)
- Sample Atom article feed
- Mixed feed (articles + enclosures) to verify detection
- Feed with full `<content:encoded>` vs summary-only

---

## Migration Safety

- All new columns have defaults or are nullable - safe for existing data
- `enclosure_url`/`enclosure_type` becoming nullable won't affect existing
  rows (they all have values)
- `content_type` defaults to `"podcast"` - existing records are correct
- No data migration needed - only schema changes
- Rollback: drop new columns, restore NOT NULL constraints on enclosure fields

---

## Key Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Article extraction quality varies | Poor search results | Use trafilatura (best-in-class); fall back to feed content |
| Some feeds are mixed (articles + podcasts) | Incorrect content_type | Detect by presence of audio enclosures; if any entries have audio, treat as podcast |
| Rate limiting on article fetches | Slow processing | Respect robots.txt, add configurable delays, concurrent fetching with limits |
| Large article content | DB bloat | Cap at configurable max length (500K chars) |
| Feed content is HTML-heavy | Poor indexing | Strip HTML before storing; trafilatura handles this |
