# Web Application Architecture

## System Overview

The web application uses Google ADK (Agent Development Kit) to orchestrate parallel search across podcast transcripts and the web, then synthesize results into a unified response.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              User's Browser                                  │
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │  Chat Interface (index.html + Tailwind CSS)                           │  │
│  │  • Message bubbles (user/assistant)                                   │  │
│  │  • Citation cards (podcast + web sources)                             │  │
│  │  • Real-time status updates during agent execution                    │  │
│  └─────────────────────────────────┬─────────────────────────────────────┘  │
│                                    │                                         │
│  ┌─────────────────────────────────▼─────────────────────────────────────┐  │
│  │  Frontend Logic (chat.js - Vanilla JS)                                │  │
│  │  • Form handling                                                      │  │
│  │  • EventSource for SSE streaming                                      │  │
│  │  • Status event rendering                                             │  │
│  │  • Citation card rendering (P1, W1 prefixes)                          │  │
│  └─────────────────────────────────┬─────────────────────────────────────┘  │
└─────────────────────────────────────┼────────────────────────────────────────┘
                                      │
                                      │ HTTP/SSE (Port 8080)
                                      │
┌─────────────────────────────────────▼────────────────────────────────────────┐
│                  Google Cloud Run (Serverless Container)                      │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │  FastAPI Application (src/web/app.py)                                  │ │
│  │                                                                        │ │
│  │  ┌─────────────────────┐    ┌──────────────────────────────────────┐  │ │
│  │  │  /api/chat          │    │  /health                             │  │ │
│  │  │  (POST, SSE stream) │    │  (health check)                      │  │ │
│  │  └──────────┬──────────┘    └──────────────────────────────────────┘  │ │
│  │             │                                                          │ │
│  │  ┌──────────▼──────────────────────────────────────────────────────┐  │ │
│  │  │  Session Management                                             │  │ │
│  │  │  • X-Session-ID header validation                               │  │ │
│  │  │  • Per-session ADK Runner instances                             │  │ │
│  │  │  • Thread-safe citation storage                                 │  │ │
│  │  └──────────┬──────────────────────────────────────────────────────┘  │ │
│  │             │                                                          │ │
│  │  ┌──────────▼──────────────────────────────────────────────────────┐  │ │
│  │  │  Rate Limiter (slowapi)                                         │  │ │
│  │  │  • Configurable via WEB_RATE_LIMIT                              │  │ │
│  │  └──────────┬──────────────────────────────────────────────────────┘  │ │
│  └─────────────┼──────────────────────────────────────────────────────────┘ │
│                │                                                             │
│  ┌─────────────▼──────────────────────────────────────────────────────────┐ │
│  │  Google ADK Runner                                                     │ │
│  │  • InMemorySessionService for conversation state                       │ │
│  │  • Async event streaming via run_async()                               │ │
│  └─────────────┬──────────────────────────────────────────────────────────┘ │
│                │                                                             │
│  ┌─────────────▼──────────────────────────────────────────────────────────┐ │
│  │  SequentialAgent (PodcastRAGOrchestrator)                              │ │
│  │                                                                        │ │
│  │  ┌──────────────────────────────────────────────────────────────────┐ │ │
│  │  │  Step 1: ParallelAgent (ParallelSearchAgent)                     │ │ │
│  │  │  Runs both search agents SIMULTANEOUSLY                          │ │ │
│  │  │                                                                  │ │ │
│  │  │  ┌───────────────────────┐    ┌───────────────────────────────┐ │ │ │
│  │  │  │  PodcastSearchAgent   │    │  WebSearchAgent               │ │ │ │
│  │  │  │                       │    │                               │ │ │ │
│  │  │  │  Tools:               │    │  Tools:                       │ │ │ │
│  │  │  │  • search_podcasts    │    │  • google_search (built-in)   │ │ │ │
│  │  │  │    (custom tool)      │    │  • url_context (built-in)     │ │ │ │
│  │  │  │                       │    │                               │ │ │ │
│  │  │  │  Output:              │    │  Output:                      │ │ │ │
│  │  │  │  {podcast_results}    │    │  {web_results}                │ │ │ │
│  │  │  └───────────────────────┘    └───────────────────────────────┘ │ │ │
│  │  └──────────────────────────────────────────────────────────────────┘ │ │
│  │                                    │                                   │ │
│  │                                    ▼                                   │ │
│  │  ┌──────────────────────────────────────────────────────────────────┐ │ │
│  │  │  Step 2: SynthesizerAgent                                        │ │ │
│  │  │                                                                  │ │ │
│  │  │  Inputs:                                                         │ │ │
│  │  │  • {podcast_results} from PodcastSearchAgent                     │ │ │
│  │  │  • {web_results} from WebSearchAgent                             │ │ │
│  │  │                                                                  │ │ │
│  │  │  Behavior:                                                       │ │ │
│  │  │  • Weighs both sources equally                                   │ │ │
│  │  │  • Notes agreements/conflicts                                    │ │ │
│  │  │  • Outputs HTML-formatted response                               │ │ │
│  │  │                                                                  │ │ │
│  │  │  Output: {final_response}                                        │ │ │
│  │  └──────────────────────────────────────────────────────────────────┘ │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │  Environment Variables                                                 │ │
│  │  • GEMINI_API_KEY (from Secret Manager)                               │ │
│  │  • GEMINI_MODEL (gemini-2.0-flash required for web search)            │ │
│  │  • GEMINI_FILE_SEARCH_STORE_NAME (podcast-transcripts)                │ │
│  │  • ADK_PARALLEL_TIMEOUT (60s default)                                 │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────┘
                    │                                      │
                    │                                      │
                    ▼                                      ▼
┌───────────────────────────────────┐    ┌────────────────────────────────────┐
│       Gemini File Search          │    │         Google Search API          │
│                                   │    │                                    │
│  • Podcast transcript store       │    │  • google_search tool              │
│  • Automatic chunking/embedding   │    │  • url_context for page content    │
│  • Returns grounding_chunks       │    │  • Returns grounding_metadata      │
│  • Citation metadata from cache   │    │  • Web source URLs                 │
└───────────────────────────────────┘    └────────────────────────────────────┘
```

## Request Flow

### 1. User Submits Query

```
User types: "What's happening with AI regulation?"
         ↓
chat.js captures form submission
         ↓
Creates EventSource connection:
POST /api/chat
Body: {"query": "What's happening with AI regulation?"}
Header: X-Session-ID: <uuid>
```

### 2. Session Setup

```
FastAPI app.py receives request
         ↓
Validates session ID (sanitizes, generates if needed)
         ↓
Gets or creates session-specific ADK Runner
  • Each session gets its own orchestrator instance
  • Ensures thread-safe citation storage
         ↓
Gets or creates ADK InMemorySessionService
```

### 3. ADK Orchestration

```
Runner.run_async() starts event stream
         ↓
SequentialAgent (PodcastRAGOrchestrator) begins
         ↓
┌─────────────────────────────────────────────────────┐
│  ParallelAgent executes BOTH agents simultaneously  │
│                                                     │
│  PodcastSearchAgent          WebSearchAgent         │
│  │                           │                      │
│  ├─ Calls search_podcasts    ├─ Calls google_search │
│  │  tool with query          │  with query          │
│  │                           │                      │
│  ├─ File Search returns      ├─ Returns web results │
│  │  grounding_chunks         │  with URLs           │
│  │                           │                      │
│  ├─ Enriches with metadata   ├─ May call url_context│
│  │  from local cache         │  for deeper content  │
│  │                           │                      │
│  └─ Stores citations in      └─ Returns with        │
│     session storage             grounding_metadata  │
└─────────────────────────────────────────────────────┘
         ↓
SynthesizerAgent receives:
  • {podcast_results}: Text + citations from podcast search
  • {web_results}: Text + grounding from web search
         ↓
Synthesizer creates unified HTML response
  • Equal weight to both sources
  • Notes agreements/conflicts
  • No inline citation brackets
```

### 4. Event Streaming

```
generate_streaming_response() yields SSE events:

Phase: Searching
Event 1: {"event": "status", "data": {"phase": "searching"}}
Event 2: {"event": "status", "data": {"agent": "podcast", "status": "started"}}
Event 3: {"event": "status", "data": {"agent": "web", "status": "started"}}
Event 4: {"event": "status", "data": {"tool": "search_podcasts", "message": "..."}}
Event 5: {"event": "status", "data": {"tool": "google_search", "message": "..."}}
Event 6: {"event": "status", "data": {"agent": "podcast", "status": "complete"}}
Event 7: {"event": "status", "data": {"agent": "web", "status": "complete"}}

Phase: Responding
Event 8: {"event": "status", "data": {"phase": "responding"}}
Event 9: {"event": "token", "data": {"token": "Based "}}
Event 10: {"event": "token", "data": {"token": "on "}}
...
Event N: {"event": "citations", "data": {"citations": [...]}}
Event N+1: {"event": "done", "data": {"status": "complete"}}
```

### 5. Citation Assembly

```
After orchestration completes:
         ↓
Get podcast citations from session storage
  (set by search_podcasts tool during execution)
         ↓
Get web citations from grounding_metadata
  (extracted from google_search responses)
         ↓
_combine_citations() merges both:
  [
    {ref_id: "P1", source_type: "podcast", metadata: {...}},
    {ref_id: "P2", source_type: "podcast", metadata: {...}},
    {ref_id: "W1", source_type: "web", metadata: {url: "..."}},
    {ref_id: "W2", source_type: "web", metadata: {url: "..."}}
  ]
```

### 6. Frontend Rendering

```
chat.js EventSource handlers:

on 'status' event:
  - Update status indicator
  - Show "Searching podcasts...", "Searching web...", etc.

on 'token' event:
  - Append word to message bubble
  - Auto-scroll to bottom

on 'citations' event:
  - Render podcast citations:
    [P1] Podcast Name - Episode Title (YYYY-MM-DD)
  - Render web citations:
    [W1] Page Title - https://example.com

on 'done' event:
  - Close EventSource
  - Re-enable input
  - Focus on query input
```

## Key Components

### Agent Architecture (src/agents/)

| File | Agent | Purpose |
|------|-------|---------|
| `orchestrator.py` | PodcastRAGOrchestrator | SequentialAgent coordinating search → synthesis |
| `podcast_search.py` | PodcastSearchAgent | LlmAgent with custom File Search tool |
| `web_search.py` | WebSearchAgent | LlmAgent with google_search + url_context |
| `synthesizer.py` | SynthesizerAgent | LlmAgent that combines results |

### Citation Storage

Podcast citations use thread-safe session-based storage:

```python
# In podcast_search.py
_session_citations: Dict[str, Dict] = {}  # {session_id: {citations: [...], timestamp: ...}}
_citations_lock = threading.Lock()

# Tool stores citations during execution
set_podcast_citations(session_id, citations)

# Web app retrieves after orchestration
get_podcast_citations(session_id)
```

### Frontend Stack
- **HTML/CSS**: Tailwind CSS via CDN (no build step)
- **JavaScript**: Vanilla JS with EventSource API
- **No frameworks**: Simple, lightweight, fast loading

### Backend Stack
- **FastAPI**: Modern async Python web framework
- **uvicorn**: ASGI server with auto-reload
- **Google ADK**: Multi-agent orchestration
- **slowapi**: Rate limiting
- **Pydantic**: Request/response validation

### Infrastructure
- **Docker**: Multi-stage build, ~500MB image
- **Cloud Run**: Serverless, auto-scaling, scale-to-zero
- **Cloud Build**: CI/CD from GitHub
- **Secret Manager**: API key storage

### External Services
- **Gemini API**: LLM for all agents
- **Gemini File Search**: Podcast transcript vector store
- **Google Search**: Real-time web search (via built-in tool)

## Performance Characteristics

### Cold Start
- **Time**: 3-8 seconds
- **Factors**: Python interpreter, ADK initialization, dependency loading
- **Optimization**: Minimal dependencies, multi-stage build

### Query Latency
- **SSE Connection**: ~100ms
- **Parallel Search Phase**: 2-10 seconds (both run simultaneously)
- **Synthesis Phase**: 1-3 seconds
- **Streaming**: 50ms per word (configurable)
- **Total**: 5-15 seconds depending on query complexity

### Resource Usage
- **Memory**: 300-500MB (512MB allocated)
- **CPU**: Burst during agent execution, idle otherwise
- **Network**: ~10-100KB per query

### Scalability
- **Concurrent requests**: Limited by Gemini API quotas
- **Max instances**: 10 (configurable)
- **Scale to zero**: Yes (saves costs)
- **Stateless**: Session storage is per-instance (not shared)

## Security Considerations

### Query Sanitization
- Control characters stripped
- Length limited to 2000 characters
- Prompt injection patterns logged (defense-in-depth)

### Session Validation
- Max 64 characters
- Alphanumeric, hyphens, underscores only
- Invalid sessions get new UUID

### Rate Limiting
- Configurable via `WEB_RATE_LIMIT`
- Default: 10 requests/minute per IP

### API Key Protection
- **Storage**: Google Secret Manager
- **Access**: Cloud Run service account only
- **Never exposed**: Not sent to frontend

### HTTPS
- **Cloud Run**: Automatic HTTPS with managed certificates
- **Custom domain**: Supported with SSL

## Monitoring & Observability

### Logging
- **Application logs**: Python logging to stdout
- **Cloud Logging**: Automatic collection
- **Log levels**: INFO, WARNING, ERROR
- **Debug logging**: Agent events, citation counts, tool calls

### Metrics (Cloud Run)
- **Request count**: Automatic
- **Request latency**: P50, P95, P99
- **CPU/Memory usage**: Real-time graphs
- **Error rate**: 5xx responses

### Health Checks
- **Endpoint**: `/health`
- **Interval**: 30 seconds
- **Timeout**: 10 seconds
- **Action**: Restart unhealthy instances

## Cost Breakdown

### Per Query (Estimate)
```
Gemini API (parallel agents):
  PodcastSearchAgent:     ~$0.001
  WebSearchAgent:         ~$0.001
  SynthesizerAgent:       ~$0.001
  Subtotal:               ~$0.003

Cloud Run:
  Request:                $0.0000004
  CPU-seconds (5s):       $0.00012
  Memory GB-sec (2.5GB):  $0.0000063
  Subtotal:               ~$0.0001

Total per query:          ~$0.003 (0.3 cents)
```

### Monthly (1,000 queries)
```
Gemini API:  $3.00
Cloud Run:   $0.10
Total:       ~$3.10/month
```

## Future Enhancements

### Near-term
- [ ] Conversation history integration with ADK sessions
- [ ] Response caching for repeated queries
- [ ] Custom 404/500 error pages

### Medium-term
- [ ] Additional search agents (academic papers, news)
- [ ] User feedback collection
- [ ] Query analytics dashboard

### Long-term
- [ ] Multi-language support
- [ ] Voice input/output
- [ ] Admin dashboard for agent tuning

---

**Architecture Status**: Production Ready
**Last Updated**: 2025-12-10
