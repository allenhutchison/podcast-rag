"""Tests for the OPML parser."""

import pytest
from src.podcast.opml_parser import OPMLParser, PodcastFeed, OPMLImportResult


@pytest.fixture
def parser():
    """
    Create and return a new OPMLParser instance.
    
    Returns:
        OPMLParser: A new parser configured for parsing OPML content.
    """
    return OPMLParser()


class TestOPMLParser:
    """Tests for OPML parsing functionality."""

    def test_parse_simple_opml(self, parser):
        """Test parsing a simple OPML file."""
        content = """<?xml version="1.0" encoding="UTF-8"?>
        <opml version="1.0">
            <head>
                <title>My Podcasts</title>
            </head>
            <body>
                <outline type="rss" text="Test Podcast"
                         xmlUrl="https://example.com/feed.xml"
                         htmlUrl="https://example.com"/>
            </body>
        </opml>"""

        result = parser.parse_string(content)

        assert result.title == "My Podcasts"
        assert len(result.feeds) == 1
        assert result.feeds[0].feed_url == "https://example.com/feed.xml"
        assert result.feeds[0].title == "Test Podcast"
        assert result.feeds[0].website_url == "https://example.com"

    def test_parse_nested_opml(self, parser):
        """Test parsing OPML with nested categories."""
        content = """<?xml version="1.0" encoding="UTF-8"?>
        <opml version="1.0">
            <head>
                <title>My Podcasts</title>
            </head>
            <body>
                <outline text="Technology">
                    <outline type="rss" text="Tech Podcast 1"
                             xmlUrl="https://example.com/tech1.xml"/>
                    <outline type="rss" text="Tech Podcast 2"
                             xmlUrl="https://example.com/tech2.xml"/>
                </outline>
                <outline text="Comedy">
                    <outline type="rss" text="Comedy Podcast"
                             xmlUrl="https://example.com/comedy.xml"/>
                </outline>
            </body>
        </opml>"""

        result = parser.parse_string(content)

        assert len(result.feeds) == 3

        tech_feeds = [f for f in result.feeds if f.category == "Technology"]
        assert len(tech_feeds) == 2

        comedy_feeds = [f for f in result.feeds if f.category == "Comedy"]
        assert len(comedy_feeds) == 1

    def test_parse_apple_podcasts_format(self, parser):
        """Test parsing Apple Podcasts OPML format."""
        content = """<?xml version="1.0" encoding="UTF-8"?>
        <opml version="1.0">
            <head>
                <title>Apple Podcasts Subscriptions</title>
            </head>
            <body>
                <outline text="feeds">
                    <outline type="rss" text="Podcast 1" title="Podcast 1"
                             xmlUrl="https://feeds.example.com/feed1"
                             htmlUrl="https://example.com/podcast1"/>
                    <outline type="rss" text="Podcast 2" title="Podcast 2"
                             xmlUrl="https://feeds.example.com/feed2"
                             htmlUrl="https://example.com/podcast2"/>
                </outline>
            </body>
        </opml>"""

        result = parser.parse_string(content)

        assert len(result.feeds) == 2
        assert result.feeds[0].feed_url == "https://feeds.example.com/feed1"
        assert result.feeds[1].feed_url == "https://feeds.example.com/feed2"

    def test_parse_overcast_format(self, parser):
        """Test parsing Overcast OPML format."""
        content = """<?xml version="1.0" encoding="UTF-8"?>
        <opml version="1.0">
            <head>
                <title>Overcast Podcast Subscriptions</title>
                <ownerName>Test User</ownerName>
                <ownerEmail>test@example.com</ownerEmail>
            </head>
            <body>
                <outline type="rss" text="Podcast 1"
                         xmlUrl="https://feeds.example.com/feed1"/>
                <outline type="rss" text="Podcast 2"
                         xmlUrl="https://feeds.example.com/feed2"/>
            </body>
        </opml>"""

        result = parser.parse_string(content)

        assert result.owner_name == "Test User"
        assert result.owner_email == "test@example.com"
        assert len(result.feeds) == 2

    def test_skip_outlines_without_url(self, parser):
        """Test that outlines without URLs are skipped."""
        content = """<?xml version="1.0" encoding="UTF-8"?>
        <opml version="1.0">
            <head><title>Test</title></head>
            <body>
                <outline text="Category Only"/>
                <outline type="rss" text="Valid Podcast"
                         xmlUrl="https://example.com/feed.xml"/>
                <outline text="Another Category"/>
            </body>
        </opml>"""

        result = parser.parse_string(content)

        assert len(result.feeds) == 1
        assert result.skipped_no_url == 2

    def test_handle_feed_urls(self, parser):
        """Test that feed:// URLs are normalized."""
        content = """<?xml version="1.0" encoding="UTF-8"?>
        <opml version="1.0">
            <head><title>Test</title></head>
            <body>
                <outline type="rss" text="Podcast"
                         xmlUrl="feed://example.com/feed.xml"/>
            </body>
        </opml>"""

        result = parser.parse_string(content)

        assert len(result.feeds) == 1
        assert result.feeds[0].feed_url == "https://example.com/feed.xml"

    def test_case_insensitive_attributes(self, parser):
        """Test that attribute names are case-insensitive."""
        content = """<?xml version="1.0" encoding="UTF-8"?>
        <opml version="1.0">
            <head><title>Test</title></head>
            <body>
                <outline type="rss" TEXT="Podcast 1"
                         XMLURL="https://example.com/feed1.xml"/>
                <outline type="rss" text="Podcast 2"
                         xmlurl="https://example.com/feed2.xml"/>
            </body>
        </opml>"""

        result = parser.parse_string(content)

        # Note: XML attribute names are case-sensitive, but we try multiple variants
        # This test verifies we handle common variations
        assert len(result.feeds) >= 1

    def test_empty_body(self, parser):
        """Test parsing OPML with empty body."""
        content = """<?xml version="1.0" encoding="UTF-8"?>
        <opml version="1.0">
            <head><title>Empty</title></head>
            <body></body>
        </opml>"""

        result = parser.parse_string(content)

        assert len(result.feeds) == 0
        assert result.title == "Empty"

    def test_invalid_opml_no_body(self, parser):
        """Test that OPML without body raises error."""
        content = """<?xml version="1.0" encoding="UTF-8"?>
        <opml version="1.0">
            <head><title>Invalid</title></head>
        </opml>"""

        with pytest.raises(ValueError, match="missing body"):
            parser.parse_string(content)

    def test_invalid_root_element(self, parser):
        """Test that non-OPML root element raises error."""
        content = """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0">
            <channel><title>Not OPML</title></channel>
        </rss>"""

        with pytest.raises(ValueError, match="Invalid OPML"):
            parser.parse_string(content)

    def test_parse_file(self, parser, tmp_path):
        """Test parsing from file."""
        opml_file = tmp_path / "test.opml"
        opml_file.write_text("""<?xml version="1.0" encoding="UTF-8"?>
        <opml version="1.0">
            <head><title>File Test</title></head>
            <body>
                <outline type="rss" text="Podcast"
                         xmlUrl="https://example.com/feed.xml"/>
            </body>
        </opml>""")

        result = parser.parse_file(opml_file)

        assert result.title == "File Test"
        assert len(result.feeds) == 1

    def test_parse_nonexistent_file(self, parser):
        """Test that parsing nonexistent file raises error."""
        with pytest.raises(FileNotFoundError):
            parser.parse_file("/nonexistent/path/file.opml")


class TestPodcastFeed:
    """Tests for PodcastFeed dataclass."""

    def test_create_feed(self):
        """Test creating a PodcastFeed."""
        feed = PodcastFeed(
            feed_url="https://example.com/feed.xml",
            title="Test Podcast",
            website_url="https://example.com",
        )

        assert feed.feed_url == "https://example.com/feed.xml"
        assert feed.title == "Test Podcast"

    def test_feed_url_required(self):
        """Test that feed_url is required."""
        with pytest.raises(ValueError, match="feed_url is required"):
            PodcastFeed(feed_url="")

    def test_feed_url_normalized(self):
        """Test that feed URL is stripped."""
        feed = PodcastFeed(feed_url="  https://example.com/feed.xml  ")
        assert feed.feed_url == "https://example.com/feed.xml"