"""Tests for email content generation and rendering.

Tests the new EmailContent schema, email rendering with rich content,
and fallback behavior when email content is not available.
"""

from datetime import datetime
from typing import Optional
from unittest.mock import Mock

import pytest

from src.schemas import EmailContent, PodcastMetadata, StoryItem
from src.services.email_renderer import render_digest_html, render_digest_text


class MockPodcast:
    """Mock podcast for testing."""

    def __init__(self, title: str = "Test Podcast"):
        self.title = title


class MockEpisode:
    """Mock episode for testing email rendering."""

    def __init__(
        self,
        id: str = "test-id",
        title: str = "Test Episode",
        published_date: Optional[datetime] = None,
        ai_summary: str = "Default AI summary for testing.",
        ai_keywords: Optional[list] = None,
        ai_email_content: Optional[dict] = None,
        enclosure_url: str = "https://example.com/ep.mp3",
        podcast: Optional[MockPodcast] = None,
    ):
        self.id = id
        self.title = title
        self.published_date = published_date or datetime(2024, 12, 20)
        self.ai_summary = ai_summary
        self.ai_keywords = ai_keywords or ["keyword1", "keyword2"]
        self.ai_email_content = ai_email_content
        self.enclosure_url = enclosure_url
        self.podcast = podcast or MockPodcast()


class TestEmailContentSchema:
    """Tests for EmailContent Pydantic schema."""

    def test_valid_interview_content(self):
        """Test valid email content for interview podcast."""
        content = EmailContent(
            podcast_type="interview",
            teaser_summary="An engaging hook that draws readers in to listen to this episode.",
            key_takeaways=["Point 1", "Point 2", "Point 3"],
            highlight_moment="A memorable quote from the episode",
        )
        assert content.podcast_type == "interview"
        assert len(content.key_takeaways) == 3
        assert content.story_summaries is None

    def test_valid_news_content_with_stories(self):
        """Test valid email content for news podcast with story summaries."""
        content = EmailContent(
            podcast_type="news",
            teaser_summary="Today's top tech stories and what they mean for you in the coming weeks.",
            key_takeaways=["Key insight 1", "Key insight 2"],
            story_summaries=[
                StoryItem(headline="Breaking news story", summary="Details about the story."),
                StoryItem(headline="Another story", summary="More details here."),
            ],
        )
        assert content.podcast_type == "news"
        assert len(content.story_summaries) == 2
        assert content.story_summaries[0].headline == "Breaking news story"

    def test_teaser_too_short(self):
        """Test that teaser summary must be at least 20 characters (lenient limit)."""
        with pytest.raises(ValueError):
            EmailContent(
                podcast_type="general",
                teaser_summary="Too short",  # < 20 chars (lenient limit)
                key_takeaways=["a", "b"],
            )

    def test_teaser_too_long(self):
        """Test that teaser summary must not exceed 300 characters (lenient limit)."""
        with pytest.raises(ValueError):
            EmailContent(
                podcast_type="general",
                teaser_summary="x" * 301,  # > 300 chars (lenient limit)
                key_takeaways=["a", "b"],
            )

    def test_minimum_takeaways_required(self):
        """Test that at least 1 key takeaway is required (lenient limit)."""
        with pytest.raises(ValueError):
            EmailContent(
                podcast_type="general",
                teaser_summary="A valid teaser summary that is long enough to pass validation.",
                key_takeaways=[],  # < 1 item (lenient limit)
            )

    def test_podcast_type_literal(self):
        """Test that podcast_type must be one of the allowed values."""
        with pytest.raises(ValueError):
            EmailContent(
                podcast_type="invalid_type",  # Not in allowed values
                teaser_summary="A valid teaser summary that is long enough to pass validation.",
                key_takeaways=["a", "b"],
            )


class TestPodcastMetadataWithEmailContent:
    """Tests for PodcastMetadata schema with email_content field."""

    def test_metadata_with_email_content(self):
        """Test that PodcastMetadata correctly includes email_content."""
        metadata = PodcastMetadata(
            podcast_title="Test Podcast",
            episode_title="Test Episode",
            episode_number="42",
            date="2024-12-20",
            hosts=["Host Name"],
            co_hosts=[],
            guests=["Guest Name"],
            summary="A detailed summary that is at least 100 characters long to pass the validation requirements for the summary field.",
            keywords=["k1", "k2", "k3", "k4", "k5"],
            email_content=EmailContent(
                podcast_type="interview",
                teaser_summary="An engaging teaser that makes people want to listen to the episode.",
                key_takeaways=["Takeaway 1", "Takeaway 2"],
            ),
        )
        assert metadata.email_content is not None
        assert metadata.email_content.podcast_type == "interview"

    def test_metadata_without_email_content(self):
        """Test that PodcastMetadata works without email_content (optional)."""
        metadata = PodcastMetadata(
            podcast_title="Test Podcast",
            episode_title="Test Episode",
            episode_number=None,
            date=None,
            hosts=["Host"],
            co_hosts=[],
            guests=[],
            summary="A detailed summary that is at least 100 characters long to pass the validation requirements for the summary field.",
            keywords=["k1", "k2", "k3", "k4", "k5"],
        )
        assert metadata.email_content is None


class TestEmailRendererHtml:
    """Tests for HTML email rendering with email content."""

    def test_render_with_teaser_summary(self):
        """Test that teaser_summary is used when available."""
        ep = MockEpisode(
            ai_summary="Long detailed summary that should not appear...",
            ai_email_content={
                "teaser_summary": "Short engaging hook for the email!",
                "key_takeaways": [],
                "podcast_type": "interview",
            },
        )
        html = render_digest_html("User", [ep])
        assert "Short engaging hook for the email!" in html
        assert "Long detailed summary" not in html

    def test_render_with_key_takeaways(self):
        """Test that key takeaways render as bullet points."""
        ep = MockEpisode(
            ai_email_content={
                "teaser_summary": "Summary text that is long enough for validation.",
                "key_takeaways": ["Takeaway 1", "Takeaway 2", "Takeaway 3"],
                "podcast_type": "general",
            },
        )
        html = render_digest_html("User", [ep])
        assert "Key Takeaways:" in html
        assert "Takeaway 1" in html
        assert "Takeaway 2" in html
        assert "Takeaway 3" in html
        assert "<li" in html

    def test_render_with_highlight_moment(self):
        """Test that highlight moment renders as blockquote."""
        ep = MockEpisode(
            ai_email_content={
                "teaser_summary": "Summary text that is long enough for validation.",
                "key_takeaways": ["a", "b"],
                "highlight_moment": "\"Amazing quote here!\" - Speaker Name",
                "podcast_type": "interview",
            },
        )
        html = render_digest_html("User", [ep])
        assert "Amazing quote here!" in html
        assert "blockquote" in html

    def test_render_news_with_stories(self):
        """Test that news podcasts show story summaries."""
        ep = MockEpisode(
            ai_email_content={
                "podcast_type": "news",
                "teaser_summary": "Today's top news stories from the tech world and beyond.",
                "key_takeaways": ["Key 1", "Key 2"],
                "story_summaries": [
                    {"headline": "Story 1 Headline", "summary": "Summary 1"},
                    {"headline": "Story 2 Headline", "summary": "Summary 2"},
                ],
            },
        )
        html = render_digest_html("User", [ep])
        assert "Stories Covered:" in html
        assert "Story 1 Headline" in html
        assert "Summary 1" in html
        assert "Story 2 Headline" in html

    def test_render_non_news_without_stories(self):
        """Test that non-news podcasts don't show stories even if present."""
        ep = MockEpisode(
            ai_email_content={
                "podcast_type": "interview",  # Not news
                "teaser_summary": "An interview episode with interesting guests to discuss.",
                "key_takeaways": ["Key 1", "Key 2"],
                "story_summaries": [  # Should be ignored
                    {"headline": "Should not appear", "summary": "Ignored"},
                ],
            },
        )
        html = render_digest_html("User", [ep])
        assert "Stories Covered:" not in html
        assert "Should not appear" not in html

    def test_render_fallback_without_email_content(self):
        """Test graceful fallback when ai_email_content is None."""
        ep = MockEpisode(
            ai_summary="Fallback summary from ai_summary field",
            ai_email_content=None,
        )
        html = render_digest_html("User", [ep])
        assert "Fallback summary from ai_summary field" in html

    def test_render_truncates_long_fallback_summary(self):
        """Test that fallback summary is truncated to 300 chars."""
        long_summary = "x" * 400
        ep = MockEpisode(
            ai_summary=long_summary,
            ai_email_content=None,
        )
        html = render_digest_html("User", [ep])
        assert "x" * 300 in html
        assert "..." in html
        assert "x" * 400 not in html


class TestEmailRendererText:
    """Tests for plain text email rendering with email content."""

    def test_render_text_with_teaser(self):
        """Test plain text rendering with teaser summary."""
        ep = MockEpisode(
            ai_summary="Long summary...",
            ai_email_content={
                "teaser_summary": "Short teaser for text email format testing purposes.",
                "key_takeaways": [],
                "podcast_type": "general",
            },
        )
        text = render_digest_text("User", [ep])
        assert "Short teaser for text email format testing purposes." in text

    def test_render_text_with_takeaways(self):
        """Test plain text rendering with key takeaways."""
        ep = MockEpisode(
            ai_email_content={
                "teaser_summary": "Summary text that is long enough for validation testing.",
                "key_takeaways": ["Text takeaway 1", "Text takeaway 2"],
                "podcast_type": "general",
            },
        )
        text = render_digest_text("User", [ep])
        assert "Key Takeaways:" in text
        assert "- Text takeaway 1" in text
        assert "- Text takeaway 2" in text

    def test_render_text_with_highlight(self):
        """Test plain text rendering with highlight moment."""
        ep = MockEpisode(
            ai_email_content={
                "teaser_summary": "Summary text that is long enough for validation testing.",
                "key_takeaways": ["a", "b"],
                "highlight_moment": "Memorable quote here",
                "podcast_type": "interview",
            },
        )
        text = render_digest_text("User", [ep])
        assert 'Highlight: "Memorable quote here"' in text

    def test_render_text_news_stories(self):
        """Test plain text rendering with news stories."""
        ep = MockEpisode(
            ai_email_content={
                "podcast_type": "news",
                "teaser_summary": "Today's headlines from around the tech world for you.",
                "key_takeaways": ["Key 1", "Key 2"],
                "story_summaries": [
                    {"headline": "Text Story 1", "summary": "Text summary 1"},
                ],
            },
        )
        text = render_digest_text("User", [ep])
        assert "Stories Covered:" in text
        assert "- Text Story 1: Text summary 1" in text

    def test_render_text_fallback(self):
        """Test plain text fallback when no email content."""
        ep = MockEpisode(
            ai_summary="Plain text fallback summary here",
            ai_email_content=None,
        )
        text = render_digest_text("User", [ep])
        assert "Plain text fallback summary here" in text
