#!/usr/bin/env python3
"""
Test LangExtract service with sample documents
"""
import asyncio
import os
import httpx
import json


async def test_langextract_service():
    """Test the LangExtract service with various document types"""
    
    # Service URL
    base_url = "http://localhost:8009"
    api_key = os.getenv("MICROSERVICES_API_KEY")
    if not api_key:
        raise RuntimeError("MICROSERVICES_API_KEY environment variable is required for test_langextract.py")
    
    # Test documents
    test_documents = [
        {
            "name": "Contract Test",
            "document_type": "contract",
            "text": """
                SERVICE AGREEMENT
                
                This Service Agreement ("Agreement") is entered into as of August 6, 2025,
                between TechCorp Solutions Inc. ("Service Provider") located at 123 Tech Street,
                San Francisco, CA 94105, and Digital Innovations Ltd. ("Client") located at
                456 Innovation Ave, New York, NY 10001.
                
                1. SERVICES
                The Service Provider agrees to provide software development and consulting services
                as detailed in Schedule A attached hereto.
                
                2. PAYMENT TERMS
                Client agrees to pay Service Provider a monthly fee of $15,000 USD,
                payable within 30 days of invoice receipt. Late payments will incur
                a 1.5% monthly interest charge.
                
                3. TERM
                This Agreement shall commence on August 6, 2025, and continue for a period
                of 12 months, unless earlier terminated in accordance with Section 4.
                
                4. TERMINATION
                Either party may terminate this Agreement with 60 days written notice.
                
                5. CONFIDENTIALITY
                Both parties agree to maintain strict confidentiality regarding all proprietary
                information exchanged during the term of this Agreement.
                
                Signed:
                _____________________
                John Smith, CEO
                TechCorp Solutions Inc.
                
                _____________________
                Jane Doe, President
                Digital Innovations Ltd.
            """
        },
        {
            "name": "Invoice Test",
            "document_type": "invoice",
            "text": """
                INVOICE
                
                Invoice Number: INV-2025-0847
                Date: August 6, 2025
                Due Date: September 6, 2025
                
                FROM:
                TechCorp Solutions Inc.
                123 Tech Street
                San Francisco, CA 94105
                Tax ID: 98-7654321
                
                BILL TO:
                Digital Innovations Ltd.
                456 Innovation Ave
                New York, NY 10001
                
                ITEMS:
                1. Software Development Services (160 hours @ $150/hour): $24,000.00
                2. Cloud Infrastructure Setup: $5,000.00
                3. Technical Documentation: $3,000.00
                
                Subtotal: $32,000.00
                Tax (8.875%): $2,840.00
                
                TOTAL DUE: $34,840.00
                
                Payment Methods:
                - Wire Transfer to Account: 123456789
                - Check payable to: TechCorp Solutions Inc.
                
                Thank you for your business!
            """
        },
        {
            "name": "Report Test",
            "document_type": "report",
            "text": """
                QUARTERLY FINANCIAL REPORT Q2 2025
                
                Prepared by: Finance Department
                Date: July 31, 2025
                
                EXECUTIVE SUMMARY
                
                This report presents the financial performance of TechCorp Solutions Inc.
                for the second quarter of 2025 (April 1 - June 30, 2025).
                
                KEY FINDINGS:
                
                1. Revenue Growth: Total revenue increased by 25% year-over-year to $12.5 million,
                   driven primarily by new enterprise clients and expanded service offerings.
                
                2. Operating Margins: Operating margin improved to 18.5%, up from 15.2% in Q2 2024,
                   due to operational efficiencies and automation initiatives.
                
                3. Customer Acquisition: Added 47 new clients in Q2, bringing total active
                   clients to 523, a 15% increase from the previous quarter.
                
                RECOMMENDATIONS:
                
                1. Increase investment in sales and marketing by 20% to accelerate growth
                2. Expand technical team by 15 engineers to meet growing demand
                3. Implement new CRM system to improve customer retention
                
                CONCLUSION:
                
                Q2 2025 demonstrated strong financial performance with significant growth
                in revenue and profitability. The company is well-positioned for continued
                expansion in the second half of 2025.
            """
        }
    ]
    
    print("=" * 60)
    print("🧪 TESTING LANGEXTRACT SERVICE")
    print("=" * 60)
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        # First, check health
        print("\n📋 Checking service health...")
        try:
            response = await client.get(f"{base_url}/health")
            if response.status_code == 200:
                health = response.json()
                print(f"✅ Service is healthy")
                print(f"   Version: {health['version']}")
                print(f"   Providers: {', '.join(health['providers'])}")
                print(f"   Default: {health['default_provider']}")
            else:
                print(f"❌ Health check failed: {response.status_code}")
                return
        except Exception as e:
            print(f"❌ Cannot connect to service: {e}")
            print("   Make sure the service is running with: docker-compose up langextract-service")
            return
        
        # Test each document
        for test_doc in test_documents:
            print(f"\n{'='*60}")
            print(f"📄 Testing: {test_doc['name']}")
            print(f"   Type: {test_doc['document_type']}")
            print(f"{'='*60}")
            
            try:
                # Send extraction request
                response = await client.post(
                    f"{base_url}/api/v1/extraction/extract",
                    json={
                        "text": test_doc["text"],
                        "document_type": test_doc["document_type"],
                        "filename": f"test_{test_doc['document_type']}.txt"
                    },
                    headers={"X-API-Key": api_key}
                )
                
                if response.status_code == 200:
                    result = response.json()
                    
                    print(f"\n✅ Extraction successful!")
                    print(f"   Total extractions: {len(result.get('extractions', []))}")
                    
                    # Show entities by type
                    entities = result.get("entities", {})
                    if entities:
                        print(f"\n📊 Entities found:")
                        for entity_type, items in entities.items():
                            print(f"   • {entity_type}: {len(items)} items")
                            for item in items[:2]:  # Show first 2 of each type
                                print(f"     - {item['text'][:50]}...")
                    
                    # Show summary
                    summary = result.get("summary", {})
                    if summary:
                        print(f"\n📝 Summary:")
                        for key, value in summary.items():
                            if value:
                                if isinstance(value, list):
                                    print(f"   • {key}: {len(value)} items")
                                    for v in value[:2]:
                                        print(f"     - {str(v)[:50]}...")
                                elif isinstance(value, dict):
                                    print(f"   • {key}: {len(value)} entries")
                                else:
                                    print(f"   • {key}: {str(value)[:100]}...")
                    
                    # Show metadata
                    metadata = result.get("metadata", {})
                    print(f"\n🔧 Metadata:")
                    print(f"   Provider: {metadata.get('provider')}")
                    print(f"   Model: {metadata.get('model')}")
                    print(f"   Passes: {metadata.get('extraction_passes')}")
                    
                else:
                    print(f"❌ Extraction failed: {response.status_code}")
                    print(f"   Error: {response.text}")
                    
            except Exception as e:
                print(f"❌ Error testing {test_doc['name']}: {e}")
        
        # Get service stats
        print(f"\n{'='*60}")
        print("📊 Service Statistics")
        print(f"{'='*60}")
        
        try:
            response = await client.get(
                f"{base_url}/api/v1/extraction/stats",
                headers={"X-API-Key": api_key}
            )
            
            if response.status_code == 200:
                stats = response.json()
                print(f"✅ Stats retrieved:")
                print(f"   Supported types: {', '.join(stats['supported_document_types'])}")
                print(f"   Available providers: {', '.join(stats['available_providers'])}")
                print(f"   Extraction passes: {stats['extraction_passes']}")
                print(f"   Max buffer: {stats['max_char_buffer']} chars")
                print(f"   Confidence threshold: {stats['confidence_threshold']}")
        except Exception as e:
            print(f"❌ Error getting stats: {e}")
    
    print(f"\n{'='*60}")
    print("✅ Tests completed!")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(test_langextract_service())
