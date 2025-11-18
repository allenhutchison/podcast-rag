#!/bin/bash
# Quick start script for running the web application locally

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 Starting Podcast RAG Web Application${NC}"
echo ""

# Check if .env file exists
if [ ! -f .env ]; then
    echo -e "${RED}Error: .env file not found${NC}"
    echo "Please create a .env file with required variables:"
    echo "  GEMINI_API_KEY=your-api-key"
    echo "  GEMINI_MODEL=gemini-2.5-flash"
    echo "  GEMINI_FILE_SEARCH_STORE_NAME=podcast-transcripts"
    exit 1
fi

# Load environment variables
export $(cat .env | grep -v '^#' | xargs)

# Check if cache file exists
if [ ! -f .file_search_cache.json ]; then
    echo -e "${RED}Warning: .file_search_cache.json not found${NC}"
    echo "Metadata lookups will be slower. Run: python scripts/rebuild_cache.py"
    echo ""
fi

# Check if virtual environment is active
if [ -z "$VIRTUAL_ENV" ]; then
    echo -e "${BLUE}Activating virtual environment...${NC}"
    if [ -d ".venv" ]; then
        source .venv/bin/activate
    else
        echo -e "${RED}Error: Virtual environment not found${NC}"
        echo "Run: python -m venv .venv && source .venv/bin/activate && pip install -e ."
        exit 1
    fi
fi

echo -e "${GREEN}✓ Environment loaded${NC}"
echo ""

# Start the server
echo -e "${BLUE}Starting uvicorn server on http://localhost:8080${NC}"
echo -e "${BLUE}Press Ctrl+C to stop${NC}"
echo ""

uvicorn src.web.app:app --reload --host 0.0.0.0 --port 8080
