#!/usr/bin/env python3
"""
Test script for CAG Service
Execute inside Docker network
"""
import asyncio
import httpx
import json
import time


async def test_cag_health():
    """Test CAG service health"""
    print("=== Testing CAG Service Health ===\n")
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get("http://cag-service:8008/health")
            print(f"Status: {response.status_code}")
            print(f"Response: {json.dumps(response.json(), indent=2)}")
            return response.status_code == 200
        except Exception as e:
            print(f"Error: {e}")
            return False


async def test_document_analysis():
    """Test document analysis with CAG service"""
    print("\n=== Testing Document Analysis ===\n")
    
    document_content = """
    SERVICE AGREEMENT
    
    This agreement is between TechCorp Inc. and CloudServices Ltd.
    
    Services: Cloud infrastructure management and support
    Duration: 12 months starting January 1, 2025
    Monthly Fee: $10,000 USD
    
    Terms:
    1. 24/7 support availability
    2. 99.9% uptime guarantee
    3. Monthly performance reports
    4. Dedicated account manager
    
    Signed on December 15, 2024
    """
    
    request_data = {
        "document_content": document_content,
        "document_id": "test_doc_001",
        "tenant_id": "1",
        "user_id": "1",
        "analysis_type": "contract"
    }
    
    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            print("Sending document for analysis...")
            start_time = time.time()
            
            response = await client.post(
                "http://cag-service:8008/api/v1/cag/analyze",
                json=request_data,
                headers={"X-API-Key": "unified-microservices-key-12345"}
            )
            
            elapsed = time.time() - start_time
            print(f"\nResponse received in {elapsed:.2f}s")
            print(f"Status: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                print(f"\nAnalysis successful!")
                print(f"Quality Score: {result.get('quality_score', 0)}")
                print(f"Execution Time: {result.get('execution_time', 0):.2f}s")
                print(f"\nAnalysis Result:")
                print("-" * 50)
                print(result.get('analysis', 'No analysis available')[:500])
                print("-" * 50)
            else:
                print(f"Error: {response.text}")
                
        except httpx.TimeoutException:
            print(f"Request timed out after {time.time() - start_time:.2f}s")
        except Exception as e:
            print(f"Error: {e}")


async def test_query_processing():
    """Test query processing with CAG service"""
    print("\n=== Testing Query Processing ===\n")
    
    request_data = {
        "query": "What are the key differences between contracts and agreements?",
        "tenant_id": "1",
        "user_id": "1",
        "context": {"source": "test"}
    }
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            print("Sending query...")
            start_time = time.time()
            
            response = await client.post(
                "http://cag-service:8008/api/v1/cag/query",
                json=request_data,
                headers={"X-API-Key": "unified-microservices-key-12345"}
            )
            
            elapsed = time.time() - start_time
            print(f"\nResponse received in {elapsed:.2f}s")
            print(f"Status: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                print(f"\nQuery processed successfully!")
                print(f"Quality Score: {result.get('quality_score', 0)}")
                print(f"Iterations: {result.get('iterations', 0)}")
                print(f"Gaps Identified: {result.get('gaps_identified', 0)}")
                print(f"\nAnswer:")
                print("-" * 50)
                print(result.get('answer', 'No answer available')[:500])
                print("-" * 50)
            else:
                print(f"Error: {response.text}")
                
        except Exception as e:
            print(f"Error: {e}")


async def main():
    """Run all tests"""
    print("🧪 CAG Service Integration Tests\n")
    
    # Test health
    health_ok = await test_cag_health()
    if not health_ok:
        print("\n❌ CAG Service is not healthy!")
        return
    
    # Test document analysis
    await test_document_analysis()
    
    # Test query processing
    await test_query_processing()
    
    print("\n✅ All tests completed!")


if __name__ == "__main__":
    asyncio.run(main())