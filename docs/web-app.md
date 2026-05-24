# Podcast RAG Web Application

A streaming chat interface for querying podcast transcripts with parallel web search, powered by Google ADK multi-agent architecture. Built with FastAPI and deployed as a Docker Compose service on a single VPS behind a Cloudflare Tunnel — see [`deploy-vps.md`](deploy-vps.md) for the runbook.

## Features

- **Multi-Agent Architecture**: Parallel podcast and web search using Google ADK
- **Streaming Responses**: Word-by-word streaming using Server-Sent Events (SSE)
- **Dual Source Citations**: Citations from both podcast transcripts and web sources
- **Fast & Lightweight**: ~500MB Docker image (multi-stage build, no ffmpeg).
- **Mobile Responsive**: Clean, minimal design with Tailwind CSS
- **Rate Limiting**: Built-in request rate limiting

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         User's Browser                               │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  Chat Interface (index.html + Tailwind CSS)                   │  │
│  │  • Message bubbles (user/assistant)                           │  │
│  │  • Citation cards (podcast + web sources)                     │  │
│  │  • Real-time status updates during search                     │  │
│  └─────────────────────────────┬─────────────────────────────────┘  │
│                                │ SSE                                 │
└────────────────────────────────┼────────────────────────────────────┘
                                 │
┌────────────────────────────────▼────────────────────────────────────┐
│                    FastAPI Application (app.py)                      │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  /api/chat endpoint                                           │  │
│  │  • Session management (X-Session-ID header)                   │  │
│  │  • Rate limiting (slowapi)                                    │  │
│  │  • SSE streaming response                                     │  │
│  └─────────────────────────────┬─────────────────────────────────┘  │
└────────────────────────────────┼────────────────────────────────────┘
                                 │
┌────────────────────────────────▼────────────────────────────────────┐
│                Google ADK Multi-Agent Orchestrator                   │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │  SequentialAgent (PodcastRAGOrchestrator)                      │ │
│  │                                                                 │ │
│  │  ┌──────────────────────────────────────────────────────────┐  │ │
│  │  │  ParallelAgent (runs simultaneously)                     │  │ │
│  │  │  ┌─────────────────────┐  ┌─────────────────────────┐   │  │ │
│  │  │  │  PodcastSearchAgent │  │  WebSearchAgent         │   │  │ │
│  │  │  │  • File Search tool │  │  • google_search tool   │   │  │ │
│  │  │  │  • Metadata cache   │  │  • url_context tool     │   │  │ │
│  │  │  └─────────────────────┘  └─────────────────────────┘   │  │ │
│  │  └──────────────────────────────────────────────────────────┘  │ │
│  │                              │                                  │ │
│  │                              ▼                                  │ │
│  │  ┌──────────────────────────────────────────────────────────┐  │ │
│  │  │  SynthesizerAgent                                        │  │ │
│  │  │  • Combines results with equal weight                    │  │ │
│  │  │  • Generates unified response                            │  │ │
│  │  └──────────────────────────────────────────────────────────┘  │ │
│  └────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
                    │                              │
                    ▼                              ▼
        ┌───────────────────┐          ┌───────────────────┐
        │ Gemini File Search│          │   Google Search   │
        │ (podcast archive) │          │   (web results)   │
        └───────────────────┘          └───────────────────┘
```

## Project Structure

```
src/
├── web/
│   ├── app.py              # FastAPI application with ADK integration
│   ├── models.py           # Pydantic request/response models
│   └── static/
│       ├── index.html      # Chat UI (Tailwind CSS)
│       └── chat.js         # Frontend logic (vanilla JS)
│
├── agents/                  # Google ADK agents
│   ├── __init__.py         # Agent exports
│   ├── orchestrator.py     # SequentialAgent + ParallelAgent setup
│   ├── podcast_search.py   # PodcastSearchAgent with File Search tool
│   ├── web_search.py       # WebSearchAgent with google_search
│   └── synthesizer.py      # SynthesizerAgent for combining results

Dockerfile.web              # Optimized Docker image for web app
```

## Agent Details

### PodcastSearchAgent
- Uses custom `search_podcasts` tool wrapping Gemini File Search
- Searches indexed podcast transcripts
- Enriches citations with metadata from local cache
- Returns structured results with episode info

### WebSearchAgent
- Uses Google's built-in `google_search` tool
- Uses `url_context` tool to fetch full page content when needed
- Provides current information and external perspectives
- Requires Gemini 2.0+ models

### SynthesizerAgent
- Receives results from both search agents via `{podcast_results}` and `{web_results}`
- Weighs both sources equally based on relevance
- Creates unified response with HTML formatting
- Notes agreements/conflicts between sources

## Local Development

### Prerequisites

- Python 3.11+
- uv (recommended) or pip
- Google ADK requires Gemini 2.0+ models

### Setup

1. **Install dependencies:**
   ```bash
   # Using uv (recommended)
   uv sync

   # Or using pip
   pip install -e .
   ```

2. **Set environment variables:**
   ```bash
   export GEMINI_API_KEY="your-api-key"
   export GEMINI_MODEL="gemini-2.0-flash"  # Must be 2.0+ for ADK tools
   export GEMINI_FILE_SEARCH_STORE_NAME="podcast-transcripts"
   ```

3. **Run the development server:**
   ```bash
   uv run poe serve
   ```

4. **Open in browser:**
   ```
   http://localhost:8080
   ```

### Testing the API Directly

```bash
# Health check
curl http://localhost:8080/health

# Chat query (SSE streaming)
curl -N -X POST http://localhost:8080/api/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "What topics are discussed?"}'
```

## Docker Development

### Build and Run Locally

```bash
# Build the web image
docker build -f Dockerfile.web -t podcast-rag-web .

# Run locally
docker run -p 8080:8080 \
  -e GEMINI_API_KEY="your-api-key" \
  -e GEMINI_MODEL="gemini-2.0-flash" \
  -e GEMINI_FILE_SEARCH_STORE_NAME="podcast-transcripts" \
  podcast-rag-web

# Open browser to http://localhost:8080
```

### Image Details

- **Base:** python:3.12-slim
- **Size:** ~500MB
- **Optimizations:**
  - No ffmpeg (not needed for queries)
  - Baked-in metadata cache for instant lookups
  - Multi-stage build
  - Non-root user

## Deployment

The web app runs as a Docker Compose service alongside the encoding pipeline and a local PostgreSQL database, behind a Cloudflare Tunnel. See [`deploy-vps.md`](deploy-vps.md) for the standup + cutover runbook. CI is in `.github/workflows/docker-release.yml`: every `v*` tag builds and pushes `allenhutchison/podcast-rag-web:latest` to Docker Hub, which Watchtower picks up on the VPS.

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GEMINI_API_KEY` | Yes | - | Gemini API key |
| `GEMINI_MODEL` | No | `gemini-2.0-flash` | Gemini model (must be 2.0+ for web search) |
| `GEMINI_FILE_SEARCH_STORE_NAME` | No | `podcast-transcripts` | File Search store name |
| `PORT` | No | `8080` | Server port (set by Docker Compose) |
| `WEB_ALLOWED_ORIGINS` | No | `*` | CORS allowed origins (comma-separated) |
| `WEB_STREAMING_DELAY` | No | `0.05` | Delay between streamed tokens (seconds) |
| `WEB_RATE_LIMIT` | No | `10/minute` | Rate limit for API endpoints |
| `ADK_PARALLEL_TIMEOUT` | No | `60` | Timeout for agent execution (seconds) |

### Container Resource Limits

Set in `homelab/compose/docker-compose.podcast-rag.yml` (`deploy.resources`):
- **Memory:** 1G limit, 256M reservation.
- **CPU:** 1.0 limit, 0.25 reservation.
- The container is always-on (no scale-to-zero); adjust limits to match VPS capacity.

## API Reference

### `POST /api/chat`

Query the podcast archive with parallel web search and streaming response.

**Request Body:**
```json
{
  "query": "What topics are discussed?",
  "history": []
}
```

**Headers:**
- `X-Session-ID` (optional): Session identifier for conversation continuity

**Response:** Server-Sent Events (SSE) stream

**Event Types:**

1. `status` - Agent execution status
   ```json
   {"phase": "searching", "message": "Searching podcasts and web..."}
   {"agent": "podcast", "status": "started"}
   {"agent": "web", "status": "complete"}
   ```

2. `token` - Word-by-word streaming
   ```json
   {"token": "The "}
   ```

3. `citations` - Combined citations from both sources
   ```json
   {
     "citations": [
       {
         "ref_id": "P1",
         "source_type": "podcast",
         "title": "episode_transcript.txt",
         "metadata": {
           "podcast": "Tech Talk",
           "episode": "AI Advances",
           "release_date": "2024-01-15"
         }
       },
       {
         "ref_id": "W1",
         "source_type": "web",
         "title": "AI News Article",
         "metadata": {
           "url": "https://example.com/article"
         }
       }
     ]
   }
   ```

4. `done` - Completion signal
   ```json
   {"status": "complete"}
   ```

5. `error` - Error occurred
   ```json
   {"error": "Error message"}
   ```

### `GET /health`

Health check endpoint (used by Docker healthcheck + cloudflared origin probe).

**Response:**
```json
{
  "status": "healthy",
  "service": "podcast-rag"
}
```

## Citation Display

Citations show source type and metadata:

**Podcast citations:**
```
[P1] Tech Talk - AI Advances (2024-01-15)
```

**Web citations:**
```
[W1] AI News Article - https://example.com/article
```

## Cost Estimates

Compute is now self-hosted on the VPS (sunk cost). Marginal per-query
spend is dominated by the Gemini API calls from the three agents.

### Gemini API Pricing

- **gemini-2.0-flash:** See current pricing at cloud.google.com
- File Search and web search are included in model pricing

**Estimated per query:** ~$0.001-0.005 depending on response length

## Troubleshooting

### "google.adk module not found"
Install the Google ADK package:
```bash
pip install google-adk
```

### "Model does not support google_search tool"
Web search requires Gemini 2.0+ models. Update your `GEMINI_MODEL`:
```bash
export GEMINI_MODEL="gemini-2.0-flash"
```

### "File Search store not found"
Ensure the store name matches your environment variable:
```bash
python scripts/file_search_utils.py --action list
```

### Slow responses
- ADK orchestration adds latency for parallel search
- Consider increasing the container memory limit in `homelab/compose/docker-compose.podcast-rag.yml`
- Check `ADK_PARALLEL_TIMEOUT` setting

### No web citations appearing
- Web search requires Gemini 2.0+ models
- Check logs for google_search tool errors

## Security Considerations

- **Rate limiting:** Built-in with slowapi
- **Session validation:** Session IDs are validated and sanitized
- **Query sanitization:** Prompt injection mitigation in podcast search
- **API key security:** Fetched at runtime from Doppler (`prod` config), never committed to git
- **CORS:** Configurable via `WEB_ALLOWED_ORIGINS`

## Resources

- **Main README:** [README.md](../README.md)
- **Docker Deployment:** [docker.md](docker.md)
- **VPS Deployment & Cutover Runbook:** [deploy-vps.md](deploy-vps.md)
- **Google ADK Docs:** https://ai.google.dev/adk
- **FastAPI Docs:** https://fastapi.tiangolo.com

## License

Apache 2.0 - See [LICENSE](../LICENSE)

## Support

For issues and questions:
- GitHub Issues: https://github.com/allenhutchison/podcast-rag/issues
