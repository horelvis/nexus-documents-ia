#!/usr/bin/env python3
"""
Simple CAG test with minimal configuration
"""
import asyncio
import httpx
import time

async def test_simple_cag():
    """Test CAG with simplest possible query"""
    print("=== Simple CAG Test ===\n")
    
    # Very simple request
    request = {
        "graph_type": "cag",
        "input_data": {
            "query": "Hi",
            "tenant_id": "1",
            "user_id": "1"
        },
        "tenant_id": "1"
    }
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        print("Sending simple CAG request...")
        start_time = time.time()
        
        try:
            response = await client.post(
                "http://langgraph-service:8007/api/v1/graphs/run",
                json=request,
                headers={"X-API-Key": "unified-microservices-key-12345"}
            )
            
            elapsed = time.time() - start_time
            print(f"\nResponse received in {elapsed:.2f}s")
            
            if response.status_code == 200:
                result = response.json()
                print(f"Status: {result.get('status')}")
                if 'final_state' in result and 'final_answer' in result['final_state']:
                    print(f"Answer: {result['final_state']['final_answer']}")
            else:
                print(f"Error: {response.status_code}")
                print(response.text)
                
        except httpx.TimeoutException:
            elapsed = time.time() - start_time
            print(f"\nTimeout after {elapsed:.2f}s")
        except Exception as e:
            print(f"\nError: {e}")

async def test_direct_ollama():
    """Test Ollama directly"""
    print("\n=== Direct Ollama Test ===\n")
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        print("Testing Ollama directly...")
        start_time = time.time()
        
        try:
            response = await client.post(
                "http://ollama-service:11434/api/generate",
                json={
                    "model": "llama3.2",
                    "prompt": "Say hi",
                    "stream": False
                }
            )
            
            elapsed = time.time() - start_time
            print(f"Response in {elapsed:.2f}s")
            
            if response.status_code == 200:
                result = response.json()
                print(f"Ollama says: {result.get('response', '')[:100]}")
            else:
                print(f"Error: {response.status_code}")
                
        except Exception as e:
            print(f"Error: {e}")

async def main():
    # First test Ollama directly
    await test_direct_ollama()
    
    # Then test CAG
    await test_simple_cag()

if __name__ == "__main__":
    asyncio.run(main())