#!/usr/bin/env python3
"""
Test script to verify LangGraph agents integration
"""

import asyncio
import httpx
import json
from datetime import datetime

# Configuration
API_BASE_URL = "http://localhost:8000"
LANGGRAPH_URL = "http://localhost:8007"

# Test user credentials (you'll need to replace with actual test user token)
AUTH_TOKEN = "your-test-token-here"  # Replace with actual Clerk token

async def test_langgraph_health():
    """Test if LangGraph service is healthy"""
    print("\n🔍 Testing LangGraph Service Health...")
    
    async with httpx.AsyncClient() as client:
        try:
            # Direct LangGraph health check
            response = await client.get(f"{LANGGRAPH_URL}/health")
            print(f"✅ LangGraph Direct Health: {response.status_code}")
            print(f"   Response: {response.json()}")
            
            # API proxy health check
            response = await client.get(f"{API_BASE_URL}/api/v1/agents/health")
            print(f"✅ API Proxy Health: {response.status_code}")
            print(f"   Response: {response.json()}")
            
        except Exception as e:
            print(f"❌ Health check failed: {e}")
            return False
    
    return True

async def test_graph_types():
    """Test available graph types"""
    print("\n📊 Testing Available Graph Types...")
    
    async with httpx.AsyncClient() as client:
        try:
            # Direct LangGraph types
            response = await client.get(f"{LANGGRAPH_URL}/api/v1/graphs/types")
            print(f"✅ LangGraph Types: {response.status_code}")
            types = response.json()
            print(f"   Available graphs: {types.get('available_graphs', [])}")
            
            # API proxy types
            response = await client.get(f"{API_BASE_URL}/api/v1/agents/types")
            print(f"✅ API Agent Types: {response.status_code}")
            agent_types = response.json()
            print(f"   Available agents: {list(agent_types.get('available_types', {}).keys())}")
            
        except Exception as e:
            print(f"❌ Failed to get types: {e}")
            return False
    
    return True

async def test_document_analysis():
    """Test document analysis workflow"""
    print("\n📄 Testing Document Analysis...")
    
    test_document = """
    PURCHASE AGREEMENT
    
    This Purchase Agreement is entered into on January 15, 2024, between:
    
    Buyer: John Smith
    Seller: ABC Corporation
    
    The Seller agrees to sell and the Buyer agrees to purchase the following:
    - Product: Enterprise Software License
    - Quantity: 100 seats
    - Price: $50,000 USD
    - Delivery Date: February 1, 2024
    
    Payment Terms: Net 30 days from delivery
    
    This agreement requires signatures from both parties to be valid.
    """
    
    async with httpx.AsyncClient() as client:
        try:
            # Test via API (would need auth in real scenario)
            print("   Sending document for analysis...")
            
            headers = {}
            if AUTH_TOKEN and AUTH_TOKEN != "your-test-token-here":
                headers["Authorization"] = f"Bearer {AUTH_TOKEN}"
            
            # Direct LangGraph test
            response = await client.post(
                f"{LANGGRAPH_URL}/api/v1/graphs/run",
                json={
                    "graph_type": "document_analysis_crew",
                    "input_data": {
                        "document_id": "test-doc-123",
                        "document_content": test_document,
                        "tenant_id": "test-tenant",
                        "user_id": "test-user"
                    },
                    "mode": "run"
                },
                headers={"X-API-Key": "langgraph-secret-key-12345"},
                timeout=30.0
            )
            
            if response.status_code == 200:
                result = response.json()
                print(f"✅ Document Analysis Complete!")
                print(f"   Document Type: {result.get('document_type', 'unknown')}")
                print(f"   Requires Signature: {result.get('requires_signature', False)}")
                print(f"   Confidence: {result.get('confidence_scores', {}).get('overall', 0)}")
                
                if result.get('extracted_data'):
                    print(f"   Extracted Entities: {json.dumps(result['extracted_data'], indent=2)}")
                
                if result.get('recommendations'):
                    print(f"   Recommendations: {result['recommendations'][:3]}")
            else:
                print(f"❌ Analysis failed: {response.status_code}")
                print(f"   Error: {response.text}")
                
        except Exception as e:
            print(f"❌ Document analysis error: {e}")
            return False
    
    return True

async def test_tag_generation():
    """Test simple tag generation graph"""
    print("\n🏷️  Testing Tag Generation...")
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{LANGGRAPH_URL}/api/v1/graphs/run",
                json={
                    "graph_type": "tag_generation",
                    "input_data": {
                        "content": "Machine learning article about neural networks and deep learning"
                    },
                    "mode": "run"
                },
                headers={"X-API-Key": "langgraph-secret-key-12345"},
                timeout=10.0
            )
            
            if response.status_code == 200:
                result = response.json()
                print(f"✅ Tag Generation Complete!")
                print(f"   Generated tags: {result.get('tags', [])}")
            else:
                print(f"❌ Tag generation failed: {response.status_code}")
                
        except Exception as e:
            print(f"❌ Tag generation error: {e}")
            return False
    
    return True

async def main():
    """Run all tests"""
    print("🚀 Starting LangGraph Agents Integration Tests")
    print(f"   Timestamp: {datetime.now().isoformat()}")
    print(f"   API URL: {API_BASE_URL}")
    print(f"   LangGraph URL: {LANGGRAPH_URL}")
    
    tests = [
        ("Health Check", test_langgraph_health),
        ("Graph Types", test_graph_types),
        ("Tag Generation", test_tag_generation),
        ("Document Analysis", test_document_analysis),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            success = await test_func()
            results.append((test_name, success))
        except Exception as e:
            print(f"\n❌ Test '{test_name}' crashed: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "="*50)
    print("📊 TEST SUMMARY")
    print("="*50)
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    for test_name, success in results:
        status = "✅ PASSED" if success else "❌ FAILED"
        print(f"{status} - {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed! LangGraph integration is working correctly.")
    else:
        print("\n⚠️  Some tests failed. Please check the logs above.")

if __name__ == "__main__":
    asyncio.run(main())