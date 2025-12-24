# Configuration Reference

This document lists all environment variables used by Podcast RAG. You can set these via:
- A `.env` file in the project root
- A secrets manager like [Doppler](https://www.doppler.com/), 1Password, or HashiCorp Vault
- Shell environment variables
- Container orchestration (Docker Compose, Kubernetes, Cloud Run)

## Required Variables

These must be set for the application to function:

| Variable | Description |
|----------|-------------|
| `GEMINI_API_KEY` | Google Gemini API key for AI features. Get one at [Google AI Studio](https://aistudio.google.com/app/apikey) |
| `MEDIA_EMBED_BASE_DIRECTORY` | Base directory for podcast audio files (e.g., `/opt/podcasts`) |

## Gemini Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `GEMINI_API_KEY` | — | **Required.** Google Gemini API key |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Model for AI features (`gemini-2.5-flash`, `gemini-2.5-pro`) |
| `GEMINI_FILE_SEARCH_STORE_NAME` | `podcast-transcripts` | Name of the Gemini File Search store |

## Whisper Transcription

| Variable | Default | Description |
|----------|---------|-------------|
| `WHISPER_MODEL` | `medium` | Whisper model size: `tiny`, `base`, `small`, `medium`, `large-v3` |
| `WHISPER_DEVICE` | `cuda` | Device for inference: `cuda` (GPU) or `cpu` |
| `WHISPER_COMPUTE_TYPE` | `float16` | Compute precision: `float16` (GPU), `int8` (CPU), `float32` |

**Note:** The `medium` model offers the best balance of speed and accuracy. Use `large-v3` for maximum accuracy (requires ~10GB VRAM).

## Database

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite:///./podcast_rag.db` | SQLAlchemy database URL |
| `DB_POOL_SIZE` | `3` | Connection pool size (PostgreSQL only) |
| `DB_MAX_OVERFLOW` | `2` | Max overflow connections (PostgreSQL only) |
| `DB_POOL_PRE_PING` | `true` | Test connections before use |
| `DB_ECHO` | `false` | Log SQL statements (for debugging) |

**Examples:**
```bash
# SQLite (local development)
DATABASE_URL=sqlite:///./podcast_rag.db

# PostgreSQL
DATABASE_URL=postgresql://user:password@localhost:5432/podcast_rag

# Supabase (use transaction pooler port 6543)
DATABASE_URL=postgresql://postgres.[PROJECT-REF]:[PASSWORD]@aws-0-[REGION].pooler.supabase.com:6543/postgres
```

## Supabase (Optional)

For future Supabase-specific features:

| Variable | Default | Description |
|----------|---------|-------------|
| `SUPABASE_URL` | — | Supabase project URL |
| `SUPABASE_ANON_KEY` | — | Supabase anonymous key |
| `SUPABASE_SERVICE_ROLE_KEY` | — | Supabase service role key (admin access) |

## Email (Resend)

| Variable | Default | Description |
|----------|---------|-------------|
| `RESEND_API_KEY` | — | Resend API key. Leave blank to disable email. Get one at [resend.com](https://resend.com/api-keys) |
| `RESEND_FROM_EMAIL` | `podcast@podcasts.hutchison.org` | Sender email address (must be verified in Resend) |
| `RESEND_FROM_NAME` | `Podcast RAG` | Sender display name |
| `WEB_BASE_URL` | — | Base URL for email links (e.g., `https://podcasts.example.com`) |
| `EMAIL_DIGEST_SEND_HOUR` | `8` | Hour (0-23) to send daily digest emails |
| `EMAIL_DIGEST_TIMEZONE` | `America/Los_Angeles` | Timezone for digest scheduling (IANA format) |

## Authentication

### Google OAuth

| Variable | Default | Description |
|----------|---------|-------------|
| `GOOGLE_CLIENT_ID` | — | Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | — | Google OAuth client secret |
| `GOOGLE_REDIRECT_URI` | — | OAuth callback URL (e.g., `https://your-domain.com/auth/callback`) |

### JWT

| Variable | Default | Description |
|----------|---------|-------------|
| `JWT_SECRET_KEY` | — | Secret key for JWT signing (use a strong random value) |
| `JWT_EXPIRATION_DAYS` | `7` | JWT token expiration in days |

### Cookies

| Variable | Default | Description |
|----------|---------|-------------|
| `COOKIE_SECURE` | `true` | Require HTTPS for cookies (set `false` for local dev) |
| `COOKIE_DOMAIN` | — | Cookie domain (leave blank for current domain) |

## Web Server

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `8080` | Web server port |
| `ALLOWED_ORIGINS` | `*` | CORS allowed origins |
| `RATE_LIMIT` | `10/minute` | API rate limit |
| `MAX_CONVERSATION_TOKENS` | `200000` | Max tokens for conversation history |
| `STREAMING_DELAY` | `0.05` | Delay between SSE chunks (seconds) |
| `ADK_PARALLEL_TIMEOUT` | `30` | Timeout for parallel agent operations |

## Podcast Downloads

| Variable | Default | Description |
|----------|---------|-------------|
| `PODCAST_DOWNLOAD_DIRECTORY` | `$MEDIA_EMBED_BASE_DIRECTORY` | Directory for downloaded podcasts |
| `PODCAST_MAX_CONCURRENT_DOWNLOADS` | `10` | Max parallel downloads |
| `PODCAST_DOWNLOAD_RETRY_ATTEMPTS` | `3` | Retry attempts for failed downloads |
| `PODCAST_DOWNLOAD_TIMEOUT` | `300` | Download timeout in seconds |
| `PODCAST_CHUNK_SIZE` | `8192` | Download chunk size in bytes |

## Docker

When running in Docker, these variables are used for volume mounts in `docker-compose.yml`:

| Variable | Default | Description |
|----------|---------|-------------|
| `PODCAST_DIR` | `/opt/podcasts` | Host path to podcast files |
| `CACHE_DIR` | `.` | Host path for cache file storage |

Inside the container, set `MEDIA_EMBED_BASE_DIRECTORY=/data/podcasts` to match the mount point.

## Cloud Run

| Variable | Default | Description |
|----------|---------|-------------|
| `CLOUD_RUN_SERVICE` | — | Cloud Run service name |
| `CLOUD_RUN_REGION` | — | Cloud Run region (e.g., `us-west2`) |
| `CLOUD_RUN_URL` | — | Cloud Run service URL or custom domain |

## Quick Start Examples

### Local Development (SQLite)

```bash
GEMINI_API_KEY=your_key_here
MEDIA_EMBED_BASE_DIRECTORY=/path/to/podcasts
```

### Production (Supabase + Resend)

```bash
GEMINI_API_KEY=your_key_here
MEDIA_EMBED_BASE_DIRECTORY=/data/podcasts
DATABASE_URL=postgresql://postgres.[ref]:[pass]@aws-0-us-west-1.pooler.supabase.com:6543/postgres
RESEND_API_KEY=re_xxxxx
WEB_BASE_URL=https://podcasts.example.com
JWT_SECRET_KEY=your_secure_random_key
GOOGLE_CLIENT_ID=xxxxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=xxxxx
GOOGLE_REDIRECT_URI=https://podcasts.example.com/auth/callback
```

### Using Doppler

```bash
# Install Doppler CLI
brew install dopplerhq/cli/doppler

# Login and setup
doppler login
doppler setup

# Run with secrets injected
doppler run -- python -m src.cli podcast pipeline
```
