#!/usr/bin/env python3
"""
NexusRouter Test Script

Tests the NexusRouter integration with Emma using OAuth authentication.
Simulates frontend calls to verify intent classification is working correctly.

Usage:
    python test_nexus_router.py
"""

import httpx
import asyncio
import json
from typing import Optional, Dict, Any


# Configuration
KEYCLOAK_URL = "http://localhost:8080/realms/nexus/protocol/openid-connect/token"
BACKEND_URL = "http://localhost:8000"
WEAVIATE_SERVICE_URL = "http://localhost:8007"

# Keycloak credentials
CLIENT_ID = "emma-app"
CLIENT_SECRET = "emma-secret-key-change-in-production"
USERNAME = "admin"
PASSWORD = "admin123"

# Test queries with expected intents
TEST_QUERIES = [
    {"query": "¿Cuántos contratos tengo?", "expected_intent": "count"},
    {"query": "Hola Emma, ¿cómo estás?", "expected_intent": "chat"},
    {"query": "busca facturas de enero", "expected_intent": "search"},
    {"query": "muéstrame las actas de 2024", "expected_intent": "list"},
    {"query": "analiza el documento de presupuesto", "expected_intent": "analyze"},
    {"query": "compara los contratos de ACME y TechCorp", "expected_intent": "compare"},
    {"query": "resume el informe mensual", "expected_intent": "summarize"},
    {"query": "extrae los datos del cliente del contrato", "expected_intent": "extract"},
    {"query": "¿qué tal el día?", "expected_intent": "chat"},
    {"query": "encuentra documentos de compliance", "expected_intent": "search"},
]


async def get_oauth_token() -> Optional[str]:
    """Get OAuth token from Keycloak."""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                KEYCLOAK_URL,
                data={
                    "grant_type": "password",
                    "client_id": CLIENT_ID,
                    "client_secret": CLIENT_SECRET,
                    "username": USERNAME,
                    "password": PASSWORD,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=10.0,
            )
            if response.status_code == 200:
                return response.json().get("access_token")
            else:
                print(f"Failed to get token: {response.status_code}")
                print(response.text)
                return None
        except Exception as e:
            print(f"Error getting token: {e}")
            return None


async def test_router_direct(api_key: str) -> None:
    """Test NexusRouter directly via weaviate-service admin API."""
    print("\n" + "="*60)
    print("DIRECT ROUTER TEST (weaviate-service /router/test)")
    print("="*60)

    async with httpx.AsyncClient() as client:
        for test in TEST_QUERIES:
            try:
                response = await client.post(
                    f"{WEAVIATE_SERVICE_URL}/router/test",
                    json={"query": test["query"]},
                    headers={"X-API-Key": api_key},
                    timeout=10.0,
                )

                if response.status_code == 200:
                    result = response.json()
                    # Direct API returns fields at top level
                    intent = result.get("intent", "unknown")
                    confidence = result.get("confidence", 0)
                    action = result.get("required_action", "unknown")
                    entities = result.get("entities", [])

                    expected = test["expected_intent"]
                    match = "✅" if intent == expected else "❌"

                    print(f"\n{match} Query: \"{test['query'][:40]}...\"")
                    print(f"   Intent: {intent} (expected: {expected})")
                    print(f"   Confidence: {confidence:.2f}")
                    print(f"   Action: {action}")
                    if entities:
                        print(f"   Entities: {entities}")
                else:
                    print(f"\n❌ Error for '{test['query'][:30]}...': {response.status_code}")

            except Exception as e:
                print(f"\n❌ Exception for '{test['query'][:30]}...': {e}")


async def test_emma_with_oauth(token: str) -> None:
    """Test Emma query via main backend with OAuth token."""
    print("\n" + "="*60)
    print("EMMA INTEGRATION TEST (OAuth via main backend)")
    print("="*60)

    # Test subset of queries through full Emma flow
    test_subset = [
        {"query": "¿Cuántos contratos tengo?", "expected_intent": "count"},
        {"query": "Hola Emma, ¿cómo estás?", "expected_intent": "chat"},
        {"query": "busca documentos de compliance", "expected_intent": "search"},
    ]

    async with httpx.AsyncClient() as client:
        for test in test_subset:
            try:
                response = await client.post(
                    f"{BACKEND_URL}/api/v1/weaviate/emma/query",
                    json={
                        "query": test["query"],
                        "enable_debug": True,
                    },
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                    timeout=60.0,
                )

                if response.status_code == 200:
                    result = response.json()
                    nexus_router = result.get("data", {}).get("nexus_router", {})
                    decision_path = result.get("decision_path", [])

                    intent = nexus_router.get("intent", "unknown")
                    confidence = nexus_router.get("confidence", 0)
                    action = nexus_router.get("required_action", "unknown")
                    expected = test["expected_intent"]
                    match = "✅" if intent == expected else "❌"

                    print(f"\n{match} Query: \"{test['query']}\"")
                    print(f"   Intent: {intent} (expected: {expected})")
                    print(f"   Confidence: {confidence:.2f}")
                    print(f"   Action: {action}")
                    print(f"   Decision path: {' → '.join(decision_path[:3])}...")
                    print(f"   Response preview: {result.get('answer', '')[:80]}...")
                else:
                    print(f"\n❌ Error for '{test['query']}': {response.status_code}")
                    print(f"   Response: {response.text[:200]}")

            except Exception as e:
                print(f"\n❌ Exception for '{test['query']}': {e}")


async def test_router_metrics(api_key: str) -> None:
    """Get router metrics."""
    print("\n" + "="*60)
    print("ROUTER METRICS")
    print("="*60)

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"{WEAVIATE_SERVICE_URL}/router/metrics",
                headers={"X-API-Key": api_key},
                timeout=10.0,
            )

            if response.status_code == 200:
                result = response.json()
                metrics = result.get("metrics", {})
                print(f"\nTotal classifications: {metrics.get('total_classifications', 0)}")
                print(f"Avg confidence: {metrics.get('avg_confidence', 0):.2f}")
                print(f"Avg latency: {metrics.get('avg_latency_ms', 0):.2f}ms")
                print(f"Forced searches: {metrics.get('forced_searches', 0)}")
                print(f"Direct responses: {metrics.get('direct_responses', 0)}")

                by_intent = metrics.get("classifications_by_intent", {})
                if by_intent:
                    print("\nClassifications by intent:")
                    for intent, count in sorted(by_intent.items()):
                        print(f"  {intent}: {count}")
            else:
                print(f"Failed to get metrics: {response.status_code}")
        except Exception as e:
            print(f"Error getting metrics: {e}")


async def main():
    """Run all tests."""
    print("="*60)
    print("NEXUSROUTER TEST SUITE")
    print("="*60)

    # Get API key from environment or use default
    import os
    api_key = os.environ.get("MICROSERVICES_API_KEY", "JWFu8l5QmBnWz1xk26Y7QMCWYeEKcTtPPzcLyb285Cc")

    # Test 1: Direct router test
    await test_router_direct(api_key)

    # Test 2: Get OAuth token and test via main backend
    print("\n\nGetting OAuth token from Keycloak...")
    token = await get_oauth_token()

    if token:
        print(f"Token obtained: {token[:50]}...")
        await test_emma_with_oauth(token)
    else:
        print("❌ Could not obtain OAuth token. Skipping Emma integration test.")

    # Test 3: Show metrics
    await test_router_metrics(api_key)

    print("\n" + "="*60)
    print("TEST SUITE COMPLETED")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())
