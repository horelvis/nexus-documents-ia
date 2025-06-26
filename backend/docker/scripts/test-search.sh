#!/bin/bash

# Script to test document search functionality

echo "🔍 Testing Document Search Functionality"
echo ""

# Set API base URL
API_URL="http://192.168.1.42:8000"
API_KEY="unified-microservices-key-12345"

# 1. Test basic search (title/description only)
echo "1️⃣ Testing basic search (title/description)..."
echo "Searching for 'sanchez' in /api/v1/documents endpoint:"
curl -s -X GET "$API_URL/api/v1/documents?search=sanchez&page=1&per_page=10" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" | jq '.items[].title' 2>/dev/null || echo "No results or error"

echo ""
echo "2️⃣ Testing content search (full document content)..."
echo "Searching for 'sanchez' in /api/v1/search endpoint:"
curl -s -X GET "$API_URL/api/v1/search?query=sanchez" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" | jq '.[].document.filename' 2>/dev/null || echo "No results or error"

echo ""
echo "📝 Summary:"
echo "- Basic search (/documents?search=): Only searches in title and description fields"
echo "- Content search (/search?query=): Searches in actual document content using embeddings"
echo ""
echo "💡 The frontend now has a 'Deep Search' toggle to switch between these modes"