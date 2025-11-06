#!/usr/bin/env python3
"""
Script para reindexar todos los documentos existentes en Elasticsearch
"""
import asyncio
import os
import sys
import logging
from pathlib import Path

# Add the parent directory to the path so we can import our modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.db.models import Document, Tenant
from app.services.elasticsearch_service import ElasticsearchService
from app.core.config import settings
from sqlalchemy import select

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def reindex_documents_by_tenant():
    """Reindex all documents grouped by tenant"""
    
    logger.info("🚀 Iniciando reindexado de Elasticsearch...")
    
    # Create async engine and session
    engine = create_async_engine(str(settings.SQLALCHEMY_DATABASE_URI))
    async_session = sessionmaker(engine, class_=AsyncSession)
    
    async with async_session() as db:
        # Get all tenants
        result = await db.execute(select(Tenant))
        tenants = result.scalars().all()
        
        total_reindexed = 0
        total_tenants = len(tenants)
        
        logger.info(f"📊 Encontrados {total_tenants} tenants")
        
        for i, tenant in enumerate(tenants, 1):
            tenant_id = str(tenant.id)
            logger.info(f"🏢 [{i}/{total_tenants}] Procesando tenant: {tenant_id} ({tenant.name})")
            
            # Initialize Elasticsearch service for this tenant
            es_service = ElasticsearchService(tenant_id)
            
            # Create index if not exists
            es_service.create_index_if_not_exists()
            
            # Get all INDEXED documents for this tenant
            query = select(Document).where(
                Document.tenant_id == tenant.id,
                Document.indexed == "INDEXED"  # Only reindex successfully processed documents
            )
            result = await db.execute(query)
            documents = result.scalars().all()
            
            tenant_count = 0
            logger.info(f"📄 Encontrados {len(documents)} documentos indexados para tenant {tenant_id}")
            
            for doc in documents:
                try:
                    # Prepare metadata for Elasticsearch
                    es_metadata = {
                        "file_type": doc.file_type,
                        "category": getattr(doc, 'category', None),
                        "tags": doc.tags if doc.tags else [],
                        "created_at": doc.created_at.isoformat() if doc.created_at else None,
                        "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
                        "file_size": doc.file_size
                    }
                    
                    # Get document content (truncated for indexing)
                    content = getattr(doc, 'content', '') or ''
                    if len(content) > 5000:
                        content = content[:5000] + "..."
                    
                    # Index document in Elasticsearch
                    success = await es_service.index_document(
                        doc_id=str(doc.id),
                        title=doc.title or doc.filename or 'Sin título',
                        content=content,
                        metadata=es_metadata
                    )
                    
                    if success:
                        tenant_count += 1
                        logger.debug(f"✅ Indexado documento {doc.id}: {doc.title or doc.filename}")
                    else:
                        logger.warning(f"⚠️ Error indexando documento {doc.id}: {doc.title or doc.filename}")
                        
                except Exception as e:
                    logger.error(f"❌ Error procesando documento {doc.id}: {str(e)}")
                    continue
            
            # Close Elasticsearch connection for this tenant
            await es_service.close()
            
            total_reindexed += tenant_count
            logger.info(f"✅ Tenant {tenant_id}: {tenant_count} documentos reindexados")
        
        logger.info(f"🎉 Reindexado completado: {total_reindexed} documentos en {total_tenants} tenants")


async def main():
    """Main function"""
    try:
        await reindex_documents_by_tenant()
    except Exception as e:
        logger.error(f"💥 Error durante el reindexado: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())