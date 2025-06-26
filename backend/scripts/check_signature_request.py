#!/usr/bin/env python3
"""
Check signature request details and document content
"""
import sys
import asyncio
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Add parent directory to path
sys.path.append('..')

from app.db.models import SignatureRequest, Document
from app.core.config import settings

async def check_signature_request(request_id: str):
    """Check signature request and its document"""
    # Create async engine
    engine = create_async_engine(
        settings.ASYNC_DATABASE_URL,
        echo=True
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
        
        print(f"✅ Found signature request:")
        print(f"   - ID: {request.id}")
        print(f"   - Title: {request.title}")
        print(f"   - Status: {request.status}")
        print(f"   - Document Name: {request.document_name}")
        print(f"   - Document Content: {'Present' if request.document_content else 'MISSING'}")
        if request.document_content:
            print(f"   - Content Size: {len(request.document_content)} bytes")
        
        # Check if there's a related document
        if hasattr(request, 'document_id') or request.request_metadata.get('document_id'):
            doc_id = getattr(request, 'document_id', None) or request.request_metadata.get('document_id')
            
            stmt = select(Document).where(Document.id == UUID(str(doc_id)))
            result = await session.execute(stmt)
            document = result.scalar_one_or_none()
            
            if document:
                print(f"\n✅ Found related document:")
                print(f"   - ID: {document.id}")
                print(f"   - Filename: {document.filename}")
                print(f"   - File Path: {document.file_path}")
                print(f"   - Size: {document.size} bytes")
            else:
                print(f"\n❌ Document {doc_id} not found")
        
    await engine.dispose()

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python check_signature_request.py <request_id>")
        sys.exit(1)
    
    request_id = sys.argv[1]
    asyncio.run(check_signature_request(request_id))