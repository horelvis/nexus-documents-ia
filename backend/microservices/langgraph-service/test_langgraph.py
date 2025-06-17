#!/usr/bin/env python3
"""
Test script for LangGraph service
Run this after starting the service to verify it's working correctly
"""

import asyncio
import httpx
import json
from typing import Dict, Any


# Configuration
BASE_URL = "http://localhost:8007"
API_KEY = "langgraph-secret-key-12345"
TENANT_ID = "test-tenant-123"


async def test_health_check():
    """Test health check endpoint"""
    print("\n1. Testing health check...")
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/health")
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        assert response.status_code == 200
        print("✓ Health check passed")


async def test_list_graph_types():
    """Test listing available graph types"""
    print("\n2. Testing list graph types...")
    headers = {
        "X-API-Key": API_KEY,
        "X-Tenant-ID": TENANT_ID
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{BASE_URL}/api/v1/graphs/types",
            headers=headers
        )
        print(f"Status: {response.status_code}")
        print(f"Available graphs: {response.json()}")
        assert response.status_code == 200
        print("✓ List graph types passed")


async def test_tag_generation():
    """Test tag generation graph"""
    print("\n3. Testing tag generation graph...")
    
    headers = {
        "X-API-Key": API_KEY,
        "X-Tenant-ID": TENANT_ID,
        "Content-Type": "application/json"
    }
    
    request_data = {
        "graph_type": "tag_generation",
        "input_data": {
            "text": """
            LangGraph is a powerful framework for building stateful applications with language models.
            It extends LangChain by adding graph-based workflows, state management, and cycles.
            This allows developers to create complex AI applications with better control flow and debugging.
            Key features include checkpointing, human-in-the-loop interactions, and parallel execution.
            """,
            "max_tags": 5,
            "tag_type": "technical"
        },
        "tenant_id": TENANT_ID
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        print("Sending request...")
        response = await client.post(
            f"{BASE_URL}/api/v1/graphs/run",
            headers=headers,
            json=request_data
        )
        
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            print(f"Run ID: {result['run_id']}")
            print(f"Status: {result['status']}")
            print(f"Execution time: {result['execution_time']:.2f}s")
            print(f"Iterations: {result['iterations']}")
            
            if result['result']:
                print(f"\nGenerated tags: {result['result']['tags']}")
                print(f"Confidence scores: {result['result']['confidence_scores']}")
                print(f"Reasoning: {result['result']['reasoning']}")
            print("✓ Tag generation passed")
        else:
            print(f"Error: {response.text}")
            raise Exception("Tag generation failed")


async def test_graph_structure():
    """Test getting graph structure"""
    print("\n4. Testing graph structure endpoint...")
    
    headers = {
        "X-API-Key": API_KEY,
        "X-Tenant-ID": TENANT_ID
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{BASE_URL}/api/v1/graphs/structure/tag_generation",
            headers=headers
        )
        
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            structure = response.json()
            print(f"Graph type: {structure['graph_type']}")
            print(f"Entry point: {structure['entry_point']}")
            print(f"Number of nodes: {len(structure['nodes'])}")
            print("Nodes:")
            for node in structure['nodes']:
                print(f"  - {node['name']} ({node['type']}): {node['description']}")
            print("✓ Graph structure passed")
        else:
            print(f"Error: {response.text}")
            raise Exception("Graph structure failed")


async def test_document_processing():
    """Test document processing graph"""
    print("\n5. Testing document processing graph...")
    
    headers = {
        "X-API-Key": API_KEY,
        "X-Tenant-ID": TENANT_ID,
        "Content-Type": "application/json"
    }
    
    request_data = {
        "graph_type": "document_processing",
        "input_data": {
            "document_id": "doc-123",
            "content": """
            This is a test document for the LangGraph migration project.
            
            The document contains multiple paragraphs to test chunking functionality.
            Each paragraph should be processed and stored with appropriate metadata.
            
            LangGraph provides better state management compared to traditional chains.
            It allows for complex workflows with conditional logic and loops.
            
            This migration will improve our document processing capabilities significantly.
            """,
            "filename": "test_document.txt",
            "tenant_id": TENANT_ID,
            "user_id": "user-456"
        },
        "tenant_id": TENANT_ID
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        print("Sending request...")
        response = await client.post(
            f"{BASE_URL}/api/v1/graphs/run",
            headers=headers,
            json=request_data
        )
        
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            print(f"Run ID: {result['run_id']}")
            print(f"Status: {result['status']}")
            
            if result['result']:
                print(f"\nDocument ID: {result['result']['document_id']}")
                print(f"Chunks created: {len(result['result']['chunks'])}")
                print(f"Quality score: {result['result']['quality_score']}")
                print(f"Processing notes: {result['result']['processing_notes']}")
            print("✓ Document processing passed")
        else:
            print(f"Error: {response.text}")
            raise Exception("Document processing failed")


async def test_rag_query():
    """Test RAG graph"""
    print("\n6. Testing RAG graph...")
    
    headers = {
        "X-API-Key": API_KEY,
        "X-Tenant-ID": TENANT_ID,
        "Content-Type": "application/json"
    }
    
    request_data = {
        "graph_type": "rag",
        "input_data": {
            "query": "What are the benefits of LangGraph over LangChain?",
            "tenant_id": TENANT_ID,
            "max_results": 3,
            "include_sources": True
        },
        "tenant_id": TENANT_ID
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        print("Sending request...")
        response = await client.post(
            f"{BASE_URL}/api/v1/graphs/run",
            headers=headers,
            json=request_data
        )
        
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            print(f"Run ID: {result['run_id']}")
            print(f"Status: {result['status']}")
            
            if result['result']:
                print(f"\nAnswer: {result['result']['answer']}")
                print(f"Confidence: {result['result']['confidence_score']:.2f}")
                if result['result'].get('sources'):
                    print(f"Sources used: {len(result['result']['sources'])}")
            print("✓ RAG query passed")
        else:
            print(f"Error: {response.text}")
            raise Exception("RAG query failed")


async def main():
    """Run all tests"""
    print("=== LangGraph Service Test Suite ===")
    print(f"Testing against: {BASE_URL}")
    
    try:
        await test_health_check()
        await test_list_graph_types()
        await test_tag_generation()
        await test_graph_structure()
        await test_document_processing()
        await test_rag_query()
        
        print("\n✅ All tests passed successfully!")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())