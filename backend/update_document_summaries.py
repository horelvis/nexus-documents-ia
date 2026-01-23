#!/usr/bin/env python3
"""
Update existing documents to replace first 1000 chars with summaries
"""
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, text
import sys
import os

# Add app to path
sys.path.insert(0, '/app' if os.path.exists('/.dockerenv') else '.')

# Database configuration - Use environment variables (required)
DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("ASYNC_DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL environment variable is required. "
        "Set it to: postgresql+asyncpg://user:password@host:port/dbname"
    )

# CAG Service URL - defaults based on environment
if os.path.exists('/.dockerenv'):
    CAG_SERVICE_URL = os.getenv("CAG_SERVICE_URL", "http://weaviate-service:8000")
else:
    CAG_SERVICE_URL = os.getenv("CAG_SERVICE_URL", "http://localhost:8000")

MICROSERVICES_API_KEY = os.getenv("MICROSERVICES_API_KEY")
DEFAULT_TENANT = os.getenv("DEFAULT_TENANT", "default")

if not MICROSERVICES_API_KEY:
    raise RuntimeError("MICROSERVICES_API_KEY environment variable is required for update_document_summaries.py")

# Create async engine
engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def create_simple_summary(text: str, filename: str) -> str:
    """Create a simple summary without LLM"""
    # Clean up text
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    # Try to identify document type from content
    text_lower = text.lower()[:2000]
    doc_type = "Document"
    
    if "contract" in text_lower or "agreement" in text_lower or "contrato" in text_lower:
        doc_type = "Contract"
    elif "invoice" in text_lower or "bill" in text_lower or "factura" in text_lower:
        doc_type = "Invoice"
    elif "report" in text_lower or "analysis" in text_lower or "informe" in text_lower:
        doc_type = "Report"
    elif "employee" in text_lower or "resume" in text_lower or "empleado" in text_lower:
        doc_type = "HR Document"
    
    # Get first meaningful lines
    meaningful_lines = []
    for line in lines[:10]:
        if len(line) > 20:  # Skip very short lines
            meaningful_lines.append(line)
            if len(meaningful_lines) >= 3:
                break
    
    if meaningful_lines:
        preview = " ".join(meaningful_lines[:2])[:200]
        return f"{doc_type}: {filename}. {preview}..."
    else:
        return f"{doc_type}: {filename}. Content preview: {text[:200]}..."


async def generate_llm_summary(text: str, filename: str) -> str:
    """Generate summary using CAG microservice"""
    try:
        import httpx
        
        text_for_summary = text[:5000] if len(text) > 5000 else text
        prompt = (
            "Genera un resumen conciso (máximo 200 palabras) en 2-3 oraciones. "
            "Incluye objetivo, puntos clave y conclusiones.\n\n"
            f"Archivo: {filename}\n"
            f"Contenido:\n{text_for_summary}"
        )
        
        async with httpx.AsyncClient(timeout=45.0) as client:
            response = await client.post(
                f"{CAG_SERVICE_URL.rstrip('/')}/api/v1/cag/query",
                json={
                    "query": prompt,
                    "tenant_id": DEFAULT_TENANT,
                    "user_id": "summary-script",
                    "context": {
                        "task": "document_summary",
                        "filename": filename
                    }
                },
                headers={
                    "X-API-Key": MICROSERVICES_API_KEY,
                    "X-Tenant-ID": DEFAULT_TENANT
                }
            )
            
            if response.status_code == 200:
                summary = response.json().get("answer", "")
                if summary:
                    return summary.strip()[:1000]
            else:
                print(f"  ⚠️  CAG summary request failed: {response.status_code} -> {response.text[:120]}")
    except Exception as e:
        print(f"  ⚠️  LLM summary failed: {e}")
    
    return create_simple_summary(text, filename)


async def update_document_summaries():
    """Update all documents with proper summaries"""
    async with AsyncSessionLocal() as db:
        # Get documents with content
        result = await db.execute(
            text("""
                SELECT id, title, filename, content 
                FROM documents 
                WHERE content IS NOT NULL 
                AND LENGTH(content) > 0
                ORDER BY created_at DESC
            """)
        )
        
        documents = result.fetchall()
        print(f"\n📊 Found {len(documents)} documents with content")
        
        updated_count = 0
        for doc in documents:
            doc_id, title, filename, content = doc
            
            print(f"\n📄 Processing: {title} ({filename})")
            print(f"   Current content length: {len(content)} chars")
            
            # Check if content looks like a summary already
            if content.startswith("Document:") or content.startswith("Contract:") or \
               content.startswith("Invoice:") or content.startswith("Report:"):
                print("   ✓ Already has summary format, skipping")
                continue
            
            # Generate summary
            print("   🔄 Generating summary...")
            summary = await generate_llm_summary(content, filename)
            
            # Update document
            await db.execute(
                text("""
                    UPDATE documents 
                    SET content = :summary 
                    WHERE id = :doc_id
                """),
                {"summary": summary[:1000], "doc_id": doc_id}
            )
            
            print(f"   ✅ Updated with summary ({len(summary)} chars)")
            updated_count += 1
        
        await db.commit()
        print(f"\n✅ Updated {updated_count} documents with summaries")
        
        # Show sample of updated documents
        if updated_count > 0:
            print("\n📋 Sample summaries:")
            result = await db.execute(
                text("""
                    SELECT title, content 
                    FROM documents 
                    WHERE content IS NOT NULL 
                    ORDER BY updated_at DESC 
                    LIMIT 3
                """)
            )
            
            for title, summary in result:
                print(f"\n📄 {title}")
                print(f"   Summary: {summary[:200]}...")


async def main():
    """Main function"""
    print("=" * 60)
    print("📝 DOCUMENT SUMMARY UPDATER")
    print("=" * 60)
    
    await update_document_summaries()
    
    print("\n" + "=" * 60)
    print("✅ Process complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
