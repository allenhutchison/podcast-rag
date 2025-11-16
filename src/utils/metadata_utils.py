"""
Utilities for handling podcast metadata.

Provides functions for loading, flattening, and converting metadata between
different formats used throughout the application.
"""
import json
import logging
import os
from typing import Dict, List, Optional


def deduplicate_preserving_order(items: List) -> List:
    """
    Deduplicate a list while preserving the original order.

    Uses a set for O(n) lookup performance while maintaining insertion order.
    Useful for combining host lists, keywords, etc.

    Args:
        items: List of items to deduplicate (must be hashable)

    Returns:
        List with duplicates removed, original order preserved

    Examples:
        >>> deduplicate_preserving_order(['A', 'B', 'A', 'C', 'B'])
        ['A', 'B', 'C']
        >>> deduplicate_preserving_order([])
        []
    """
    if not items:
        return []

    seen = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def load_metadata_from_file(metadata_path: str) -> Optional[Dict]:
    """
    Load metadata from a JSON file.

    Args:
        metadata_path: Path to the metadata JSON file

    Returns:
        Metadata dictionary or None if file doesn't exist or fails to load
    """
    if not os.path.exists(metadata_path):
        return None

    try:
        with open(metadata_path, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError, OSError) as e:
        logging.warning(f"Failed to load metadata from {metadata_path}: {e}")
        return None


def flatten_episode_metadata(metadata: Dict) -> Dict:
    """
    Flatten nested EpisodeMetadata structure to a flat dictionary.

    Handles both nested format (transcript_metadata, mp3_metadata) and
    already-flat formats. Combines hosts and co-hosts into a single list.

    Metadata Merge Priority:
    - Podcast/Episode titles: transcript_metadata only
    - Release date: transcript_metadata.date > mp3_metadata.release_date
    - Hosts: Combined from transcript_metadata.hosts + co_hosts + mp3_metadata.hosts
            (deduplicated while preserving order)
    - Guests/Keywords/Summary: transcript_metadata only

    Args:
        metadata: Nested or flat metadata dictionary

    Returns:
        Flattened metadata dictionary with keys:
        - podcast: str (from podcast_title)
        - episode: str (from episode_title)
        - release_date: str (from date or release_date)
        - hosts: list (combined and deduplicated)
        - guests: list
        - keywords: list
        - summary: str

    Examples:
        >>> nested = {
        ...     'transcript_metadata': {
        ...         'podcast_title': 'Tech Talk',
        ...         'episode_title': 'AI Advances',
        ...         'hosts': ['Alice'],
        ...         'date': '2024-01-15'
        ...     }
        ... }
        >>> result = flatten_episode_metadata(nested)
        >>> result['podcast']
        'Tech Talk'
        >>> result['episode']
        'AI Advances'
        >>> result['hosts']
        ['Alice']

        >>> # Already flat metadata passes through
        >>> flat = {'podcast': 'My Podcast', 'episode': 'Ep 1'}
        >>> flatten_episode_metadata(flat)
        {'podcast': 'My Podcast', 'episode': 'Ep 1'}

        >>> # Hosts are combined and deduplicated
        >>> nested = {
        ...     'transcript_metadata': {
        ...         'hosts': ['Alice', 'Bob'],
        ...         'co_hosts': ['Bob', 'Charlie']
        ...     },
        ...     'mp3_metadata': {'hosts': ['Alice', 'David']}
        ... }
        >>> result = flatten_episode_metadata(nested)
        >>> result['hosts']
        ['Alice', 'Bob', 'Charlie', 'David']
    """
    if not metadata:
        return {}

    # Handle Pydantic models by converting to dict
    if hasattr(metadata, 'model_dump'):
        metadata = metadata.model_dump()

    # Check if already flat (has 'podcast' or 'episode' keys directly)
    if 'podcast' in metadata or 'episode' in metadata:
        return metadata

    # Flatten nested structure
    flattened = {}

    # Get nested sections
    transcript_meta = metadata.get('transcript_metadata', {})
    mp3_meta = metadata.get('mp3_metadata', {})

    # Map podcast title
    if transcript_meta.get('podcast_title'):
        flattened['podcast'] = transcript_meta['podcast_title']

    # Map episode title
    if transcript_meta.get('episode_title'):
        flattened['episode'] = transcript_meta['episode_title']

    # Map release date (prefer transcript metadata, fall back to mp3 metadata)
    if transcript_meta.get('date'):
        flattened['release_date'] = transcript_meta['date']
    elif mp3_meta.get('release_date'):
        flattened['release_date'] = mp3_meta['release_date']

    # Combine hosts and co-hosts from both sources, with deduplication
    all_hosts = []
    if transcript_meta.get('hosts'):
        all_hosts.extend(transcript_meta['hosts'])
    if transcript_meta.get('co_hosts'):
        all_hosts.extend(transcript_meta['co_hosts'])
    if mp3_meta.get('hosts'):
        all_hosts.extend(mp3_meta['hosts'])

    # Deduplicate while preserving order using helper function
    if all_hosts:
        flattened['hosts'] = deduplicate_preserving_order(all_hosts)

    # Map guests
    if transcript_meta.get('guests'):
        flattened['guests'] = transcript_meta['guests']

    # Map keywords
    if transcript_meta.get('keywords'):
        flattened['keywords'] = transcript_meta['keywords']

    # Map summary
    if transcript_meta.get('summary'):
        flattened['summary'] = transcript_meta['summary']

    return flattened


def load_and_flatten_metadata(transcript_path: str, transcription_suffix: str = '_transcription.txt') -> Optional[Dict]:
    """
    Load metadata file corresponding to a transcript and flatten it.

    Constructs the metadata file path from the transcript path, loads it,
    and returns a flattened version.

    Args:
        transcript_path: Path to the transcript file
        transcription_suffix: Suffix used for transcription files (default: '_transcription.txt')

    Returns:
        Flattened metadata dictionary or None if not found
    """
    # Construct metadata file path
    base_path = transcript_path.replace(transcription_suffix, '')
    metadata_path = f"{base_path}_metadata.json"

    # Load raw metadata
    raw_metadata = load_metadata_from_file(metadata_path)
    if not raw_metadata:
        return None

    # Flatten and return
    return flatten_episode_metadata(raw_metadata)
