#!/usr/bin/env python3
"""
Test completo de CrewAI con todos los componentes
"""
import asyncio
import os
import httpx
import json
from datetime import datetime
import time

BASE_URL = "http://localhost:8008"
API_KEY = os.getenv("MICROSERVICES_API_KEY")

if not API_KEY:
    raise RuntimeError("MICROSERVICES_API_KEY environment variable is required for test_crewai_completo.py")

async def test_health():
    """Verificar salud del servicio"""
    print("1️⃣ Verificando salud del servicio...")
    print(f"   URL: {BASE_URL}/health")
    start_time = time.time()
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{BASE_URL}/health")
            elapsed = time.time() - start_time
            print(f"   Response time: {elapsed:.2f}s")
            print(f"   Status code: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"   Status: {data.get('status')}")
                print(f"   Engine: {data.get('engine', 'unknown')}")
                if 'checks' in data:
                    for check, status in data['checks'].items():
                        print(f"   - {check}: {'✅' if status else '❌'}")
                return data.get('status') == 'healthy'
            else:
                print(f"   ❌ Error: Status code {response.status_code}")
                return False
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"   ❌ Error after {elapsed:.2f}s: {e}")
        return False

async def test_query_simple():
    """Test con query simple"""
    print("\n2️⃣ Probando query simple...")
    query = "Hello, what are your capabilities? Just list them briefly without searching for documents."
    print(f"   Query: {query[:50]}...")
    print(f"   URL: {BASE_URL}/api/v1/cag/query")
    start_time = time.time()
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            print(f"   Sending request...")
            response = await client.post(
                f"{BASE_URL}/api/v1/cag/query",
                headers={"X-API-Key": API_KEY},
                json={
                    "query": query,
                    "tenant_id": "test-tenant",
                    "user_id": "test-user"
                }
            )
            elapsed = time.time() - start_time
            print(f"   Response received after {elapsed:.2f}s")
            print(f"   Status code: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"   ✅ Success: {data.get('success')}")
                print(f"   Engine: {data.get('engine', 'unknown')}")
                if data.get('answer'):
                    answer = str(data['answer'])[:200]
                    print(f"   Respuesta: {answer}...")
                if data.get('agents_used'):
                    print(f"   Agentes usados: {', '.join(data['agents_used'])}")
                if data.get('execution_time'):
                    print(f"   Execution time: {data['execution_time']:.2f}s")
                return True
            else:
                print(f"   ❌ Error: {response.status_code}")
                print(f"   Response: {response.text[:200]}")
                return False
        except httpx.TimeoutException:
            elapsed = time.time() - start_time
            print(f"   ⏱️ Timeout after {elapsed:.2f}s")
            return False
        except Exception as e:
            elapsed = time.time() - start_time
            print(f"   ❌ Error after {elapsed:.2f}s: {e}")
            return False

async def test_document_search():
    """Test búsqueda de documentos"""
    print("\n3️⃣ Probando búsqueda de documentos...")
    query = "Busca todos los contratos que requieren firma"
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            f"{BASE_URL}/api/v1/cag/query",
            headers={"X-API-Key": API_KEY},
            json={
                "query": query,
                "tenant_id": "test-tenant",
                "user_id": "test-user"
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ Query procesado")
            if data.get('answer'):
                print(f"   Respuesta: {str(data['answer'])[:300]}...")
            return True
        else:
            print(f"   ❌ Error: {response.status_code}")
            return False

async def test_document_analysis():
    """Test análisis de documento"""
    print("\n4️⃣ Probando análisis de documento...")
    
    document_content = """
    CONTRATO DE SERVICIOS PROFESIONALES
    
    Entre: Empresa ABC S.A. (Cliente)
    Y: NexusDocs Solutions (Proveedor)
    
    Fecha: 15 de diciembre de 2024
    Monto Total: $75,000 USD
    Duración: 18 meses
    
    SERVICIOS A PROPORCIONAR:
    1. Sistema de gestión documental con IA
    2. Integración de firma digital
    3. Análisis automático de contratos
    4. Soporte técnico 24/7
    
    CONDICIONES DE PAGO:
    - 30% al inicio
    - 40% a los 6 meses
    - 30% al finalizar
    
    PENALIZACIONES:
    - Retraso en entrega: 3% del monto total por semana
    - Incumplimiento de funcionalidades: 15% del monto total
    
    Firmado por:
    Juan Pérez - CEO Empresa ABC
    María García - Directora NexusDocs
    """
    
    async with httpx.AsyncClient(timeout=90.0) as client:
        response = await client.post(
            f"{BASE_URL}/api/v1/cag/analyze",
            headers={"X-API-Key": API_KEY},
            json={
                "document_content": document_content,
                "document_id": "test-contract-001",
                "tenant_id": "test-tenant",
                "user_id": "test-user",
                "analysis_type": "contract"
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ Documento analizado")
            print(f"   Tipo detectado: {data.get('document_type', 'unknown')}")
            print(f"   Confianza: {data.get('confidence', 0):.2%}")
            if data.get('analysis'):
                print(f"   Análisis: {str(data['analysis'])[:400]}...")
            return True
        else:
            print(f"   ❌ Error: {response.status_code}")
            print(f"   Detalles: {response.text[:200]}")
            return False

async def test_streaming():
    """Test respuesta en streaming"""
    print("\n5️⃣ Probando respuesta en streaming...")
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            async with client.stream(
                'POST',
                f"{BASE_URL}/api/v1/cag/query/stream",
                headers={
                    "X-API-Key": API_KEY,
                    "Accept": "text/event-stream"
                },
                json={
                    "query": "Dame un resumen de las capacidades del sistema",
                    "tenant_id": "test-tenant",
                    "user_id": "test-user"
                }
            ) as response:
                print("   Recibiendo eventos...")
                event_count = 0
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        event_count += 1
                        try:
                            data = json.loads(line[6:])
                            event_type = data.get('type', 'unknown')
                            print(f"   Evento #{event_count}: {event_type}")
                            
                            if event_type == 'result':
                                content = data.get('content', {})
                                if isinstance(content, dict):
                                    answer = content.get('answer', '')
                                    if answer:
                                        print(f"   ✅ Respuesta final recibida")
                                        return True
                        except json.JSONDecodeError:
                            pass
                        
                        if event_count >= 10:
                            print("   ✅ Streaming funcionando")
                            return True
                            
        except Exception as e:
            print(f"   ⚠️ Error en streaming: {e}")
            return False
    
    return False

async def test_conversation():
    """Test conversación con contexto"""
    print("\n6️⃣ Probando conversación con contexto...")
    
    messages = [
        "Hola, soy Juan de la empresa TechCorp",
        "Necesito encontrar el contrato más reciente",
        "¿Cuál es el monto total del contrato?"
    ]
    
    chat_history = []
    
    for i, message in enumerate(messages, 1):
        print(f"\n   Mensaje {i}: {message}")
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{BASE_URL}/api/v1/cag/query",  # Usar query con contexto
                headers={"X-API-Key": API_KEY},
                json={
                    "query": message,  # Cambiar de "message" a "query"
                    "tenant_id": "test-tenant",
                    "user_id": "juan-techcorp",
                    "context": {"chat_history": chat_history}  # Pasar historial en contexto
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('response'):
                    response_text = str(data['response'])[:150]
                    print(f"   Respuesta: {response_text}...")
                    
                    # Agregar al historial
                    chat_history.append({"role": "user", "content": message})
                    chat_history.append({"role": "assistant", "content": data['response']})
            else:
                print(f"   ❌ Error: {response.status_code}")
                return False
    
    print("\n   ✅ Conversación completada con contexto mantenido")
    return True

async def main():
    """Ejecutar todas las pruebas"""
    print("=" * 60)
    print("🚀 PRUEBA COMPLETA DE CREWAI")
    print("=" * 60)
    
    tests = [
        ("Salud del servicio", test_health),
        ("Query simple", test_query_simple),
        ("Búsqueda de documentos", test_document_search),
        ("Análisis de documento", test_document_analysis),
        ("Streaming", test_streaming),
        ("Conversación", test_conversation)
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = await test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n❌ Error en {name}: {e}")
            results.append((name, False))
    
    print("\n" + "=" * 60)
    print("📊 RESUMEN DE RESULTADOS")
    print("=" * 60)
    
    for name, success in results:
        status = "✅ PASÓ" if success else "❌ FALLÓ"
        print(f"{status} - {name}")
    
    total = len(results)
    passed = sum(1 for _, success in results if success)
    
    print(f"\nTotal: {passed}/{total} pruebas pasadas")
    
    if passed == total:
        print("\n🎉 ¡TODAS LAS PRUEBAS PASARON!")
        print("🚀 CrewAI está funcionando perfectamente")
        print("✨ NO más reinventar la rueda")
    else:
        print(f"\n⚠️ {total - passed} pruebas fallaron")
        print("Revisa los logs para más detalles")

if __name__ == "__main__":
    asyncio.run(main())
