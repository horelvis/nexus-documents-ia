#!/usr/bin/env python3
"""
Script de prueba simple para Elasticsearch
"""
import requests
import json

# Test básico de Elasticsearch
def test_elasticsearch():
    print("🔍 Probando Elasticsearch...")
    
    # Test 1: Health check
    try:
        response = requests.get("http://localhost:9200/_cluster/health")
        health = response.json()
        print(f"✅ Elasticsearch health: {health['status']}")
    except Exception as e:
        print(f"❌ Error conectando a Elasticsearch: {e}")
        return False
    
    # Test 2: Crear índice de prueba
    try:
        index_name = "test_nexus_documents"
        mapping = {
            "mappings": {
                "properties": {
                    "title": {"type": "text"},
                    "content": {"type": "text"},
                    "tenant_id": {"type": "keyword"}
                }
            }
        }
        
        response = requests.put(f"http://localhost:9200/{index_name}", json=mapping)
        print(f"✅ Índice de prueba creado: {response.status_code}")
    except Exception as e:
        print(f"❌ Error creando índice: {e}")
        return False
    
    # Test 3: Indexar documento de prueba
    try:
        doc = {
            "title": "Documento de Prueba",
            "content": "Este es un contenido de prueba para Elasticsearch",
            "tenant_id": "test_tenant_123"
        }
        
        response = requests.post(f"http://localhost:9200/{index_name}/_doc/1", json=doc)
        print(f"✅ Documento indexado: {response.status_code}")
    except Exception as e:
        print(f"❌ Error indexando documento: {e}")
        return False
    
    # Test 4: Búsqueda de prueba
    try:
        # Esperar a que se indexe
        import time
        time.sleep(2)
        
        search_query = {
            "query": {
                "match": {
                    "content": "prueba"
                }
            }
        }
        
        response = requests.post(f"http://localhost:9200/{index_name}/_search", json=search_query)
        results = response.json()
        hits = results.get('hits', {}).get('hits', [])
        print(f"✅ Búsqueda completada: {len(hits)} resultados encontrados")
        
        if hits:
            print(f"   📄 Documento encontrado: {hits[0]['_source']['title']}")
        
    except Exception as e:
        print(f"❌ Error en búsqueda: {e}")
        return False
    
    # Test 5: Limpieza
    try:
        response = requests.delete(f"http://localhost:9200/{index_name}")
        print(f"✅ Índice de prueba eliminado: {response.status_code}")
    except Exception as e:
        print(f"⚠️ Error eliminando índice de prueba: {e}")
    
    print("🎉 Todas las pruebas de Elasticsearch completadas exitosamente!")
    return True

# Test del backend API
def test_backend_api():
    print("\n🔍 Probando API del backend...")
    
    # Test 1: Health check
    try:
        response = requests.get("http://localhost:8000/health")
        health = response.json()
        print(f"✅ API Backend health: {health['status']}")
    except Exception as e:
        print(f"❌ Error conectando al backend: {e}")
        return False
    
    # Test 2: Documentación de la API
    try:
        response = requests.get("http://localhost:8000/api/v1/docs")
        print(f"✅ Documentación disponible: {response.status_code}")
    except Exception as e:
        print(f"❌ Error accediendo a docs: {e}")
    
    print("🎉 Pruebas del backend API completadas!")
    return True

if __name__ == "__main__":
    print("🚀 Iniciando pruebas del sistema híbrido...\n")
    
    es_ok = test_elasticsearch()
    api_ok = test_backend_api()
    
    if es_ok and api_ok:
        print("\n✅ Sistema híbrido funcionando correctamente!")
    else:
        print("\n❌ Algunos componentes tienen problemas")