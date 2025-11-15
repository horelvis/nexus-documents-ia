#!/usr/bin/env python3
"""
Test básico de CrewAI con query simple
"""
import os
import requests
import json
import time

BASE_URL = "http://localhost:8008"
API_KEY = os.getenv("MICROSERVICES_API_KEY")

if not API_KEY:
    raise RuntimeError("MICROSERVICES_API_KEY environment variable is required for test_crewai_basic.py")

def test_simple_query():
    """Test con query simple que no debería buscar documentos"""
    print("🧪 Testing CrewAI with simple query...")
    print("=" * 60)
    
    query = "Hello, what are your capabilities?"
    
    payload = {
        "query": query,
        "tenant_id": "test-tenant",
        "user_id": "test-user"
    }
    
    headers = {
        "X-API-Key": API_KEY,
        "Content-Type": "application/json"
    }
    
    print(f"📝 Query: {query}")
    print(f"🔗 URL: {BASE_URL}/api/v1/cag/query")
    print(f"⏱️  Timeout: 30 seconds")
    print("-" * 60)
    
    try:
        start = time.time()
        print("📤 Sending request...")
        
        response = requests.post(
            f"{BASE_URL}/api/v1/cag/query",
            headers=headers,
            json=payload,
            timeout=30
        )
        
        elapsed = time.time() - start
        print(f"📥 Response received in {elapsed:.2f} seconds")
        print(f"   Status code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print("\n✅ SUCCESS!")
            print("-" * 60)
            print(f"Engine: {data.get('engine', 'unknown')}")
            print(f"Success: {data.get('success')}")
            print(f"Execution time: {data.get('execution_time', 0):.2f}s")
            
            if data.get('agents_used'):
                print(f"Agents used: {', '.join(data['agents_used'])}")
            
            if data.get('answer'):
                print(f"\n📝 Answer:")
                print("-" * 60)
                answer = str(data['answer'])
                # Print answer with line wrapping
                import textwrap
                for line in textwrap.wrap(answer, width=60):
                    print(line)
            
            if data.get('metadata'):
                print(f"\n📊 Metadata:")
                print(json.dumps(data['metadata'], indent=2))
            
            return True
            
        else:
            print(f"\n❌ ERROR: Status {response.status_code}")
            print(f"Response: {response.text[:500]}")
            return False
            
    except requests.exceptions.Timeout:
        elapsed = time.time() - start
        print(f"\n⏱️ TIMEOUT after {elapsed:.2f} seconds")
        print("The request took too long to complete.")
        return False
        
    except Exception as e:
        elapsed = time.time() - start
        print(f"\n❌ ERROR after {elapsed:.2f} seconds: {e}")
        return False

if __name__ == "__main__":
    print("🚀 CrewAI Basic Test")
    print("=" * 60)
    
    success = test_simple_query()
    
    print("\n" + "=" * 60)
    if success:
        print("✅ TEST PASSED - CrewAI is working!")
        print("🎉 No reinventar la rueda - CrewAI hace todo!")
    else:
        print("❌ TEST FAILED - Check the logs for details")
    
    exit(0 if success else 1)
