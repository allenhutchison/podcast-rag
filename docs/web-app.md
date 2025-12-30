# Podcast RAG Web Application

A streaming chat interface for querying podcast transcripts with parallel web search, powered by Google ADK multi-agent architecture. Built with FastAPI and designed for deployment on Google Cloud Run.

## Features

- **Multi-Agent Architecture**: Parallel podcast and web search using Google ADK
- **Streaming Responses**: Word-by-word streaming using Server-Sent Events (SSE)
- **Dual Source Citations**: Citations from both podcast transcripts and web sources
- **Fast & Lightweight**: ~500MB Docker image, optimized for Cloud Run
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
cloudbuild.yaml             # Google Cloud Build configuration
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

## Google Cloud Run Deployment

### Prerequisites

1. **Google Cloud Project** with billing enabled
2. **APIs enabled:**
   - Cloud Run API
   - Cloud Build API
   - Container Registry API
3. **gcloud CLI** installed and authenticated

### Manual Deployment

```bash
# Set variables
export PROJECT_ID="your-project-id"
export SERVICE_NAME="podcast-rag-web"
export REGION="us-central1"

# Build and push image
docker build -f Dockerfile.web -t gcr.io/$PROJECT_ID/$SERVICE_NAME .
docker push gcr.io/$PROJECT_ID/$SERVICE_NAME

# Deploy to Cloud Run
gcloud run deploy $SERVICE_NAME \
  --image gcr.io/$PROJECT_ID/$SERVICE_NAME \
  --platform managed \
  --region $REGION \
  --allow-unauthenticated \
  --memory 512Mi \
  --cpu 1 \
  --max-instances 10 \
  --set-env-vars GEMINI_API_KEY="your-key",GEMINI_MODEL="gemini-2.0-flash",GEMINI_FILE_SEARCH_STORE_NAME="podcast-transcripts"

# Get the service URL
gcloud run services describe $SERVICE_NAME --region $REGION --format 'value(status.url)'
```

### Automated Deployment with Cloud Build

See [deploy-quick-start.md](deploy-quick-start.md) for Cloud Build trigger setup.

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GEMINI_API_KEY` | Yes | - | Gemini API key |
| `GEMINI_MODEL` | No | `gemini-2.0-flash` | Gemini model (must be 2.0+ for web search) |
| `GEMINI_FILE_SEARCH_STORE_NAME` | No | `podcast-transcripts` | File Search store name |
| `PORT` | No | `8080` | Server port (auto-set in Cloud Run) |
| `WEB_ALLOWED_ORIGINS` | No | `*` | CORS allowed origins (comma-separated) |
| `WEB_STREAMING_DELAY` | No | `0.05` | Delay between streamed tokens (seconds) |
| `WEB_RATE_LIMIT` | No | `10/minute` | Rate limit for API endpoints |
| `ADK_PARALLEL_TIMEOUT` | No | `60` | Timeout for agent execution (seconds) |

### Cloud Run Settings

- **Memory:** 512Mi (adjust if needed)
- **CPU:** 1 vCPU
- **Max instances:** 10 (adjust based on expected traffic)
- **Min instances:** 0 (save costs with scale-to-zero)
- **Timeout:** 300s (for long queries)

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

Health check endpoint for Cloud Run.

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

### Cloud Run Pricing (as of 2024)

- **Free tier:** 2 million requests/month
- **Beyond free tier:** ~$0.40 per million requests
- **Memory:** $0.0000025/GB-second
- **CPU:** $0.00002400/vCPU-second

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
- Consider increasing Cloud Run memory (512Mi -> 1Gi)
- Check `ADK_PARALLEL_TIMEOUT` setting

### No web citations appearing
- Web search requires Gemini 2.0+ models
- Check logs for google_search tool errors

## Security Considerations

- **Rate limiting:** Built-in with slowapi
- **Session validation:** Session IDs are validated and sanitized
- **Query sanitization:** Prompt injection mitigation in podcast search
- **API key security:** Store in Secret Manager, never commit to git
- **CORS:** Configurable via `WEB_ALLOWED_ORIGINS`

## Resources

- **Main README:** [README.md](../README.md)
- **Docker Deployment:** [docker.md](docker.md)
- **Cloud Run Docs:** https://cloud.google.com/run/docs
- **Google ADK Docs:** https://ai.google.dev/adk
- **FastAPI Docs:** https://fastapi.tiangolo.com

## License

Apache 2.0 - See [LICENSE](../LICENSE)

## Support

For issues and questions:
- GitHub Issues: https://github.com/allenhutchison/podcast-rag/issues
