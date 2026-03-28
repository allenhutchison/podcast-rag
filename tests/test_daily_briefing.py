"""Tests for the daily briefing model and feed repository methods."""

from datetime import UTC, datetime, timedelta

import pytest

from src.db.factory import create_repository


@pytest.fixture
def repository(tmp_path):
    db_path = tmp_path / "test.db"
    repo = create_repository(f"sqlite:///{db_path}", create_tables=True)
    yield repo
    repo.close()


@pytest.fixture
def sample_user(repository):
    return repository.create_user(
        google_id="test_google_id",
        email="test@example.com",
        name="Test User",
    )


@pytest.fixture
def sample_podcast(repository):
    return repository.create_podcast(
        feed_url="https://example.com/feed.xml",
        title="Test Podcast",
        description="A test podcast",
        author="Test Author",
        language="en",
    )


@pytest.fixture
def subscribed_episodes(repository, sample_user, sample_podcast):
    """Create a subscription and episodes for the user."""
    repository.subscribe_user_to_podcast(sample_user.id, sample_podcast.id)

    today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday = today - timedelta(days=1)

    episodes = []
    for i, pub_date in enumerate([today, today, yesterday]):
        ep = repository.create_episode(
            podcast_id=sample_podcast.id,
            guid=f"guid-{i}",
            title=f"Episode {i}",
            enclosure_url=f"https://example.com/ep{i}.mp3",
            enclosure_type="audio/mpeg",
            published_date=pub_date + timedelta(hours=i),
        )
        repository.update_episode(
            str(ep.id),
            ai_summary=f"Summary for episode {i}",
            metadata_status="completed",
        )
        episodes.append(ep)

    return episodes


class TestDailyBriefingCRUD:

    def test_create_briefing(self, repository, sample_user):
        briefing_date = datetime(2026, 3, 28, tzinfo=UTC)
        briefing = repository.create_or_update_daily_briefing(
            user_id=sample_user.id,
            briefing_date=briefing_date,
            headline="Test Headline",
            briefing_text="Test briefing text.",
            key_themes=["theme1", "theme2"],
            episode_highlights=[{"podcast_name": "P1", "episode_title": "E1", "analysis": "Good"}],
            connection_insight="A connection",
            episode_count=1,
            episode_ids=["ep-1"],
        )

        assert briefing.id is not None
        assert briefing.headline == "Test Headline"
        assert briefing.key_themes == ["theme1", "theme2"]
        assert briefing.episode_count == 1

    def test_upsert_briefing(self, repository, sample_user):
        briefing_date = datetime(2026, 3, 28, tzinfo=UTC)
        kwargs = dict(
            user_id=sample_user.id,
            briefing_date=briefing_date,
            headline="Original",
            briefing_text="Original text.",
            key_themes=["t1"],
            episode_highlights=[],
            connection_insight=None,
            episode_count=1,
            episode_ids=["ep-1"],
        )

        b1 = repository.create_or_update_daily_briefing(**kwargs)

        # Update with new headline
        kwargs["headline"] = "Updated"
        kwargs["episode_count"] = 2
        b2 = repository.create_or_update_daily_briefing(**kwargs)

        assert b2.id == b1.id
        assert b2.headline == "Updated"
        assert b2.episode_count == 2

    def test_get_briefings_in_range(self, repository, sample_user):
        base = datetime(2026, 3, 25, tzinfo=UTC)
        for i in range(5):
            repository.create_or_update_daily_briefing(
                user_id=sample_user.id,
                briefing_date=base + timedelta(days=i),
                headline=f"Day {i}",
                briefing_text=f"Text {i}",
                key_themes=[],
                episode_highlights=[],
                connection_insight=None,
                episode_count=0,
                episode_ids=[],
            )

        # Query a 3-day range
        start = base + timedelta(days=1)
        end = base + timedelta(days=4)
        results = repository.get_daily_briefings_in_range(
            sample_user.id, start, end
        )

        assert len(results) == 3
        # Should be ordered by date desc
        assert results[0].headline == "Day 3"
        assert results[-1].headline == "Day 1"


class TestFeedEpisodes:

    def test_get_feed_episodes_in_range(self, repository, sample_user, subscribed_episodes):
        today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow = today + timedelta(days=1)

        episodes = repository.get_feed_episodes_in_range(
            sample_user.id, today, tomorrow
        )

        # Should get 2 episodes from today (not yesterday's)
        assert len(episodes) == 2

    def test_get_feed_episodes_empty_range(self, repository, sample_user, subscribed_episodes):
        old_date = datetime(2020, 1, 1, tzinfo=UTC)
        end = old_date + timedelta(days=1)

        episodes = repository.get_feed_episodes_in_range(
            sample_user.id, old_date, end
        )

        assert len(episodes) == 0

    def test_feed_excludes_unsubscribed(self, repository, sample_podcast):
        """Episodes from unsubscribed podcasts should not appear."""
        user = repository.create_user(
            google_id="other_user",
            email="other@example.com",
            name="Other User",
        )

        today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        ep = repository.create_episode(
            podcast_id=sample_podcast.id,
            guid="unsubscribed-ep",
            title="Unsubscribed Episode",
            enclosure_url="https://example.com/ep.mp3",
            enclosure_type="audio/mpeg",
            published_date=today,
        )
        repository.update_episode(
            str(ep.id),
            ai_summary="Summary",
            metadata_status="completed",
        )

        episodes = repository.get_feed_episodes_in_range(
            user.id, today, today + timedelta(days=1)
        )

        assert len(episodes) == 0
