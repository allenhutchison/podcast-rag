"""Tests for the Scribe migration export."""

import hashlib
import json

from scripts.export_transcripts_to_scribe import export_transcripts
from src.db.factory import create_repository


def test_export_completed_transcripts_with_manifest(tmp_path) -> None:
    repository = create_repository(f"sqlite:///{tmp_path / 'podcasts.db'}", create_tables=True)
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
    repository.close()

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


def test_dry_run_does_not_write_transcript_file(tmp_path) -> None:
    repository = create_repository(f"sqlite:///{tmp_path / 'podcasts.db'}", create_tables=True)
    output = tmp_path / "export.jsonl"

    manifest = export_transcripts(repository, output, dry_run=True)
    repository.close()

    assert manifest["exported_rows"] == 0
    assert not output.exists()
