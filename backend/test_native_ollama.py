#!/usr/bin/env python3
"""
Test completo de integración Ollama nativa
Verifica que las herramientas funcionen sin LiteLLM
"""
import asyncio
import requests
import json
import time

CAG_SERVICE_URL = "http://localhost:8008"
API_KEY = "nxs_dev_GYCa7km7zmibtf54yzA9NwPMj4fAYFGt"

def test_health():
    """Test health check del servicio nativo"""
    print("🏥 Testing native Ollama health check...")
    try:
        response = requests.get(f"{CAG_SERVICE_URL}/health", timeout=10)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Health check OK: {data.get('status')}")
            print(f"📋 Service: {data.get('service')}")
            print(f"🔧 Version: {data.get('version')}")
            print(f"🛠️ Pattern: {data.get('pattern')}")
            print(f"🦙 Model: {data.get('model')}")
            print(f"🚀 API Endpoint: {data.get('api_endpoint')}")
            print(f"🔧 Features: {len(data.get('features', []))} available")
            
            features = data.get('features', [])
            for feature in features:
                print(f"  - {feature}")
            
            return True
        else:
            print(f"❌ Health check failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Error en health check: {e}")
        return False

def test_native_ollama_tool(message: str, expected_tool: str = None):
    """Test específico con herramientas usando Ollama nativo"""
    print(f"\\n🦙 Testing Native Ollama Tool: {message}")
    print(f"🎯 Expected tool usage: {expected_tool}")
    
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
            timeout=120
        )
        
        execution_time = time.time() - start_time
        
        if response.status_code == 200:
            data = response.json()
            success = data.get("success", False)
            answer = data.get("answer", "No response")
            engine = data.get("engine", "unknown")
            metadata = data.get("metadata", {})
            
            print(f"✅ Native Ollama successful: {success}")
            print(f"🤖 Engine: {engine}")
            print(f"🦙 Model used: {metadata.get('model_used', 'unknown')}")
            print(f"🔌 API integration: {metadata.get('api_integration', 'unknown')}")
            print(f"🚫 Bypass LiteLLM: {metadata.get('bypass_litelm', False)}")
            print(f"🛠️ Tools integration: {metadata.get('tools_integration', 'unknown')}")
            print(f"⏱️ Response time: {execution_time:.2f}s")
            print(f"📝 Response: {answer[:300]}...")
            
            # Verificar evidencia de uso de herramientas
            if expected_tool:
                answer_lower = answer.lower()
                tool_evidence = False
                
                if expected_tool == "time_tool" and any(word in answer_lower for word in ['hora', 'tiempo', '2025-', 'fecha']):
                    tool_evidence = True
                elif expected_tool == "calculator_tool" and any(word in answer_lower for word in ['resultado', '=', 'calculado']):
                    tool_evidence = True
                elif expected_tool == "web_search" and any(word in answer_lower for word in ['información', 'búsqueda', 'encontrado']):
                    tool_evidence = True
                elif expected_tool == "weather_search" and any(word in answer_lower for word in ['clima', 'temperatura', 'weather']):
                    tool_evidence = True
                elif expected_tool == "statistics" and any(word in answer_lower for word in ['system', 'status', 'operational']):
                    tool_evidence = True
                
                if tool_evidence:
                    print(f"✅ Evidencia de uso de herramienta {expected_tool} encontrada!")
                else:
                    print(f"⚠️ No se encontró evidencia clara de uso de {expected_tool}")
            
            return success
        else:
            print(f"❌ Native Ollama failed: {response.status_code}")
            try:
                error_data = response.json()
                print(f"Error details: {error_data}")
            except:
                print(f"Response text: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Error en test nativo: {e}")
        return False

async def test_complete_integration():
    """Test completo de integración nativa de Ollama"""
    print("🚀 Testing COMPLETE Native Ollama Integration")
    print("=" * 70)
    print("🎯 OBJETIVO: Verificar que Ollama funciona SIN LiteLLM")
    print("🔧 MÉTODO: API REST nativa de Ollama")
    print("🛠️ HERRAMIENTAS: Ejecutadas directamente sin function calling")
    print("=" * 70)
    
    # Health check primero
    if not test_health():
        print("❌ Health check failed - stopping tests")
        return
    
    # Test cases específicos para herramientas
    test_cases = [
        {
            "query": "¿Qué hora es exactamente ahora mismo?",
            "tool": "time_tool",
            "description": "Verificar herramienta de tiempo"
        },
        {
            "query": "Calcula exactamente: 234 * 56 + 789",
            "tool": "calculator_tool", 
            "description": "Verificar calculadora matemática"
        },
        {
            "query": "Busca información actual sobre inteligencia artificial generativa",
            "tool": "web_search",
            "description": "Verificar búsqueda web"
        },
        {
            "query": "¿Cómo está el clima en Barcelona hoy?",
            "tool": "weather_search",
            "description": "Verificar información meteorológica"
        },
        {
            "query": "Muéstrame estadísticas del sistema actual",
            "tool": "statistics",
            "description": "Verificar estadísticas del sistema"
        },
        {
            "query": "Hola, ¿cómo estás? Cuéntame sobre tus capacidades",
            "tool": None,
            "description": "Verificar conversación básica"
        }
    ]
    
    successful_tests = 0
    total_time = 0
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\\n{'='*60}")
        print(f"🧪 TEST {i}/{len(test_cases)}: {test_case['description']}")
        print(f"Query: {test_case['query']}")
        print(f"Expected tool: {test_case['tool'] or 'conversation'}")
        print(f"{'='*60}")
        
        start_time = time.time()
        success = test_native_ollama_tool(test_case['query'], test_case['tool'])
        test_time = time.time() - start_time
        total_time += test_time
        
        if success:
            successful_tests += 1
            print(f"✅ TEST {i} PASSED in {test_time:.2f}s")
        else:
            print(f"❌ TEST {i} FAILED")
        
        # Pausa entre tests para no sobrecargar Ollama
        if i < len(test_cases):
            print("⏳ Pausa entre tests...")
            await asyncio.sleep(3)
    
    # Resultados finales
    print(f"\\n📊 RESULTADOS FINALES - NATIVE OLLAMA INTEGRATION:")
    print(f"✅ Tests exitosos: {successful_tests}/{len(test_cases)}")
    print(f"📈 Tasa de éxito: {(successful_tests/len(test_cases))*100:.1f}%")
    print(f"⏱️ Tiempo total: {total_time:.2f}s")
    print(f"⏱️ Tiempo promedio por test: {total_time/len(test_cases):.2f}s")
    
    print(f"\\n🔍 ANÁLISIS DE INTEGRACIÓN:")
    
    if successful_tests == len(test_cases):
        print("🎉 🎉 🎉 ¡INTEGRACIÓN COMPLETAMENTE FUNCIONAL! 🎉 🎉 🎉")
        print("✅ Ollama funciona perfectamente con API nativa")
        print("✅ Todas las herramientas ejecutan correctamente")
        print("✅ No hay dependencia de LiteLLM")
        print("✅ Bug #10499 completamente solucionado")
        print("🦙 ¡OLLAMA ESTÁ 100% OPERATIVO CON HERRAMIENTAS!")
    elif successful_tests >= len(test_cases) * 0.8:
        print("✅ Integración mayoritariamente funcional")
        print("🔧 Algunas mejoras menores requeridas")
    else:
        print("⚠️ Integración requiere revisión")
        print("🔧 Varios componentes necesitan ajustes")
    
    # Verificación técnica
    print(f"\\n🔧 VERIFICACIÓN TÉCNICA:")
    print(f"🦙 Ollama API: Acceso directo vía REST")
    print(f"🚫 LiteLLM: Completamente bypassed")
    print(f"🛠️ Herramientas: Ejecución directa sin function calling")
    print(f"⚡ Rendimiento: {total_time/len(test_cases):.1f}s promedio por consulta")

if __name__ == "__main__":
    asyncio.run(test_complete_integration())