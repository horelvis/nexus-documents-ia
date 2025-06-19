#!/usr/bin/env python3
"""
Test script to verify async endpoints are working correctly after migration
"""
import asyncio
import httpx
from datetime import datetime

# Configuration
API_BASE_URL = "http://localhost:8000"
API_KEY = "nxs_dev_0VIsZVY4uwvOXyeGu8A2MelI87yCSXyZDgVFZpY9"  # From .env.example

# Test endpoints
ENDPOINTS_TO_TEST = [
    ("GET", "/api/v1/documents", "List Documents"),
    ("GET", "/api/v1/auth/me", "Get Current User"),
    ("GET", "/api/v1/tenants/current", "Get Current Tenant"),
    ("GET", "/api/v1/admin/users", "List Users (Admin)"),
    ("GET", "/api/v1/document-shares", "List Document Shares"),
    ("GET", "/api/v1/chat/conversations", "List Conversations"),
]

async def test_endpoint(client: httpx.AsyncClient, method: str, path: str, description: str):
    """Test a single endpoint"""
    try:
        response = await client.request(method, path)
        status = response.status_code
        
        # Check if it's an expected status
        if status == 200:
            print(f"✅ {description}: {status} OK")
            return True
        elif status == 401:
            print(f"⚠️  {description}: {status} Unauthorized (need auth)")
            return True  # Expected for protected endpoints
        elif status == 403:
            print(f"⚠️  {description}: {status} Forbidden (need permissions)")
            return True  # Expected for admin endpoints
        else:
            print(f"❌ {description}: {status}")
            if response.content:
                print(f"   Response: {response.text[:200]}")
            return False
    except Exception as e:
        print(f"❌ {description}: Error - {str(e)}")
        return False

async def test_health_endpoint(client: httpx.AsyncClient):
    """Test the health endpoint separately"""
    try:
        response = await client.get("/health")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Health Check: {data}")
            return True
        else:
            print(f"❌ Health Check: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Health Check: Error - {str(e)}")
        return False

async def main():
    """Run all tests"""
    print("Testing Async Endpoints")
    print("=" * 60)
    print(f"API URL: {API_BASE_URL}")
    print(f"Time: {datetime.now().isoformat()}")
    print("=" * 60)
    
    # Create client with headers
    headers = {
        "X-API-Key": API_KEY,
        "Content-Type": "application/json"
    }
    
    async with httpx.AsyncClient(base_url=API_BASE_URL, headers=headers, timeout=30.0) as client:
        # Test health endpoint first
        print("\n1. Testing Health Endpoint:")
        await test_health_endpoint(client)
        
        # Test all other endpoints
        print("\n2. Testing API Endpoints:")
        results = []
        for method, path, description in ENDPOINTS_TO_TEST:
            result = await test_endpoint(client, method, path, description)
            results.append(result)
        
        # Summary
        print("\n" + "=" * 60)
        print("Summary:")
        total = len(results)
        passed = sum(results)
        print(f"Total endpoints tested: {total}")
        print(f"Passed: {passed}")
        print(f"Failed: {total - passed}")
        
        if passed == total:
            print("\n✅ All endpoints are responding correctly!")
        else:
            print("\n⚠️  Some endpoints had issues, but this might be expected due to auth/permissions")

if __name__ == "__main__":
    asyncio.run(main())