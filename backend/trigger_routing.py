#!/usr/bin/env python3
"""
Manually trigger routing analysis for existing documents
"""
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, text
import os
import sys

# Add app to path
sys.path.insert(0, '/app')

from app.services.agent_router_service import AgentRouterService

# Database configuration - Use environment variable (required)
DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("ASYNC_DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL environment variable is required. "
        "Set it to: postgresql+asyncpg://user:password@host:port/dbname"
    )

# Create async engine
engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def trigger_routing_for_document(doc_id: str):
    """Trigger routing analysis for a specific document"""
    async with AsyncSessionLocal() as db:
        try:
            # Get document details
            result = await db.execute(
                text("""
                    SELECT d.id, d.title, d.filename, d.file_path, d.content,
                           d.tenant_id, d.created_by
                    FROM documents d
                    WHERE d.id = :doc_id
                """),
                {"doc_id": doc_id}
            )
            
            doc = result.fetchone()
            if not doc:
                print(f"❌ Document {doc_id} not found")
                return
            
            print(f"\n📄 Processing document: {doc.title}")
            print(f"   Filename: {doc.filename}")
            print(f"   Tenant: {doc.tenant_id}")
            
            # Check if routing already exists
            result = await db.execute(
                text("SELECT COUNT(*) FROM document_routing_analysis WHERE document_id = :doc_id"),
                {"doc_id": doc_id}
            )
            count = result.scalar()
            
            if count > 0:
                print(f"⚠️  Routing analysis already exists for this document")
                return
            
            # Create router service
            router = AgentRouterService(
                tenant_id=str(doc.tenant_id),
                user_id=str(doc.created_by)
            )
            
            # Get document content (use description if content is empty)
            content = doc.content or f"Document: {doc.title}. File: {doc.filename}"
            
            print(f"\n🔄 Starting routing analysis...")
            
            # Trigger routing
            routing_result = await router.analyze_and_route_document(
                db=db,
                document_id=str(doc.id),
                content=content,
                filename=doc.filename,
                file_type=doc.file_path.split('.')[-1] if '.' in doc.file_path else 'pdf'
            )
            
            if routing_result.get("success"):
                print(f"✅ Routing completed successfully!")
                print(f"   Document Type: {routing_result.get('document_type')}")
                print(f"   Confidence: {routing_result.get('confidence', 0)*100:.1f}%")
                print(f"   Assigned Agents: {routing_result.get('assigned_agents')}")
                print(f"   Strategy: {routing_result.get('routing_strategy')}")
                print(f"   Priority: {routing_result.get('priority')}")
            else:
                print(f"❌ Routing failed: {routing_result.get('error')}")
                
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()


async def main():
    """Main function"""
    print("=" * 60)
    print("📊 MANUAL ROUTING TRIGGER")
    print("=" * 60)
    
    # Document ID to process (from your upload)
    doc_id = "ffa47652-6750-4853-81b3-a3efc3bd5b0d"
    
    await trigger_routing_for_document(doc_id)
    
    print("\n" + "=" * 60)
    print("✅ Process complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())