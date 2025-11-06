#!/usr/bin/env python3
"""
Simple test for LangExtract service using curl
"""
import json
import subprocess

def test_extraction(doc_type, text):
    """Test extraction for a specific document type"""
    print(f"\n{'='*60}")
    print(f"📄 Testing: {doc_type.upper()}")
    print(f"{'='*60}")
    
    # Prepare request data
    data = {
        "text": text,
        "document_type": doc_type,
        "filename": f"test_{doc_type}.txt"
    }
    
    # Send request using curl
    cmd = [
        "curl", "-s", "-X", "POST",
        "http://localhost:8009/api/v1/extraction/extract",
        "-H", "Content-Type: application/json",
        "-H", "X-API-Key: dev-api-key-2024",
        "-d", json.dumps(data)
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            response = json.loads(result.stdout)
            
            if response.get("success"):
                print("✅ Extraction successful!")
                
                # Show summary
                summary = response.get("summary", {})
                if summary:
                    print("\n📝 Summary:")
                    for key, value in list(summary.items())[:5]:  # Show first 5 items
                        if value:
                            if isinstance(value, list):
                                print(f"   • {key}: {len(value)} items")
                                for v in value[:2]:
                                    print(f"     - {str(v)[:50]}...")
                            else:
                                print(f"   • {key}: {str(value)[:100]}...")
                
                # Show entities
                entities = response.get("entities", {})
                if entities:
                    print("\n📊 Entities found:")
                    for entity_type, items in list(entities.items())[:3]:
                        print(f"   • {entity_type}: {len(items)} items")
                        for item in items[:2]:
                            print(f"     - {item.get('text', '')[:50]}...")
                
                # Show metadata
                metadata = response.get("metadata", {})
                print(f"\n🔧 Metadata:")
                print(f"   Provider: {metadata.get('provider')}")
                print(f"   Model: {metadata.get('model')}")
                print(f"   Total extractions: {metadata.get('total_extractions')}")
            else:
                print(f"❌ Extraction failed: {response.get('error', 'Unknown error')}")
        else:
            print(f"❌ Request failed: {result.stderr}")
            
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON response: {e}")
        print(f"   Response: {result.stdout[:200]}...")
    except Exception as e:
        print(f"❌ Error: {e}")


# Test documents
print("=" * 60)
print("🧪 TESTING LANGEXTRACT SERVICE")
print("=" * 60)

# Test 1: Contract
contract_text = """
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
payable within 30 days of invoice receipt.

3. TERM
This Agreement shall commence on August 6, 2025, and continue for a period
of 12 months, unless earlier terminated.

Signed:
John Smith, CEO
TechCorp Solutions Inc.
"""

test_extraction("contract", contract_text)

# Test 2: Invoice
invoice_text = """
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
"""

test_extraction("invoice", invoice_text)

# Test 3: Report
report_text = """
QUARTERLY FINANCIAL REPORT Q2 2025

Prepared by: Finance Department
Date: July 31, 2025

EXECUTIVE SUMMARY

This report presents the financial performance of TechCorp Solutions Inc.
for the second quarter of 2025 (April 1 - June 30, 2025).

KEY FINDINGS:

1. Revenue Growth: Total revenue increased by 25% year-over-year to $12.5 million,
   driven primarily by new enterprise clients.

2. Operating Margins: Operating margin improved to 18.5%, up from 15.2% in Q2 2024,
   due to operational efficiencies.

3. Customer Acquisition: Added 47 new clients in Q2, bringing total active
   clients to 523, a 15% increase from previous quarter.

RECOMMENDATIONS:

1. Increase investment in sales and marketing by 20%
2. Expand technical team by 15 engineers
3. Implement new CRM system

CONCLUSION:

Q2 2025 demonstrated strong financial performance with significant growth
in revenue and profitability.
"""

test_extraction("report", report_text)

# Check service stats
print("\n" + "=" * 60)
print("📊 Service Statistics")
print("=" * 60)

stats_cmd = [
    "curl", "-s", "-X", "GET",
    "http://localhost:8009/api/v1/extraction/stats",
    "-H", "X-API-Key: dev-api-key-2024"
]

try:
    result = subprocess.run(stats_cmd, capture_output=True, text=True)
    if result.returncode == 0:
        stats = json.loads(result.stdout)
        print("✅ Stats retrieved:")
        print(f"   Supported types: {', '.join(stats['supported_document_types'])}")
        print(f"   Available providers: {', '.join(stats['available_providers'])}")
        print(f"   Extraction passes: {stats['extraction_passes']}")
        print(f"   Max buffer: {stats['max_char_buffer']} chars")
except Exception as e:
    print(f"❌ Error getting stats: {e}")

print("\n" + "=" * 60)
print("✅ Tests completed!")
print("=" * 60)