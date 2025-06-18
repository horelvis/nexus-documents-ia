#!/usr/bin/env python3
"""Quick test script to verify document shares API endpoints"""

import requests
import json
from datetime import datetime, timedelta

# Base URL - adjust as needed
BASE_URL = "http://localhost:8000/api/v1"

# Test token - replace with a valid token
AUTH_TOKEN = "your-auth-token-here"

headers = {
    "Authorization": f"Bearer {AUTH_TOKEN}",
    "Content-Type": "application/json"
}

def test_list_shares():
    """Test listing document shares"""
    print("\n1. Testing GET /document-shares")
    response = requests.get(f"{BASE_URL}/document-shares", headers=headers)
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"Response: {json.dumps(data, indent=2)}")
    else:
        print(f"Error: {response.text}")

def test_create_share():
    """Test creating a document share"""
    print("\n2. Testing POST /document-shares")
    
    # Replace with a valid document ID
    share_data = {
        "document_id": "123e4567-e89b-12d3-a456-426614174000",
        "share_type": "view",
        "expires_at": (datetime.now() + timedelta(days=7)).isoformat(),
        "recipient_email": "test@example.com",
        "recipient_name": "Test User",
        "permissions": {
            "view": True,
            "download": False,
            "edit": False
        }
    }
    
    response = requests.post(f"{BASE_URL}/document-shares", headers=headers, json=share_data)
    print(f"Status: {response.status_code}")
    if response.status_code in [200, 201]:
        data = response.json()
        print(f"Response: {json.dumps(data, indent=2)}")
        return data.get("id")
    else:
        print(f"Error: {response.text}")
        return None

def test_get_statistics():
    """Test getting share statistics"""
    print("\n3. Testing GET /document-shares/statistics")
    response = requests.get(f"{BASE_URL}/document-shares/statistics", headers=headers)
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"Response: {json.dumps(data, indent=2)}")
    else:
        print(f"Error: {response.text}")

if __name__ == "__main__":
    print("Testing Document Shares API")
    print("=" * 50)
    print(f"Base URL: {BASE_URL}")
    print("\nNote: Make sure to:")
    print("1. Replace AUTH_TOKEN with a valid authentication token")
    print("2. Replace document_id in test_create_share() with a valid document ID")
    print("3. Ensure the backend is running")
    print("\nPress Enter to continue...")
    input()
    
    test_list_shares()
    test_get_statistics()
    # share_id = test_create_share()