#!/usr/bin/env python
"""
Script to reindex documents
Usage: python -m scripts.reindex_documents [--tenant-id TENANT_ID] [--force]
"""
import asyncio
import argparse
import logging
from typing import Optional

from app.db.async_database import AsyncSessionLocal
from app.db.models import Document
from app.services.reindex_service import ReindexService
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def reindex_tenant_documents(
    tenant_id: Optional[str] = None,
    force: bool = False
):
    """
    Reindex documents for a specific tenant or all tenants
    
    Args:
        tenant_id: Specific tenant ID to reindex (None for all)
        force: Force reindex even if already indexed
    """
    async with AsyncSessionLocal() as db:
        try:
            # Get tenants to process
            if tenant_id:
                tenant_ids = [tenant_id]
                logger.info(f"Reindexing documents for tenant: {tenant_id}")
            else:
                # Get all unique tenant IDs
                stmt = select(Document.tenant_id).distinct()
                result = await db.execute(stmt)
                tenant_ids = [row[0] for row in result.fetchall()]
                logger.info(f"Reindexing documents for {len(tenant_ids)} tenants")
            
            total_processed = 0
            total_failed = 0
            
            for tid in tenant_ids:
                logger.info(f"\n--- Processing tenant: {tid} ---")
                
                # Get documents for this tenant
                if force:
                    # Reindex all documents
                    stmt = select(Document).filter(
                        Document.tenant_id == tid
                    )
                else:
                    # Only reindex documents marked as INDEXED (to fix missing vectors)
                    stmt = select(Document).filter(
                        and_(
                            Document.tenant_id == tid,
                            Document.indexed == 1  # IndexingStatus.INDEXED
                        )
                    )
                
                result = await db.execute(stmt)
                documents = result.scalars().all()
                
                logger.info(f"Found {len(documents)} documents to check")
                
                # Initialize reindex service
                reindex_service = ReindexService(tenant_id=str(tid))
                
                # Check and reindex missing documents
                for doc in documents:
                    try:
                        # Check if document exists in vector store
                        exists = await reindex_service.vector_service.document_exists(str(doc.id))
                        
                        if not exists or force:
                            logger.info(f"Reindexing document: {doc.id} - {doc.title}")
                            
                            # Get document content
                            if doc.content:
                                # Reindex the document
                                success = await reindex_service.reindex_single_document(
                                    document_id=str(doc.id),
                                    content=doc.content,
                                    metadata={
                                        'title': doc.title,
                                        'filename': doc.filename,
                                        'file_type': doc.file_type,
                                        'created_at': doc.created_at.isoformat() if doc.created_at else None
                                    }
                                )
                                
                                if success:
                                    total_processed += 1
                                    logger.info(f"✓ Successfully reindexed: {doc.title}")
                                else:
                                    total_failed += 1
                                    logger.error(f"✗ Failed to reindex: {doc.title}")
                            else:
                                logger.warning(f"⚠ No content for document: {doc.id}")
                                total_failed += 1
                        else:
                            logger.debug(f"✓ Document already in vector store: {doc.id}")
                            
                    except Exception as e:
                        logger.error(f"Error processing document {doc.id}: {e}")
                        total_failed += 1
                
            logger.info(f"\n=== Reindexing Complete ===")
            logger.info(f"Total processed: {total_processed}")
            logger.info(f"Total failed: {total_failed}")
            
        except Exception as e:
            logger.error(f"Fatal error during reindexing: {e}")
            raise


async def main():
    """Main function"""
    parser = argparse.ArgumentParser(description='Reindex documents in vector store')
    parser.add_argument(
        '--tenant-id',
        type=str,
        help='Specific tenant ID to reindex (default: all tenants)'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Force reindex all documents, even if already indexed'
    )
    
    args = parser.parse_args()
    
    await reindex_tenant_documents(
        tenant_id=args.tenant_id,
        force=args.force
    )


if __name__ == "__main__":
    asyncio.run(main())