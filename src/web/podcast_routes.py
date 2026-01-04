"""API routes for podcast management: adding, searching, and importing podcasts.

Provides endpoints for:
- Adding podcasts by feed URL
- Searching podcasts via iTunes Search API
- Importing podcasts from OPML files
"""

import asyncio
import logging
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request

from src.podcast.feed_sync import FeedSyncService
from src.podcast.opml_parser import OPMLParser
from src.web.auth import get_current_user
from src.web.models import (
    AddPodcastByUrlRequest,
    AddPodcastResponse,
    OPMLImportRequest,
    OPMLImportResponse,
    OPMLImportResult,
    PodcastSearchResponse,
    PodcastSearchResult,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/podcasts", tags=["podcasts"])

# iTunes Search API endpoint
ITUNES_SEARCH_URL = "https://itunes.apple.com/search"


@router.post("/add", response_model=AddPodcastResponse)
async def add_podcast_by_url(
    request: Request,
    body: AddPodcastByUrlRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Add a podcast to the system by its RSS feed URL.

    If the podcast already exists, subscribes the user to it.
    If new, adds the podcast to the system and subscribes the user.

    Args:
        body: Request containing the feed URL
        current_user: Authenticated user from JWT cookie

    Returns:
        AddPodcastResponse with podcast details and subscription status
    """
    repository = request.app.state.repository
    config = request.app.state.config
    user_id = current_user["sub"]
    feed_url = body.feed_url.strip()

    # Validate URL format
    if not feed_url.startswith(("http://", "https://", "feed://")):
        raise HTTPException(
            status_code=400,
            detail="Invalid feed URL. Must start with http://, https://, or feed://"
        )

    # Normalize feed:// URLs to https://
    if feed_url.startswith("feed://"):
        feed_url = "https://" + feed_url[7:]

    # Check if podcast already exists (run in thread to avoid blocking)
    existing_podcast = await asyncio.to_thread(
        repository.get_podcast_by_feed_url, feed_url
    )

    if existing_podcast:
        # Podcast exists - just subscribe the user
        was_subscribed = await asyncio.to_thread(
            repository.is_user_subscribed, user_id, existing_podcast.id
        )

        if not was_subscribed:
            await asyncio.to_thread(
                repository.subscribe_user_to_podcast, user_id, existing_podcast.id
            )

        # Get episode count
        episodes = await asyncio.to_thread(
            repository.list_episodes, podcast_id=existing_podcast.id
        )

        return AddPodcastResponse(
            podcast_id=existing_podcast.id,
            title=existing_podcast.title,
            is_new=False,
            is_subscribed=True,
            episode_count=len(episodes),
            message="Subscribed to existing podcast" if not was_subscribed else "Already subscribed",
        )

    # Add new podcast
    try:
        sync_service = FeedSyncService(
            repository=repository,
            download_directory=config.PODCAST_DOWNLOAD_DIRECTORY,
        )

        # Run in thread pool to avoid blocking the event loop
        # (add_podcast_from_url does blocking HTTP requests and DB writes)
        result = await asyncio.to_thread(
            sync_service.add_podcast_from_url, feed_url
        )

        if result["error"]:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to add podcast: {result['error']}"
            )

        podcast_id = result["podcast_id"]
        title = result["title"]
        episode_count = result["episodes"]

        # Subscribe the user to the new podcast
        await asyncio.to_thread(
            repository.subscribe_user_to_podcast, user_id, podcast_id
        )

        logger.info(f"User {user_id} added and subscribed to new podcast: {title}")

        return AddPodcastResponse(
            podcast_id=podcast_id,
            title=title,
            is_new=True,
            is_subscribed=True,
            episode_count=episode_count,
            message=f"Added podcast with {episode_count} episodes",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error adding podcast from {feed_url}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to add podcast: {str(e)}"
        ) from e


@router.get("/search", response_model=PodcastSearchResponse)
async def search_podcasts(
    request: Request,
    q: str,
    limit: int = 20,
    current_user: dict = Depends(get_current_user),
):
    """
    Search for podcasts using the iTunes Search API.

    Args:
        request: FastAPI request object for accessing repository
        q: Search query string
        limit: Maximum number of results (1-50, default 20)
        current_user: Authenticated user from JWT cookie

    Returns:
        PodcastSearchResponse with search results including subscription status
    """
    if not q or not q.strip():
        raise HTTPException(status_code=400, detail="Search query cannot be empty")

    query = q.strip()
    limit = max(1, min(50, limit))  # Clamp between 1 and 50
    repository = request.app.state.repository
    user_id = current_user["sub"]

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                ITUNES_SEARCH_URL,
                params={
                    "term": query,
                    "media": "podcast",
                    "entity": "podcast",
                    "limit": limit,
                },
            )
            response.raise_for_status()
            data = response.json()

        results = []
        for item in data.get("results", []):
            # Skip items without a feed URL
            feed_url = item.get("feedUrl")
            if not feed_url:
                continue

            # Check if podcast exists in database and if user is subscribed
            is_subscribed = False
            podcast_id = None
            existing_podcast = await asyncio.to_thread(
                repository.get_podcast_by_feed_url, feed_url
            )
            if existing_podcast:
                podcast_id = existing_podcast.id
                is_subscribed = await asyncio.to_thread(
                    repository.is_user_subscribed, user_id, existing_podcast.id
                )

            results.append(
                PodcastSearchResult(
                    title=item.get("collectionName", item.get("trackName", "Unknown")),
                    author=item.get("artistName", ""),
                    feed_url=feed_url,
                    image_url=item.get("artworkUrl600") or item.get("artworkUrl100"),
                    description=None,  # iTunes API doesn't return descriptions in search
                    genre=item.get("primaryGenreName"),
                    is_subscribed=is_subscribed,
                    podcast_id=podcast_id,
                )
            )

        return PodcastSearchResponse(
            query=query,
            results=results,
            count=len(results),
        )

    except httpx.TimeoutException as e:
        raise HTTPException(
            status_code=504,
            detail="iTunes search timed out. Please try again."
        ) from e
    except httpx.HTTPStatusError as e:
        logger.exception(f"iTunes API error: {e.response.status_code}")
        raise HTTPException(
            status_code=502,
            detail="iTunes search service temporarily unavailable"
        ) from e
    except Exception as e:
        logger.exception("Error searching podcasts")
        raise HTTPException(
            status_code=500,
            detail="Failed to search podcasts"
        ) from e


@router.post("/import-opml", response_model=OPMLImportResponse)
async def import_opml(
    request: Request,
    body: OPMLImportRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Import podcasts from an OPML file.

    Parses the OPML content, adds new podcasts to the system,
    and subscribes the user to all podcasts (new and existing).

    Args:
        body: Request containing OPML XML content
        current_user: Authenticated user from JWT cookie

    Returns:
        OPMLImportResponse with import statistics and per-feed results
    """
    repository = request.app.state.repository
    config = request.app.state.config
    user_id = current_user["sub"]

    # Parse OPML content
    parser = OPMLParser()
    try:
        parsed = parser.parse_string(body.content)
    except Exception as e:
        logger.exception("OPML parse error")
        raise HTTPException(
            status_code=400,
            detail=f"Invalid OPML format: {str(e)}"
        ) from e

    if not parsed.feeds:
        return OPMLImportResponse(
            total=0,
            added=0,
            existing=0,
            failed=0,
            results=[],
        )

    # Process each feed
    results = []
    added_count = 0
    existing_count = 0
    failed_count = 0

    sync_service = FeedSyncService(
        repository=repository,
        download_directory=config.PODCAST_DOWNLOAD_DIRECTORY,
    )

    for feed in parsed.feeds:
        feed_url = feed.feed_url
        title = feed.title

        try:
            # Check if podcast already exists (run in thread to avoid blocking)
            existing = await asyncio.to_thread(
                repository.get_podcast_by_feed_url, feed_url
            )

            if existing:
                # Subscribe user to existing podcast
                was_subscribed = await asyncio.to_thread(
                    repository.is_user_subscribed, user_id, existing.id
                )
                if not was_subscribed:
                    await asyncio.to_thread(
                        repository.subscribe_user_to_podcast, user_id, existing.id
                    )

                existing_count += 1
                results.append(
                    OPMLImportResult(
                        feed_url=feed_url,
                        title=existing.title,
                        status="existing",
                        podcast_id=existing.id,
                    )
                )
            else:
                # Add new podcast
                # Run in thread pool to avoid blocking the event loop
                add_result = await asyncio.to_thread(
                    sync_service.add_podcast_from_url, feed_url
                )

                if add_result["error"]:
                    failed_count += 1
                    results.append(
                        OPMLImportResult(
                            feed_url=feed_url,
                            title=title,
                            status="failed",
                            error=add_result["error"],
                        )
                    )
                else:
                    # Subscribe user to new podcast
                    await asyncio.to_thread(
                        repository.subscribe_user_to_podcast,
                        user_id,
                        add_result["podcast_id"],
                    )

                    added_count += 1
                    results.append(
                        OPMLImportResult(
                            feed_url=feed_url,
                            title=add_result["title"],
                            status="added",
                            podcast_id=add_result["podcast_id"],
                        )
                    )

        except Exception as e:
            logger.exception(f"Error importing feed {feed_url}")
            failed_count += 1
            results.append(
                OPMLImportResult(
                    feed_url=feed_url,
                    title=title,
                    status="failed",
                    error=str(e),
                )
            )

    logger.info(
        f"OPML import complete for user {user_id}: "
        f"{added_count} added, {existing_count} existing, {failed_count} failed"
    )

    return OPMLImportResponse(
        total=len(parsed.feeds),
        added=added_count,
        existing=existing_count,
        failed=failed_count,
        results=results,
    )
