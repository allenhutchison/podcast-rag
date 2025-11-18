# Podcast RAG Web Application

A streaming chat interface for querying podcast transcripts using Gemini File Search. Built with FastAPI and designed for deployment on Google Cloud Run.

## Features

- 🎯 **Streaming Responses**: Word-by-word streaming like ChatGPT using Server-Sent Events (SSE)
- 📚 **Source Citations**: Every answer includes citations with podcast metadata
- 🚀 **Fast & Lightweight**: ~200MB Docker image, 2-5 second cold starts
- 🔓 **No Authentication**: Public demo application
- 📱 **Mobile Responsive**: Clean, minimal design with Tailwind CSS
- ☁️ **Cloud Run Ready**: Optimized for serverless deployment

## Architecture

```
┌─────────────┐
│   Browser   │
│  (Tailwind) │
└──────┬──────┘
       │ SSE
       ↓
┌─────────────┐      ┌──────────────┐      ┌─────────────────┐
│   FastAPI   │─────→│  RAG Manager │─────→│ Gemini File     │
│  (uvicorn)  │      │  (src/rag.py)│      │ Search API      │
└─────────────┘      └──────────────┘      └─────────────────┘
       │
       ↓
┌─────────────┐
│ Local Cache │
│  (.json)    │
└─────────────┘
```

## Project Structure

```
src/web/
├── app.py              # FastAPI application with SSE streaming
├── models.py           # Pydantic request/response models
└── static/
    ├── index.html      # Chat UI (Tailwind CSS)
    └── chat.js         # Frontend logic (vanilla JS)

Dockerfile.web          # Optimized Docker image for web app
cloudbuild.yaml         # Google Cloud Build configuration
```

## Local Development

### Prerequisites

- Python 3.11+
- uv (recommended) or pip
- `.file_search_cache.json` (metadata cache)

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
   export GEMINI_MODEL="gemini-2.5-flash"
   export GEMINI_FILE_SEARCH_STORE_NAME="podcast-transcripts"
   ```

3. **Run the development server:**
   ```bash
   uvicorn src.web.app:app --reload --port 8080
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
curl -N http://localhost:8080/api/chat?query="What%20topics%20are%20discussed?"
```

## Docker Development

### Build and Run Locally

```bash
# Build the web image
docker build -f Dockerfile.web -t podcast-rag-web .

# Run locally
docker run -p 8080:8080 \
  -e GEMINI_API_KEY="your-api-key" \
  -e GEMINI_MODEL="gemini-2.5-flash" \
  -e GEMINI_FILE_SEARCH_STORE_NAME="podcast-transcripts" \
  podcast-rag-web

# Open browser to http://localhost:8080
```

### Image Details

- **Base:** python:3.12-slim
- **Size:** ~200MB (vs ~800MB for full Dockerfile)
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
  --set-env-vars GEMINI_API_KEY="your-key",GEMINI_MODEL="gemini-2.5-flash",GEMINI_FILE_SEARCH_STORE_NAME="podcast-transcripts"

# Get the service URL
gcloud run services describe $SERVICE_NAME --region $REGION --format 'value(status.url)'
```

### Automated Deployment with Cloud Build

1. **Connect GitHub repository to Cloud Build:**
   ```bash
   # Link your repository in Cloud Console
   # https://console.cloud.google.com/cloud-build/triggers
   ```

2. **Create a Cloud Build trigger:**
   - Source: Your GitHub repository
   - Branch: `^main$`
   - Configuration: `cloudbuild.yaml`
   - Substitution variables:
     - `_GEMINI_API_KEY`: (from Secret Manager)
     - `_GEMINI_MODEL`: `gemini-2.5-flash`
     - `_REGION`: `us-central1`
     - `_SERVICE_NAME`: `podcast-rag-web`
     - `_FILE_SEARCH_STORE_NAME`: `podcast-transcripts`

3. **Store API key in Secret Manager:**
   ```bash
   # Create secret
   echo -n "your-gemini-api-key" | gcloud secrets create gemini-api-key --data-file=-

   # Grant Cloud Build access
   gcloud secrets add-iam-policy-binding gemini-api-key \
     --member=serviceAccount:PROJECT_NUMBER@cloudbuild.gserviceaccount.com \
     --role=roles/secretmanager.secretAccessor

   # Update cloudbuild.yaml to use secret:
   # availableSecrets:
   #   secretManager:
   #   - versionName: projects/PROJECT_ID/secrets/gemini-api-key/versions/latest
   #     env: _GEMINI_API_KEY
   ```

4. **Push to trigger deployment:**
   ```bash
   git push origin main
   # Cloud Build will automatically build and deploy
   ```

### Updating the Cache

The `.file_search_cache.json` is baked into the Docker image. To update:

1. Rebuild cache locally:
   ```bash
   python scripts/rebuild_cache.py
   ```

2. Rebuild and redeploy Docker image:
   ```bash
   docker build -f Dockerfile.web -t gcr.io/$PROJECT_ID/$SERVICE_NAME .
   docker push gcr.io/$PROJECT_ID/$SERVICE_NAME
   gcloud run deploy $SERVICE_NAME --image gcr.io/$PROJECT_ID/$SERVICE_NAME
   ```

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GEMINI_API_KEY` | Yes | - | Gemini API key for File Search |
| `GEMINI_MODEL` | No | `gemini-2.5-flash` | Gemini model to use |
| `GEMINI_FILE_SEARCH_STORE_NAME` | No | `podcast-transcripts` | File Search store name |
| `PORT` | No | `8080` | Server port (auto-set in Cloud Run) |

### Cloud Run Settings

- **Memory:** 512Mi (adjust if needed for larger caches)
- **CPU:** 1 vCPU
- **Max instances:** 10 (adjust based on expected traffic)
- **Min instances:** 0 (save costs with scale-to-zero)
- **Timeout:** 300s (for long queries)

## API Reference

### `POST /api/chat`

Query the podcast archive with streaming response.

**Query Parameter:**
- `query` (string): User's question

**Response:** Server-Sent Events (SSE) stream

**Event Types:**
1. `token` - Word-by-word streaming
   ```json
   {"token": "The "}
   ```

2. `citations` - Final citations
   ```json
   {
     "citations": [
       {
         "index": 1,
         "metadata": {
           "podcast": "Tech Talk",
           "episode": "AI Advances",
           "release_date": "2024-01-15"
         }
       }
     ]
   }
   ```

3. `done` - Completion signal
   ```json
   {"status": "complete"}
   ```

4. `error` - Error occurred
   ```json
   {"error": "Error message"}
   ```

### `GET /health`

Health check endpoint for Cloud Run.

**Response:**
```json
{
  "status": "healthy",
  "service": "podcast-rag-web"
}
```

## Citation Display

Citations show only metadata (no text excerpts):

```
[1] Tech Talk - AI Advances (2024-01-15)
[2] Data Science Weekly - ML Fundamentals (2024-02-20)
```

Displayed fields:
- **Podcast name**
- **Episode title**
- **Release date** (YYYY-MM-DD)

## Cost Estimates

### Cloud Run Pricing (as of 2024)

- **Free tier:** 2 million requests/month
- **Beyond free tier:** ~$0.40 per million requests
- **Memory:** $0.0000025/GB-second
- **CPU:** $0.00002400/vCPU-second

**Estimated monthly cost for light demo usage:**
- < 10,000 requests/month: **$0** (free tier)
- 100,000 requests/month: **~$2-5**

### Gemini API Pricing

- **File Search:** Bundled with generate_content calls
- **gemini-2.5-flash:** $0.075 per 1M input tokens, $0.30 per 1M output tokens

**Estimated per query:**
- Input: ~5,000 tokens (context) = $0.000375
- Output: ~500 tokens (answer) = $0.00015
- **Total per query:** ~$0.0005 (0.05 cents)

## Troubleshooting

### "Module 'src.web' not found"
Make sure you've installed the project:
```bash
uv sync
# or
pip install -e .
```

### "File Search store not found"
Ensure the store name matches your environment variable:
```bash
python scripts/file_search_utils.py --action list
```

### "Health check failed"
Check logs:
```bash
# Local
curl http://localhost:8080/health

# Cloud Run
gcloud run services logs read $SERVICE_NAME --region $REGION
```

### Slow responses
- Check Gemini API latency
- Consider increasing Cloud Run memory (512Mi → 1Gi)
- Verify cache file is included in image

## Development Notes

### Adding New Features

1. **Backend changes:** Edit `src/web/app.py`
2. **API models:** Update `src/web/models.py`
3. **Frontend UI:** Modify `src/web/static/index.html`
4. **Frontend logic:** Update `src/web/static/chat.js`

### Testing Locally

```bash
# Install dev dependencies
uv sync --dev

# Run tests
pytest tests/

# Type checking (if using mypy)
mypy src/web/
```

## Security Considerations

- **No authentication:** This is a public demo app
- **Rate limiting:** Consider adding rate limits for production
- **API key security:** Store in Secret Manager, never commit to git
- **CORS:** Currently allows all origins, restrict for production
- **Input validation:** Query length limited to 1000 characters

## Resources

- **Main README:** [README.md](README.md)
- **Gemini File Search Guide:** [GEMINI.md](GEMINI.md)
- **Cloud Run Docs:** https://cloud.google.com/run/docs
- **FastAPI Docs:** https://fastapi.tiangolo.com
- **Tailwind CSS:** https://tailwindcss.com

## License

Apache 2.0 - See [LICENSE](LICENSE)

## Support

For issues and questions:
- GitHub Issues: https://github.com/allenhutchison/podcast-rag/issues
- Email: allen@hutchison.org
