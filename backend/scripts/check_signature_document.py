#!/usr/bin/env python3
"""
Check signature request document content issue
"""
import os
import sys
sys.path.append('..')

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from app.db.models import SignatureRequest, Document
from app.core.config import settings

def check_signature_request_document(request_id: str):
    """Check why document content is None"""
    
    # Create database connection
    engine = create_engine(settings.DATABASE_URL)
    
    with Session(engine) as db:
        # Get the signature request
        request = db.query(SignatureRequest).filter(
            SignatureRequest.id == request_id
        ).first()
        
        if not request:
            print(f"❌ Signature request {request_id} not found")
            return
        
        print(f"📋 Signature Request: {request.title}")
        print(f"   ID: {request.id}")
        print(f"   Status: {request.status}")
        print(f"   Created: {request.created_at}")
        print(f"   Document Name: {request.document_name}")
        print(f"   Document URL: {request.document_url}")
        print(f"   Has Document Content: {'Yes' if request.document_content else 'No'}")
        
        if request.document_content:
            print(f"   Document Content Size: {len(request.document_content)} bytes")
            print(f"   Content Type: {type(request.document_content)}")
            # Check if it's valid PDF
            if request.document_content[:4] == b'%PDF':
                print("   ✅ Appears to be a valid PDF")
            else:
                print(f"   ⚠️  Content doesn't start with PDF header: {request.document_content[:10]}")
        else:
            print("   ❌ NO DOCUMENT CONTENT!")
            
            # Check if there's a document_id field (might be in metadata)
            if request.request_metadata and 'document_id' in request.request_metadata:
                doc_id = request.request_metadata['document_id']
                print(f"\n   Found document_id in metadata: {doc_id}")
                
                # Try to load the document
                document = db.query(Document).filter(Document.id == doc_id).first()
                if document:
                    print(f"   Document found: {document.filename}")
                    print(f"   File path: {document.file_path}")
                    print(f"   File size: {document.file_size} bytes")
                    print(f"   File type: {document.file_type}")
                else:
                    print(f"   ❌ Document {doc_id} not found in database")
        
        print("\n💡 Diagnosis:")
        if not request.document_content:
            print("The signature request has no document content stored.")
            print("\nPossible causes:")
            print("1. Document content was not loaded from storage when creating the request")
            print("2. The document content field is too large for the database column")
            print("3. There was an error during the document loading process")
            print("\nSolutions:")
            print("1. Check if the document exists in Google Cloud Storage")
            print("2. Check the logs when the signature request was created")
            print("3. Try re-creating the signature request with proper document loading")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        request_id = sys.argv[1]
    else:
        # Use the request ID from the error
        request_id = "d406061e-e48c-4a6e-b43e-9bde674389d9"
    
    check_signature_request_document(request_id)