#!/usr/bin/env python3
"""
Quick sanity test for the LangExtract microservice.

Run inside the backend container (needs MICROSERVICES_API_KEY and LANGEXTRACT_SERVICE_URL).
"""
import asyncio
import httpx
from app.core.config import settings

LANGEXTRACT_URL = settings.LANGEXTRACT_SERVICE_URL.rstrip("/")
API_KEY = settings.MICROSERVICES_API_KEY
TENANT_ID = settings.DEFAULT_TENANT

if not API_KEY:
    raise RuntimeError("MICROSERVICES_API_KEY is required to run test_entity_extraction.py")


async def test_entity_extraction():
    """Call LangExtract service with a sample contract and display the entities."""
    sample_text = """
    CONTRATO DE PRESTACIÓN DE SERVICIOS
    
    Entre Apple Inc., representada por Tim Cook (CEO), y Microsoft Corporation,
    representada por Satya Nadella (CEO), ambas con domicilio en Seattle, Washington.
    
    Objeto: colaboración en iniciativas de IA.
    Duración: 6 meses (15 de diciembre 2024 - 15 de junio 2025).
    Valor: USD 50,000 pagaderos a la firma.
    """
    
    payload = {
        "text": sample_text.strip(),
        "document_type": "contract",
        "filename": "sample_contract.txt",
        "tenant_id": TENANT_ID,
        "user_id": "test-user"
    }
    
    headers = {
        "X-API-Key": API_KEY,
        "X-Tenant-ID": TENANT_ID
    }
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            f"{LANGEXTRACT_URL}/api/v1/extraction/extract",
            json=payload,
            headers=headers
        )
        response.raise_for_status()
        result = response.json()
    
    if not result.get("success"):
        raise RuntimeError(f"LangExtract returned error: {result.get('error')}")
    
    entities = result.get("entities", {})
    print("\n✅ LangExtract responded successfully")
    print(f"Total extractions: {result.get('metadata', {}).get('total_extractions')}")
    
    for entity_type, items in entities.items():
        print(f"\n{entity_type.upper()} ({len(items)})")
        for item in items[:5]:
            text = item.get("text") or item.get("value")
            attrs = item.get("attributes", {})
            print(f"  - {text}")
            if attrs:
                print(f"    attrs: {attrs}")
    
    summary = result.get("summary") or {}
    if summary:
        print("\n📋 Summary:")
        for key, value in summary.items():
            if isinstance(value, (list, tuple)):
                print(f"  {key}: {', '.join(value)}")
            else:
                print(f"  {key}: {value}")


if __name__ == "__main__":
    asyncio.run(test_entity_extraction())
