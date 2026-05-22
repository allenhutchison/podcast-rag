#!/usr/bin/env bash
#
# backup-db.sh — Back up the local PostgreSQL database.
#
# Dumps the local Dockerized database (the `podcast-rag-db` service) to a
# timestamped, gzip-compressed file and prunes old backups. This replaces
# the managed backups Supabase provided before the migration, so it should
# run on a schedule (see the cron example below).
#
# Usage:
#   ./scripts/backup-db.sh
#
# Environment overrides:
#   BACKUP_DIR      Destination directory   (default: ./backups)
#   RETENTION_DAYS  Delete backups older than this many days (default: 14)
#
# Cron example (nightly at 03:15 — note the cd, cron has a minimal PATH):
#   15 3 * * * cd /opt/podcast-rag && /opt/podcast-rag/scripts/backup-db.sh >> /var/log/podcast-rag-backup.log 2>&1
#
set -euo pipefail

# Backups contain production data; restrict permissions on the directory
# and every file this script creates (mkdir, the gzip output, etc.).
umask 077

# ── Resolve repo root so `docker compose` finds docker-compose.yml ─────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$REPO_ROOT"

DB_SERVICE="podcast-rag-db"
LOCAL_DB_USER="podcast_rag"
LOCAL_DB_NAME="podcast_rag"
BACKUP_DIR="${BACKUP_DIR:-$REPO_ROOT/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"

mkdir -p "$BACKUP_DIR"

TS="$(date +%Y%m%d_%H%M%S)"
OUT_FILE="$BACKUP_DIR/podcast_rag_${TS}.sql.gz"

# ── Dump (pipefail makes a pg_dump failure fail the whole pipeline) ───────
echo "==> Backing up '$LOCAL_DB_NAME' to $OUT_FILE ..."
docker compose exec -T "$DB_SERVICE" \
    pg_dump --no-owner --no-privileges -U "$LOCAL_DB_USER" "$LOCAL_DB_NAME" \
    | gzip > "$OUT_FILE"

if [[ ! -s "$OUT_FILE" ]]; then
    echo "ERROR: backup file is empty — removing it." >&2
    rm -f "$OUT_FILE"
    exit 1
fi
echo "    Backup complete: $(du -h "$OUT_FILE" | cut -f1)"

# ── Prune old backups ─────────────────────────────────────────────────────
echo "==> Pruning backups older than $RETENTION_DAYS days..."
find "$BACKUP_DIR" -maxdepth 1 -name 'podcast_rag_*.sql.gz' -type f \
    -mtime "+$RETENTION_DAYS" -print -delete

REMAINING="$(find "$BACKUP_DIR" -maxdepth 1 -name 'podcast_rag_*.sql.gz' -type f | wc -l | tr -d ' ')"
echo "    Done. $REMAINING backup(s) retained in $BACKUP_DIR"
