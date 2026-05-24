# VPS Deployment & Migration Runbook (bubba)

This guide moves the **database** off Supabase and the **frontend** off Google
Cloud Run, consolidating the whole stack onto **bubba** (the VPS that already
runs the transcription pipeline).

## Where the infra lives

The runtime stack on bubba is managed by the **homelab** repo, not this one.
The relevant pieces:

| Container | Owned by | Role |
|---|---|---|
| `podcast-rag-db` | `homelab/compose/docker-compose.podcast-rag.yml` | Local PostgreSQL 17 (replaces Supabase) |
| `podcast-rag` | `homelab/compose/docker-compose.podcast-rag.yml` | Transcription pipeline (image: `allenhutchison/podcast-rag:latest`) |
| `podcast-rag-web` | `homelab/compose/docker-compose.podcast-rag.yml` | FastAPI web app (image: `allenhutchison/podcast-rag-web:latest`, replaces Cloud Run) |
| `cloudflared` | `homelab/compose/docker-compose.podcast-rag.yml` | Cloudflare Tunnel — public HTTPS ingress, outbound-only |

What lives in **this** repo:

- `Dockerfile.web` — the `--proxy-headers` / `UVICORN_FORWARDED_ALLOW_IPS` change
  that makes uvicorn trust the cloudflared sidecar's `X-Forwarded-*` headers.
  Ships through Watchtower (pulls `:latest` daily).
- `scripts/migrate-prod-db.sh`, `scripts/verify-db-clone.sh`,
  `scripts/backup-db.sh` — compose-project-agnostic (raw `docker exec` against
  the fixed container name `podcast-rag-db`), so they work whether the
  container is owned by this repo's `docker-compose.yml` or by the homelab
  stack.

```text
Internet ──HTTPS──> Cloudflare edge ──tunnel──> cloudflared ─┐
                                                             │ default compose net
        ┌────────────────────────────────────────────────────┤
   podcast-rag-web:8080      podcast-rag (pipeline)      podcast-rag-db:5432
   (127.0.0.1:8080 on host)                                   │ volume: podcast_rag_db_data
                                              127.0.0.1:5432 ─┘ (host admin only)
```

Gemini File Search is unaffected — it is Google-hosted and holds no data in this
database. The database stores only podcast/episode metadata, indexing status,
users, chat history, and briefings.

---

## Prerequisites

- bubba: Docker + Docker Compose, already running the `podcast-rag` pipeline
  under the homelab stack (`~/src/homelab/nodes/bubba.sh`).
- Doppler CLI on bubba, with access to the **`prod`** config of the
  `podcast-rag` project.
- Working copy of `~/src/homelab` and `~/src/podcast-rag`.
- A Cloudflare account with the web app's domain as a zone.

## New secrets

Add these to `~/src/homelab/compose/podcast-rag.env` (also push to the
1Password environment for this service per `homelab/CLAUDE.md`):

| Key | Value |
|---|---|
| `POSTGRES_USER` | `podcast_rag` |
| `POSTGRES_DB` | `podcast_rag` |
| `POSTGRES_PASSWORD` | A freshly generated strong password for the local DB |
| `TUNNEL_TOKEN` | The token for the Cloudflare Tunnel (created in Phase 3) |

`DATABASE_URL` lives in **Doppler `prod`** and is **changed during cutover
(Phase 4)**, not now. Recommended final value:

```dotenv
DATABASE_URL=postgresql://podcast_rag:<POSTGRES_PASSWORD>@podcast-rag-db:5432/podcast_rag
```

> The host `podcast-rag-db` only resolves **inside** the compose network. For
> host-side tooling (Alembic, psql) use `127.0.0.1:5432` instead — see
> *Operations* at the end.

---

## Phase 1 — Stand up local PostgreSQL (no downtime)

1. Update `~/src/homelab/compose/podcast-rag.env` with `POSTGRES_*` (see above).
2. From `~/src/homelab`:
   ```bash
   ./nodes/bubba.sh up -d podcast-rag-db
   docker ps --filter name=podcast-rag-db   # wait for "(healthy)"
   ```

The `podcast_rag_db_data` named volume persists the data directory across
restarts.

## Phase 2 — Clone tooling & rehearsal (no downtime)

While Supabase is still live and serving production, rehearse the clone so the
tooling is proven before the real maintenance window. Run these from
`~/src/podcast-rag`:

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

## Phase 3 — Cloudflare Tunnel + web smoke test (no downtime)

Production traffic still lives on Cloud Run at this point. We bring up
cloudflared pointing at the bubba web container, smoke-test through a
**temporary** hostname, and leave the production DNS alone until Phase 4.

1. **Create the tunnel.** In the Cloudflare dashboard → Zero Trust → Networks →
   Tunnels, create a tunnel, copy its **token** into
   `~/src/homelab/compose/podcast-rag.env` as `TUNNEL_TOKEN`. Add a
   **public hostname** route:
   - Temporary test hostname (e.g. `vps-test.<your-domain>`) → service
     `http://podcast-rag-web:8080` (the compose service name, not localhost).
2. **Pull the new web image.** The `--proxy-headers` change ships with
   `allenhutchison/podcast-rag-web:latest`; Watchtower pulls it daily at 3 AM,
   or force it:
   ```bash
   ./nodes/bubba.sh pull podcast-rag-web
   ./nodes/bubba.sh up -d podcast-rag-web   # recreate with new image + tightened UVICORN_FORWARDED_ALLOW_IPS
   ```
3. **Register the OAuth redirect URI.** In Google Cloud Console, add
   `https://vps-test.<your-domain>/auth/callback` as an authorized redirect URI
   (temporary, for testing). The production URI should already be registered.
4. **Start cloudflared, still pointed at Supabase** (`DATABASE_URL` unchanged):
   ```bash
   ./nodes/bubba.sh up -d cloudflared
   ```
5. **Smoke-test the bubba app** over the test hostname before touching the
   database or production DNS:
   - `https://vps-test.<your-domain>/health` → healthy
   - Google OAuth login round-trips
   - A chat query streams a response with citations
6. Confirm `WEB_BASE_URL` in Doppler `prod` equals the **final production**
   hostname, so `WEB_BASE_URL/auth/callback` stays a registered redirect URI.

## Phase 4 — Cutover (maintenance window, a few minutes)

1. **Freeze writes to Supabase:**
   - Stop the Cloud Run app first (set min/max instances to 0 in the Cloud Run
     console — full deletion is Phase 5). This is the most important step:
     once `DATABASE_URL` flips in Doppler, any still-running Cloud Run instance
     would try to reach `podcast-rag-db:5432`, which it can't resolve.
   - Stop the bubba pipeline:
     ```bash
     ./nodes/bubba.sh stop podcast-rag
     ```
2. **Final clone** of the now-quiescent production database (from
   `~/src/podcast-rag`):
   ```bash
   ./scripts/migrate-prod-db.sh
   ```
3. **Verify — the gate for the rest of cutover:**
   ```bash
   ./scripts/verify-db-clone.sh
   ```
   Proceed **only** if it exits 0. If not, see *Rollback*.
4. **Repoint the app** — change `DATABASE_URL` in Doppler `prod` to the local
   value (see *New secrets* above).
5. **Restart everything on the local DB** (from `~/src/homelab`):
   ```bash
   ./nodes/bubba.sh up -d
   ```
   The web and pipeline containers re-read Doppler at start and now connect to
   `podcast-rag-db:5432`.
6. **Confirm schema head** against the local DB (expected: no-op, already at
   head, since `verify-db-clone.sh` already confirmed the Alembic version):
   ```bash
   docker exec podcast-rag alembic upgrade head
   ```
7. **Switch DNS** — in the Cloudflare tunnel, change the **production** hostname
   route to `http://podcast-rag-web:8080` (and remove the temp `vps-test`
   route).
8. **Smoke-test production:**
   - Site loads over HTTPS, OAuth login works, a chat query works.
   - `docker exec podcast-rag python -m src.cli podcast status`
     shows the expected episode/indexing counts.
   - `docker logs -f podcast-rag` shows the pipeline writing to the local DB.

## Phase 5 — Decommission & hardening (after stable operation)

1. **Schedule local backups** (replaces Supabase's managed backups):
   ```bash
   crontab -e
   # 15 3 * * * /home/allen/src/podcast-rag/scripts/backup-db.sh >> /home/allen/src/podcast-rag/backups/backup.log 2>&1
   ```
   The log file lives next to the dumps because `/var/log/` isn't writable
   by an unprivileged user. The bubba VM itself is snapshotted nightly by
   Proxmox Backup Service to a NAS, so the gzipped dumps automatically
   land off-box via the VM snapshot. The local pg_dump is still worth
   running: it's application-consistent (unlike a VM snapshot of a live
   data directory) and restores faster than a full VM rollback.
2. **Retire Cloud Run:** delete the Cloud Run service, the Cloud Build
   trigger, and `cloudbuild.yaml` from the repo. Remove the temporary
   `vps-test` OAuth redirect URI from Google Cloud Console.
3. **Pause/delete the Supabase project** when you no longer want the
   rollback bridge. Deleting closes it permanently — see *Rollback* below.

Status of the initial bubba cutover (2026-05-23): all three Phase 5 items
above were completed the same evening. Supabase was deleted, the
extra Doppler `staging` config was deleted (only `prod` and `dev` remain),
and the Cloud Run service + OAuth redirect URIs were removed.

---

## Rollback

Because the pipeline is stopped and Supabase is untouched after its final dump,
nothing is written to the local DB until Phase 4 step 5 — so rollback is clean
within the window. Rollback options decay as you progress through Phase 5:

- **During the maintenance window, verification fails (step 3):** abort the
  cutover. Restart the pipeline (`./nodes/bubba.sh start podcast-rag`) and
  re-enable Cloud Run. Investigate, fix `migrate-prod-db.sh`, and retry.
- **App breaks after cutover, Supabase still alive:** revert `DATABASE_URL`
  in Doppler back to the Supabase URL, `./nodes/bubba.sh up -d`, re-point
  the tunnel / re-enable Cloud Run. Any writes made to the local DB after
  step 5 are lost on this path — so run the smoke tests promptly.
- **App breaks after Supabase has been deleted:** restore from the most
  recent `scripts/backup-db.sh` dump (see *Operations*). There is no
  source-of-truth to fall back to once Supabase is gone — backups become
  the only recovery story.

---

## Operations

**Backup now:** `./scripts/backup-db.sh` (from `~/src/podcast-rag`)

**Restore from a backup:**
```bash
gunzip -c backups/podcast_rag_YYYYMMDD_HHMMSS.sql.gz \
  | docker exec -i podcast-rag-db psql -v ON_ERROR_STOP=1 -U podcast_rag -d podcast_rag
```

**Host-side Alembic / psql** — the Doppler `DATABASE_URL` uses the Docker
network host `podcast-rag-db`, which the host shell cannot resolve. Either run
inside a container (`docker exec podcast-rag alembic ...`) or override for
host runs — `alembic/env.py` prefers `ALEMBIC_DATABASE_URL`:
```bash
ALEMBIC_DATABASE_URL="postgresql://podcast_rag:$POSTGRES_PASSWORD@127.0.0.1:5432/podcast_rag" \
  alembic upgrade head
```

**Logs:** `docker logs -f podcast-rag-web` (or `podcast-rag`, `podcast-rag-db`,
`podcast-rag-cloudflared`)
