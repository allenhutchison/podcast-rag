"""OPML parser for importing podcast subscriptions.

Supports various OPML flavors from podcast apps like:
- Apple Podcasts
- Overcast
- Pocket Casts
- AntennaPod
- Generic RSS readers
"""

import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Union

logger = logging.getLogger(__name__)


@dataclass
class PodcastFeed:
    """Represents a podcast feed extracted from OPML."""

    feed_url: str
    title: Optional[str] = None
    website_url: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None

    def __post_init__(self):
        """
        Ensure the feed_url is present and normalized.
        
        Validates that the dataclass instance has a non-empty `feed_url` and trims surrounding whitespace from it.
        
        Raises:
            ValueError: If `feed_url` is not provided (falsy).
        """
        if not self.feed_url:
            raise ValueError("feed_url is required")
        # Normalize feed URL
        self.feed_url = self.feed_url.strip()


@dataclass
class OPMLImportResult:
    """Result of an OPML import operation."""

    feeds: List[PodcastFeed]
    total_outlines: int
    skipped_no_url: int
    title: Optional[str] = None
    owner_name: Optional[str] = None
    owner_email: Optional[str] = None
    date_created: Optional[str] = None


class OPMLParser:
    """Parser for OPML files containing podcast subscriptions.

    Handles various OPML formats and extracts podcast feed URLs
    with associated metadata.

    Example:
        parser = OPMLParser()
        result = parser.parse_file("subscriptions.opml")
        for feed in result.feeds:
            print(f"{feed.title}: {feed.feed_url}")
    """

    # Common attribute names for feed URLs across different OPML flavors
    URL_ATTRIBUTES = ["xmlUrl", "xmlurl", "url", "feedUrl", "feedurl"]

    # Common attribute names for website URLs
    HTML_URL_ATTRIBUTES = ["htmlUrl", "htmlurl", "link"]

    # Common attribute names for titles
    TITLE_ATTRIBUTES = ["title", "text", "name"]

    # Common attribute names for descriptions
    DESCRIPTION_ATTRIBUTES = ["description", "comment"]

    def __init__(self):
        """Initialize the OPML parser."""
        pass

    def parse_file(self, file_path: Union[str, Path]) -> OPMLImportResult:
        """
        Parse an OPML file and extract podcast feeds.
        
        Returns:
            OPMLImportResult: Contains extracted feeds and parsed metadata (title, owner, date, totals).
        
        Raises:
            FileNotFoundError: If the given file path does not exist.
            ET.ParseError: If the file contains invalid XML.
            ValueError: If the OPML content is missing required structure (e.g., no body element).
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"OPML file not found: {file_path}")

        logger.info(f"Parsing OPML file: {file_path}")

        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        return self.parse_string(content)

    def parse_string(self, content: str) -> OPMLImportResult:
        """
        Parse an OPML document and extract podcast feeds and related metadata.
        
        Parameters:
            content (str): OPML XML content as a string.
        
        Returns:
            OPMLImportResult: Result containing extracted PodcastFeed entries, total outline count, number of outlines skipped for missing URLs, and optional head metadata (`title`, `owner_name`, `owner_email`, `date_created`).
        
        Raises:
            ET.ParseError: If the provided XML is not well-formed.
            ValueError: If the root element is not `opml` or the document is missing a `body` element.
        """
        try:
            root = ET.fromstring(content)
        except ET.ParseError as e:
            logger.error(f"Failed to parse OPML XML: {e}")
            raise

        # Validate root element
        if root.tag.lower() != "opml":
            raise ValueError(f"Invalid OPML: root element is '{root.tag}', expected 'opml'")

        # Extract head metadata
        # Note: Empty Element is falsy, so we can't use `or` here
        head = root.find("head")
        if head is None:
            head = root.find("HEAD")
        title = None
        owner_name = None
        owner_email = None
        date_created = None

        if head is not None:
            title = self._get_element_text(head, ["title", "Title"])
            owner_name = self._get_element_text(head, ["ownerName", "ownername"])
            owner_email = self._get_element_text(head, ["ownerEmail", "owneremail"])
            date_created = self._get_element_text(head, ["dateCreated", "datecreated"])

        # Find body element
        # Note: Empty Element is falsy, so we can't use `or` here
        body = root.find("body")
        if body is None:
            body = root.find("BODY")
        if body is None:
            raise ValueError("Invalid OPML: missing body element")

        # Extract feeds from all outline elements
        feeds = []
        total_outlines = 0
        skipped_no_url = 0
        current_category = None

        def process_outlines(parent, category=None):
            """
            Recursively traverse OPML outline elements under `parent`, extract podcast feeds, and assign categories.
            
            Processes each child "outline" element (case-insensitive), increments the total outline count, and for outlines that contain a feed URL extracts a PodcastFeed and appends it to the surrounding `feeds` collection. For outlines without a feed URL but with nested outlines, recurses into children using the outline's title as the category (if present); for leaf outlines without a URL, increments the skipped-no-URL counter. This function updates the nonlocal counters `total_outlines` and `skipped_no_url` and appends found feeds to the nonlocal `feeds` list.
            
            Parameters:
            	parent (xml.etree.ElementTree.Element): XML element whose child outline elements will be processed.
            	category (str | None): Optional category to apply to extracted feeds; if a container outline has a title it will override this for its children.
            
            Returns:
            	None
            """
            nonlocal total_outlines, skipped_no_url, current_category

            for outline in parent.findall("outline") + parent.findall("OUTLINE"):
                total_outlines += 1

                # Check if this outline has a feed URL
                feed_url = self._get_attribute(outline, self.URL_ATTRIBUTES)

                if feed_url:
                    # This is a feed entry
                    feed = self._extract_feed(outline, category)
                    if feed:
                        feeds.append(feed)
                        logger.debug(f"Found feed: {feed.title or feed.feed_url}")
                else:
                    # This might be a category/folder - check for nested outlines
                    nested = outline.findall("outline") + outline.findall("OUTLINE")
                    if nested:
                        # Use this outline's title as the category
                        cat_name = self._get_attribute(outline, self.TITLE_ATTRIBUTES)
                        process_outlines(outline, cat_name or category)
                    else:
                        # No URL and no children - skip
                        skipped_no_url += 1
                        logger.debug(
                            f"Skipped outline without URL: "
                            f"{self._get_attribute(outline, self.TITLE_ATTRIBUTES)}"
                        )

        process_outlines(body)

        logger.info(
            f"Parsed OPML: {len(feeds)} feeds found, "
            f"{skipped_no_url} outlines skipped (no URL), "
            f"{total_outlines} total outlines"
        )

        return OPMLImportResult(
            feeds=feeds,
            total_outlines=total_outlines,
            skipped_no_url=skipped_no_url,
            title=title,
            owner_name=owner_name,
            owner_email=owner_email,
            date_created=date_created,
        )

    def _extract_feed(self, outline: ET.Element, category: Optional[str] = None) -> Optional[PodcastFeed]:
        """
        Create a PodcastFeed from an outline element or return None when no valid feed URL is present.
        
        Extracts the feed URL and optional metadata (title, website URL, description) from the given outline. Validates the feed URL must start with "http://", "https://", or "feed://"; normalizes "feed://" to "https://". Returns None for missing or invalid feed URLs.
        
        Parameters:
            outline (xml.etree.ElementTree.Element): The outline element containing feed attributes.
            category (str | None): Optional parent category to assign to the feed.
        
        Returns:
            PodcastFeed | None: A PodcastFeed populated from the outline, or `None` if extraction or validation fails.
        """
        feed_url = self._get_attribute(outline, self.URL_ATTRIBUTES)
        if not feed_url:
            return None

        # Validate URL format
        feed_url = feed_url.strip()
        if not feed_url.startswith(("http://", "https://", "feed://")):
            logger.warning(f"Skipping invalid feed URL: {feed_url}")
            return None

        # Normalize feed:// URLs to https://
        if feed_url.startswith("feed://"):
            feed_url = "https://" + feed_url[7:]

        return PodcastFeed(
            feed_url=feed_url,
            title=self._get_attribute(outline, self.TITLE_ATTRIBUTES),
            website_url=self._get_attribute(outline, self.HTML_URL_ATTRIBUTES),
            description=self._get_attribute(outline, self.DESCRIPTION_ATTRIBUTES),
            category=category,
        )

    def _get_attribute(self, element: ET.Element, attr_names: List[str]) -> Optional[str]:
        """Get attribute value trying multiple possible names.

        Args:
            element: XML element
            attr_names: List of possible attribute names to try

        Returns:
            Attribute value or None if not found
        """
        for name in attr_names:
            value = element.get(name)
            if value:
                return value.strip()
        return None

    def _get_element_text(self, parent: ET.Element, tag_names: List[str]) -> Optional[str]:
        """
        Return the text of the first child element whose tag matches any name in `tag_names`.
        
        Parameters:
            parent (ET.Element): Parent XML element to search.
            tag_names (List[str]): Candidate child tag names to try in order.
        
        Returns:
            str | None: The stripped text of the first matching child element, or `None` if no matching child with text is found.
        """
        for name in tag_names:
            element = parent.find(name)
            if element is not None and element.text:
                return element.text.strip()
        return None


def import_opml_to_repository(
    opml_path: Union[str, Path],
    repository,
    skip_existing: bool = True,
) -> dict:
    """
    Import podcasts from an OPML file into a podcast repository.
    
    Parses the OPML file at `opml_path` and creates or updates podcast records in `repository`. When `skip_existing` is True, feeds already present in the repository are left unchanged; when False, existing records are updated with metadata from the OPML.
    
    Parameters:
        opml_path (Union[str, Path]): Path to the OPML file to import.
        skip_existing (bool): If True, do not modify feeds that already exist in the repository (default True).
        repository is intentionally undocumented as it represents the repository service provided by the caller.
    
    Returns:
        dict: Import statistics containing:
            - added (int): Number of new podcasts created.
            - skipped (int): Number of feeds skipped because they already existed (or were updated when skip_existing is False).
            - failed (int): Number of feeds that failed to import due to errors.
            - total (int): Total number of feed outlines processed from the OPML file.
    """
    parser = OPMLParser()
    result = parser.parse_file(opml_path)

    stats = {
        "added": 0,
        "skipped": 0,
        "failed": 0,
        "total": len(result.feeds),
    }

    for feed in result.feeds:
        try:
            # Check if podcast already exists
            existing = repository.get_podcast_by_feed_url(feed.feed_url)
            if existing:
                if skip_existing:
                    logger.debug(f"Skipping existing podcast: {feed.title or feed.feed_url}")
                    stats["skipped"] += 1
                    continue
                else:
                    # Update existing podcast
                    repository.update_podcast(
                        existing.id,
                        title=feed.title or existing.title,
                        website_url=feed.website_url or existing.website_url,
                        description=feed.description or existing.description,
                    )
                    stats["skipped"] += 1
                    continue

            # Create new podcast with minimal info
            # Full metadata will be fetched when syncing the feed
            repository.create_podcast(
                feed_url=feed.feed_url,
                title=feed.title or "Unknown Podcast",
                website_url=feed.website_url,
                description=feed.description,
            )
            logger.info(f"Added podcast: {feed.title or feed.feed_url}")
            stats["added"] += 1

        except Exception as e:
            logger.error(f"Failed to import feed {feed.feed_url}: {e}")
            stats["failed"] += 1

    logger.info(
        f"OPML import complete: {stats['added']} added, "
        f"{stats['skipped']} skipped, {stats['failed']} failed"
    )

    return stats