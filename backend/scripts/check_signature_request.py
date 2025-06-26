#!/usr/bin/env python3
"""
Check signature request details
"""
import sys
import asyncio
from uuid import UUID
import base64

# Add parent directory to path
sys.path.append('..')

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.async_database import AsyncSessionLocal
from app.db.models import SignatureRequest, SignatureRequestSigner, Document


async def check_request(request_id: str):
    """Check details of a signature request"""
    async with AsyncSessionLocal() as db:
        try:
            # Get request with all relations
            stmt = select(SignatureRequest).options(
                selectinload(SignatureRequest.provider),
                selectinload(SignatureRequest.signers),
                selectinload(SignatureRequest.documents)
            ).filter(SignatureRequest.id == UUID(request_id))
            
            result = await db.execute(stmt)
            request = result.scalar_one_or_none()
            
            if not request:
                print(f"❌ Signature request {request_id} not found")
                return
            
            print(f"📋 Signature Request Details")
            print("=" * 60)
            print(f"ID: {request.id}")
            print(f"Title: {request.title}")
            print(f"Status: {request.status}")
            print(f"Provider: {request.provider.display_name if request.provider else 'None'}")
            print(f"Created: {request.created_at}")
            
            # Check document content
            print(f"\n📄 Document Information:")
            print(f"Document Name: {request.document_name}")
            print(f"Document URL: {request.document_url}")
            print(f"Has Content: {'Yes' if request.document_content else 'No'}")
            
            if request.document_content:
                print(f"Content Size: {len(request.document_content)} bytes")
                print(f"Content Type: {type(request.document_content)}")
                # Show first 100 chars if it's base64
                if isinstance(request.document_content, bytes):
                    try:
                        # Try to decode as base64
                        decoded = base64.b64decode(request.document_content)
                        print(f"Base64 Decoded Size: {len(decoded)} bytes")
                    except:
                        print("Content is not valid base64")
                        print(f"First 100 bytes: {request.document_content[:100]}")
            else:
                print("⚠️  NO DOCUMENT CONTENT FOUND!")
                
                # Check if there's a document_id that should be loaded
                if hasattr(request, 'document_id') and request.document_id:
                    print(f"\nDocument ID found: {request.document_id}")
                    # Try to load the document
                    doc_stmt = select(Document).filter(Document.id == request.document_id)
                    doc_result = await db.execute(doc_stmt)
                    document = doc_result.scalar_one_or_none()
                    
                    if document:
                        print(f"Document found: {document.filename}")
                        print(f"File path: {document.file_path}")
                        print(f"Has content: {'Yes' if document.content else 'No'}")
            
            # Check signers
            print(f"\n👥 Signers ({len(request.signers)}):")
            for i, signer in enumerate(request.signers, 1):
                print(f"  {i}. {signer.name} ({signer.email}) - Status: {signer.status}")
            
            # Check related documents
            if hasattr(request, 'documents') and request.documents:
                print(f"\n📎 Related Documents ({len(request.documents)}):")
                for doc in request.documents:
                    print(f"  - {doc.filename} ({doc.file_type})")
            
            # Suggestions
            print(f"\n💡 Diagnosis:")
            if not request.document_content:
                print("❌ The signature request has no document content!")
                print("\nPossible causes:")
                print("1. Document was not properly attached when creating the request")
                print("2. Document content was not loaded from storage")
                print("3. The document_content field was not populated")
                print("\nSolution:")
                print("- Ensure document is uploaded/selected before creating signature request")
                print("- Check if document needs to be loaded from GCS")
                print("- Verify the signature request creation process includes document content")
            
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()


async def list_recent_requests():
    """List recent signature requests"""
    async with AsyncSessionLocal() as db:
        stmt = select(SignatureRequest).order_by(
            SignatureRequest.created_at.desc()
        ).limit(10)
        
        result = await db.execute(stmt)
        requests = result.scalars().all()
        
        print("📋 Recent Signature Requests:")
        print("-" * 80)
        print(f"{'ID':<38} {'Title':<30} {'Status':<10} {'Doc?':<5}")
        print("-" * 80)
        
        for req in requests:
            has_doc = "✅" if req.document_content else "❌"
            print(f"{str(req.id):<38} {req.title[:30]:<30} {req.status:<10} {has_doc:<5}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Check signature request details")
    parser.add_argument('request_id', nargs='?', help='Signature request ID to check')
    parser.add_argument('--list', action='store_true', help='List recent requests')
    
    args = parser.parse_args()
    
    if args.list:
        asyncio.run(list_recent_requests())
    elif args.request_id:
        asyncio.run(check_request(args.request_id))
    else:
        # Default: check the request from the error
        asyncio.run(check_request("0b2c0307-5a8d-4b20-889f-8a6e5b9c147b"))