"""Tests for the RSS feed parser."""


import pytest

from src.podcast.feed_parser import FeedParser


@pytest.fixture
def parser():
    """
    Provide a new FeedParser instance for tests.

    This function is used as a pytest fixture to supply tests with a fresh FeedParser.

    Returns:
        FeedParser: A new FeedParser instance.
    """
    return FeedParser()


# Sample RSS feed for testing
SAMPLE_RSS_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
     xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"
     xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>Test Podcast</title>
    <description>A podcast for testing</description>
    <link>https://example.com</link>
    <language>en-us</language>
    <itunes:author>Test Author</itunes:author>
    <itunes:category text="Technology">
      <itunes:category text="Tech News"/>
    </itunes:category>
    <itunes:explicit>no</itunes:explicit>
    <itunes:type>episodic</itunes:type>
    <itunes:image href="https://example.com/artwork.jpg"/>

    <item>
      <title>Episode 1: Introduction</title>
      <description>The first episode of our podcast.</description>
      <link>https://example.com/ep1</link>
      <guid>episode-1-guid</guid>
      <pubDate>Mon, 01 Jan 2024 12:00:00 +0000</pubDate>
      <itunes:episode>1</itunes:episode>
      <itunes:duration>01:30:00</itunes:duration>
      <itunes:explicit>no</itunes:explicit>
      <enclosure url="https://example.com/ep1.mp3"
                 length="54000000"
                 type="audio/mpeg"/>
    </item>

    <item>
      <title>Episode 2: Deep Dive</title>
      <description><![CDATA[<p>A deeper look at the topic.</p>]]></description>
      <guid>episode-2-guid</guid>
      <pubDate>Mon, 08 Jan 2024 12:00:00 +0000</pubDate>
      <itunes:episode>2</itunes:episode>
      <itunes:season>1</itunes:season>
      <itunes:duration>45:30</itunes:duration>
      <enclosure url="https://example.com/ep2.mp3"
                 length="27000000"
                 type="audio/mpeg"/>
    </item>
  </channel>
</rss>"""


class TestFeedParser:
    """Tests for RSS feed parsing functionality."""

    def test_parse_string(self, parser):
        """Test parsing feed from string."""
        podcast = parser.parse_string(SAMPLE_RSS_FEED, "https://example.com/feed.xml")

        assert podcast.title == "Test Podcast"
        assert podcast.description == "A podcast for testing"
        assert podcast.website_url == "https://example.com"
        assert podcast.language == "en-us"

    def test_parse_itunes_metadata(self, parser):
        """Test parsing iTunes-specific metadata."""
        podcast = parser.parse_string(SAMPLE_RSS_FEED, "")

        # feedparser may store itunes_author in author field
        assert podcast.author == "Test Author"
        assert podcast.itunes_type == "episodic"
        assert podcast.image_url == "https://example.com/artwork.jpg"

    def test_parse_episodes(self, parser):
        """Test parsing episode list."""
        podcast = parser.parse_string(SAMPLE_RSS_FEED, "")

        assert len(podcast.episodes) == 2

        ep1 = podcast.episodes[0]
        assert ep1.title == "Episode 1: Introduction"
        assert ep1.guid == "episode-1-guid"
        assert ep1.enclosure_url == "https://example.com/ep1.mp3"
        assert ep1.enclosure_type == "audio/mpeg"

    def test_parse_episode_metadata(self, parser):
        """Test parsing episode metadata."""
        podcast = parser.parse_string(SAMPLE_RSS_FEED, "")

        ep1 = podcast.episodes[0]
        assert ep1.description == "The first episode of our podcast."
        assert ep1.link == "https://example.com/ep1"
        assert ep1.itunes_episode == "1"
        assert ep1.enclosure_length == 54000000

    def test_parse_episode_duration(self, parser):
        """Test parsing episode duration."""
        podcast = parser.parse_string(SAMPLE_RSS_FEED, "")

        # Episode 1: "01:30:00" = 5400 seconds
        ep1 = podcast.episodes[0]
        assert ep1.duration_seconds == 5400

        # Episode 2: "45:30" = 2730 seconds
        ep2 = podcast.episodes[1]
        assert ep2.duration_seconds == 2730

    def test_parse_published_date(self, parser):
        """Test parsing published date."""
        podcast = parser.parse_string(SAMPLE_RSS_FEED, "")

        ep1 = podcast.episodes[0]
        assert ep1.published_date is not None
        assert ep1.published_date.year == 2024
        assert ep1.published_date.month == 1
        assert ep1.published_date.day == 1

    def test_parse_season_number(self, parser):
        """Test parsing season number."""
        podcast = parser.parse_string(SAMPLE_RSS_FEED, "")

        ep2 = podcast.episodes[1]
        assert ep2.itunes_season == 1
        assert ep2.season_number == 1

    def test_clean_html_description(self, parser):
        """Test that HTML is cleaned from descriptions."""
        podcast = parser.parse_string(SAMPLE_RSS_FEED, "")

        ep2 = podcast.episodes[1]
        assert ep2.description == "A deeper look at the topic."
        assert "<p>" not in ep2.description

    def test_skip_non_audio_enclosures(self, parser):
        """Test that non-audio enclosures are skipped."""
        feed = """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0">
          <channel>
            <title>Test Podcast</title>
            <item>
              <title>Episode with PDF</title>
              <guid>ep-pdf</guid>
              <enclosure url="https://example.com/doc.pdf"
                         type="application/pdf"/>
            </item>
            <item>
              <title>Episode with Audio</title>
              <guid>ep-audio</guid>
              <enclosure url="https://example.com/ep.mp3"
                         type="audio/mpeg"/>
            </item>
          </channel>
        </rss>"""

        podcast = parser.parse_string(feed, "")

        assert len(podcast.episodes) == 1
        assert podcast.episodes[0].title == "Episode with Audio"

    def test_use_enclosure_url_as_guid_fallback(self, parser):
        """Test that enclosure URL is used as GUID fallback."""
        feed = """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0">
          <channel>
            <title>Test Podcast</title>
            <item>
              <title>Episode Without GUID</title>
              <enclosure url="https://example.com/ep.mp3"
                         type="audio/mpeg"/>
            </item>
          </channel>
        </rss>"""

        podcast = parser.parse_string(feed, "")

        assert len(podcast.episodes) == 1
        assert podcast.episodes[0].guid == "https://example.com/ep.mp3"

    def test_parse_explicit_values(self, parser):
        """Test parsing various explicit flag values."""
        # Test internal parsing function directly
        assert parser._parse_explicit("yes") is True
        assert parser._parse_explicit("true") is True
        assert parser._parse_explicit("explicit") is True
        assert parser._parse_explicit("no") is False
        assert parser._parse_explicit("false") is False
        assert parser._parse_explicit("clean") is False
        assert parser._parse_explicit(None) is None
        assert parser._parse_explicit(True) is True
        assert parser._parse_explicit(False) is False


class TestDurationParsing:
    """Tests for duration parsing."""

    def test_parse_duration_seconds(self, parser):
        """Test parsing duration in seconds."""
        assert parser._parse_duration("3600") == 3600
        assert parser._parse_duration("60") == 60

    def test_parse_duration_mm_ss(self, parser):
        """Test parsing duration in MM:SS format."""
        assert parser._parse_duration("60:00") == 3600
        assert parser._parse_duration("30:30") == 1830

    def test_parse_duration_hh_mm_ss(self, parser):
        """Test parsing duration in HH:MM:SS format."""
        assert parser._parse_duration("1:00:00") == 3600
        assert parser._parse_duration("2:30:45") == 9045

    def test_parse_duration_invalid(self, parser):
        """Test parsing invalid duration."""
        assert parser._parse_duration(None) is None
        assert parser._parse_duration("") is None
        assert parser._parse_duration("invalid") is None


class TestHTMLCleaning:
    """Tests for HTML cleaning."""

    def test_remove_html_tags(self, parser):
        """Test removing HTML tags."""
        assert parser._clean_html("<p>Hello</p>") == "Hello"
        assert parser._clean_html("<b>Bold</b> text") == "Bold text"

    def test_decode_html_entities(self, parser):
        """Test decoding HTML entities."""
        assert parser._clean_html("Tom &amp; Jerry") == "Tom & Jerry"
        assert parser._clean_html("&lt;not a tag&gt;") == "<not a tag>"
        assert parser._clean_html("&quot;quoted&quot;") == '"quoted"'

    def test_normalize_whitespace(self, parser):
        """Test whitespace normalization."""
        assert parser._clean_html("  multiple   spaces  ") == "multiple spaces"
        assert parser._clean_html("line\n\nbreaks") == "line breaks"

    def test_handle_none(self, parser):
        """Test handling None input."""
        assert parser._clean_html(None) is None
        assert parser._clean_html("") is None
