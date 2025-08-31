#!/usr/bin/env python3
"""
Test del microservicio CAG con implementación funcional de CrewAI
"""
import asyncio
import requests
import json

CAG_SERVICE_URL = "http://localhost:8008"

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

def test_chat_endpoint(message: str):
    """Test del endpoint de chat"""
    print(f"\n💬 Testing chat: {message}")
    try:
        payload = {
            "query": message,
            "tenant_id": "test-tenant",
            "user_id": "test-user",
            "context": {}
        }
        
        headers = {
            "X-API-Key": "nxs_dev_GYCa7km7zmibtf54yzA9NwPMj4fAYFGt"
        }
        
        response = requests.post(
            f"{CAG_SERVICE_URL}/api/v1/cag/query",
            json=payload,
            headers=headers,
            timeout=60
        )
        
        if response.status_code == 200:
            data = response.json()
            success = data.get("success", False)
            answer = data.get("answer", "No response")
            engine = data.get("engine", "unknown")
            execution_time = data.get("execution_time", 0)
            
            print(f"✅ Chat successful: {success}")
            print(f"🤖 Engine: {engine}")
            print(f"⏱️ Time: {execution_time:.2f}s")
            print(f"📝 Response: {answer[:200]}...")
            
            return success
        else:
            print(f"❌ Chat failed: {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Error en chat: {e}")
        return False

async def main():
    """Test principal del microservicio funcional"""
    print("🚀 Testing Microservicio CAG con Implementación Funcional")
    print("="*60)
    
    # Test 1: Health check
    if not test_health():
        print("❌ Health check failed - stopping tests")
        return
    
    # Test 2: Chat queries
    test_queries = [
        "¿Qué hora es?",
        "Calcula 15 * 12 + 30",
        "Busca información sobre inteligencia artificial",
        "¿Cuál es el clima en Barcelona?"
    ]
    
    successful_tests = 0
    total_tests = len(test_queries)
    
    for query in test_queries:
        if test_chat_endpoint(query):
            successful_tests += 1
        await asyncio.sleep(2)  # Pausa entre tests
    
    print(f"\n📊 RESULTADOS:")
    print(f"✅ Tests exitosos: {successful_tests}/{total_tests}")
    print(f"📈 Tasa de éxito: {(successful_tests/total_tests)*100:.1f}%")
    
    if successful_tests == total_tests:
        print("🎉 ¡Todos los tests pasaron! Implementación funcional OK")
    else:
        print("⚠️ Algunos tests fallaron - revisar implementación")

if __name__ == "__main__":
    asyncio.run(main())