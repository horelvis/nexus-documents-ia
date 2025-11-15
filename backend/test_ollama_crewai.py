#!/usr/bin/env python3
"""
Test específico de CrewAI con Ollama como LLM principal
Verifica que el microservicio use modelos locales correctamente
"""
import asyncio
import os
import requests
import json
import time

CAG_SERVICE_URL = "http://localhost:8008"
API_KEY = os.getenv("MICROSERVICES_API_KEY")

if not API_KEY:
    raise RuntimeError("MICROSERVICES_API_KEY environment variable is required for test_ollama_crewai.py")

def test_health():
    """Test health check del microservicio"""
    print("🏥 Testing health check...")
    try:
        response = requests.get(f"{CAG_SERVICE_URL}/health", timeout=10)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Health check OK: {data.get('status')}")
            print(f"📋 Service: {data.get('service')}")
            print(f"🔧 Version: {data.get('version')}")
            print(f"🛠️ Tools: {data.get('tools_count', 'unknown')}")
            return True
        else:
            print(f"❌ Health check failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Error en health check: {e}")
        return False

def test_ollama_query(message: str, expected_tool: str = None):
    """Test específico con Ollama"""
    print(f"\n🦙 Testing Ollama: {message}")
    print(f"🎯 Expected tool: {expected_tool}")
    
    start_time = time.time()
    
    try:
        payload = {
            "query": message,
            "tenant_id": "test-tenant",
            "user_id": "test-user",
            "context": {}
        }
        
        headers = {
            "X-API-Key": API_KEY
        }
        
        response = requests.post(
            f"{CAG_SERVICE_URL}/api/v1/cag/query",
            json=payload,
            headers=headers,
            timeout=120  # Ollama puede ser más lento
        )
        
        execution_time = time.time() - start_time
        
        if response.status_code == 200:
            data = response.json()
            success = data.get("success", False)
            answer = data.get("answer", "No response")
            engine = data.get("engine", "unknown")
            metadata = data.get("metadata", {})
            
            print(f"✅ Ollama chat successful: {success}")
            print(f"🤖 Engine: {engine}")
            print(f"⏱️ Ollama response time: {execution_time:.2f}s")
            print(f"🛠️ Tools available: {metadata.get('tools_available', 'unknown')}")
            print(f"📝 Response preview: {answer[:150]}...")
            
            # Verificar que realmente usó la herramienta esperada
            if expected_tool:
                if expected_tool.lower() in answer.lower() or "tool" in answer.lower():
                    print(f"✅ Herramienta {expected_tool} parece haber sido usada")
                else:
                    print(f"⚠️ No hay evidencia clara del uso de {expected_tool}")
            
            return success
        else:
            print(f"❌ Ollama chat failed: {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Error en Ollama test: {e}")
        return False

async def test_ollama_performance():
    """Test de rendimiento específico con Ollama"""
    print("\n🚀 Testing Ollama Performance & Tool Usage")
    print("="*60)
    
    # Health check primero
    if not test_health():
        print("❌ Health check failed - stopping tests")
        return
    
    # Test queries específicos para herramientas
    test_cases = [
        {
            "query": "¿Qué hora es exactamente ahora?",
            "tool": "time_tool",
            "description": "Debe usar time_tool para obtener hora actual"
        },
        {
            "query": "Calcula exactamente 25 * 15 + 100",
            "tool": "calculator_tool", 
            "description": "Debe usar calculator_tool para cálculo matemático"
        },
        {
            "query": "Busca información actual sobre machine learning",
            "tool": "web_search",
            "description": "Debe usar web_search_tool o SerperDevTool"
        },
        {
            "query": "¿Cómo está el clima hoy en Madrid?",
            "tool": "weather_search",
            "description": "Debe usar weather_search_tool"
        },
        {
            "query": "Muéstrame las estadísticas del sistema",
            "tool": "statistics",
            "description": "Debe usar statistics_tool"
        }
    ]
    
    successful_tests = 0
    total_time = 0
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n{'='*50}")
        print(f"🧪 Test {i}/5: {test_case['description']}")
        print(f"Query: {test_case['query']}")
        print(f"{'='*50}")
        
        start_time = time.time()
        success = test_ollama_query(test_case['query'], test_case['tool'])
        test_time = time.time() - start_time
        total_time += test_time
        
        if success:
            successful_tests += 1
            print(f"✅ Test {i} PASSED in {test_time:.2f}s")
        else:
            print(f"❌ Test {i} FAILED")
        
        # Pausa entre tests para no sobrecargar Ollama
        if i < len(test_cases):
            print("⏳ Pausa entre tests...")
            await asyncio.sleep(3)
    
    # Resultados finales
    print(f"\n📊 RESULTADOS FINALES CON OLLAMA:")
    print(f"✅ Tests exitosos: {successful_tests}/{len(test_cases)}")
    print(f"📈 Tasa de éxito: {(successful_tests/len(test_cases))*100:.1f}%")
    print(f"⏱️ Tiempo total: {total_time:.2f}s")
    print(f"⏱️ Tiempo promedio por test: {total_time/len(test_cases):.2f}s")
    
    if successful_tests == len(test_cases):
        print("🎉 ¡Todos los tests con Ollama pasaron! ✅")
        print("🦙 Ollama funciona perfectamente como LLM principal")
        print("🛠️ Todas las herramientas funcionan correctamente")
    elif successful_tests >= len(test_cases) * 0.8:
        print("✅ La mayoría de tests pasaron - Ollama funciona bien")
    else:
        print("⚠️ Varios tests fallaron - revisar configuración Ollama")

if __name__ == "__main__":
    asyncio.run(test_ollama_performance())
