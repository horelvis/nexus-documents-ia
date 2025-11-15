#!/usr/bin/env python3
"""
Simple CAG test with minimal configuration (directly hits CAG service).
"""
import asyncio
import os
import httpx

API_KEY = os.getenv("MICROSERVICES_API_KEY")
CAG_URL = os.getenv("CAG_SERVICE_URL", "http://cag-service:8000").rstrip("/")
TENANT_ID = os.getenv("DEFAULT_TENANT", "default")

if not API_KEY:
    raise RuntimeError("MICROSERVICES_API_KEY environment variable is required for test_simple_cag.py")


async def test_simple_cag():
    """Test CAG with simplest possible query"""
    print("=== Simple CAG Test ===\n")
    
    request = {
        "query": "Hola, ¿qué tipos de documentos puedes analizar?",
        "tenant_id": str(TENANT_ID),
        "user_id": "simple-test",
        "context": {"demo": True}
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        print("Enviando consulta simple a CAG...")
        response = await client.post(
            f"{CAG_URL}/api/v1/cag/query",
            json=request,
            headers={"X-API-Key": API_KEY, "X-Tenant-ID": str(TENANT_ID)}
        )
        
        if response.status_code == 200:
            data = response.json()
            print("\n✅ Respuesta recibida!")
            print("-" * 50)
            print(data.get("answer", "Sin respuesta")[:500])
            print("-" * 50)
        else:
            print(f"\n❌ Error: {response.status_code}")
            print(response.text[:300])


async def main():
    await test_simple_cag()


if __name__ == "__main__":
    asyncio.run(main())
