from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

from api.routes import podcasts
from db.database import init_db

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Podcast Manager API",
    description="API for managing podcasts and episodes",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# Include routers
app.include_router(podcasts.router)

# Initialize database
@app.on_event("startup")
async def startup_event():
    logger.info("Initializing database...")
    init_db()
    logger.info("Database initialized")

# Root endpoint
@app.get("/")
async def root():
    return {"message": "Welcome to the Podcast Manager API"} 