#!/usr/bin/env python3
"""
Test script for the new LangExtract integration in document upload flow
"""
import asyncio
import logging
import sys
import tempfile
import os
from pathlib import Path
from typing import Optional
import io

# Add parent directory to path
sys.path.append(str(Path(__file__).parent))

from app.services.async_document_service import AsyncDocumentService
from app.db.async_database import get_async_engine, get_async_session_maker
from app.db.models import Document, Tenant
from app.core.config import settings
from sqlalchemy import select
from fastapi import UploadFile

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def create_test_pdf_content() -> bytes:
    """Create a simple test PDF content"""
    # This is a minimal PDF content for testing
    pdf_content = b"""%PDF-1.4
1 0 obj
<<
/Type /Catalog
/Pages 2 0 R
>>
endobj

2 0 obj
<<
/Type /Pages
/Kids [3 0 R]
/Count 1
>>
endobj

3 0 obj
<<
/Type /Page
/Parent 2 0 R
/MediaBox [0 0 612 792]
/Contents 4 0 R
/Resources <<
/Font <<
/F1 <<
/Type /Font
/Subtype /Type1
/BaseFont /Helvetica
>>
>>
>>
>>
endobj

4 0 obj
<<
/Length 100
>>
stream
BT
/F1 12 Tf
72 720 Td
(Test Contract Document) Tj
0 -20 Td
(Party A: TechCorp Inc.) Tj
0 -20 Td
(Party B: ClientCo Ltd.) Tj
0 -20 Td
(Effective Date: January 1, 2025) Tj
0 -20 Td
(Total Amount: $50,000.00) Tj
ET
endstream
endobj

xref
0 5
0000000000 65535 f
0000000015 00000 n
0000000060 00000 n
0000000111 00000 n
0000000339 00000 n
trailer
<<
/Size 5
/Root 1 0 R
>>
startxref
487
%%EOF"""
    return pdf_content


def create_test_contract_text() -> str:
    """Create test contract text content"""
    return """
SERVICE AGREEMENT

This Service Agreement ("Agreement") is entered into as of January 1, 2025, between TechCorp Inc., 
a corporation organized under the laws of Delaware ("Service Provider") and ClientCo Ltd., 
a limited liability company organized under the laws of California ("Client").

PARTIES:
- Service Provider: TechCorp Inc.
  Address: 123 Tech Street, San Francisco, CA 94102
  Contact: John Smith, CEO
  Email: john.smith@techcorp.com

- Client: ClientCo Ltd.
  Address: 456 Client Avenue, Los Angeles, CA 90210
  Contact: Sarah Johnson, CTO
  Email: sarah.johnson@clientco.com

TERMS:
- Contract Type: Professional Services Agreement
- Effective Date: January 1, 2025
- Expiration Date: December 31, 2025
- Total Contract Value: $250,000.00
- Payment Terms: Net 30 days
- Payment Schedule: Monthly invoicing

DELIVERABLES:
- Software development services
- Technical consultation
- Project management
- Quality assurance testing

OBLIGATIONS:
Service Provider shall:
1. Provide qualified personnel for the services
2. Maintain confidentiality of Client information
3. Deliver services according to agreed timeline

Client shall:
1. Provide necessary access and information
2. Pay invoices within payment terms
3. Designate project liaison

TERMINATION:
Either party may terminate this agreement with 30 days written notice.

GOVERNING LAW:
This agreement shall be governed by the laws of California.

SIGNATURES:
Service Provider: _________________ Date: _________
John Smith, CEO, TechCorp Inc.

Client: _________________ Date: _________
Sarah Johnson, CTO, ClientCo Ltd.
"""


async def test_entity_extraction_integration():
    """Test the complete entity extraction integration"""
    
    logger.info("🧪 Starting LangExtract Integration Test")
    logger.info(f"📋 LangExtract Service URL: {settings.LANGEXTRACT_SERVICE_URL}")
    
    # Get database engine
    engine = await get_async_engine()
    async_session_maker = await get_async_session_maker(engine)
    
    try:
        async with async_session_maker() as db:
            # Get default tenant
            stmt = select(Tenant).filter(Tenant.name == settings.DEFAULT_TENANT)
            result = await db.execute(stmt)
            tenant = result.scalar_one_or_none()
            
            if not tenant:
                logger.error(f"❌ Default tenant '{settings.DEFAULT_TENANT}' not found")
                return False
            
            tenant_id = str(tenant.id)
            logger.info(f"🏢 Using tenant: {tenant.name} ({tenant_id})")
            
            # Create document service
            doc_service = await AsyncDocumentService.create(
                tenant_id=tenant_id,
                user_id="test-user-id",
                db=db
            )
            
            # Test 1: Upload contract document
            logger.info("\n📄 Test 1: Contract Document Upload with Entity Extraction")
            
            # Create test contract file
            contract_content = create_test_contract_text().encode('utf-8')
            contract_file = UploadFile(
                filename="test_contract.txt",
                file=io.BytesIO(contract_content),
                size=len(contract_content),
                headers={"content-type": "text/plain"}
            )
            
            # Upload document
            try:
                document = await doc_service.upload_document(
                    db=db,
                    file=contract_file,
                    title="Test Contract - Entity Extraction",
                    description="Contract document for testing entity extraction",
                    category="contract"
                )
                
                logger.info(f"✅ Document uploaded successfully: {document.id}")
                logger.info(f"📊 Document status: {document.indexed}")
                
                # Wait a bit for background processing
                logger.info("⏳ Waiting for background processing (entity extraction)...")
                await asyncio.sleep(10)
                
                # Check if entities were extracted
                await db.refresh(document)
                
                if document.extracted_entities:
                    logger.info(f"✅ Entity extraction successful!")
                    logger.info(f"🔍 Total entities found: {len(document.extracted_entities)}")
                    
                    # Group entities by type
                    entities_by_type = {}
                    for entity in document.extracted_entities:
                        entity_type = entity.get('type', 'other')
                        if entity_type not in entities_by_type:
                            entities_by_type[entity_type] = []
                        entities_by_type[entity_type].append(entity)
                    
                    logger.info("📋 Entities by type:")
                    for entity_type, entities in entities_by_type.items():
                        logger.info(f"   {entity_type.upper()} ({len(entities)}):")
                        for entity in entities[:3]:  # Show first 3
                            name = entity.get('name', 'Unknown')
                            role = entity.get('role', '')
                            context = entity.get('context', '')
                            logger.info(f"     - {name}" + (f" ({role})" if role else "") + (f" [{context}]" if context else ""))
                        if len(entities) > 3:
                            logger.info(f"     ... and {len(entities) - 3} more")
                    
                    # Test extraction metadata
                    first_entity = document.extracted_entities[0]
                    extraction_metadata = first_entity.get('metadata', {})
                    logger.info(f"🔧 Extraction metadata:")
                    logger.info(f"   Method: {extraction_metadata.get('extraction_method')}")
                    logger.info(f"   Provider: {extraction_metadata.get('provider')}")
                    logger.info(f"   Model: {extraction_metadata.get('model')}")
                    logger.info(f"   Document type: {extraction_metadata.get('document_type')}")
                    
                    return True
                    
                else:
                    logger.warning("⚠️  No entities extracted - this may indicate an issue")
                    logger.info("🔍 Checking document content and status...")
                    logger.info(f"   Content length: {len(document.content) if document.content else 0}")
                    logger.info(f"   Indexed status: {document.indexed}")
                    logger.info(f"   Category: {document.category}")
                    return False
                
            except Exception as e:
                logger.error(f"❌ Document upload failed: {e}")
                return False
                
    except Exception as e:
        logger.error(f"❌ Test failed with exception: {e}")
        return False


async def test_langextract_service_directly():
    """Test LangExtract service directly"""
    
    logger.info("\n🧪 Test 2: Direct LangExtract Service Test")
    
    try:
        import httpx
        
        # Test contract text
        test_text = create_test_contract_text()
        
        request_payload = {
            "text": test_text,
            "document_type": "contract",
            "filename": "direct_test_contract.txt",
            "provider": "ollama"
        }
        
        microservice_url = f"{settings.LANGEXTRACT_SERVICE_URL}/api/v1/extraction/extract"
        headers = {
            "X-API-Key": settings.MICROSERVICES_API_KEY,
            "Content-Type": "application/json"
        }
        
        logger.info(f"📞 Calling LangExtract service directly...")
        logger.info(f"   URL: {microservice_url}")
        logger.info(f"   Text length: {len(test_text)} characters")
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(microservice_url, json=request_payload, headers=headers)
            
            if response.status_code == 200:
                result = response.json()
                
                if result.get("success"):
                    extractions = result.get("extractions", [])
                    summary = result.get("summary", {})
                    metadata = result.get("metadata", {})
                    
                    logger.info(f"✅ Direct service call successful!")
                    logger.info(f"🔍 Total extractions: {len(extractions)}")
                    logger.info(f"📊 Summary: {summary}")
                    logger.info(f"🔧 Metadata: {metadata}")
                    
                    # Show first few extractions
                    for i, extraction in enumerate(extractions[:5]):
                        logger.info(f"   {i+1}. {extraction.get('class')}: {extraction.get('text')}")
                    
                    return True
                else:
                    logger.error(f"❌ LangExtract service returned error: {result.get('error')}")
                    return False
            else:
                logger.error(f"❌ HTTP error {response.status_code}: {response.text}")
                return False
                
    except Exception as e:
        logger.error(f"❌ Direct service test failed: {e}")
        return False


async def main():
    """Main test function"""
    logger.info("🚀 LangExtract Integration Testing Suite")
    logger.info("=" * 60)
    
    success_count = 0
    total_tests = 2
    
    # Test 1: Full integration test
    if await test_entity_extraction_integration():
        success_count += 1
        logger.info("✅ Test 1 PASSED: Integration test")
    else:
        logger.error("❌ Test 1 FAILED: Integration test")
    
    # Test 2: Direct service test
    if await test_langextract_service_directly():
        success_count += 1
        logger.info("✅ Test 2 PASSED: Direct service test")
    else:
        logger.error("❌ Test 2 FAILED: Direct service test")
    
    logger.info("\n" + "=" * 60)
    logger.info(f"📊 Test Results: {success_count}/{total_tests} tests passed")
    
    if success_count == total_tests:
        logger.info("🎉 All tests passed! LangExtract integration is working correctly.")
        return True
    else:
        logger.error(f"💥 {total_tests - success_count} test(s) failed. Check configuration and services.")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)