#!/usr/bin/env python3
"""Export completed podcast-rag transcripts for Scribe's seed command.

Run database-backed invocations through Doppler, for example:

    doppler run -- python scripts/export_transcripts_to_scribe.py export.jsonl

The JSONL and its manifest are written atomically with owner-only permissions.
No database rows are modified.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import tempfile
from contextlib import suppress
from pathlib import Path
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from src.config import Config
from src.db.factory import create_repository

_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
logger = logging.getLogger(__name__)


def _record_for_episode(episode, transcript_text: str) -> tuple[dict[str, Any], bool]:
    """Build one Scribe seed record and report whether its file hash is invalid."""
    file_hash = episode.file_hash
    valid_hash = bool(file_hash and _SHA256_RE.fullmatch(file_hash))
    record = {
        "episode_id": episode.id,
        "enclosure_url": episode.enclosure_url,
        "transcript_text": transcript_text,
        "transcript_sha256": hashlib.sha256(transcript_text.encode("utf-8")).hexdigest(),
        "file_hash": file_hash.lower() if valid_hash else None,
        "duration_seconds": episode.duration_seconds,
        "transcript_status": "completed",
        "model": episode.transcript_model,
        "lang": episode.transcript_language or "en",
    }
    return record, bool(file_hash and not valid_hash)


def export_transcripts(repository, output_path: Path, *, dry_run: bool = False) -> dict[str, Any]:
    """Export completed transcripts and return a verification manifest."""
    manifest: dict[str, Any] = {
        "completed_rows": 0,
        "exported_rows": 0,
        "skipped_missing_text": 0,
        "invalid_file_hashes": 0,
        "duplicate_urls": 0,
        "duplicate_file_hashes": 0,
        "conflicting_file_hashes": 0,
        "transcript_characters": 0,
        "jsonl_bytes": 0,
        "jsonl_sha256": None,
    }
    seen_urls: set[str] = set()
    seen_hashes: dict[str, str] = {}
    digest = hashlib.sha256()

    output_path = output_path.resolve()
    temp_path: Path | None = None
    manifest_temp: Path | None = None
    output = None

    try:
        episodes = repository.list_episodes(transcript_status="completed")
        manifest["completed_rows"] = len(episodes)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if not dry_run:
            handle = tempfile.NamedTemporaryFile(
                mode="wb",
                dir=output_path.parent,
                prefix=f".{output_path.name}.",
                delete=False,
            )
            os.chmod(handle.name, 0o600)
            temp_path = Path(handle.name)
            output = handle

        for episode in episodes:
            transcript_text = repository.get_transcript_text(episode.id)
            if transcript_text is None:
                manifest["skipped_missing_text"] += 1
                continue

            record, invalid_hash = _record_for_episode(episode, transcript_text)
            manifest["invalid_file_hashes"] += int(invalid_hash)

            url = record["enclosure_url"]
            if url in seen_urls:
                manifest["duplicate_urls"] += 1
            seen_urls.add(url)

            file_hash = record["file_hash"]
            if file_hash:
                if file_hash in seen_hashes:
                    manifest["duplicate_file_hashes"] += 1
                    if seen_hashes[file_hash] != record["transcript_sha256"]:
                        manifest["conflicting_file_hashes"] += 1
                else:
                    seen_hashes[file_hash] = record["transcript_sha256"]

            encoded = (json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n").encode(
                "utf-8"
            )
            digest.update(encoded)
            if output is not None:
                output.write(encoded)
            manifest["exported_rows"] += 1
            manifest["transcript_characters"] += len(transcript_text)
            manifest["jsonl_bytes"] += len(encoded)

        manifest["jsonl_sha256"] = digest.hexdigest()
        if output is not None and temp_path is not None:
            output.flush()
            os.fsync(output.fileno())
            output.close()
            output = None
            os.replace(temp_path, output_path)
            temp_path = None

            manifest_path = output_path.with_suffix(output_path.suffix + ".manifest.json")
            manifest_temp = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
            manifest_temp.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            os.chmod(manifest_temp, 0o600)
            os.replace(manifest_temp, manifest_path)
            manifest_temp = None

        return manifest
    except (OSError, SQLAlchemyError):
        logger.error("Failed to export transcripts to %s", output_path, exc_info=True)
        raise
    finally:
        if output is not None:
            with suppress(OSError):
                output.close()
        if temp_path is not None:
            with suppress(OSError):
                temp_path.unlink(missing_ok=True)
        if manifest_temp is not None:
            with suppress(OSError):
                manifest_temp.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    """Run the transcript export command and return a process exit status."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="Destination JSONL file")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Inventory exportable rows without writing transcript data",
    )
    args = parser.parse_args(argv)

    config = Config()
    repository = create_repository(
        database_url=config.DATABASE_URL,
        pool_size=config.DB_POOL_SIZE,
        max_overflow=config.DB_MAX_OVERFLOW,
        pool_pre_ping=config.DB_POOL_PRE_PING,
        echo=config.DB_ECHO,
    )
    try:
        manifest = export_transcripts(repository, args.output, dry_run=args.dry_run)
    finally:
        repository.close()

    print(json.dumps(manifest, indent=2))
    clean = manifest["skipped_missing_text"] == 0 and manifest["conflicting_file_hashes"] == 0
    return 0 if clean else 2


if __name__ == "__main__":
    raise SystemExit(main())
