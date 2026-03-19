"""Tests for the digest briefing generator."""

import json
from unittest.mock import Mock, patch

import pytest

from src.services.briefing_generator import (
    _build_episode_block,
    generate_digest_briefing,
)


class MockPodcast:
    def __init__(self, title="Test Podcast"):
        self.title = title


class MockEpisode:
    def __init__(
        self,
        title="Test Episode",
        ai_summary="A detailed test summary for the episode that covers the main topics discussed.",
        ai_keywords=None,
        ai_email_content=None,
        podcast=None,
        published_date=None,
    ):
        self.title = title
        self.ai_summary = ai_summary
        self.ai_keywords = ai_keywords or ["tech", "AI"]
        self.ai_email_content = ai_email_content
        self.podcast = podcast or MockPodcast()
        self.published_date = published_date


def _make_gemini_response(data: dict) -> Mock:
    """Create a mock Gemini API response."""
    response = Mock()
    response.text = json.dumps(data)
    return response


VALID_BRIEFING = {
    "headline": "AI and Tech Dominate Today's Podcast Landscape",
    "briefing": (
        "Today's episodes reveal a strong convergence around artificial intelligence "
        "and its practical applications. Multiple shows explored how AI is reshaping "
        "workflows and decision-making across industries.\n\n"
        "The consensus view is cautiously optimistic, with experts emphasizing the "
        "importance of human oversight. Dr. Smith on the a16z show argued that current "
        "adoption is 'barely scratching the surface' while the Daily's interview with "
        "a government regulator painted a more nuanced picture of the challenges ahead."
    ),
    "key_themes": ["Artificial Intelligence", "Workplace Automation", "Regulation"],
    "episode_highlights": [
        {
            "podcast_name": "The a16z Show",
            "episode_title": "AI in the Enterprise",
            "analysis": "Dr. Smith makes a compelling case for AI-first workflows. Key insight: productivity gains compound over time.",
        },
        {
            "podcast_name": "The Daily",
            "episode_title": "Future of Automation",
            "analysis": "A sobering look at regulation gaps. The FTC commissioner interview is the highlight.",
        },
    ],
    "connection_insight": "Both shows independently concluded that AI augments rather than replaces human expertise.",
}


class TestGenerateDigestBriefing:
    """Tests for generate_digest_briefing function."""

    def test_empty_episodes_returns_none(self):
        """Empty episode list returns None without calling API."""
        config = Mock()
        result = generate_digest_briefing([], config)
        assert result is None

    @patch("src.services.briefing_generator._get_file_search_store_name", return_value=None)
    @patch("src.services.briefing_generator.genai")
    def test_multiple_episodes_returns_valid_briefing(self, mock_genai, mock_store):
        """Multiple episodes produce a valid briefing dict."""
        client = mock_genai.Client.return_value
        client.models.generate_content.return_value = _make_gemini_response(VALID_BRIEFING)

        config = Mock()
        config.GEMINI_API_KEY = "test-key"
        config.GEMINI_MODEL_FLASH = "gemini-2.0-flash"

        episodes = [
            MockEpisode(
                title="AI in the Workplace",
                ai_summary="A deep dive into how AI is transforming office work across multiple industries.",
                ai_email_content={
                    "teaser_summary": "How AI is changing office work.",
                    "key_takeaways": ["AI helps with mundane tasks"],
                },
            ),
            MockEpisode(
                title="Future of Automation",
                podcast=MockPodcast("Tech Talk"),
                ai_summary="This episode explores automation trends and their economic implications.",
                ai_email_content={
                    "teaser_summary": "Automation trends for 2026.",
                    "key_takeaways": ["Robots in warehouses"],
                },
            ),
        ]

        result = generate_digest_briefing(episodes, config)

        assert result is not None
        assert result["headline"] == VALID_BRIEFING["headline"]
        assert len(result["key_themes"]) == 3
        assert len(result["episode_highlights"]) == 2
        assert result["episode_highlights"][0]["podcast_name"] == "The a16z Show"
        assert result["connection_insight"] is not None

    @patch("src.services.briefing_generator._get_file_search_store_name", return_value=None)
    @patch("src.services.briefing_generator.genai")
    def test_single_episode_uses_variant_prompt(self, mock_genai, mock_store):
        """Single episode uses the depth-focused prompt variant."""
        client = mock_genai.Client.return_value
        single_briefing = {
            "headline": "Deep Dive into Machine Learning Ethics",
            "briefing": (
                "This episode provides a thorough examination of ethical considerations "
                "in machine learning deployment. The host brings clarity to complex issues "
                "around bias and fairness in AI systems used for critical decisions.\n\n"
                "The standout moment comes when Dr. Jones reveals that most bias audits "
                "miss systemic issues because they focus on individual predictions rather "
                "than population-level outcomes."
            ),
            "key_themes": ["ML Ethics", "Bias in AI", "Fairness"],
            "episode_highlights": [
                {
                    "podcast_name": "Test Podcast",
                    "episode_title": "ML Ethics Deep Dive",
                    "analysis": "Essential listening for anyone deploying ML in production. Dr. Jones's framework for bias audits is practical and actionable.",
                },
            ],
            "connection_insight": None,
        }
        client.models.generate_content.return_value = _make_gemini_response(single_briefing)

        config = Mock()
        config.GEMINI_API_KEY = "test-key"
        config.GEMINI_MODEL_FLASH = "gemini-2.0-flash"

        episodes = [MockEpisode(title="ML Ethics Deep Dive")]
        result = generate_digest_briefing(episodes, config)

        assert result is not None
        assert result["connection_insight"] is None
        assert len(result["episode_highlights"]) == 1

        # Verify the single-episode prompt was used
        call_args = client.models.generate_content.call_args
        prompt = call_args.kwargs.get("contents") or call_args[1].get("contents") or call_args[0][0]
        assert "why this episode matters" in str(prompt)

    @patch("src.services.briefing_generator._get_file_search_store_name", return_value=None)
    @patch("src.services.briefing_generator.genai")
    def test_api_failure_returns_none(self, mock_genai, mock_store):
        """API errors return None (graceful degradation)."""
        client = mock_genai.Client.return_value
        client.models.generate_content.side_effect = Exception("API error")

        config = Mock()
        config.GEMINI_API_KEY = "test-key"
        config.GEMINI_MODEL_FLASH = "gemini-2.0-flash"

        episodes = [MockEpisode()]
        result = generate_digest_briefing(episodes, config)
        assert result is None

    @patch("src.services.briefing_generator._get_file_search_store_name", return_value=None)
    @patch("src.services.briefing_generator.genai")
    def test_empty_response_returns_none(self, mock_genai, mock_store):
        """Empty API response returns None."""
        client = mock_genai.Client.return_value
        response = Mock()
        response.text = ""
        client.models.generate_content.return_value = response

        config = Mock()
        config.GEMINI_API_KEY = "test-key"
        config.GEMINI_MODEL_FLASH = "gemini-2.0-flash"

        episodes = [MockEpisode()]
        result = generate_digest_briefing(episodes, config)
        assert result is None

    @patch("src.services.briefing_generator._get_file_search_store_name", return_value="stores/abc123")
    @patch("src.services.briefing_generator.genai")
    def test_file_search_grounding_two_step(self, mock_genai, mock_store):
        """When File Search store is available, uses two-step grounded generation."""
        client = mock_genai.Client.return_value

        # Step 1: grounded response returns rich text
        grounded_response = Mock()
        grounded_response.text = "Rich grounded analysis text with quotes and details..."

        # Step 2: structured response returns JSON
        structured_response = _make_gemini_response(VALID_BRIEFING)

        client.models.generate_content.side_effect = [
            grounded_response,
            structured_response,
        ]

        config = Mock()
        config.GEMINI_API_KEY = "test-key"
        config.GEMINI_MODEL_FLASH = "gemini-2.0-flash"
        config.GEMINI_MODEL_LITE = "gemini-flash-lite"

        episodes = [MockEpisode(), MockEpisode(title="Second Episode")]
        result = generate_digest_briefing(episodes, config)

        assert result is not None
        # Verify two API calls were made
        assert client.models.generate_content.call_count == 2


class TestBuildEpisodeBlock:
    """Tests for _build_episode_block helper."""

    def test_uses_full_ai_summary(self):
        """Episode block includes the full ai_summary, not just the teaser."""
        ep = MockEpisode(
            ai_summary="This is a comprehensive multi-paragraph summary of the episode.",
            ai_email_content={
                "teaser_summary": "Short teaser",
                "key_takeaways": ["Takeaway 1"],
            },
        )
        block = _build_episode_block(ep)
        # Both should be present — full summary is primary, teaser is supplementary
        assert "comprehensive multi-paragraph summary" in block
        assert "Short teaser" in block
        assert "Takeaway 1" in block

    def test_falls_back_to_ai_summary_alone(self):
        """Episode block uses ai_summary when no email content."""
        ep = MockEpisode(
            ai_summary="Fallback summary text that should appear in the block.",
            ai_email_content=None,
        )
        block = _build_episode_block(ep)
        assert "Fallback summary text" in block

    def test_includes_podcast_title(self):
        """Episode block includes the podcast title."""
        ep = MockEpisode(podcast=MockPodcast("My Great Podcast"))
        block = _build_episode_block(ep)
        assert "My Great Podcast" in block

    def test_includes_keywords(self):
        """Episode block includes keywords."""
        ep = MockEpisode(ai_keywords=["python", "testing"])
        block = _build_episode_block(ep)
        assert "python" in block
        assert "testing" in block

    def test_includes_story_summaries(self):
        """Episode block includes story summaries for news podcasts."""
        ep = MockEpisode(
            ai_email_content={
                "teaser_summary": "News roundup teaser",
                "key_takeaways": [],
                "story_summaries": [
                    {"headline": "Big Story", "summary": "Details here"},
                ],
            },
        )
        block = _build_episode_block(ep)
        assert "Big Story" in block
        assert "Details here" in block

    def test_includes_highlight_moment(self):
        """Episode block includes highlight moment."""
        ep = MockEpisode(
            ai_email_content={
                "teaser_summary": "A teaser",
                "key_takeaways": [],
                "highlight_moment": "A surprising revelation about the topic.",
            },
        )
        block = _build_episode_block(ep)
        assert "surprising revelation" in block
