# Scribe Transcription Migration

This runbook covers the reversible compatibility phase. Scribe receives a copy
of every completed transcript, while podcast-rag continues retaining transcript
text for downstream metadata and indexing.

## 1. Inventory

Run database commands through Doppler:

```bash
doppler run -- python scripts/export_transcripts_to_scribe.py \
  /tmp/podcast-rag-transcripts.jsonl --dry-run
```

Resolve every `skipped_missing_text` and `conflicting_file_hashes` row before
cutover, or record it as an explicit exception. Invalid file hashes do not block
export; those records are seeded with URL-only deduplication.

## 2. Back up both stores

- Run `scripts/backup-db.sh` for podcast-rag PostgreSQL.
- Keep Scribe's API online for Pepper. Create a consistent live snapshot with
  SQLite's backup API; do not copy only `scribe.db` while WAL writes are active:

  ```bash
  docker exec scribe python -c 'import sqlite3; source=sqlite3.connect("/data/scribe.db"); backup=sqlite3.connect("/data/scribe-preseed.db"); source.backup(backup); backup.close(); source.close()'
  docker cp scribe:/data/scribe-preseed.db /secure/backup/path/scribe-preseed.db
  ```

  Store the copied snapshot outside the `scribe-data` volume so losing or
  restoring that volume does not also lose the backup.
- Record the backup paths and export manifest with the change record.

## 3. Export

```bash
doppler run -- python scripts/export_transcripts_to_scribe.py \
  /tmp/podcast-rag-transcripts.jsonl
```

The exporter writes owner-only JSONL plus
`podcast-rag-transcripts.jsonl.manifest.json`. Preserve both until the migration
and soak period are complete.

## 4. Online canary

Pepper is a live Scribe consumer. Keep the Scribe API and Cloudflare tunnel
available throughout the migration. Copy the export into the running container,
then seed and verify the first 100 records:

```bash
docker cp /tmp/podcast-rag-transcripts.jsonl \
  scribe:/tmp/podcast-rag-transcripts.jsonl
docker exec scribe scribe-seed /tmp/podcast-rag-transcripts.jsonl \
  --owner podcast-rag --limit 100
docker exec scribe scribe-seed /tmp/podcast-rag-transcripts.jsonl \
  --owner podcast-rag --limit 100 --verify-only
```

The verification must report zero `missing`, `mismatched`, and `errored`
records. Wait through at least one Pepper podcast-collector interval and inspect
both services for elevated latency, HTTP failures, or `database is locked`.
Pepper's collector fails open on transport errors, but a clean canary is still
the gate for the full import.

## 5. Full online seed and verify

Run the idempotent full import while continuing to monitor Pepper and Scribe:

```bash
docker exec scribe scribe-seed /tmp/podcast-rag-transcripts.jsonl \
  --owner podcast-rag
docker exec scribe scribe-seed /tmp/podcast-rag-transcripts.jsonl \
  --owner podcast-rag --verify-only
```

The full import skips the 100 canary rows. Verification must report zero
`missing`, `mismatched`, and `errored` records, and re-running the seed must
report zero imports. Abort before cutover if Pepper or Scribe shows sustained
errors; the import does not require an application outage.

## 6. Compatibility cutover

Configure the podcast-rag Doppler production environment:

```text
TRANSCRIPTION_BACKEND=scribe
SCRIBE_API_TOKEN=<podcast-rag consumer token>
```

On bubba, `SCRIBE_BASE_URL=http://scribe:8000` is supplied by Compose. Restart
only the podcast-rag pipeline, then verify one cache hit and one fresh episode
through transcription, metadata extraction, Gemini File Search indexing, and
audio cleanup.

## Rollback

Set `TRANSCRIPTION_BACKEND=local` and restart the podcast-rag pipeline. During
this phase all completed transcript text remains in PostgreSQL, so rollback does
not require restoring data. Do not remove transcript text, Whisper dependencies,
or podcast-rag's GPU reservation until the later remote-only phase is complete.
