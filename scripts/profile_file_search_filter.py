#!/usr/bin/env python3
"""
Profile File Search API with different numbers of OR clauses in the metadata filter.

Usage:
    doppler run -- python scripts/profile_file_search_filter.py --email user@example.com
"""

import time
import sys
from functools import partial
from google import genai
from google.genai import types

# Force unbuffered output
print = partial(print, flush=True)

from src.config import Config
from src.db.gemini_file_search import GeminiFileSearchManager
from src.db.repository import SQLAlchemyPodcastRepository

import argparse

QUERY = "is money real definition social construct"
# Model to test with
FILE_SEARCH_MODEL = "gemini-3-flash-preview"


def get_subscription_podcasts(repository: SQLAlchemyPodcastRepository, user_email: str) -> list[str]:
    """Get podcast titles from a user's subscriptions."""
    user = repository.get_user_by_email(user_email)
    if not user:
        print(f"User {user_email} not found, using empty list")
        return []

    subscriptions = repository.get_user_subscriptions(user.id)
    titles = [p.title for p in subscriptions if p.title]
    print(f"Found {len(titles)} subscriptions for {user_email}")
    return titles


def build_filter(podcasts: list[str], num_podcasts: int) -> str:
    """Build a metadata filter with the specified number of OR clauses."""
    if num_podcasts == 0:
        return 'type="transcript"'

    subset = podcasts[:num_podcasts]
    or_clauses = [f'podcast="{p}"' for p in subset]
    return f'type="transcript" AND ({" OR ".join(or_clauses)})'


def test_query(client: genai.Client, store_name: str, podcasts: list[str], num_podcasts: int, timeout: float = 60.0) -> dict:
    """Test a query with the given number of OR clauses."""
    metadata_filter = build_filter(podcasts, num_podcasts)
    filter_len = len(metadata_filter)

    print(f"\n{'='*60}")
    print(f"Testing with {num_podcasts} OR clauses (filter length: {filter_len} chars)")
    print(f"Filter: {metadata_filter[:100]}..." if len(metadata_filter) > 100 else f"Filter: {metadata_filter}")

    file_search_config = types.FileSearch(
        file_search_store_names=[store_name],
        metadata_filter=metadata_filter
    )

    start_time = time.time()
    try:
        print(f"Making API call to {FILE_SEARCH_MODEL}...")
        response = client.models.generate_content(
            model=FILE_SEARCH_MODEL,
            contents=f"Search podcast transcripts for: {QUERY}",
            config=types.GenerateContentConfig(
                tools=[types.Tool(file_search=file_search_config)],
                response_modalities=["TEXT"]
            )
        )
        elapsed = time.time() - start_time
        print(f"API call returned after {elapsed:.2f}s")

        # Check if we got a valid response
        has_text = hasattr(response, 'text') and response.text
        text_preview = response.text[:100] if has_text else "No text"

        print(f"✓ Success in {elapsed:.2f}s")
        print(f"  Response: {text_preview}...")

        return {
            "num_podcasts": num_podcasts,
            "filter_length": filter_len,
            "elapsed": elapsed,
            "success": True,
            "has_response": has_text
        }

    except Exception as e:
        elapsed = time.time() - start_time
        print(f"✗ Failed after {elapsed:.2f}s: {e}")
        return {
            "num_podcasts": num_podcasts,
            "filter_length": filter_len,
            "elapsed": elapsed,
            "success": False,
            "error": str(e)
        }


def main():
    parser = argparse.ArgumentParser(description="Profile File Search API with different OR clause counts")
    parser.add_argument("--email", required=True, help="User email to get subscriptions for")
    args = parser.parse_args()

    config = Config()
    client = genai.Client(api_key=config.GEMINI_API_KEY)

    # Get the store name
    file_search_manager = GeminiFileSearchManager(config)
    store_name = file_search_manager.create_or_get_store()
    print(f"Using store: {store_name}")

    # Get subscriptions from database
    repository = SQLAlchemyPodcastRepository(config.DATABASE_URL)
    podcasts = get_subscription_podcasts(repository, args.email)

    if not podcasts:
        print("No subscriptions found, exiting")
        return

    # Test different numbers of OR clauses
    max_count = len(podcasts)
    test_counts = [0, 1, 5, 10, 15, 20, 25, 30, 35, 40, 45, min(49, max_count), max_count]
    # Remove duplicates and sort
    test_counts = sorted(set(c for c in test_counts if c <= max_count))

    results = []
    for count in test_counts:
        result = test_query(client, store_name, podcasts, count)
        results.append(result)

        # If it failed or took too long, we might want to stop
        if not result["success"]:
            print(f"\nStopping after failure at {count} OR clauses")
            break
        if result["elapsed"] > 30:
            print(f"\nStopping after slow response ({result['elapsed']:.1f}s) at {count} OR clauses")
            break

    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    print(f"{'OR Clauses':<12} {'Filter Len':<12} {'Time (s)':<10} {'Status'}")
    print("-" * 50)
    for r in results:
        status = "✓" if r["success"] else "✗"
        print(f"{r['num_podcasts']:<12} {r['filter_length']:<12} {r['elapsed']:<10.2f} {status}")


if __name__ == "__main__":
    main()
