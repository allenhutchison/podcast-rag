#!/usr/bin/env bash
#
# migrate-prod-db.sh — One-time production clone.
#
# Dumps the Supabase-hosted production database and restores it into the
# local PostgreSQL container named `podcast-rag-db` on the VPS.
#
# Compose-project-agnostic: the script uses raw `docker exec` against the
# fixed container name, so it doesn't care whether the container was started
# by this repo's docker-compose.yml or by the homelab repo's compose stack
# (which is the case on bubba).
#
# Unlike scripts/sync-dev-db.sh (a dev convenience that suppresses errors),
# this script FAILS LOUDLY: any pg_dump or psql error aborts the run, so a
# partial or corrupt clone can never pass silently. Always follow a run
# with scripts/verify-db-clone.sh before cutting over.
#
# Usage:
#   ./scripts/migrate-prod-db.sh            # full clone (schema + data)
#   ./scripts/migrate-prod-db.sh --schema   # schema only, no data
#   ./scripts/migrate-prod-db.sh --yes      # skip the confirmation prompt
#
# Prerequisites:
#   - The podcast-rag-db container is running and healthy
#   - Doppler CLI configured with access to the `prod` config
#   - Docker available (the postgres:17 image is used for pg_dump)
#
set -euo pipefail

# ── Configuration ─────────────────────────────────────────────────────────
DB_CONTAINER="podcast-rag-db"
LOCAL_DB_USER="podcast_rag"
LOCAL_DB_NAME="podcast_rag"
PG_IMAGE="postgres:17"

umask 077
DUMP_FILE="$(mktemp /tmp/podcast-rag-prod-dump.XXXXXX.sql)"
trap 'rm -f "$DUMP_FILE"' EXIT INT TERM

# ── Parse arguments ───────────────────────────────────────────────────────
SCHEMA_ONLY=false
ASSUME_YES=false
for arg in "$@"; do
    case "$arg" in
        --schema) SCHEMA_ONLY=true ;;
        --yes|-y) ASSUME_YES=true ;;
        *) echo "ERROR: unknown argument '$arg'" >&2; exit 2 ;;
    esac
done

# ── Resolve production DATABASE_URL from Doppler ──────────────────────────
echo "==> Fetching production DATABASE_URL from Doppler (config: prod)..."
PROD_URL="$(doppler secrets get DATABASE_URL --plain --config prod 2>/dev/null || true)"
if [[ -z "$PROD_URL" ]]; then
    echo "ERROR: Could not retrieve DATABASE_URL from Doppler (config: prod)." >&2
    echo "       Run 'doppler setup' and confirm access to the prod config." >&2
    exit 1
fi

# Supabase pooler URLs use port 6543 (transaction mode) or 5432 (session
# mode). pg_dump requires session mode, so rewrite the port if needed.
DUMP_URL="${PROD_URL//:6543/:5432}"
echo "    Production URL resolved (credentials hidden)."

# ── Confirm: this destroys the local podcast_rag database ─────────────────
echo ""
echo "    This will DROP and recreate the local '$LOCAL_DB_NAME' database"
echo "    in the '$DB_CONTAINER' container and replace it with a fresh clone"
echo "    of production. Any existing local data will be lost."
echo ""
if ! $ASSUME_YES; then
    if [[ ! -t 0 ]]; then
        echo "ERROR: not an interactive shell; re-run with --yes to proceed." >&2
        exit 1
    fi
    read -r -p "Type 'yes' to continue: " reply
    [[ "$reply" == "yes" ]] || { echo "Aborted."; exit 1; }
fi

# ── Ensure the local database container is up and healthy ─────────────────
echo "==> Checking the $DB_CONTAINER container..."
if ! docker inspect "$DB_CONTAINER" --format '{{.State.Running}}' 2>/dev/null | grep -qx "true"; then
    echo "ERROR: container '$DB_CONTAINER' is not running." >&2
    echo "       Start it from the compose stack that defines it (on bubba:" >&2
    echo "       ~/src/homelab/nodes/bubba.sh up -d podcast-rag-db)." >&2
    exit 1
fi
echo "    Waiting for PostgreSQL to accept connections..."
MAX_WAIT_SECONDS="${MAX_WAIT_SECONDS:-120}"
elapsed=0
until docker exec "$DB_CONTAINER" pg_isready -U "$LOCAL_DB_USER" -d postgres >/dev/null 2>&1; do
    sleep 1
    elapsed=$((elapsed + 1))
    if (( elapsed >= MAX_WAIT_SECONDS )); then
        echo "ERROR: '$DB_CONTAINER' (user '$LOCAL_DB_USER') not ready after ${MAX_WAIT_SECONDS}s." >&2
        echo "       Check 'docker logs $DB_CONTAINER' for details." >&2
        exit 1
    fi
done
echo "    PostgreSQL is ready."

# Helper: run psql inside the db container against the maintenance database.
# No -i — callers pass SQL via -c, not via stdin. (`docker exec -i` would
# eat any surrounding heredoc/loop stdin; see verify-db-clone.sh::tgt_q.)
psql_admin() {
    docker exec "$DB_CONTAINER" \
        psql -v ON_ERROR_STOP=1 -U "$LOCAL_DB_USER" -d postgres "$@"
}

# ── Dump the production database ───────────────────────────────────────────
echo "==> Dumping production database..."
# -n public restricts the dump to the public schema. Supabase preloads
# extensions (hypopg, supabase_vault, etc.) and schemas (auth, storage,
# realtime, graphql, …) that don't exist in stock postgres:17 and aren't
# used by this app. Without the filter the restore aborts inside the
# --single-transaction on the first missing extension. Confirmed safe:
# `grep -E 'uuid_generate|gen_random|hypopg|...' src/ alembic/` is empty,
# and no public column default references an extension function.
DUMP_ARGS=(--no-owner --no-privileges --clean --if-exists -n public)
if $SCHEMA_ONLY; then
    DUMP_ARGS+=(--schema-only)
    echo "    (schema only — no data)"
fi

# pg_dump runs in a throwaway postgres:17 container so the client version
# matches the local server. set -e aborts the script on any failure.
docker run --rm "$PG_IMAGE" pg_dump "${DUMP_ARGS[@]}" "$DUMP_URL" > "$DUMP_FILE"

if [[ ! -s "$DUMP_FILE" ]]; then
    echo "ERROR: dump file is empty — aborting before touching the local DB." >&2
    exit 1
fi
echo "    Dump complete: $(du -h "$DUMP_FILE" | cut -f1)"

# ── Recreate the local database (clean slate) ─────────────────────────────
echo "==> Recreating the local '$LOCAL_DB_NAME' database..."
psql_admin -c "
    SELECT pg_terminate_backend(pid) FROM pg_stat_activity
    WHERE datname = '$LOCAL_DB_NAME' AND pid <> pg_backend_pid();
" >/dev/null
psql_admin -c "DROP DATABASE IF EXISTS $LOCAL_DB_NAME;" >/dev/null
psql_admin -c "CREATE DATABASE $LOCAL_DB_NAME OWNER $LOCAL_DB_USER;" >/dev/null

# ── Restore into the local database ───────────────────────────────────────
echo "==> Restoring into the local database..."
# ON_ERROR_STOP + --single-transaction: any error aborts the whole restore
# and leaves the database empty rather than half-populated.
docker exec -i "$DB_CONTAINER" \
    psql -v ON_ERROR_STOP=1 --single-transaction \
    -U "$LOCAL_DB_USER" -d "$LOCAL_DB_NAME" < "$DUMP_FILE"

echo "    Restore complete."
echo ""
echo "==> Clone finished. NEXT STEP — verify it before cutting over:"
echo "    ./scripts/verify-db-clone.sh"
echo ""
