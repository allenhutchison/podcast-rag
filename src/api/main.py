from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import podcasts
from src.core.config import settings
from src.db.database import init_db

# Create FastAPI app
app = FastAPI(
    title="Podcast RAG",
    description="A podcast management and search system with RAG capabilities",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(podcasts.router)

@app.on_event("startup")
async def startup_event():
    """Initialize the database on startup."""
    init_db()

@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "Welcome to Podcast RAG API",
        "version": "1.0.0",
        "docs_url": "/docs"
    } 