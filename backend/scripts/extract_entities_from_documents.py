#!/usr/bin/env python3
"""
Script to extract entities from existing documents that don't have entities extracted yet.
This is useful for documents that were uploaded before entity extraction was implemented.
"""
import asyncio
import logging
import sys
from pathlib import Path
from typing import Optional

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.async_database import get_async_engine, get_async_session_maker
from app.db.models import Document
from app.services.langchain_client import LangChainClient
from app.core.config import settings
import httpx

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def extract_entities_for_document(
    db: AsyncSession, 
    document: Document, 
    langchain_client: LangChainClient
) -> bool:
    """Extract entities for a single document."""
    try:
        # Skip if entities already extracted
        if document.extracted_entities and len(document.extracted_entities) > 0:
            logger.info(f"Document {document.id} already has {len(document.extracted_entities)} entities")
            return True
        
        # Skip if no content
        if not document.content:
            logger.warning(f"Document {document.id} has no content to extract entities from")
            return False
        
        # Extract entities
        logger.info(f"Extracting entities for document {document.id}: {document.title}")
        entities = await langchain_client.extract_entities(
            document.content, 
            str(document.tenant_id)
        )
        
        if entities:
            document.extracted_entities = entities
            await db.commit()
            logger.info(f"Extracted {len(entities)} entities for document {document.id}")
            return True
        else:
            document.extracted_entities = []
            await db.commit()
            logger.info(f"No entities found in document {document.id}")
            return True
            
    except Exception as e:
        logger.error(f"Failed to extract entities for document {document.id}: {str(e)}")
        await db.rollback()
        return False


async def extract_entities_for_tenant(
    tenant_id: Optional[str] = None,
    limit: Optional[int] = None
):
    """Extract entities for all documents in a tenant."""
    engine = await get_async_engine()
    async_session_maker = await get_async_session_maker(engine)
    
    async with httpx.AsyncClient(timeout=30.0) as http_client:
        langchain_client = LangChainClient(
            http_client=http_client,
            tenant_id=tenant_id
        )
        
        async with async_session_maker() as db:
            # Build query
            query = select(Document).where(
                Document.indexed == 1  # Only process indexed documents
            )
            
            if tenant_id:
                query = query.where(Document.tenant_id == tenant_id)
            
            # Filter for documents without extracted entities
            query = query.where(
                (Document.extracted_entities == None) | 
                (Document.extracted_entities == [])
            )
            
            if limit:
                query = query.limit(limit)
            
            # Execute query
            result = await db.execute(query)
            documents = result.scalars().all()
            
            logger.info(f"Found {len(documents)} documents to process")
            
            # Process each document
            success_count = 0
            for i, document in enumerate(documents):
                logger.info(f"Processing document {i+1}/{len(documents)}")
                if await extract_entities_for_document(db, document, langchain_client):
                    success_count += 1
                
                # Add a small delay to avoid overwhelming the LLM service
                await asyncio.sleep(1)
            
            logger.info(f"Successfully processed {success_count}/{len(documents)} documents")


async def main():
    """Main function."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Extract entities from existing documents")
    parser.add_argument(
        "--tenant-id", 
        help="Tenant ID to process (optional, processes all if not specified)"
    )
    parser.add_argument(
        "--limit", 
        type=int,
        help="Maximum number of documents to process"
    )
    
    args = parser.parse_args()
    
    try:
        await extract_entities_for_tenant(
            tenant_id=args.tenant_id,
            limit=args.limit
        )
    except Exception as e:
        logger.error(f"Script failed: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())