# VPS Deployment & Migration Runbook

This guide moves the **database** off Supabase and the **frontend** off Google
Cloud Run, consolidating the whole stack onto the VPS that already runs the
transcription pipeline.

After the migration the VPS runs four containers as one Docker Compose stack:

| Container | Role |
|---|---|
| `podcast-rag-db` | Local PostgreSQL 17 (replaces Supabase) |
| `podcast-rag` | Transcription pipeline (unchanged) |
| `podcast-rag-web` | FastAPI web app (replaces Cloud Run) |
| `cloudflared` | Cloudflare Tunnel — public HTTPS ingress, outbound-only |

```text
Internet ──HTTPS──> Cloudflare edge ──tunnel──> cloudflared ─┐
                                                             │ podcast-rag-net
        ┌────────────────────────────────────────────────────┤ (internal)
   podcast-rag-web:8080      podcast-rag (pipeline)      podcast-rag-db:5432
                                                              │ volume: pgdata
                                            127.0.0.1:5432 ──>┘ (host admin only)
```

Gemini File Search is unaffected — it is Google-hosted and holds no data in this
database. The database stores only podcast/episode metadata, indexing status,
users, chat history, and briefings.

---

## Prerequisites

- VPS with Docker + Docker Compose, already running the `podcast-rag` pipeline.
- Doppler CLI on the VPS, with access to the **`prod`** config.
- A Cloudflare account with the web app's domain as a zone.
- `ffmpeg` (already present for the pipeline).

## New Doppler secrets (config: `prod`)

Add these to the `prod` config before starting:

| Secret | Value |
|---|---|
| `LOCAL_DB_PASSWORD` | A freshly generated strong password for the local DB |
| `CLOUDFLARE_TUNNEL_TOKEN` | The token for the Cloudflare Tunnel (created in Phase 3) |
| `DOPPLER_TOKEN` | A Doppler **service token** for `prod` — lets the web/pipeline containers self-inject secrets via `docker-entrypoint.sh` |

`DATABASE_URL` is **changed** during cutover (Phase 4), not now. Recommended
final value, using a Doppler secret reference so the password has one source of
truth:

```dotenv
DATABASE_URL = postgresql://podcast_rag:${LOCAL_DB_PASSWORD}@podcast-rag-db:5432/podcast_rag
```

> The host `podcast-rag-db` only resolves **inside** `podcast-rag-net`. For
> host-side tooling (Alembic, psql) use `127.0.0.1:5432` instead — see the note
> at the end.

**Always run compose under Doppler** so `LOCAL_DB_PASSWORD` and
`CLOUDFLARE_TUNNEL_TOKEN` are available for variable substitution:

```bash
doppler run -- docker compose up -d <service>
```

---

## Phase 1 — Stand up local PostgreSQL (no downtime)

1. Add `LOCAL_DB_PASSWORD` to Doppler `prod`.
2. Start the database container:
   ```bash
   doppler run -- docker compose up -d podcast-rag-db
   docker compose ps          # wait for "(healthy)"
   ```

The `pgdata` named volume persists the data directory across restarts.

## Phase 2 — Clone tooling & rehearsal (no downtime)

While Supabase is still live and serving production, rehearse the clone so the
tooling is proven before the real maintenance window.

1. Clone production into the local DB:
   ```bash
   ./scripts/migrate-prod-db.sh
   ```
   It dumps Supabase (rewriting the pooler port `6543`→`5432` for `pg_dump`),
   drops/recreates the local `podcast_rag` database, and restores with
   `ON_ERROR_STOP=1 --single-transaction` — any error aborts loudly.
2. Verify the clone:
   ```bash
   ./scripts/verify-db-clone.sh
   ```
   It compares Alembic version, table inventory, per-table row counts, an
   order-independent per-table content checksum, and sequence values. It must
   print **`VERIFICATION PASSED`** and exit 0.
3. If verification fails, fix the cause and repeat. Do not continue until a
   clean run succeeds. (The rehearsal clone is overwritten by the real one in
   Phase 4, so a stale rehearsal is harmless.)

## Phase 3 — Web app on the VPS + Cloudflare Tunnel (no downtime)

1. **Create the tunnel.** In the Cloudflare dashboard → Zero Trust → Networks →
   Tunnels, create a tunnel, copy its **token** into Doppler `prod` as
   `CLOUDFLARE_TUNNEL_TOKEN`. Add a **public hostname** route:
   - Temporary test hostname (e.g. `vps-test.<your-domain>`) → service
     `http://podcast-rag-web:8080`.
2. **Build/pull the web image.** Push a git tag to build via
   `.github/workflows/docker-release.yml`, or build on the VPS:
   ```bash
   docker compose build podcast-rag-web   # or: docker compose pull
   ```
   The image's uvicorn command now includes `--proxy-headers
   --forwarded-allow-ips=*` so OAuth, Secure cookies, and rate limiting work
   correctly behind the tunnel.
3. **Register the OAuth redirect URI.** In Google Cloud Console, add
   `https://vps-test.<your-domain>/auth/callback` as an authorized redirect URI
   (temporary, for testing). The production URI should already be registered.
4. **Start web + tunnel, still pointed at Supabase** (`DATABASE_URL` unchanged):
   ```bash
   doppler run -- docker compose up -d podcast-rag-web cloudflared
   ```
5. **Smoke-test the VPS app** over the test hostname before touching the
   database or production DNS:
   - `https://vps-test.<your-domain>/health` → healthy
   - Google OAuth login round-trips
   - A chat query streams a response with citations
6. Confirm `WEB_BASE_URL` in Doppler `prod` equals the **final production**
   hostname, so `WEB_BASE_URL/auth/callback` stays a registered redirect URI.

## Phase 4 — Cutover (maintenance window, a few minutes)

1. **Freeze writes to Supabase:**
   ```bash
   docker compose stop podcast-rag          # stop the pipeline
   ```
   Stop public traffic to the Cloud Run app (set min/max instances to 0 in the
   Cloud Run console — full deletion is Phase 5).
2. **Final clone** of the now-quiescent production database:
   ```bash
   ./scripts/migrate-prod-db.sh
   ```
3. **Verify — the gate for the rest of cutover:**
   ```bash
   ./scripts/verify-db-clone.sh
   ```
   Proceed **only** if it exits 0. If not, see *Rollback*.
4. **Repoint the app** — change `DATABASE_URL` in Doppler `prod` to the local
   value (see *New Doppler secrets* above).
5. **Restart everything on the local DB:**
   ```bash
   doppler run -- docker compose up -d
   ```
6. **Confirm schema head** against the local DB — the container now resolves
   `DATABASE_URL` to the local database (expected: no-op, already at head, since
   `verify-db-clone.sh` already confirmed the Alembic version):
   ```bash
   docker compose run --rm podcast-rag alembic upgrade head
   ```
7. **Switch DNS** — in the Cloudflare tunnel, change the **production** hostname
   route to `http://podcast-rag-web:8080` (and remove the temp `vps-test`
   route).
8. **Smoke-test production:**
   - Site loads over HTTPS, OAuth login works, a chat query works.
   - `docker compose run --rm podcast-rag python -m src.cli podcast status`
     shows the expected episode/indexing counts.
   - `docker compose logs -f podcast-rag` shows the pipeline writing to the
     local DB.

## Phase 5 — Decommission & hardening (after stable operation)

1. **Schedule local backups** (replaces Supabase's managed backups):
   ```bash
   crontab -e
   # 15 3 * * * cd /opt/podcast-rag && /opt/podcast-rag/scripts/backup-db.sh >> /var/log/podcast-rag-backup.log 2>&1
   ```
   Copy `./backups/` off-box (rsync/object storage) — the VPS is now a single
   point of failure for the DB.
2. **Retire Cloud Run:** delete the Cloud Run service and its Cloud Build
   trigger, then delete `cloudbuild.yaml` from the repo. Remove the temporary
   `vps-test` OAuth redirect URI from Google Cloud Console.
3. **Update docs:** `AGENTS.md`, `docs/deploy-quick-start.md`, and
   `docs/WEB_ARCHITECTURE.md` still describe the Cloud Run deployment.
4. **After ~2 weeks** of stable operation, delete or pause the Supabase project.

---

## Rollback

Because the pipeline is stopped and Supabase is untouched after its final dump,
nothing is written to the local DB until Phase 4 step 6 — so rollback is clean
within the window:

- **Verification fails (step 3):** abort the cutover. Restart the pipeline
  (`docker compose start podcast-rag`) and re-enable Cloud Run. Investigate, fix
  `migrate-prod-db.sh`, and retry.
- **App breaks after cutover:** revert `DATABASE_URL` in Doppler back to the
  Supabase URL, `doppler run -- docker compose up -d`, and re-point the tunnel /
  re-enable Cloud Run. Any writes made to the local DB after step 6 are lost on
  this path — so run the smoke tests promptly.

Supabase is kept as a **point-in-time standby for ~2 weeks**. It is a snapshot,
not a live replica: a rollback after the window loses post-cutover data.

---

## Operations

**Backup now:** `./scripts/backup-db.sh`

**Restore from a backup:**
```bash
gunzip -c backups/podcast_rag_YYYYMMDD_HHMMSS.sql.gz \
  | docker compose exec -T podcast-rag-db psql -v ON_ERROR_STOP=1 -U podcast_rag -d podcast_rag
```

**Host-side Alembic / psql** — the Doppler `DATABASE_URL` uses the Docker
network host `podcast-rag-db`, which the host shell cannot resolve. Either run
inside a container (`docker compose run --rm podcast-rag alembic ...`) or
override for host runs — `alembic/env.py` prefers `ALEMBIC_DATABASE_URL`:
```bash
ALEMBIC_DATABASE_URL="postgresql://podcast_rag:$LOCAL_DB_PASSWORD@127.0.0.1:5432/podcast_rag" \
  alembic upgrade head
```

**Logs:** `docker compose logs -f podcast-rag-web cloudflared podcast-rag-db`
