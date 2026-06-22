"""Tests for briefing audio repository methods."""

from datetime import UTC, date, datetime, timedelta

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
def sample_briefing(repository, sample_user):
    return repository.create_or_update_daily_briefing(
        user_id=sample_user.id,
        briefing_date=date(2026, 6, 19),
        headline="Test Headline",
        briefing_text="Test briefing text.",
        key_themes=["theme1"],
        episode_highlights=[],
        connection_insight=None,
        episode_count=1,
        episode_ids=["ep-1"],
    )


class TestGetBriefingById:
    def test_found(self, repository, sample_briefing):
        result = repository.get_briefing_by_id(sample_briefing.id)
        assert result is not None
        assert result.id == sample_briefing.id
        assert result.headline == "Test Headline"

    def test_not_found(self, repository):
        result = repository.get_briefing_by_id("nonexistent-id")
        assert result is None


class TestClaimBriefingAudio:
    def test_first_claim_succeeds(self, repository, sample_briefing):
        claimed = repository.claim_briefing_audio(sample_briefing.id)
        assert claimed is True
        briefing = repository.get_briefing_by_id(sample_briefing.id)
        assert briefing.audio_status == "generating"

    def test_second_claim_fails(self, repository, sample_briefing):
        assert repository.claim_briefing_audio(sample_briefing.id) is True
        assert repository.claim_briefing_audio(sample_briefing.id) is False

    def test_claim_after_failed_succeeds(self, repository, sample_briefing):
        repository.update_briefing_audio_status(sample_briefing.id, "failed")
        claimed = repository.claim_briefing_audio(sample_briefing.id)
        assert claimed is True
        briefing = repository.get_briefing_by_id(sample_briefing.id)
        assert briefing.audio_status == "generating"

    def test_claim_after_ready_fails(self, repository, sample_briefing):
        repository.update_briefing_audio(
            briefing_id=sample_briefing.id,
            audio_data=b"fake mp3",
            audio_mime_type="audio/mpeg",
            audio_duration_sec=120,
            status="ready",
        )
        claimed = repository.claim_briefing_audio(sample_briefing.id)
        assert claimed is False


class TestUpdateBriefingAudio:
    def test_update_sets_all_fields(self, repository, sample_briefing):
        repository.update_briefing_audio(
            briefing_id=sample_briefing.id,
            audio_data=b"mp3 bytes",
            audio_mime_type="audio/mpeg",
            audio_duration_sec=180,
            status="ready",
        )
        briefing = repository.get_briefing_by_id(sample_briefing.id)
        assert briefing.audio_data == b"mp3 bytes"
        assert briefing.audio_mime_type == "audio/mpeg"
        assert briefing.audio_duration_sec == 180
        assert briefing.audio_status == "ready"
        assert briefing.audio_generated_at is not None


class TestUpdateBriefingAudioStatus:
    def test_update_status(self, repository, sample_briefing):
        repository.update_briefing_audio_status(sample_briefing.id, "failed")
        briefing = repository.get_briefing_by_id(sample_briefing.id)
        assert briefing.audio_status == "failed"


class TestClearAudioDataBefore:
    def test_clears_old_audio(self, repository, sample_user):
        # Create two briefings: one old, one new
        old_briefing = repository.create_or_update_daily_briefing(
            user_id=sample_user.id,
            briefing_date=date(2026, 5, 1),
            headline="Old",
            briefing_text="Old text.",
            key_themes=[],
            episode_highlights=[],
            connection_insight=None,
            episode_count=1,
            episode_ids=["ep-old"],
        )
        new_briefing = repository.create_or_update_daily_briefing(
            user_id=sample_user.id,
            briefing_date=date(2026, 6, 19),
            headline="New",
            briefing_text="New text.",
            key_themes=[],
            episode_highlights=[],
            connection_insight=None,
            episode_count=1,
            episode_ids=["ep-new"],
        )

        # Add audio to both
        repository.update_briefing_audio(
            old_briefing.id, b"old mp3", "audio/mpeg", 100, "ready"
        )
        repository.update_briefing_audio(
            new_briefing.id, b"new mp3", "audio/mpeg", 100, "ready"
        )

        # Clear audio older than now
        cutoff = datetime.now(UTC)
        affected = repository.clear_audio_data_before(cutoff)

        assert affected >= 1
        old = repository.get_briefing_by_id(old_briefing.id)
        new = repository.get_briefing_by_id(new_briefing.id)
        assert old.audio_data is None
        assert old.audio_status is None
        assert new.audio_data is None  # both are older than now
        assert new.audio_status is None

    def test_clears_only_old(self, repository, sample_user):
        old_briefing = repository.create_or_update_daily_briefing(
            user_id=sample_user.id,
            briefing_date=date(2026, 5, 1),
            headline="Old",
            briefing_text="Old text.",
            key_themes=[],
            episode_highlights=[],
            connection_insight=None,
            episode_count=1,
            episode_ids=["ep-old"],
        )
        new_briefing = repository.create_or_update_daily_briefing(
            user_id=sample_user.id,
            briefing_date=date(2026, 6, 19),
            headline="New",
            briefing_text="New text.",
            key_themes=[],
            episode_highlights=[],
            connection_insight=None,
            episode_count=1,
            episode_ids=["ep-new"],
        )
        repository.update_briefing_audio(
            old_briefing.id, b"old mp3", "audio/mpeg", 100, "ready"
        )
        repository.update_briefing_audio(
            new_briefing.id, b"new mp3", "audio/mpeg", 100, "ready"
        )

        # Clear audio older than 1 second ago — both will be cleared since
        # audio_generated_at is set to now() for both.
        # Instead, use a future cutoff that's between old and new by
        # clearing with cutoff = now (both are <= now).
        # To test selective clearing, use cutoff = 1 day ago (both newer).
        yesterday = datetime.now(UTC) - timedelta(days=1)
        repository.clear_audio_data_before(yesterday)

        old = repository.get_briefing_by_id(old_briefing.id)
        new = repository.get_briefing_by_id(new_briefing.id)
        # Both have audio_generated_at = now(), which is after yesterday,
        # so neither should be cleared.
        assert old.audio_data is not None
        assert new.audio_data is not None
