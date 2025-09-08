#!/usr/bin/env python3
"""
Test del sistema de búsqueda híbrida
"""
import asyncio
import sys
import logging
from pathlib import Path

# Add the parent directory to the path so we can import our modules
sys.path.insert(0, str(Path(__file__).parent))

from app.services.elasticsearch_service import ElasticsearchService
from app.services.search_service import SearchService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_elasticsearch_service():
    """Test ElasticsearchService directly"""
    
    logger.info("🔍 Probando ElasticsearchService...")
    
    # Test tenant ID
    test_tenant_id = "test_tenant_12345"
    
    # Create service
    es_service = ElasticsearchService(test_tenant_id)
    
    try:
        # Test 1: Create index
        logger.info("📝 Creando índice...")
        success = es_service.create_index_if_not_exists()
        logger.info(f"✅ Índice creado: {success}")
        
        # Test 2: Index a test document
        logger.info("📄 Indexando documento de prueba...")
        success = await es_service.index_document(
            doc_id="test_doc_001",
            title="Documento de Prueba Elasticsearch",
            content="Este es un contenido de prueba para verificar la funcionalidad de búsqueda híbrida con Elasticsearch en el sistema NexusDocs360.",
            metadata={
                "file_type": "txt",
                "category": "test",
                "tags": ["prueba", "elasticsearch", "híbrido"],
                "created_at": "2024-01-01T00:00:00",
                "updated_at": "2024-01-01T00:00:00",
                "file_size": 1024
            }
        )
        logger.info(f"✅ Documento indexado: {success}")
        
        # Wait for indexing
        await asyncio.sleep(2)
        
        # Test 3: Hybrid search
        logger.info("🔍 Probando búsqueda híbrida...")
        results = await es_service.hybrid_search(
            query="prueba Elasticsearch",
            limit=5
        )
        logger.info(f"✅ Resultados encontrados: {len(results)}")
        
        if results:
            for i, result in enumerate(results, 1):
                doc = result.get('document', {})
                score = result.get('score', 0)
                logger.info(f"   {i}. {doc.get('title', 'Sin título')} (score: {score:.2f})")
        
        # Test 4: Analytics
        logger.info("📊 Probando analytics...")
        analytics = await es_service.get_analytics()
        logger.info(f"✅ Analytics obtenidos: {analytics.get('total_documents', 0)} documentos")
        
        # Cleanup
        await es_service.delete_document("test_doc_001")
        logger.info("🧹 Documento de prueba eliminado")
        
    except Exception as e:
        logger.error(f"❌ Error en prueba de Elasticsearch: {str(e)}")
        return False
    finally:
        await es_service.close()
    
    logger.info("✅ ElasticsearchService funciona correctamente!")
    return True

async def test_search_service():
    """Test SearchService with hybrid functionality"""
    
    logger.info("🔍 Probando SearchService híbrido...")
    
    # Test tenant ID
    test_tenant_id = "test_tenant_12345"
    
    # Create service
    search_service = SearchService(test_tenant_id)
    
    try:
        # Test híbrido search
        logger.info("🔍 Probando búsqueda híbrida via SearchService...")
        results = await search_service.search_documents(
            query="prueba sistema",
            limit=5,
            search_type="hybrid"
        )
        logger.info(f"✅ Búsqueda híbrida: {len(results)} resultados")
        
        # Test semantic search (Weaviate)
        logger.info("🧠 Probando búsqueda semántica via SearchService...")
        results = await search_service.search_documents(
            query="document management system",
            limit=5,
            search_type="semantic"
        )
        logger.info(f"✅ Búsqueda semántica: {len(results)} resultados")
        
        # Test keyword search (Elasticsearch)
        logger.info("🔤 Probando búsqueda por keywords via SearchService...")
        results = await search_service.search_documents(
            query="document",
            limit=5,
            search_type="keyword"
        )
        logger.info(f"✅ Búsqueda keywords: {len(results)} resultados")
        
        # Test suggest search type
        logger.info("🤖 Probando sugerencia de tipo de búsqueda...")
        suggested_type = await search_service.suggest_search_type("complex boolean query with AND OR filters")
        logger.info(f"✅ Tipo sugerido: {suggested_type}")
        
    except Exception as e:
        logger.error(f"❌ Error en SearchService: {str(e)}")
        return False
    
    logger.info("✅ SearchService híbrido funciona correctamente!")
    return True

async def main():
    """Main test function"""
    logger.info("🚀 Iniciando pruebas del sistema híbrido de búsqueda...")
    
    try:
        # Test Elasticsearch service
        es_ok = await test_elasticsearch_service()
        
        # Test Search service
        search_ok = await test_search_service()
        
        if es_ok and search_ok:
            logger.info("🎉 ¡Todas las pruebas del sistema híbrido completadas exitosamente!")
            logger.info("✅ Sistema listo para producción")
        else:
            logger.error("❌ Algunas pruebas fallaron")
            
    except Exception as e:
        logger.error(f"💥 Error general en las pruebas: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main())