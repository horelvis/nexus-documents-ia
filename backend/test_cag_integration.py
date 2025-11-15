#!/usr/bin/env python3
"""
Script de prueba para CAG integration
Ejecutar dentro del contenedor API
"""
import asyncio
import os
import httpx
import json

API_KEY = os.getenv("MICROSERVICES_API_KEY")

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
    
    # Crear usuario fake
    user = FakeUser()
    
    # Crear request simple
    document_content = """
        CONTRATO DE PRESTACIÓN DE SERVICIOS
        
        Entre ABC Corp y XYZ Consulting
        
        Objeto: Servicios de consultoría en IA
        Duración: 6 meses
        Valor: $50,000 USD
        Fecha: 5 de agosto de 2025
        """
    
    print(f"Documento: {document_content[:100]}...")
    print("\nEnviando a CAG para análisis...")
    
    try:
        # Simular la llamada al endpoint
        # En producción esto sería a través de HTTP
        async def mock_analyze():
            # Aquí normalmente iría la lógica del endpoint
            # Por ahora solo verificamos que CAG esté disponible
            import httpx
            
            async with httpx.AsyncClient() as client:
                # Verificar que LangGraph esté activo
                response = await client.get(
                    "http://langgraph-service:8007/health",
                    headers={"X-API-Key": API_KEY}
                )
                
                if response.status_code == 200:
                    print("\n✅ LangGraph service está activo")
                    health = response.json()
                    print(f"Estado: {health}")
                    
                    # Ahora probar CAG directamente
                    cag_request = {
                        "graph_type": "cag",
                        "input_data": {
                            "query": f"Analiza este contrato: {document_content}",
                            "tenant_id": str(user.tenant_id),
                            "user_id": str(user.id)
                        },
                        "tenant_id": str(user.tenant_id)
                    }
                    
                    print("\n📤 Enviando a CAG...")
                    response = await client.post(
                        "http://langgraph-service:8007/api/v1/graphs/run",
                        json=cag_request,
                        headers={"X-API-Key": API_KEY},
                        timeout=30.0
                    )
                    
                    if response.status_code == 200:
                        result = response.json()
                        print("\n✅ CAG procesó exitosamente!")
                        print(f"Run ID: {result.get('run_id')}")
                        print(f"Estado: {result.get('status')}")
                        print(f"Tiempo: {result.get('execution_time', 0):.2f}s")
                        
                        if 'final_state' in result:
                            state = result['final_state']
                            if 'final_answer' in state:
                                print(f"\n📝 Respuesta del CAG:")
                                print("-" * 50)
                                print(state['final_answer'][:500])
                                print("-" * 50)
                    else:
                        print(f"\n❌ Error en CAG: {response.status_code}")
                        print(response.text[:200])
                else:
                    print(f"\n❌ LangGraph service no está disponible: {response.status_code}")
        
        await mock_analyze()
        
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()


async def test_chat_with_cag():
    """Probar chat con CAG"""
    print("\n\n=== Prueba de Chat con CAG ===\n")
    
    user = FakeUser()
    
    try:
        import httpx
        
        async with httpx.AsyncClient() as client:
            chat_request = {
                "graph_type": "cag",
                "input_data": {
                    "query": "¿Qué tipos de contratos puedes analizar?",
                    "tenant_id": str(user.tenant_id),
                    "user_id": str(user.id)
                },
                "tenant_id": str(user.tenant_id)
            }
            
            print("Pregunta: ¿Qué tipos de contratos puedes analizar?")
            print("\n📤 Enviando a CAG...")
            
            response = await client.post(
                "http://langgraph-service:8007/api/v1/graphs/run",
                json=chat_request,
                headers={"X-API-Key": API_KEY},
                timeout=30.0
            )
            
            if response.status_code == 200:
                result = response.json()
                print("\n✅ Respuesta recibida!")
                
                if 'final_state' in result and 'final_answer' in result['final_state']:
                    print(f"\n🤖 CAG responde:")
                    print("-" * 50)
                    print(result['final_state']['final_answer'][:500])
                    print("-" * 50)
            else:
                print(f"\n❌ Error: {response.status_code}")
                
    except Exception as e:
        print(f"\n❌ Error en chat: {str(e)}")


async def main():
    """Ejecutar todas las pruebas"""
    print("🧪 Iniciando pruebas de integración CAG\n")
    
    # Probar análisis de documentos
    await test_document_analysis()
    
    # Probar chat
    await test_chat_with_cag()
    
    print("\n\n✅ Pruebas completadas!")


if __name__ == "__main__":
    asyncio.run(main())
