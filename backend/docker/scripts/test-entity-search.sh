#!/bin/bash

# Script to test entity search functionality

echo "🔍 Testing Entity Search Functionality"
echo ""

# Configuration
API_URL="http://192.168.1.42:8000"
DOCUMENT_ID="83dac046-4612-46c6-a2eb-cdf10e834868"

# Function to test entity search
test_entity_search() {
    local query="$1"
    echo "Testing search for: '$query'"
    
    # Make the API call
    response=$(curl -s -X GET "$API_URL/api/v1/search/entities?q=$query&document_id=$DOCUMENT_ID&limit=10" \
        -H "Authorization: Bearer YOUR_TOKEN_HERE" \
        -H "Content-Type: application/json")
    
    # Check if response is empty
    if [ -z "$response" ]; then
        echo "❌ No response from server"
        return
    fi
    
    # Parse with jq
    entities=$(echo "$response" | jq -r '.entities' 2>/dev/null)
    total=$(echo "$response" | jq -r '.total' 2>/dev/null)
    
    if [ "$entities" = "null" ] || [ "$entities" = "[]" ]; then
        echo "⚠️  No entities found"
    else
        echo "✅ Found $total entities:"
        echo "$response" | jq '.entities[] | {name, email, type}' 2>/dev/null
    fi
    echo ""
}

# Test different search queries
echo "1️⃣ Testing partial name search:"
test_entity_search "jo"

echo "2️⃣ Testing email search:"
test_entity_search "@"

echo "3️⃣ Testing full name search:"
test_entity_search "john"

echo "4️⃣ Testing without document_id:"
curl -s -X GET "$API_URL/api/v1/search/entities?q=jo&limit=10" \
    -H "Authorization: Bearer YOUR_TOKEN_HERE" \
    -H "Content-Type: application/json" | jq '.'

echo ""
echo "📊 Debugging Tips:"
echo "1. Check backend logs for the SQL query being executed"
echo "2. Verify users exist in the same tenant with matching names"
echo "3. Check if users have full_name field populated"
echo "4. Ensure the authorization token is valid"
echo ""
echo "🔧 To check users in database:"
echo "docker compose exec db psql -U postgres -d nexus_db -c \"SELECT id, full_name, email, tenant_id FROM users WHERE full_name ILIKE '%jo%' OR email ILIKE '%jo%';\""