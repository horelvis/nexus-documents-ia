#!/usr/bin/env python3
"""
Direct test of Ollama connection
"""
import asyncio
from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain_core.messages import HumanMessage
import os

async def test_ollama_direct():
    """Test Ollama connection directly"""
    print("=== Testing Ollama Direct Connection ===\n")
    
    # Print environment
    print(f"OLLAMA_HOST: {os.getenv('OLLAMA_HOST', 'not set')}")
    print(f"OLLAMA_BASE_URL: {os.getenv('OLLAMA_BASE_URL', 'not set')}")
    
    # Test 1: Direct with base_url
    print("\n1. Testing ChatOllama with base_url...")
    try:
        llm = ChatOllama(
            base_url="http://ollama-service:11434",
            model="llama3.2",
            temperature=0.7,
            timeout=10.0
        )
        response = await llm.ainvoke([HumanMessage(content="Say hello in 5 words")])
        print(f"Success! Response: {response.content}")
    except Exception as e:
        print(f"Failed with base_url: {e}")
    
    # Test 2: Using environment variable
    print("\n2. Testing ChatOllama with env var...")
    os.environ["OLLAMA_HOST"] = "http://ollama-service:11434"
    try:
        llm = ChatOllama(
            model="llama3.2",
            temperature=0.7,
            timeout=10.0
        )
        response = await llm.ainvoke([HumanMessage(content="Say hello in 5 words")])
        print(f"Success! Response: {response.content}")
    except Exception as e:
        print(f"Failed with env var: {e}")
    
    # Test 3: Test embeddings
    print("\n3. Testing OllamaEmbeddings...")
    try:
        embeddings = OllamaEmbeddings(
            model="all-minilm:latest"
        )
        result = await embeddings.aembed_query("test")
        print(f"Success! Embedding size: {len(result)}")
    except Exception as e:
        print(f"Failed embeddings: {e}")
    
    # Test 4: Sync calls
    print("\n4. Testing sync calls...")
    try:
        llm = ChatOllama(
            base_url="http://ollama-service:11434",
            model="llama3.2"
        )
        response = llm.invoke([HumanMessage(content="Say hello")])
        print(f"Sync success! Response: {response.content}")
    except Exception as e:
        print(f"Sync failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_ollama_direct())