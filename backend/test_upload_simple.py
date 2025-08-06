#!/usr/bin/env python3
"""
Simple test to verify document upload and routing
Uses direct database access to check results
"""
import asyncio
import httpx
import time
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, text

# Database configuration
# Use db service name when running inside Docker
import os
if os.path.exists('/.dockerenv'):
    # Running inside Docker container
    DATABASE_URL = "postgresql+asyncpg://postgres:password@db:5432/nexus_db"
else:
    # Running on host
    DATABASE_URL = "postgresql+asyncpg://postgres:password@localhost:5432/nexus_db"

# Create async engine
engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def check_routing_analysis():
    """Check if routing analysis records exist"""
    async with AsyncSessionLocal() as db:
        # Check routing analysis table
        result = await db.execute(
            text("SELECT COUNT(*) FROM document_routing_analysis")
        )
        count = result.scalar()
        print(f"\n📊 Routing Analysis Records: {count}")
        
        if count > 0:
            # Get recent routing analyses
            result = await db.execute(
                text("""
                    SELECT 
                        dra.document_id,
                        dra.document_type,
                        dra.confidence_score,
                        dra.assigned_agents,
                        dra.routing_strategy,
                        dra.priority_level,
                        d.title,
                        d.filename
                    FROM document_routing_analysis dra
                    JOIN documents d ON d.id = dra.document_id
                    ORDER BY dra.created_at DESC
                    LIMIT 5
                """)
            )
            
            print("\n🎯 Recent Routing Analyses:")
            print("-" * 80)
            for row in result:
                print(f"\n📄 Document: {row.title} ({row.filename})")
                print(f"   Type: {row.document_type}")
                print(f"   Confidence: {row.confidence_score:.2%}")
                print(f"   Agents: {row.assigned_agents}")
                print(f"   Strategy: {row.routing_strategy}")
                print(f"   Priority: {row.priority_level}")
        
        # Check agent assignments
        result = await db.execute(
            text("SELECT COUNT(*) FROM document_agent_assignments")
        )
        assignment_count = result.scalar()
        print(f"\n🤖 Agent Assignments: {assignment_count}")
        
        if assignment_count > 0:
            result = await db.execute(
                text("""
                    SELECT 
                        agent_type,
                        agent_name,
                        status,
                        execution_order
                    FROM document_agent_assignments
                    ORDER BY created_at DESC
                    LIMIT 10
                """)
            )
            
            print("\n📋 Recent Agent Assignments:")
            for row in result:
                status_icon = "✅" if row.status == "completed" else "⏳" if row.status == "pending" else "❌"
                print(f"   {status_icon} {row.agent_name} ({row.agent_type}) - Order: {row.execution_order}")


async def check_documents():
    """Check recently uploaded documents"""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            text("""
                SELECT 
                    id,
                    title,
                    filename,
                    category,
                    created_at
                FROM documents
                ORDER BY created_at DESC
                LIMIT 5
            """)
        )
        
        print("\n📁 Recent Documents:")
        print("-" * 80)
        for row in result:
            print(f"\n📄 {row.title}")
            print(f"   ID: {row.id}")
            print(f"   File: {row.filename}")
            print(f"   Category: {row.category}")
            print(f"   Created: {row.created_at}")


async def monitor_cag_service():
    """Monitor CAG service activity"""
    print("\n🔍 Checking CAG Service...")
    
    # Use service name when running inside Docker
    cag_url = "http://cag-service:8008/health" if os.path.exists('/.dockerenv') else "http://localhost:8008/health"
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(cag_url)
            if response.status_code == 200:
                print("✅ CAG Service is healthy")
            else:
                print(f"⚠️  CAG Service status: {response.status_code}")
        except Exception as e:
            print(f"❌ CAG Service error: {e}")


async def main():
    """Main monitoring function"""
    print("=" * 80)
    print("📊 DOCUMENT ROUTING ANALYSIS MONITOR")
    print("=" * 80)
    
    # Check CAG service
    await monitor_cag_service()
    
    # Check documents
    await check_documents()
    
    # Check routing analysis
    await check_routing_analysis()
    
    print("\n" + "=" * 80)
    print("✅ Monitoring complete!")
    print("=" * 80)
    
    print("\n💡 To upload documents and trigger routing:")
    print("   1. Use the frontend at http://localhost:3000")
    print("   2. Log in with your account")
    print("   3. Upload documents with different types (contracts, invoices, reports)")
    print("   4. Run this script again to see the routing results")


if __name__ == "__main__":
    asyncio.run(main())