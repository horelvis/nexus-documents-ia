#!/usr/bin/env python3
"""
Test script for CAG Service Streaming
NO DUMMY DATA - REAL PROCESSING ONLY
"""
import asyncio
import httpx
import json
import time


async def test_streaming_query():
    """Test streaming query endpoint"""
    print("\n=== Testing Streaming Query ===\n")
    
    request_data = {
        "query": "What are the key differences between contracts and agreements?",
        "tenant_id": "1",
        "user_id": "1",
        "context": {"source": "test"}
    }
    
    async with httpx.AsyncClient() as client:
        try:
            print("Sending streaming query...")
            start_time = time.time()
            
            async with client.stream(
                "POST",
                "http://cag-service:8008/api/v1/cag/query/stream",
                json=request_data,
                headers={"X-API-Key": "unified-microservices-key-12345"},
                timeout=60.0
            ) as response:
                print(f"Status: {response.status_code}")
                
                if response.status_code == 200:
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            data_str = line[6:]
                            if data_str == "[DONE]":
                                print("\n[Stream completed]")
                                break
                            
                            try:
                                event = json.loads(data_str)
                                if event["type"] == "progress":
                                    print(f"Progress ({event.get('progress', 0)}%): {event['content']}")
                                elif event["type"] == "result":
                                    print(f"\nResult received!")
                                    print(f"Quality Score: {event['content'].get('quality_score', 0)}")
                                    print(f"Answer preview: {event['content'].get('answer', '')[:200]}...")
                                elif event["type"] == "error":
                                    print(f"Error: {event['content']}")
                            except json.JSONDecodeError:
                                print(f"Failed to parse: {data_str}")
                else:
                    error_text = await response.aread()
                    print(f"Error response: {error_text.decode()}")
                    
            elapsed = time.time() - start_time
            print(f"\nTotal time: {elapsed:.2f}s")
            
        except Exception as e:
            print(f"Error: {e}")


async def test_streaming_document_analysis():
    """Test streaming document analysis endpoint"""
    print("\n=== Testing Streaming Document Analysis ===\n")
    
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
        "document_id": "test_doc_stream_001",
        "tenant_id": "1",
        "user_id": "1",
        "analysis_type": "contract"
    }
    
    async with httpx.AsyncClient() as client:
        try:
            print("Sending document for streaming analysis...")
            start_time = time.time()
            
            async with client.stream(
                "POST",
                "http://cag-service:8008/api/v1/cag/analyze/stream",
                json=request_data,
                headers={"X-API-Key": "unified-microservices-key-12345"},
                timeout=120.0
            ) as response:
                print(f"Status: {response.status_code}")
                
                if response.status_code == 200:
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            data_str = line[6:]
                            if data_str == "[DONE]":
                                print("\n[Stream completed]")
                                break
                            
                            try:
                                event = json.loads(data_str)
                                if event["type"] == "progress":
                                    print(f"Progress ({event.get('progress', 0)}%): {event['content']}")
                                elif event["type"] == "result":
                                    print(f"\nAnalysis completed!")
                                    print(f"Document Type: {event['content'].get('analysis_type', 'unknown')}")
                                    print(f"Quality Score: {event['content'].get('quality_score', 0)}")
                                    print(f"Analysis preview: {event['content'].get('analysis', '')[:300]}...")
                                elif event["type"] == "error":
                                    print(f"Error: {event['content']}")
                            except json.JSONDecodeError:
                                print(f"Failed to parse: {data_str}")
                else:
                    error_text = await response.aread()
                    print(f"Error response: {error_text.decode()}")
                    
            elapsed = time.time() - start_time
            print(f"\nTotal time: {elapsed:.2f}s")
            
        except Exception as e:
            print(f"Error: {e}")


async def test_direct_cag_endpoints():
    """Test direct CAG endpoints (non-streaming)"""
    print("\n=== Testing Direct CAG Endpoints ===\n")
    
    # Test direct query endpoint
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                "http://cag-service:8008/api/v1/cag/query",
                json={
                    "query": "What is artificial intelligence?",
                    "tenant_id": "1",
                    "user_id": "1"
                },
                headers={"X-API-Key": "unified-microservices-key-12345"},
                timeout=30.0
            )
            print(f"Direct query status: {response.status_code}")
            if response.status_code == 200:
                result = response.json()
                print(f"Success: {result.get('success', False)}")
                print(f"Quality Score: {result.get('quality_score', 0)}")
            else:
                print(f"Error: {response.text}")
        except Exception as e:
            print(f"Direct query error: {e}")


async def check_ollama_connectivity():
    """Check if Ollama is accessible from CAG service"""
    print("\n=== Checking Ollama Connectivity ===\n")
    
    try:
        # Check from inside CAG service container
        result = await asyncio.create_subprocess_exec(
            'docker', 'exec', 'docker-cag-service-1', 
            'curl', '-s', 'http://ollama-service:11434/api/tags',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await result.communicate()
        
        if result.returncode == 0:
            data = json.loads(stdout.decode())
            print("Ollama is accessible from CAG service!")
            print(f"Available models: {[m['name'] for m in data.get('models', [])]}")
        else:
            print(f"Ollama connection failed: {stderr.decode()}")
            
    except Exception as e:
        print(f"Error checking Ollama: {e}")


async def main():
    """Run all tests"""
    print("🧪 CAG Service Streaming Tests (REAL DATA ONLY)\n")
    
    # First check Ollama connectivity
    await check_ollama_connectivity()
    
    # Test streaming endpoints
    await test_streaming_query()
    await test_streaming_document_analysis()
    
    # Test direct endpoints
    await test_direct_cag_endpoints()
    
    print("\n✅ All tests completed!")


if __name__ == "__main__":
    asyncio.run(main())