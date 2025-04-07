#!/bin/bash

# Exit on error
set -e

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
  echo "Error: Docker is not running. Please start Docker and try again."
  exit 1
fi

# Check Docker authentication
echo "Checking Docker authentication..."
if ! docker pull hello-world > /dev/null 2>&1; then
  echo "Error: Docker authentication failed. Please run 'docker login' and try again."
  exit 1
fi

# Check if .env file exists
if [ ! -f ../.env ]; then
  echo "Warning: .env file not found. Using default configuration."
  echo "Create a .env file based on .env.example if you need to customize settings."
fi

# Build and start the containers
echo "Building and starting containers..."
docker compose -p podcast-rag -f docker-compose.yml up --build -d

# Show container status
echo "Container status:"
docker compose -p podcast-rag ps

echo ""
echo "Frontend is available at: http://localhost:3000"
echo "Backend API is available at: http://localhost:8000"
echo ""
echo "To view logs: docker compose -p podcast-rag logs -f"
echo "To stop containers: docker compose -p podcast-rag down" 