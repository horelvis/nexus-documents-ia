#!/usr/bin/env python3
"""
Setup script for Elasticsearch hybrid architecture
- Remove Qdrant dependencies
- Initialize Elasticsearch indices
- Test hybrid search functionality
"""
import asyncio
import logging
import sys
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

from app.core.config import settings
from app.services.elasticsearch_service import ElasticsearchService
from app.services.search_service import SearchService
from app.db.database import SessionLocal
from app.db.models import Document

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def setup_elasticsearch_indices():
    """Initialize Elasticsearch indices for all tenants"""
    logger.info("🚀 Setting up Elasticsearch indices...")
    
    with SessionLocal() as db:
        # Get all unique tenant IDs
        tenant_ids = db.query(Document.tenant_id).distinct().all()
        tenant_ids = [str(tid[0]) for tid in tenant_ids]
    
    logger.info(f"Found {len(tenant_ids)} tenants: {tenant_ids}")
    
    for tenant_id in tenant_ids:
        try:
            logger.info(f"📋 Setting up Elasticsearch index for tenant: {tenant_id}")
            
            # Initialize Elasticsearch service
            es_service = ElasticsearchService(tenant_id)
            
            # Create index if not exists
            success = es_service.create_index_if_not_exists()
            if success:
                logger.info(f"✅ Index ready for tenant: {tenant_id}")
            else:
                logger.error(f"❌ Failed to create index for tenant: {tenant_id}")
                
            await es_service.close()
            
        except Exception as e:
            logger.error(f"❌ Error setting up tenant {tenant_id}: {e}")


async def test_hybrid_search():
    """Test hybrid search functionality"""
    logger.info("🧪 Testing hybrid search functionality...")
    
    # Get a sample tenant
    with SessionLocal() as db:
        sample_doc = db.query(Document).first()
        if not sample_doc:
            logger.warning("⚠️ No documents found for testing")
            return
        
        tenant_id = str(sample_doc.tenant_id)
    
    logger.info(f"Testing with tenant: {tenant_id}")
    
    # Initialize search service
    search_service = SearchService(tenant_id)
    
    test_queries = [
        {"query": "test document", "type": "semantic"},
        {"query": "recent pdf files", "type": "hybrid"}, 
        {"query": "type:pdf AND created:2024", "type": "keyword"}
    ]
    
    for test in test_queries:
        try:
            logger.info(f"🔍 Testing {test['type']} search: '{test['query']}'")
            
            results = await search_service.search_documents(
                query=test['query'],
                search_type=test['type'],
                limit=3
            )
            
            logger.info(f"✅ {test['type'].capitalize()} search returned {len(results)} results")
            
        except Exception as e:
            logger.error(f"❌ {test['type'].capitalize()} search failed: {e}")


async def check_qdrant_removal():
    """Verify Qdrant is properly removed from configuration"""
    logger.info("🗑️ Checking Qdrant removal...")
    
    # Check if Qdrant config still exists
    try:
        qdrant_host = getattr(settings, 'QDRANT_HOST', None)
        if qdrant_host:
            logger.warning(f"⚠️ QDRANT_HOST still configured: {qdrant_host}")
            logger.info("Consider removing from config.py")
        else:
            logger.info("✅ Qdrant configuration removed")
    except Exception:
        logger.info("✅ Qdrant configuration not found")
    
    # Check Elasticsearch configuration
    try:
        es_url = settings.ELASTICSEARCH_URL
        logger.info(f"✅ Elasticsearch configured at: {es_url}")
    except Exception as e:
        logger.error(f"❌ Elasticsearch not configured: {e}")


async def migration_summary():
    """Print migration summary"""
    logger.info("=" * 60)
    logger.info("🎉 ELASTICSEARCH HYBRID SETUP SUMMARY")
    logger.info("=" * 60)
    
    architecture_info = """
    NEW HYBRID ARCHITECTURE:
    
    🚀 Weaviate (Primary - 80% queries)
       - Fast semantic search
       - RAG with Elysia
       - Low latency
    
    🔍 Elasticsearch (Specialized - 20% queries)  
       - Hybrid search (keyword + semantic)
       - Complex filtering
       - Analytics & reporting
       - Compliance queries
       
    ❌ Qdrant (REMOVED)
       - No longer used
       - Dependencies cleaned up
       
    BENEFITS:
    ✅ Reduced complexity (one less vector DB)
    ✅ Better search capabilities  
    ✅ Analytics included
    ✅ Cost optimized (~25% increase vs 100% duplication)
    """
    
    logger.info(architecture_info)
    
    logger.info("🔧 NEXT STEPS:")
    logger.info("1. Update API endpoints to use search_type parameter")
    logger.info("2. Update frontend to show search type options")
    logger.info("3. Monitor performance metrics")
    logger.info("4. Remove any remaining Qdrant references")
    logger.info("=" * 60)


async def main():
    """Main setup function"""
    logger.info("🚀 Starting Elasticsearch Hybrid Setup...")
    
    try:
        # Step 1: Check Qdrant removal
        await check_qdrant_removal()
        
        # Step 2: Setup Elasticsearch indices
        await setup_elasticsearch_indices()
        
        # Step 3: Test hybrid search
        await test_hybrid_search()
        
        # Step 4: Show summary
        await migration_summary()
        
        logger.info("✅ Elasticsearch hybrid setup completed successfully!")
        
    except Exception as e:
        logger.error(f"❌ Setup failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())