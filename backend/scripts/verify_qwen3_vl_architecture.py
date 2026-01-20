#!/usr/bin/env python3
"""
Verification script for Qwen3-VL Architecture

Tests the all-Qwen3-VL architecture:
- Qwen3-VL-8B-Thinking (generation with vision + thinking mode)
- Qwen3-VL-Embedding-2B (multimodal embeddings)

Run with: python scripts/verify_qwen3_vl_architecture.py
"""

import asyncio
import httpx
import json
import sys
import base64
from pathlib import Path


# Configuration - Docker internal network URLs
# These services are only accessible from within the Docker network
VLLM_URL = "http://vllm:8000"  # Qwen3-VL-8B-Thinking
EMBEDDING_URL = "http://qwen3-vl-embedding:8000"  # Qwen3-VL-Embedding-2B


def print_status(service: str, status: bool, message: str = ""):
    """Print status with emoji"""
    emoji = "✅" if status else "❌"
    print(f"{emoji} {service}: {message}")


async def check_vllm_health(client: httpx.AsyncClient, base_url: str) -> dict:
    """Check vLLM server health and model info"""
    result = {"healthy": False, "model": None, "supports_vision": False}

    try:
        # Health check
        response = await client.get(f"{base_url}/health", timeout=5.0)
        result["healthy"] = response.status_code == 200

        # Get model info
        response = await client.get(f"{base_url}/v1/models", timeout=5.0)
        if response.status_code == 200:
            data = response.json()
            if data.get("data"):
                result["model"] = data["data"][0].get("id", "unknown")
                # Check if it's a VL model (vision-language)
                result["supports_vision"] = "VL" in result["model"].upper()

    except Exception as e:
        result["error"] = str(e)

    return result


async def test_text_completion(client: httpx.AsyncClient, base_url: str) -> dict:
    """Test basic text completion"""
    result = {"success": False, "response": None, "has_thinking": False}

    try:
        response = await client.post(
            f"{base_url}/v1/chat/completions",
            json={
                "model": "Qwen/Qwen3-VL-8B-Thinking",
                "messages": [
                    {"role": "user", "content": "/think What is 25 * 4?"}
                ],
                "max_tokens": 500,
                "temperature": 0.7,
            },
            timeout=60.0
        )

        if response.status_code == 200:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            result["success"] = True
            result["response"] = content[:200] + "..." if len(content) > 200 else content
            result["has_thinking"] = "<think>" in content

    except Exception as e:
        result["error"] = str(e)

    return result


async def test_text_embedding(client: httpx.AsyncClient, base_url: str) -> dict:
    """Test text embedding generation"""
    result = {"success": False, "dimensions": None}

    try:
        response = await client.post(
            f"{base_url}/v1/embeddings",
            json={
                "model": "Qwen/Qwen3-VL-Embedding-2B",
                "input": ["This is a test sentence for embedding."],
            },
            timeout=30.0
        )

        if response.status_code == 200:
            data = response.json()
            if data.get("data"):
                embedding = data["data"][0]["embedding"]
                result["success"] = True
                result["dimensions"] = len(embedding)

    except Exception as e:
        result["error"] = str(e)

    return result


async def test_vision_completion(client: httpx.AsyncClient, base_url: str) -> dict:
    """Test vision completion with a simple image"""
    result = {"success": False, "response": None}

    # Create a simple 1x1 red pixel PNG for testing
    # This is a minimal valid PNG
    simple_png = base64.b64encode(bytes([
        0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,  # PNG signature
        0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,  # IHDR chunk
        0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
        0x08, 0x02, 0x00, 0x00, 0x00, 0x90, 0x77, 0x53,
        0xDE, 0x00, 0x00, 0x00, 0x0C, 0x49, 0x44, 0x41,  # IDAT chunk
        0x54, 0x08, 0xD7, 0x63, 0xF8, 0xFF, 0xFF, 0x3F,
        0x00, 0x05, 0xFE, 0x02, 0xFE, 0xDC, 0xCC, 0x59,
        0xE7, 0x00, 0x00, 0x00, 0x00, 0x49, 0x45, 0x4E,  # IEND chunk
        0x44, 0xAE, 0x42, 0x60, 0x82
    ])).decode("utf-8")

    try:
        response = await client.post(
            f"{base_url}/v1/chat/completions",
            json={
                "model": "Qwen/Qwen3-VL-8B-Thinking",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Describe this image briefly."},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{simple_png}"
                                }
                            }
                        ]
                    }
                ],
                "max_tokens": 200,
            },
            timeout=60.0
        )

        if response.status_code == 200:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            result["success"] = True
            result["response"] = content[:100] + "..." if len(content) > 100 else content
        else:
            result["error"] = f"Status {response.status_code}: {response.text[:200]}"

    except Exception as e:
        result["error"] = str(e)

    return result


async def main():
    """
    Run all verification tests.

    NOTE: This script must be run from inside a Docker container
    that has access to the backend-network.

    Usage:
        docker compose exec api python scripts/verify_qwen3_vl_architecture.py
        # or
        docker compose exec weaviate-service python /app/scripts/verify_qwen3_vl_architecture.py
    """
    print("=" * 60)
    print("🔍 Qwen3-VL Architecture Verification")
    print("=" * 60)
    print()

    # URLs for Docker internal network
    vllm_url = VLLM_URL
    embedding_url = EMBEDDING_URL

    print(f"📡 vLLM URL: {vllm_url}")
    print(f"📡 Embedding URL: {embedding_url}")
    print()

    async with httpx.AsyncClient() as client:
        # 1. Check vLLM health (Qwen3-VL-8B-Thinking)
        print("1️⃣  Checking Qwen3-VL-8B-Thinking (Generation)...")
        vllm_health = await check_vllm_health(client, vllm_url)
        print_status(
            "vLLM Health",
            vllm_health["healthy"],
            f"Model: {vllm_health.get('model', 'N/A')}, Vision: {vllm_health.get('supports_vision', False)}"
        )
        if vllm_health.get("error"):
            print(f"   Error: {vllm_health['error']}")
        print()

        # 2. Check embedding service health (Qwen3-VL-Embedding-2B)
        print("2️⃣  Checking Qwen3-VL-Embedding-2B (Embeddings)...")
        embedding_health = await check_vllm_health(client, embedding_url)
        print_status(
            "Embedding Health",
            embedding_health["healthy"],
            f"Model: {embedding_health.get('model', 'N/A')}"
        )
        if embedding_health.get("error"):
            print(f"   Error: {embedding_health['error']}")
        print()

        # 3. Test text completion with thinking mode
        if vllm_health["healthy"]:
            print("3️⃣  Testing Text Completion with Thinking Mode...")
            text_result = await test_text_completion(client, vllm_url)
            print_status(
                "Text Completion",
                text_result["success"],
                f"Has thinking: {text_result.get('has_thinking', False)}"
            )
            if text_result.get("response"):
                print(f"   Response preview: {text_result['response'][:100]}...")
            if text_result.get("error"):
                print(f"   Error: {text_result['error']}")
            print()

        # 4. Test vision completion
        if vllm_health["healthy"] and vllm_health.get("supports_vision"):
            print("4️⃣  Testing Vision Completion...")
            vision_result = await test_vision_completion(client, vllm_url)
            print_status(
                "Vision Completion",
                vision_result["success"],
                vision_result.get("response", "")[:50] if vision_result.get("response") else ""
            )
            if vision_result.get("error"):
                print(f"   Error: {vision_result['error']}")
            print()

        # 5. Test text embedding
        if embedding_health["healthy"]:
            print("5️⃣  Testing Text Embedding...")
            embedding_result = await test_text_embedding(client, embedding_url)
            print_status(
                "Text Embedding",
                embedding_result["success"],
                f"Dimensions: {embedding_result.get('dimensions', 'N/A')}"
            )
            if embedding_result.get("error"):
                print(f"   Error: {embedding_result['error']}")
            print()

    # Summary
    print("=" * 60)
    print("📊 Summary")
    print("=" * 60)

    all_healthy = vllm_health["healthy"] and embedding_health["healthy"]

    if all_healthy:
        print("✅ All services are healthy!")
        print()
        print("Architecture:")
        print(f"  • Generation: {vllm_health.get('model', 'Qwen3-VL-8B-Thinking')}")
        print(f"  • Embeddings: {embedding_health.get('model', 'Qwen3-VL-Embedding-2B')}")
        print(f"  • Vision Support: {vllm_health.get('supports_vision', False)}")
        return 0
    else:
        print("❌ Some services are not healthy.")
        print()
        print("Troubleshooting:")
        print("  1. Check if Docker containers are running: docker ps")
        print("  2. Check container logs: docker logs <container_name>")
        print("  3. Verify GPU memory: nvidia-smi")
        print("  4. Ensure HF_TOKEN is set for model download")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
