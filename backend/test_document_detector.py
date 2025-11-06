#!/usr/bin/env python3
"""
Test the new DocumentTypeDetector with configuration-based patterns
"""
import sys
import os
sys.path.insert(0, '.')

from app.services.document_type_detector import DocumentTypeDetector

def test_detector():
    """Test document type detection with various samples"""
    
    # Create detector instance
    detector = DocumentTypeDetector()
    
    # Test samples
    test_cases = [
        {
            "name": "English Contract",
            "filename": "service_agreement.pdf",
            "content": """
                SERVICE AGREEMENT
                This Agreement is entered into between Company A ("Client") and Company B ("Provider").
                The parties hereby agree to the following terms and conditions:
                1. Provider shall deliver services as specified
                2. Client shall pay monthly fees
                Both parties acknowledge their obligations under this contract.
            """
        },
        {
            "name": "Spanish Contract",
            "filename": "contrato_trabajo.pdf",
            "content": """
                CONTRATO DE TRABAJO INDEFINIDO
                Entre el empleador TechCorp S.A. y el empleado Juan García.
                Las partes acuerdan las siguientes cláusulas:
                1. El empleado prestará servicios como desarrollador
                2. El salario mensual será de 3000 euros
                Firmado en Madrid a 6 de agosto de 2025.
            """
        },
        {
            "name": "Invoice",
            "filename": "invoice_2025_001.pdf",
            "content": """
                INVOICE #2025-001
                Bill To: Customer Inc.
                Date: August 6, 2025
                Due Date: September 6, 2025
                
                Items:
                - Consulting Services: $5,000
                - Development Work: $10,000
                
                Subtotal: $15,000
                Tax (10%): $1,500
                Total Amount Due: $16,500
            """
        },
        {
            "name": "Financial Report",
            "filename": "annual_report_2025.pdf",
            "content": """
                ANNUAL FINANCIAL REPORT 2025
                
                Executive Summary:
                This report presents the financial performance for fiscal year 2025.
                
                Key Findings:
                - Revenue increased by 25%
                - Profit margins improved to 18%
                - Operating expenses reduced by 10%
                
                Conclusion:
                The company showed strong financial performance across all metrics.
            """
        },
        {
            "name": "Technical Documentation",
            "filename": "api_specification.md",
            "content": """
                API Technical Specification
                
                This manual describes the REST API endpoints and configuration.
                
                Installation Requirements:
                - Python 3.9+
                - Docker
                
                API Endpoints:
                GET /api/v1/documents
                POST /api/v1/upload
                
                Configuration:
                Set environment variables for authentication.
            """
        },
        {
            "name": "Unknown Document",
            "filename": "random_notes.txt",
            "content": """
                Some random notes here.
                Nothing specific or structured.
                Just general information.
            """
        }
    ]
    
    print("=" * 60)
    print("DOCUMENT TYPE DETECTOR TEST")
    print("=" * 60)
    
    # Test each case
    for test_case in test_cases:
        print(f"\n📄 Testing: {test_case['name']}")
        print(f"   Filename: {test_case['filename']}")
        
        # Detect type
        doc_type, confidence = detector.detect_type(
            test_case['content'], 
            test_case['filename']
        )
        
        # Detect language
        language = detector.detect_language(test_case['content'])
        
        print(f"   ✅ Type: {doc_type}")
        print(f"   ✅ Confidence: {confidence:.2%}")
        print(f"   ✅ Language: {language}")
    
    print("\n" + "=" * 60)
    
    # Test custom pattern addition
    print("\n🔧 Testing Custom Pattern Addition:")
    detector.add_custom_pattern(
        doc_type="medical",
        keywords=["patient", "diagnosis", "treatment", "medical", "prescription"],
        language="english"
    )
    
    medical_content = """
        PATIENT MEDICAL RECORD
        Patient Name: John Doe
        Diagnosis: Hypertension
        Treatment: Daily medication
        Prescription: Lisinopril 10mg
    """
    
    doc_type, confidence = detector.detect_type(medical_content, "medical_record.pdf")
    print(f"   Medical document detected as: {doc_type} (confidence: {confidence:.2%})")
    
    print("\n✅ All tests completed!")


if __name__ == "__main__":
    test_detector()