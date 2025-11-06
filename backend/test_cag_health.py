#!/usr/bin/env python3
"""
Test simple de salud del servicio CAG
"""
import requests
import time

BASE_URL = "http://localhost:8008"

def test_health():
    """Test health endpoint"""
    print("🔍 Testing CAG Service Health...")
    print(f"   URL: {BASE_URL}/health")
    
    try:
        start = time.time()
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        elapsed = time.time() - start
        
        print(f"   Response time: {elapsed:.2f}s")
        print(f"   Status code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"   Status: {data.get('status')}")
            print(f"   Engine: {data.get('engine', 'unknown')}")
            print(f"   Service: {data.get('service', 'unknown')}")
            
            if 'checks' in data:
                print("\n   Component checks:")
                for check, status in data['checks'].items():
                    print(f"   - {check}: {'✅' if status else '❌'}")
            
            print("\n✅ Service is healthy!")
            return True
        else:
            print(f"\n❌ Service returned status {response.status_code}")
            print(f"   Response: {response.text[:200]}")
            return False
            
    except requests.exceptions.Timeout:
        print(f"\n⏱️ Request timed out after 5 seconds")
        return False
    except requests.exceptions.ConnectionError:
        print(f"\n❌ Could not connect to service at {BASE_URL}")
        print("   Is the service running?")
        return False
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        return False

if __name__ == "__main__":
    success = test_health()
    exit(0 if success else 1)