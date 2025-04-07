# Docker Setup for Podcast RAG

This directory contains the Docker configuration for running the Podcast RAG application.

## Prerequisites

- Docker and Docker Compose installed on your system
- Docker Hub account (for pulling base images)

## Authentication

Before running the application, make sure you're authenticated with Docker Hub:

```bash
docker login
```

This will prompt you for your Docker Hub username and password.

## Quick Start

Run the following command from the project root:

```bash
./docker/run.sh
```

This will:
1. Check Docker authentication
2. Check for the presence of a `.env` file (optional)
3. Build and start both the frontend and backend containers
4. Display the container status and access URLs

## Manual Setup

If you prefer to run the commands manually:

```bash
# Build and start the containers
docker compose -f docker/docker-compose.yml up --build -d

# View logs
docker compose -f docker/docker-compose.yml logs -f

# Stop the containers
docker compose -f docker/docker-compose.yml down
```

## Accessing the Application

- Frontend: http://localhost:3000
- Backend API: http://localhost:8000

## Container Structure

- **backend**: Python FastAPI application
- **frontend**: React application

## Volumes

The following volumes are mounted:
- `../data:/app/data`: Persistent storage for podcasts, transcripts, and database

## Environment Variables

The following environment variables are used:
- `DATABASE_URL`: SQLite database path (default: sqlite:///./data/podcast_rag.db)
- `CHROMA_PERSIST_DIRECTORY`: Directory for ChromaDB persistence (default: /app/data/chroma)
- `REACT_APP_API_URL`: Backend API URL for the frontend (default: http://backend:8000)

## Customization

To customize the application settings, create a `.env` file in the project root based on `.env.example`. This is optional as the application will use default values if no `.env` file is present. 