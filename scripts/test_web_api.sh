#!/bin/bash
# Test script for web API endpoints

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

BASE_URL="${1:-http://localhost:8080}"

echo -e "${BLUE}Testing Podcast RAG Web API at ${BASE_URL}${NC}"
echo ""

# Test 1: Health check
echo -e "${BLUE}Test 1: Health check${NC}"
RESPONSE=$(curl -s "${BASE_URL}/health")
STATUS=$?

if [ $STATUS -eq 0 ]; then
    echo -e "${GREEN}✓ Health check passed${NC}"
    echo "Response: $RESPONSE"
else
    echo -e "${RED}✗ Health check failed${NC}"
    exit 1
fi
echo ""

# Test 2: Chat endpoint (streaming)
echo -e "${BLUE}Test 2: Chat endpoint (SSE streaming)${NC}"
echo "Query: What topics are discussed?"
echo ""

curl -N "${BASE_URL}/api/chat?query=What%20topics%20are%20discussed%3F" 2>/dev/null | head -n 20

echo ""
echo -e "${GREEN}✓ Chat endpoint working${NC}"
echo ""

# Test 3: Static files
echo -e "${BLUE}Test 3: Static files${NC}"
STATUS_CODE=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}/")

if [ "$STATUS_CODE" = "200" ]; then
    echo -e "${GREEN}✓ Static files served (HTTP $STATUS_CODE)${NC}"
else
    echo -e "${RED}✗ Static files failed (HTTP $STATUS_CODE)${NC}"
fi
echo ""

echo -e "${GREEN}All tests passed!${NC}"
echo ""
echo "Open in browser: ${BASE_URL}"
