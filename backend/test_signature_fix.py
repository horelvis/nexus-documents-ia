#!/usr/bin/env python3
"""
Test script to verify the signature request endpoint fix
"""
import asyncio
import httpx
import json
import os
from datetime import datetime

# API Configuration
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
API_TOKEN = os.getenv("API_TOKEN", "")  # Set your auth token

async def test_signature_requests():
    """Test the signature requests endpoint"""
    
    headers = {
        "Authorization": f"Bearer {API_TOKEN}",
        "Content-Type": "application/json"
    }
    
    async with httpx.AsyncClient() as client:
        print(f"\n🔍 Testing GET /api/v1/signatures/requests at {datetime.now()}")
        
        try:
            # Test get all signature requests
            response = await client.get(
                f"{API_BASE_URL}/api/v1/signatures/requests",
                headers=headers
            )
            
            print(f"Status Code: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"✅ Success! Retrieved {len(data)} signature requests")
                
                # Show first request if any
                if data:
                    request = data[0]
                    print(f"\nFirst request:")
                    print(f"  - ID: {request.get('id')}")
                    print(f"  - Title: {request.get('title')}")
                    print(f"  - Status: {request.get('status')}")
                    print(f"  - Signers: {len(request.get('signers', []))}")
                    
                    # Test get single request
                    request_id = request.get('id')
                    if request_id:
                        print(f"\n🔍 Testing GET /api/v1/signatures/requests/{request_id}")
                        single_response = await client.get(
                            f"{API_BASE_URL}/api/v1/signatures/requests/{request_id}",
                            headers=headers
                        )
                        
                        if single_response.status_code == 200:
                            print(f"✅ Successfully retrieved single request")
                        else:
                            print(f"❌ Error: {single_response.status_code} - {single_response.text}")
                            
            elif response.status_code == 401:
                print("❌ Authentication error - please set API_TOKEN environment variable")
                print("   Example: API_TOKEN=your_token python test_signature_fix.py")
            else:
                print(f"❌ Error: {response.text}")
                
        except Exception as e:
            print(f"❌ Exception: {type(e).__name__}: {str(e)}")
            if "greenlet.error" in str(e) or "MissingGreenlet" in str(e):
                print("\n⚠️  This error indicates the lazy loading issue is still present!")
                print("   The relationship is being accessed outside the async context.")
            raise

async def main():
    """Main test function"""
    print("=" * 60)
    print("Signature Request Endpoint Test")
    print("=" * 60)
    
    if not API_TOKEN:
        print("\n⚠️  Warning: No API_TOKEN set. The request may fail with 401.")
        print("   Set it with: export API_TOKEN=your_token_here")
    
    await test_signature_requests()
    
    print("\n" + "=" * 60)
    print("Test completed!")

if __name__ == "__main__":
    asyncio.run(main())