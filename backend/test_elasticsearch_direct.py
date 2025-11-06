#!/usr/bin/env python3
"""
Test directo de la integración de Elasticsearch
"""
import asyncio
import logging
from app.services.elasticsearch_service import ElasticsearchService

logging.basicConfig(level=logging.INFO)

async def test_elasticsearch():
    # Crear servicio con tenant de prueba
    es_service = ElasticsearchService("test-tenant-12345")
    
    print("🔧 Testing Elasticsearch Service...")
    
    # 1. Test crear índice
    print("1. Creating index...")
    index_created = es_service.create_index_if_not_exists()
    print(f"   Index created: {index_created}")
    
    # 2. Test indexar documento
    print("2. Indexing test document...")
    doc_indexed = await es_service.index_document(
        doc_id="test-doc-123",
        title="Test Document",
        content="This is a test document with some content to search.",
        metadata={
            "file_type": "txt",
            "category": "test",
            "tags": ["test", "elasticsearch"],
            "created_at": "2024-01-01T00:00:00",
            "file_size": 1024
        }
    )
    print(f"   Document indexed: {doc_indexed}")
    
    # 3. Test búsqueda
    print("3. Testing search...")
    await asyncio.sleep(2)  # Wait for indexing
    results = await es_service.hybrid_search(
        query="test document",
        limit=5
    )
    print(f"   Search results: {len(results)} found")
    for i, result in enumerate(results):
        print(f"   - Result {i+1}: {result['document']['title']} (score: {result['score']})")
    
    # 4. Test analytics
    print("4. Testing analytics...")
    analytics = await es_service.get_analytics()
    print(f"   Total documents: {analytics.get('total_documents', 0)}")
    
    # 5. Cleanup
    print("5. Cleaning up...")
    deleted = await es_service.delete_document("test-doc-123")
    print(f"   Document deleted: {deleted}")
    
    await es_service.close()
    print("✅ Test completed!")

if __name__ == "__main__":
    asyncio.run(test_elasticsearch())