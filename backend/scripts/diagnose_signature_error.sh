#!/bin/bash

# Diagnostic script for signature sending error

echo "🔍 Diagnosing Signature Request Error"
echo "===================================="
echo ""

cd ../docker

# 1. Check if signature microservice is running
echo "1️⃣ Checking signature microservice status..."
docker compose ps | grep signature-service
if [ $? -ne 0 ]; then
    echo "❌ Signature microservice is NOT running!"
    echo "   Run: docker compose up -d signature-service"
else
    echo "✅ Signature microservice is running"
fi

# 2. Check microservice logs
echo ""
echo "2️⃣ Recent signature service logs:"
docker compose logs signature-service --tail=20 | grep -E "(ERROR|WARNING|Failed|Exception)" || echo "No errors found in recent logs"

# 3. Test microservice connectivity
echo ""
echo "3️⃣ Testing microservice connectivity..."
docker compose exec -T api curl -s -X GET http://signature-service:8006/health -H "X-API-Key: unified-microservices-key-12345" || echo "❌ Cannot connect to signature service"

# 4. Check encryption key
echo ""
echo "4️⃣ Checking encryption key configuration..."
docker compose exec -T api python -c "
import os
key = os.getenv('SIGNATURE_ENCRYPTION_KEY')
if key:
    print('✅ SIGNATURE_ENCRYPTION_KEY is set')
else:
    print('❌ SIGNATURE_ENCRYPTION_KEY is NOT set')
    print('   Generate one with:')
    print('   python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"')
"

# 5. Check providers in database
echo ""
echo "5️⃣ Checking signature providers in database..."
docker compose exec -T db psql -U postgres -d nexus_db -c "
SELECT 
    sp.id,
    sp.provider_name,
    sp.display_name,
    sp.is_active,
    CASE WHEN sp.encrypted_credentials IS NOT NULL THEN 'Yes' ELSE 'No' END as has_credentials,
    t.name as tenant_name
FROM signature_providers sp
JOIN tenants t ON sp.tenant_id = t.id
ORDER BY sp.created_at DESC
LIMIT 5;
"

# 6. Check specific request
if [ ! -z "$1" ]; then
    echo ""
    echo "6️⃣ Checking specific signature request: $1"
    docker compose exec -T db psql -U postgres -d nexus_db -c "
    SELECT 
        sr.id,
        sr.title,
        sr.status,
        sr.external_id,
        sp.provider_name,
        sp.is_active as provider_active,
        COUNT(srs.id) as signer_count
    FROM signature_requests sr
    JOIN signature_providers sp ON sr.provider_id = sp.id
    LEFT JOIN signature_request_signers srs ON sr.id = srs.request_id
    WHERE sr.id = '$1'
    GROUP BY sr.id, sr.title, sr.status, sr.external_id, sp.provider_name, sp.is_active;
    "
fi

# 7. Test creating a simple request
echo ""
echo "7️⃣ Testing signature service endpoint directly..."
docker compose exec -T api python -c "
import httpx
import json

url = 'http://signature-service:8006/api/v1/test'
headers = {
    'X-API-Key': 'unified-microservices-key-12345',
    'Content-Type': 'application/json'
}

try:
    with httpx.Client() as client:
        response = client.get(url, headers=headers, timeout=5.0)
        print(f'Response: {response.status_code}')
        if response.status_code == 200:
            print('✅ Signature service is responding')
        else:
            print(f'❌ Unexpected response: {response.text}')
except Exception as e:
    print(f'❌ Error connecting to signature service: {e}')
"

echo ""
echo "📋 Summary:"
echo "- If signature service is not running, start it with: docker compose up -d signature-service"
echo "- If encryption key is missing, add SIGNATURE_ENCRYPTION_KEY to .env file"
echo "- If no providers exist, create one from the admin panel"
echo "- Check the full error in: docker compose logs api --tail=50"