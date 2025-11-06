#!/usr/bin/env python3
"""
Script to extract entities from existing documents using LangExtract service.
This migrates documents that were uploaded before entity extraction was integrated.
"""
import asyncio
import logging
import sys
from pathlib import Path
from typing import Optional, List
import httpx

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from sqlalchemy import select, and_, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.async_database import get_async_engine, get_async_session_maker
from app.db.models import Document
from app.schemas.enums import IndexingStatus
from app.core.config import settings

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def extract_entities_for_document(
    document: Document,
    http_client: httpx.AsyncClient
) -> bool:
    """Extract entities for a single document using LangExtract service."""
    try:
        # Skip if entities already extracted
        if document.extracted_entities and len(document.extracted_entities) > 0:
            logger.info(f"Document {document.id} already has {len(document.extracted_entities)} entities")
            return True
        
        # Skip if no content
        if not document.content:
            logger.warning(f"Document {document.id} has no content to extract entities from")
            return False
        
        # Map document categories to LangExtract types
        langextract_type_mapping = {
            "contract": "contract",
            "legal": "contract", 
            "invoice": "invoice",
            "financial": "invoice",
            "report": "report",
            "compliance": "report",
            "technical": "report",
            "correspondence": "general",
            "hr": "general",
            "general": "general"
        }
        
        doc_type = document.category or "general"
        extraction_type = langextract_type_mapping.get(doc_type, "general")
        
        # Prepare request payload
        request_payload = {
            "text": document.content[:50000],  # Limit text size
            "document_type": extraction_type,
            "filename": document.filename,
            "provider": "ollama"
        }
        
        logger.info(f"🧠 Extracting entities for document {document.id}: {document.title} ({extraction_type})")
        
        # Call LangExtract microservice
        microservice_url = f"{settings.LANGEXTRACT_SERVICE_URL}/api/v1/extraction/extract"
        headers = {
            "X-API-Key": settings.MICROSERVICES_API_KEY,
            "Content-Type": "application/json"
        }
        
        response = await http_client.post(microservice_url, json=request_payload, headers=headers)
        
        if response.status_code == 200:
            result = response.json()
            
            if result.get("success", False):
                extractions = result.get("extractions", [])
                metadata = result.get("metadata", {})
                
                # Format entities for storage
                formatted_entities = []
                for extraction in extractions:
                    formatted_entities.append({
                        "name": extraction.get("text", ""),
                        "type": extraction.get("class", "other"),
                        "role": extraction.get("attributes", {}).get("role", ""),
                        "context": extraction.get("attributes", {}).get("type", ""),
                        "metadata": {
                            "extraction_method": "langextract_migration",
                            "provider": metadata.get("provider", "ollama"),
                            "model": metadata.get("model", "unknown"),
                            "confidence": extraction.get("attributes", {}).get("confidence", 0.8),
                            "source_indices": extraction.get("source_indices"),
                            "document_type": extraction_type
                        }
                    })
                
                # Store in document
                document.extracted_entities = formatted_entities
                logger.info(f"✅ Extracted {len(extractions)} entities for document {document.id}")
                return True
            else:
                error_msg = result.get("error", "Unknown error")
                logger.warning(f"⚠️ LangExtract returned error for {document.id}: {error_msg}")
                # Set empty array to mark as processed
                document.extracted_entities = []
                return True
        else:
            logger.error(f"❌ LangExtract service error {response.status_code}: {response.text}")
            document.extracted_entities = []
            return True
            
    except Exception as e:
        logger.error(f"❌ Failed to extract entities for document {document.id}: {str(e)}")
        return False


async def migrate_entities_for_tenant(
    tenant_id: Optional[str] = None,
    limit: Optional[int] = None,
    dry_run: bool = False
) -> dict:
    """Extract entities for all documents in a tenant that don't have entities yet."""
    
    engine = await get_async_engine()
    async_session_maker = await get_async_session_maker(engine)
    
    stats = {
        "total_found": 0,
        "successful": 0,
        "failed": 0,
        "skipped": 0
    }
    
    async with httpx.AsyncClient(timeout=120.0) as http_client:
        async with async_session_maker() as db:
            # Build query for documents that need entity extraction
            query = select(Document).where(
                and_(
                    Document.indexed == IndexingStatus.INDEXED,  # Only indexed documents
                    Document.indexed > 0,  # Has been indexed (content processed)
                    or_(
                        Document.extracted_entities.is_(None),  # No entities extracted yet
                        Document.extracted_entities == []  # Or empty array
                    )
                )
            )
            
            if tenant_id:
                query = query.where(Document.tenant_id == tenant_id)
            
            if limit:
                query = query.limit(limit)
            
            # Order by creation date (oldest first)
            query = query.order_by(Document.created_at.asc())
            
            # Execute query
            result = await db.execute(query)
            documents = result.scalars().all()
            
            stats["total_found"] = len(documents)
            logger.info(f"🔍 Found {len(documents)} documents that need entity extraction")
            
            if dry_run:
                logger.info("🧪 DRY RUN MODE: No changes will be made")
                for i, doc in enumerate(documents):
                    logger.info(f"Would process {i+1}/{len(documents)}: {doc.title} ({doc.category or 'general'})")
                return stats
            
            # Process each document
            for i, document in enumerate(documents):
                logger.info(f"📄 Processing document {i+1}/{len(documents)}: {document.title}")
                
                try:
                    if await extract_entities_for_document(document, http_client):
                        await db.commit()
                        stats["successful"] += 1
                    else:
                        await db.rollback()
                        stats["failed"] += 1
                        
                except Exception as e:
                    logger.error(f"❌ Exception processing document {document.id}: {e}")
                    await db.rollback()
                    stats["failed"] += 1
                
                # Add delay to avoid overwhelming the service
                if i < len(documents) - 1:  # Don't sleep after the last document
                    await asyncio.sleep(2)  # 2 second delay between documents
            
            logger.info(
                f"🏁 Migration completed: {stats['successful']} successful, "
                f"{stats['failed']} failed out of {stats['total_found']} documents"
            )
    
    return stats


async def main():
    """Main function."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Extract entities from existing documents using LangExtract service"
    )
    parser.add_argument(
        "--tenant-id", 
        help="Tenant ID to process (optional, processes all if not specified)"
    )
    parser.add_argument(
        "--limit", 
        type=int,
        help="Maximum number of documents to process"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be processed without making changes"
    )
    
    args = parser.parse_args()
    
    logger.info("🚀 Starting LangExtract entity migration...")
    logger.info(f"📋 Configuration:")
    logger.info(f"   - Tenant ID: {args.tenant_id or 'All tenants'}")
    logger.info(f"   - Limit: {args.limit or 'No limit'}")
    logger.info(f"   - Dry run: {args.dry_run}")
    logger.info(f"   - LangExtract service: {settings.LANGEXTRACT_SERVICE_URL}")
    
    try:
        stats = await migrate_entities_for_tenant(
            tenant_id=args.tenant_id,
            limit=args.limit,
            dry_run=args.dry_run
        )
        
        logger.info("📊 Final statistics:")
        logger.info(f"   - Total documents found: {stats['total_found']}")
        logger.info(f"   - Successfully processed: {stats['successful']}")
        logger.info(f"   - Failed: {stats['failed']}")
        
        if stats['failed'] > 0:
            logger.warning(f"⚠️  {stats['failed']} documents failed processing")
            sys.exit(1)
        else:
            logger.info("✅ All documents processed successfully!")
            
    except Exception as e:
        logger.error(f"💥 Migration script failed: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())