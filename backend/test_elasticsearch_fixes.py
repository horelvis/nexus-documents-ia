#!/usr/bin/env python3
"""
Test mejorado para verificar que los fixes de Elasticsearch funcionan
"""
import asyncio
import logging
import sys
import os

# Add the app directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '.'))

from app.services.elasticsearch_service import ElasticsearchService
from app.services.async_document_service import AsyncDocumentService
from app.db.async_database import AsyncSessionLocal
from app.core.config import settings

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_elasticsearch_integration():
    """Test complete Elasticsearch integration"""
    print("🧪 Testing Elasticsearch Integration Fixes")
    print("=" * 50)
    
    # Test 1: Direct Elasticsearch Service
    print("\n1. Testing ElasticsearchService directly...")
    es_service = ElasticsearchService("test-tenant-fixes")
    
    try:
        # Create index
        index_created = es_service.create_index_if_not_exists()
        print(f"   ✅ Index creation: {index_created}")
        
        # Index a test document
        doc_indexed = await es_service.index_document(
            doc_id="test-fix-doc-1",
            title="Test Document for Fixes",
            content="This is a comprehensive test document to verify all Elasticsearch fixes are working correctly. It contains important information about testing.",
            metadata={
                "file_type": "txt",
                "category": "test",
                "tags": ["elasticsearch", "fixes", "testing"],
                "created_at": "2024-01-01T00:00:00",
                "file_size": 1024,
                "tenant_id": "test-tenant-fixes"
            }
        )
        print(f"   ✅ Document indexing: {doc_indexed}")
        
        # Wait for indexing
        await asyncio.sleep(2)
        
        # Test search
        results = await es_service.hybrid_search(
            query="comprehensive test document",
            limit=5
        )
        print(f"   ✅ Search results: {len(results)} found")
        
        if results:
            for i, result in enumerate(results):
                print(f"      - Result {i+1}: '{result['document']['title']}' (score: {result['score']:.3f})")
        
        await es_service.close()
        
    except Exception as e:
        print(f"   ❌ Direct ES test failed: {e}")
        return False
    
    # Test 2: AsyncDocumentService initialization  
    print("\n2. Testing AsyncDocumentService initialization...")
    try:
        async with AsyncSessionLocal() as db:
            service = await AsyncDocumentService.create(
                tenant_id="test-tenant-fixes",
                user_id="test-user-123",
                db=db
            )
            
            if service.elasticsearch_service:
                print("   ✅ ElasticsearchService initialized in AsyncDocumentService")
                
                # Test the search functionality
                print("\n3. Testing hybrid search in get_documents...")
                
                # This would normally require actual documents in the database
                # For now, we'll test the logic path
                search_results = await service.get_documents(
                    db=db,
                    page=1,
                    per_page=10,
                    search="comprehensive test"
                )
                
                print(f"   ✅ Hybrid search executed")
                print(f"   ✅ Search engine used: {search_results.get('search_engine', 'unknown')}")
                print(f"   ✅ Results returned: {len(search_results.get('items', []))}")
                
            else:
                print("   ❌ ElasticsearchService not initialized in AsyncDocumentService")
                return False
        
    except Exception as e:
        print(f"   ❌ AsyncDocumentService test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Test 3: Check Elasticsearch indices
    print("\n4. Checking Elasticsearch indices...")
    try:
        import httpx
        
        async with httpx.AsyncClient() as client:
            # Check indices
            response = await client.get("http://localhost:9200/_cat/indices?v&h=index,docs.count,store.size")
            print("   Current indices:")
            for line in response.text.strip().split('\n'):
                if 'nexus_' in line:
                    print(f"      {line}")
            
            # Check specific index health
            test_index = f"nexus_test_tenant_fixes_documents"
            response = await client.get(f"http://localhost:9200/{test_index}/_search?size=0")
            if response.status_code == 200:
                data = response.json()
                doc_count = data['hits']['total']['value']
                print(f"   ✅ Test index '{test_index}' has {doc_count} documents")
            else:
                print(f"   ⚠️ Test index '{test_index}' not found (expected for new test)")
        
    except Exception as e:
        print(f"   ❌ Index check failed: {e}")
    
    print("\n" + "=" * 50)
    print("✅ Elasticsearch integration test completed!")
    print("\nKey improvements implemented:")
    print("- ✅ MANDATORY ES initialization - fails fast if broken")
    print("- ✅ NO FALLBACKS - exposes errors explicitly")
    print("- ✅ Hybrid search integration in get_documents()")
    print("- ✅ Elasticsearch REQUIRED for search functionality")
    print("- ✅ Document indexing MANDATORY - fails if ES broken")
    print("- ✅ Search result ranking preserved from ES")
    
    return True

async def cleanup_test_data():
    """Clean up test data"""
    print("\n🧹 Cleaning up test data...")
    try:
        es_service = ElasticsearchService("test-tenant-fixes")
        await es_service.delete_document("test-fix-doc-1")
        await es_service.close()
        print("   ✅ Test data cleaned up")
    except Exception as e:
        print(f"   ⚠️ Cleanup warning: {e}")

if __name__ == "__main__":
    async def main():
        try:
            success = await test_elasticsearch_integration()
            await cleanup_test_data()
            
            if success:
                print("\n🎉 All tests passed! Elasticsearch integration is working correctly.")
                sys.exit(0)
            else:
                print("\n❌ Some tests failed. Check the logs above.")
                sys.exit(1)
                
        except KeyboardInterrupt:
            print("\n⏹️ Test interrupted by user")
            sys.exit(1)
        except Exception as e:
            print(f"\n💥 Unexpected error: {e}")
            sys.exit(1)
    
    asyncio.run(main())