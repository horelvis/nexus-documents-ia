#!/usr/bin/env python3
"""
Check sync between GCS bucket and database documents
"""
import asyncio
import logging
from sqlalchemy import select, func
from app.db.async_database import AsyncSessionLocal
from app.db.models import Document, User, Tenant
from app.services.storage_service import StorageService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def check_sync():
    async with AsyncSessionLocal() as db:
        # Get tenant info
        result = await db.execute(
            select(Tenant).limit(1)
        )
        tenant = result.scalar_one_or_none()
        
        if not tenant:
            logger.error("No tenants found in database")
            return
            
        logger.info(f"Checking tenant: {tenant.id} - {tenant.name}")
        
        # Count documents in database
        count_result = await db.execute(
            select(func.count(Document.id)).filter(
                Document.tenant_id == tenant.id
            )
        )
        db_count = count_result.scalar() or 0
        logger.info(f"Documents in database: {db_count}")
        
        # List documents in database
        if db_count > 0:
            docs_result = await db.execute(
                select(Document).filter(
                    Document.tenant_id == tenant.id
                ).limit(5)
            )
            docs = docs_result.scalars().all()
            logger.info("Sample documents in DB:")
            for doc in docs:
                logger.info(f"  - {doc.id}: {doc.title} ({doc.filename})")
        
        # Check storage
        try:
            storage = StorageService(str(tenant.id))
            files = storage.list_files()
            logger.info(f"Files in GCS bucket: {len(files)}")
            
            if files:
                logger.info("Sample files in GCS:")
                for file in files[:5]:
                    logger.info(f"  - {file['name']} ({file['size']} bytes)")
                    
            # Find files not in database
            if db_count == 0 and len(files) > 0:
                logger.warning("Files exist in GCS but no documents in database!")
                logger.info("You may need to run a sync script to import GCS files into the database")
                
        except Exception as e:
            logger.error(f"Error checking storage: {e}")
            
        # Check for orphaned DB records
        if db_count > 0:
            docs_result = await db.execute(
                select(Document.file_path).filter(
                    Document.tenant_id == tenant.id
                )
            )
            db_file_paths = [doc[0] for doc in docs_result.all()]
            
            gcs_file_names = [f['name'] for f in files] if files else []
            
            orphaned = set(db_file_paths) - set(gcs_file_names)
            if orphaned:
                logger.warning(f"Found {len(orphaned)} documents in DB without corresponding GCS files")

if __name__ == "__main__":
    asyncio.run(check_sync())