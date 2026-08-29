"""Tests for the Scribe migration export."""

import hashlib
import json
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import SQLAlchemyError

from scripts import export_transcripts_to_scribe as exporter
from scripts.export_transcripts_to_scribe import export_transcripts
from src.db.factory import create_repository


@pytest.fixture
def repository(tmp_path):
    """Yield an isolated repository and always close its connection pool."""
    repository = create_repository(f"sqlite:///{tmp_path / 'podcasts.db'}", create_tables=True)
    try:
        yield repository
    finally:
        repository.close()


def test_export_completed_transcripts_with_manifest(repository, tmp_path) -> None:
    podcast = repository.create_podcast(feed_url="https://example.com/feed.xml", title="Podcast")
    first = repository.create_episode(
        podcast_id=podcast.id,
        guid="one",
        title="One",
        enclosure_url="https://example.com/one.mp3",
        enclosure_type="audio/mpeg",
        duration_seconds=60,
        file_hash="a" * 64,
    )
    repository.mark_transcript_complete(
        first.id,
        transcript_text="First transcript",
        provider="local",
        model="medium",
        language="en",
    )
    second = repository.create_episode(
        podcast_id=podcast.id,
        guid="two",
        title="Two",
        enclosure_url="https://example.com/two.mp3",
        enclosure_type="audio/mpeg",
        file_hash="not-a-sha256",
    )
    repository.update_episode(second.id, transcript_status="completed")
    third = repository.create_episode(
        podcast_id=podcast.id,
        guid="three",
        title="Three",
        enclosure_url="https://example.com/three.mp3",
        enclosure_type="audio/mpeg",
        file_hash="a" * 64,
    )
    repository.mark_transcript_complete(
        third.id,
        transcript_text="Conflicting transcript",
        provider="local",
    )

    output = tmp_path / "export.jsonl"
    manifest = export_transcripts(repository, output)

    rows = [json.loads(line) for line in output.read_text().splitlines()]
    assert len(rows) == 2
    exported_first = next(row for row in rows if row["episode_id"] == first.id)
    assert exported_first["transcript_text"] == "First transcript"
    assert exported_first["transcript_sha256"] == hashlib.sha256(b"First transcript").hexdigest()
    assert manifest["completed_rows"] == 3
    assert manifest["exported_rows"] == 2
    assert manifest["skipped_missing_text"] == 1
    assert manifest["duplicate_file_hashes"] == 1
    assert manifest["conflicting_file_hashes"] == 1
    assert output.with_suffix(".jsonl.manifest.json").exists()


def test_empty_completed_transcript_exits_cleanly(
    repository, tmp_path, monkeypatch, capsys
) -> None:
    podcast = repository.create_podcast(
        feed_url="https://example.com/empty-feed.xml", title="Empty"
    )
    episode = repository.create_episode(
        podcast_id=podcast.id,
        guid="empty",
        title="Empty transcript",
        enclosure_url="https://example.com/empty.mp3",
        enclosure_type="audio/mpeg",
    )
    repository.mark_transcript_complete(episode.id, transcript_text="")
    output = tmp_path / "empty.jsonl"
    config = SimpleNamespace(
        DATABASE_URL="unused",
        DB_POOL_SIZE=1,
        DB_MAX_OVERFLOW=0,
        DB_POOL_PRE_PING=False,
        DB_ECHO=False,
    )
    monkeypatch.setattr(exporter, "Config", lambda: config)
    monkeypatch.setattr(exporter, "create_repository", lambda **kwargs: repository)

    assert exporter.main([str(output)]) == 0

    rows = [json.loads(line) for line in output.read_text().splitlines()]
    assert rows[0]["transcript_text"] == ""
    manifest = json.loads(capsys.readouterr().out)
    assert manifest["exported_rows"] == 1
    assert manifest["skipped_missing_text"] == 0
    assert manifest["conflicting_file_hashes"] == 0


def test_dry_run_does_not_write_transcript_file(repository, tmp_path) -> None:
    output = tmp_path / "export.jsonl"

    manifest = export_transcripts(repository, output, dry_run=True)

    assert manifest["exported_rows"] == 0
    assert not output.exists()


def test_export_logs_repository_failure_and_cleans_temp_file(
    repository, tmp_path, monkeypatch, caplog
) -> None:
    output = tmp_path / "failed.jsonl"
    monkeypatch.setattr(
        repository,
        "list_episodes",
        lambda **kwargs: (_ for _ in ()).throw(SQLAlchemyError("database unavailable")),
    )

    with caplog.at_level("ERROR"), pytest.raises(SQLAlchemyError):
        export_transcripts(repository, output)

    assert not output.exists()
    assert list(tmp_path.glob(".failed.jsonl.*")) == []
    assert any(str(output) in record.message and record.exc_info for record in caplog.records)
