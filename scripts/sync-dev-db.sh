#!/usr/bin/env bash
#
# sync-dev-db.sh — Clone the production Supabase database into a local
# Docker Postgres instance for development.
#
# Usage:
#   ./scripts/sync-dev-db.sh            # full sync (dump + restore)
#   ./scripts/sync-dev-db.sh --schema   # schema only, no data
#
# Prerequisites:
#   - Docker running with the dev-db container (docker compose -f docker-compose.dev.yml up -d)
#   - Doppler CLI configured for this project
#
set -euo pipefail

# ── Configuration ──────────────────────────────────────────────────────────
LOCAL_DB_USER="podcast_rag"
LOCAL_DB_PASSWORD="${DEV_DB_PASSWORD:-dev_password}"
LOCAL_DB_NAME="podcast_rag"
LOCAL_DB_PORT="5433"
LOCAL_DB_HOST="localhost"
umask 077
DUMP_FILE="$(mktemp /tmp/podcast-rag-prod-dump.XXXXXX.sql)"
trap 'rm -f "$DUMP_FILE"' EXIT INT TERM

SCHEMA_ONLY=false
if [[ "${1:-}" == "--schema" ]]; then
    SCHEMA_ONLY=true
fi

# ── Resolve production DATABASE_URL from Doppler ──────────────────────────
echo "==> Fetching production DATABASE_URL from Doppler (config: prod)..."
PROD_URL=$(doppler secrets get DATABASE_URL --plain --config prod 2>/dev/null)

if [[ -z "$PROD_URL" ]]; then
    echo "ERROR: Could not retrieve DATABASE_URL from Doppler." >&2
    echo "Make sure Doppler is configured: doppler setup" >&2
    exit 1
fi

# Supabase pooler URLs use port 6543 (transaction mode) or 5432 (session mode).
# pg_dump requires session mode (port 5432), so rewrite if needed.
DUMP_URL="${PROD_URL//:6543/:5432}"

echo "   Production URL resolved (credentials hidden)"

# ── Ensure the dev-db container is running ────────────────────────────────
echo "==> Checking dev-db container..."
if ! docker compose -f docker-compose.dev.yml ps --status running 2>/dev/null | grep -q dev-db; then
    echo "   Starting dev-db container..."
    docker compose -f docker-compose.dev.yml up -d dev-db
    echo "   Waiting for Postgres to be ready..."
    until docker compose -f docker-compose.dev.yml exec -T dev-db pg_isready -U "$LOCAL_DB_USER" >/dev/null 2>&1; do
        sleep 1
    done
    echo "   Postgres is ready."
else
    echo "   dev-db is already running."
fi

# ── Dump production database ──────────────────────────────────────────────
echo "==> Dumping production database..."
DUMP_ARGS=(--no-owner --no-privileges --clean --if-exists)

if $SCHEMA_ONLY; then
    DUMP_ARGS+=(--schema-only)
    echo "   (schema only — no data)"
fi

# Use the postgres:17 image for pg_dump to ensure version compatibility.
docker run --rm \
    postgres:17 \
    pg_dump "${DUMP_ARGS[@]}" "$DUMP_URL" > "$DUMP_FILE"

DUMP_SIZE=$(du -h "$DUMP_FILE" | cut -f1)
echo "   Dump complete: $DUMP_FILE ($DUMP_SIZE)"

# ── Restore into local dev database ──────────────────────────────────────
echo "==> Restoring into local dev database..."

# Drop and recreate the database to ensure a clean slate
docker compose -f docker-compose.dev.yml exec -T dev-db \
    psql -U "$LOCAL_DB_USER" -d postgres -c "
        SELECT pg_terminate_backend(pid) FROM pg_stat_activity
        WHERE datname = '$LOCAL_DB_NAME' AND pid <> pg_backend_pid();
    " >/dev/null 2>&1 || true

docker compose -f docker-compose.dev.yml exec -T dev-db \
    psql -U "$LOCAL_DB_USER" -d postgres -c "DROP DATABASE IF EXISTS $LOCAL_DB_NAME;" >/dev/null 2>&1

docker compose -f docker-compose.dev.yml exec -T dev-db \
    psql -U "$LOCAL_DB_USER" -d postgres -c "CREATE DATABASE $LOCAL_DB_NAME;" >/dev/null 2>&1

# Restore the dump
docker compose -f docker-compose.dev.yml exec -T dev-db \
    psql -U "$LOCAL_DB_USER" -d "$LOCAL_DB_NAME" < "$DUMP_FILE" >/dev/null 2>&1

echo "   Restore complete."

# ── Summary ───────────────────────────────────────────────────────────────
# (dump file is cleaned up automatically via EXIT trap)
LOCAL_URL="postgresql://${LOCAL_DB_USER}:${LOCAL_DB_PASSWORD}@${LOCAL_DB_HOST}:${LOCAL_DB_PORT}/${LOCAL_DB_NAME}"

echo ""
echo "==> Dev database ready!"
echo ""
echo "   Connection URL:"
echo "   $LOCAL_URL"
echo ""
echo "   To use with this project:"
echo "   export DATABASE_URL=\"$LOCAL_URL\""
echo ""
echo "   Or run commands with:"
echo "   DATABASE_URL=\"$LOCAL_URL\" uv run poe serve"
echo ""
