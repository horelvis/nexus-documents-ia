#!/usr/bin/env python3
"""
Fix missing document content in signature requests
"""
import sys
import asyncio
from uuid import UUID
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Add parent directory to path
sys.path.append('..')

from app.db.models import SignatureRequest, Document
from app.core.config import settings
from app.services.async_storage_service import AsyncStorageService

async def fix_signature_document_content(request_id: str):
    """Fix missing document content by reloading from storage"""
    # Create async engine
    engine = create_async_engine(
        settings.ASYNC_DATABASE_URL,
        echo=False
    )
    
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    
    async with async_session() as session:
        # Get signature request
        stmt = select(SignatureRequest).where(
            SignatureRequest.id == UUID(request_id)
        )
        result = await session.execute(stmt)
        request = result.scalar_one_or_none()
        
        if not request:
            print(f"❌ Signature request {request_id} not found")
            return
        
        print(f"✅ Found signature request: {request.title}")
        
        # Check if content already exists
        if request.document_content:
            print(f"ℹ️  Document content already present ({len(request.document_content)} bytes)")
            return
        
        # Find document ID from metadata
        doc_id = request.request_metadata.get('document_id')
        if not doc_id:
            print("❌ No document_id found in request metadata")
            return
        
        # Get document
        stmt = select(Document).where(Document.id == UUID(str(doc_id)))
        result = await session.execute(stmt)
        document = result.scalar_one_or_none()
        
        if not document:
            print(f"❌ Document {doc_id} not found")
            return
        
        print(f"✅ Found document: {document.filename}")
        
        if not document.file_path:
            print("❌ Document has no file_path")
            return
        
        # Load content from storage
        try:
            storage_service = AsyncStorageService(session)
            print(f"⏳ Loading document from storage: {document.file_path}")
            
            content = await storage_service.download_file(
                file_path=document.file_path,
                tenant_id=request.tenant_id
            )
            
            print(f"✅ Loaded {len(content)} bytes from storage")
            
            # Update signature request with content
            request.document_content = content
            request.document_name = document.filename
            
            # Also update metadata to include document_id
            if 'document_id' not in request.request_metadata:
                request.request_metadata['document_id'] = str(doc_id)
            
            await session.commit()
            
            print("✅ Successfully updated signature request with document content")
            
        except Exception as e:
            print(f"❌ Error loading document from storage: {e}")
            await session.rollback()
            return
        
    await engine.dispose()

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python fix_signature_document_content.py <request_id>")
        sys.exit(1)
    
    request_id = sys.argv[1]
    asyncio.run(fix_signature_document_content(request_id))