#!/usr/bin/env python3
"""
Test CrewAI CAG Service - Verificar que todo funciona
NO más reinventar la rueda!
"""
import asyncio
import httpx
from datetime import datetime
import json

async def test_crewai():
    """Test CrewAI CAG implementation"""
    
    base_url = "http://localhost:8008"
    api_key = "test-api-key-12345"
    
    print("🚀 Testing CrewAI CAG Service...")
    print("=" * 50)
    
    # 1. Health check
    print("\n1. Health Check:")
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{base_url}/health")
            health = response.json()
            print(f"   Status: {health.get('status')}")
            print(f"   Engine: {health.get('engine', 'unknown')}")
            if 'checks' in health:
                for check, status in health['checks'].items():
                    print(f"   - {check}: {'✅' if status else '❌'}")
        except Exception as e:
            print(f"   ❌ Health check failed: {e}")
    
    # 2. Test process_query with CrewAI
    print("\n2. Process Query (CrewAI):")
    queries = [
        "¿Cuáles son los documentos más importantes?",
        "Busca contratos que requieren firma",
        "Analiza el estado financiero actual",
        "¿Qué documentos tienen fechas de vencimiento próximas?"
    ]
    
    for query in queries[:2]:  # Test first 2 queries
        print(f"\n   Query: {query}")
        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                response = await client.post(
                    f"{base_url}/api/v1/cag/process",
                    headers={"X-API-Key": api_key},
                    json={
                        "query": query,
                        "tenant_id": "test-tenant",
                        "user_id": "test-user"
                    }
                )
                
                if response.status_code == 200:
                    result = response.json()
                    print(f"   ✅ Success: {result.get('success')}")
                    print(f"   Engine: {result.get('engine', 'unknown')}")
                    
                    # Show answer preview
                    answer = result.get('answer', '')
                    if answer:
                        print(f"   Answer preview: {answer[:200]}...")
                    
                    # Show agents used
                    agents = result.get('agents_used', [])
                    if agents:
                        print(f"   Agents used: {', '.join(agents)}")
                    
                    # Show execution time
                    exec_time = result.get('execution_time', 0)
                    print(f"   Execution time: {exec_time:.2f}s")
                else:
                    print(f"   ❌ Error: Status {response.status_code}")
                    print(f"   Response: {response.text[:200]}")
                    
            except httpx.TimeoutError:
                print(f"   ⏱️ Timeout - query took too long")
            except Exception as e:
                print(f"   ❌ Error: {e}")
    
    # 3. Test document analysis
    print("\n3. Document Analysis (CrewAI):")
    doc_content = """
    CONTRATO DE SERVICIOS
    
    Entre las partes:
    - Empresa ABC S.A. (Cliente)
    - Nexus Solutions (Proveedor)
    
    Fecha: 1 de enero de 2024
    Monto: $50,000 USD
    Plazo: 12 meses
    
    El proveedor se compromete a entregar un sistema de gestión documental
    con las siguientes características:
    - Búsqueda inteligente con IA
    - Firma digital integrada
    - Análisis automático de documentos
    - Soporte multi-tenant
    
    Penalizaciones:
    - Retraso en entrega: 2% del monto por semana
    - Incumplimiento de funcionalidades: 10% del monto total
    """
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.post(
                f"{base_url}/api/v1/cag/analyze",
                headers={"X-API-Key": api_key},
                json={
                    "document_content": doc_content,
                    "document_id": "test-doc-001",
                    "tenant_id": "test-tenant",
                    "user_id": "test-user",
                    "analysis_type": "contract"
                }
            )
            
            if response.status_code == 200:
                result = response.json()
                print(f"   ✅ Success: {result.get('success')}")
                print(f"   Engine: {result.get('engine', 'unknown')}")
                
                analysis = result.get('analysis', '')
                if analysis:
                    print(f"   Analysis preview: {analysis[:300]}...")
                
                print(f"   Execution time: {result.get('execution_time', 0):.2f}s")
            else:
                print(f"   ❌ Error: Status {response.status_code}")
                
        except Exception as e:
            print(f"   ❌ Error: {e}")
    
    # 4. Test streaming
    print("\n4. Streaming Response (CrewAI):")
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            async with client.stream(
                'POST',
                f"{base_url}/api/v1/cag/stream",
                headers={
                    "X-API-Key": api_key,
                    "Accept": "text/event-stream"
                },
                json={
                    "query": "Dame un resumen de los documentos importantes",
                    "tenant_id": "test-tenant",
                    "user_id": "test-user"
                }
            ) as response:
                print("   Streaming events:")
                event_count = 0
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        event_count += 1
                        try:
                            data = json.loads(line[6:])
                            event_type = data.get('type', 'unknown')
                            print(f"   Event #{event_count}: {event_type}")
                            
                            if event_type == 'result':
                                content = data.get('content', {})
                                if isinstance(content, dict):
                                    answer = content.get('answer', '')
                                    if answer:
                                        print(f"   Final answer: {answer[:200]}...")
                                        
                        except json.JSONDecodeError:
                            pass
                        
                        if event_count >= 5:  # Limit events shown
                            print("   ... (more events)")
                            break
                            
        except Exception as e:
            print(f"   ❌ Streaming error: {e}")
    
    print("\n" + "=" * 50)
    print("✅ CrewAI CAG Service Test Complete!")
    print("🎉 NO más reinventar la rueda - CrewAI hace TODO!")


if __name__ == "__main__":
    asyncio.run(test_crewai())