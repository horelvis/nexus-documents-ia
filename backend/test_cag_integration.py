#!/usr/bin/env python3
"""
Script de prueba para verificar el microservicio CAG real.
Ejecutar dentro del contenedor API (requiere MICROSERVICES_API_KEY).
"""
import asyncio
import os
import httpx
import json

API_KEY = os.getenv("MICROSERVICES_API_KEY")
CAG_URL = os.getenv("CAG_SERVICE_URL", "http://cag-service:8000").rstrip("/")

if not API_KEY:
    raise RuntimeError("MICROSERVICES_API_KEY environment variable is required for test_cag_integration.py")


class FakeUser:
    """Usuario fake para pruebas"""
    def __init__(self, id=1, tenant_id=1):
        self.id = id
        self.tenant_id = tenant_id
        self.email = "test@example.com"


async def test_document_analysis():
    """Probar análisis de documentos con CAG"""
    print("=== Prueba de Document Analysis con CAG ===\n")
    
    user = FakeUser()
    document_content = """
        CONTRATO DE PRESTACIÓN DE SERVICIOS
        
        Entre ABC Corp y XYZ Consulting
        Objeto: Servicios de consultoría en IA
        Duración: 6 meses
        Valor: $50,000 USD
        Fecha: 5 de agosto de 2025
    """
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        # Health check
        health = await client.get(f"{CAG_URL}/health", headers={"X-API-Key": API_KEY})
        health.raise_for_status()
        print("\n✅ CAG service está activo")
        print(json.dumps(health.json(), indent=2)[:300])
        
        # Document analysis
        request_payload = {
            "document_content": document_content,
            "document_id": "demo-contract",
            "tenant_id": str(user.tenant_id),
            "user_id": str(user.id),
            "analysis_type": "legal"
        }
        
        print("\n📤 Enviando /api/v1/cag/analyze...")
        response = await client.post(
            f"{CAG_URL}/api/v1/cag/analyze",
            json=request_payload,
            headers={"X-API-Key": API_KEY, "X-Tenant-ID": str(user.tenant_id)}
        )
        response.raise_for_status()
        result = response.json()
        
        print("\n✅ CAG procesó exitosamente!")
        print(f"Tiempo: {result.get('execution_time', 0):.2f}s | Confianza: {result.get('confidence', 0):.2f}")
        print("-" * 50)
        print(result.get("analysis", "Sin respuesta")[:600])
        print("-" * 50)


async def test_chat_with_cag():
    """Probar consulta simple con CAG query endpoint"""
    print("\n\n=== Prueba de Chat con CAG ===\n")
    
    user = FakeUser()
    prompt = "¿Qué aspectos debo revisar antes de firmar un contrato de servicios?"
    
    async with httpx.AsyncClient(timeout=45.0) as client:
        response = await client.post(
            f"{CAG_URL}/api/v1/cag/query",
            json={
                "query": prompt,
                "tenant_id": str(user.tenant_id),
                "user_id": str(user.id),
                "context": {"demo": True}
            },
            headers={"X-API-Key": API_KEY, "X-Tenant-ID": str(user.tenant_id)}
        )
        
        if response.status_code == 200:
            result = response.json()
            answer = result.get("answer", "Sin respuesta")
            print("\n✅ Respuesta recibida!")
            print("-" * 50)
            print(answer[:600])
            print("-" * 50)
        else:
            print(f"\n❌ Error: {response.status_code}")
            print(response.text[:300])


async def main():
    await test_document_analysis()
    await test_chat_with_cag()


if __name__ == "__main__":
    asyncio.run(main())
