#!/usr/bin/env python3
"""Create a test PDF with contract content"""
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import os

def create_contract_pdf():
    """Create a test PDF with contract content"""
    pdf_path = "/tmp/test_contract.pdf"
    
    # Create PDF
    c = canvas.Canvas(pdf_path, pagesize=letter)
    width, height = letter
    
    # Title
    c.setFont("Helvetica-Bold", 16)
    c.drawString(200, height - 50, "SERVICE AGREEMENT CONTRACT")
    
    # Contract content
    c.setFont("Helvetica", 12)
    y_position = height - 100
    
    contract_text = [
        "",
        "This Service Agreement ('Agreement') is entered into as of August 6, 2025,",
        "between TechCorp Solutions Inc. ('Service Provider') and Digital Innovations Ltd. ('Client').",
        "",
        "1. SCOPE OF SERVICES",
        "The Service Provider agrees to provide software development and consulting services",
        "as detailed in Schedule A attached hereto.",
        "",
        "2. PAYMENT TERMS",
        "Client agrees to pay Service Provider a monthly fee of $15,000 USD,",
        "payable within 30 days of invoice receipt.",
        "Late payments will incur a 1.5% monthly interest charge.",
        "",
        "3. TERM AND TERMINATION",
        "This Agreement shall commence on August 6, 2025, and continue for 12 months.",
        "Either party may terminate this Agreement with 60 days written notice.",
        "",
        "4. CONFIDENTIALITY",
        "Both parties agree to maintain strict confidentiality regarding all proprietary",
        "information exchanged during the term of this Agreement.",
        "",
        "5. INTELLECTUAL PROPERTY",
        "All work product created under this Agreement shall be the exclusive property",
        "of the Client upon full payment.",
        "",
        "6. LIMITATION OF LIABILITY",
        "In no event shall either party be liable for indirect, incidental,",
        "or consequential damages.",
        "",
        "7. GOVERNING LAW",
        "This Agreement shall be governed by the laws of the State of California.",
        "",
        "SIGNATURES:",
        "_____________________          _____________________",
        "Service Provider                     Client",
        "Date: ___________                   Date: ___________"
    ]
    
    for line in contract_text:
        c.drawString(50, y_position, line)
        y_position -= 20
        if y_position < 50:
            c.showPage()
            y_position = height - 50
    
    # Save PDF
    c.save()
    print(f"✅ PDF created: {pdf_path}")
    return pdf_path

if __name__ == "__main__":
    pdf_path = create_contract_pdf()
    print(f"Test PDF ready at: {pdf_path}")