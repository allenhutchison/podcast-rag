#!/usr/bin/env bash
#
# verify-db-clone.sh — Prove that the local clone matches production.
#
# Compares the Supabase production database (source) against the local
# Dockerized PostgreSQL (target) and reports any difference. Run this
# after scripts/migrate-prod-db.sh and BEFORE cutting over — the cutover
# should proceed only if this script exits 0.
#
# Checks:
#   1. Connectivity to both databases
#   2. Alembic schema version matches
#   3. Same set of tables in both
#   4. Per-table row count matches
#   5. Per-table content checksum matches (order-independent md5 of rows)
#   6. Sequence last_value matches (so the next INSERT will not collide)
#
# Usage:
#   ./scripts/verify-db-clone.sh                 # source from Doppler prod
#   ./scripts/verify-db-clone.sh <source_url>    # explicit source URL
#
# Prerequisites:
#   - The podcast-rag-db container is running
#   - Doppler CLI configured with access to the `prod` config
#   - Docker available (the postgres:17 image is used as a psql client)
#
set -euo pipefail

# Compose-project-agnostic: queries the local DB via raw `docker exec`
# against the fixed container name, so it works regardless of which
# compose stack (this repo or homelab/) owns the container.

DB_CONTAINER="podcast-rag-db"
LOCAL_DB_USER="podcast_rag"
LOCAL_DB_NAME="podcast_rag"
PG_IMAGE="postgres:17"

# ── Resolve the production (source) DATABASE_URL ──────────────────────────
SRC_URL="${1:-}"
if [[ -z "$SRC_URL" ]]; then
    echo "==> Fetching production DATABASE_URL from Doppler (config: prod)..."
    SRC_URL="$(doppler secrets get DATABASE_URL --plain --config prod 2>/dev/null || true)"
fi
if [[ -z "$SRC_URL" ]]; then
    echo "ERROR: no source DATABASE_URL (pass one as an argument or configure Doppler)." >&2
    exit 1
fi
# Use session mode (5432) for consistency with the dump.
SRC_URL="${SRC_URL//:6543/:5432}"

# ── Query helpers (-t tuples only, -A unaligned, -q quiet) ────────────────
src_q() { docker run --rm "$PG_IMAGE" psql "$SRC_URL" -tAqc "$1"; }
tgt_q() {
    docker exec -i "$DB_CONTAINER" \
        psql -U "$LOCAL_DB_USER" -d "$LOCAL_DB_NAME" -tAqc "$1"
}

FAIL=0
note_fail() { FAIL=1; echo "    ✗ MISMATCH: $1" >&2; }

# ── 1. Connectivity ───────────────────────────────────────────────────────
echo "==> Checking connectivity..."
[[ "$(src_q 'SELECT 1;')" == "1" ]] || { echo "ERROR: cannot query source." >&2; exit 1; }
[[ "$(tgt_q 'SELECT 1;')" == "1" ]] || { echo "ERROR: cannot query target." >&2; exit 1; }
echo "    Both databases reachable."

# ── 2. Alembic schema version ─────────────────────────────────────────────
echo "==> Comparing Alembic schema version..."
AV_SRC="$(src_q 'SELECT version_num FROM alembic_version;')"
AV_TGT="$(tgt_q 'SELECT version_num FROM alembic_version;')"
if [[ "$AV_SRC" == "$AV_TGT" && -n "$AV_SRC" ]]; then
    echo "    OK — both at $AV_SRC"
else
    note_fail "alembic_version: source='$AV_SRC' target='$AV_TGT'"
fi

# ── 3. Table inventory ────────────────────────────────────────────────────
echo "==> Comparing table inventory..."
LIST_SQL="SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename;"
TABLES_SRC="$(src_q "$LIST_SQL")"
TABLES_TGT="$(tgt_q "$LIST_SQL")"
if [[ "$TABLES_SRC" == "$TABLES_TGT" ]]; then
    echo "    OK — $(echo "$TABLES_TGT" | grep -c . || true) tables match"
else
    note_fail "table list differs:"
    diff <(echo "$TABLES_SRC") <(echo "$TABLES_TGT") >&2 || true
fi

# ── 4 & 5. Per-table row count + content checksum ─────────────────────────
echo "==> Comparing row counts and content checksums..."
printf '    %-34s %10s %10s  %s\n' "TABLE" "SRC ROWS" "TGT ROWS" "STATUS"
printf '    %-34s %10s %10s  %s\n' "----------------------------------" "--------" "--------" "------"

# Order-independent: hash each row, sort the hashes, hash the concatenation.
row_query() {
    echo "SELECT count(*), coalesce(md5(string_agg(rh, '' ORDER BY rh)), 'EMPTY') \
FROM (SELECT md5(x::text) AS rh FROM public.\"$1\" x) s;"
}

while IFS= read -r tbl; do
    [[ -z "$tbl" ]] && continue
    q="$(row_query "$tbl")"
    src_res="$(src_q "$q")"; tgt_res="$(tgt_q "$q")"
    src_cnt="${src_res%%|*}"; src_sum="${src_res##*|}"
    tgt_cnt="${tgt_res%%|*}"; tgt_sum="${tgt_res##*|}"
    if [[ "$src_cnt" == "$tgt_cnt" && "$src_sum" == "$tgt_sum" ]]; then
        status="OK"
    else
        status="MISMATCH"; FAIL=1
    fi
    printf '    %-34s %10s %10s  %s\n' "$tbl" "$src_cnt" "$tgt_cnt" "$status"
done <<< "$TABLES_TGT"

# ── 6. Sequences ──────────────────────────────────────────────────────────
echo "==> Comparing sequence values..."
SEQ_SQL="SELECT schemaname||'.'||sequencename||'='||coalesce(last_value::text,'NULL') \
FROM pg_sequences WHERE schemaname='public' ORDER BY 1;"
SEQ_SRC="$(src_q "$SEQ_SQL")"
SEQ_TGT="$(tgt_q "$SEQ_SQL")"
if [[ "$SEQ_SRC" == "$SEQ_TGT" ]]; then
    echo "    OK — $(echo "$SEQ_TGT" | grep -c . || true) sequences match"
else
    note_fail "sequence values differ:"
    diff <(echo "$SEQ_SRC") <(echo "$SEQ_TGT") >&2 || true
fi

# ── Verdict ───────────────────────────────────────────────────────────────
echo ""
if [[ "$FAIL" -eq 0 ]]; then
    echo "==> ✓ VERIFICATION PASSED — the clone matches production."
    exit 0
else
    echo "==> ✗ VERIFICATION FAILED — do NOT cut over. Investigate the mismatches above." >&2
    exit 1
fi
