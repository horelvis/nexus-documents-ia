"""
Debug endpoint to check document sync
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.api.async_dependencies import get_current_active_superuser_async, get_async_db
from app.db.models import Document, User, Tenant
from app.services.storage_service import StorageService
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/check-sync")
async def check_document_sync(
    current_user: User = Depends(get_current_active_superuser_async),
    db: AsyncSession = Depends(get_async_db)
):
    """Check sync between database and GCS storage"""
    
    # Count documents in database for current tenant
    count_result = await db.execute(
        select(func.count(Document.id)).filter(
            Document.tenant_id == current_user.tenant_id
        )
    )
    db_count = count_result.scalar() or 0
    
    # Get sample documents
    docs_result = await db.execute(
        select(Document).filter(
            Document.tenant_id == current_user.tenant_id
        ).limit(5)
    )
    sample_docs = docs_result.scalars().all()
    
    # Check storage
    storage_info = {
        "error": None,
        "file_count": 0,
        "sample_files": []
    }
    
    try:
        # Get tenant bucket name
        tenant_result = await db.execute(
            select(Tenant).filter(Tenant.id == current_user.tenant_id)
        )
        tenant = tenant_result.scalar_one()
        
        storage = StorageService(str(current_user.tenant_id), bucket_name=tenant.bucket_name)
        files = storage.list_files()
        storage_info["file_count"] = len(files)
        storage_info["sample_files"] = files[:5] if files else []
        storage_info["bucket_name"] = tenant.bucket_name
        
    except Exception as e:
        storage_info["error"] = str(e)
        logger.error(f"Storage check error: {e}")
    
    return {
        "tenant_id": str(current_user.tenant_id),
        "database": {
            "document_count": db_count,
            "sample_documents": [
                {
                    "id": str(doc.id),
                    "title": doc.title,
                    "filename": doc.filename,
                    "file_path": doc.file_path,
                    "created_at": doc.created_at.isoformat() if doc.created_at else None
                }
                for doc in sample_docs
            ]
        },
        "storage": storage_info,
        "sync_status": {
            "in_sync": db_count == storage_info["file_count"],
            "db_only": db_count if storage_info["file_count"] == 0 else 0,
            "storage_only": storage_info["file_count"] if db_count == 0 else 0
        }
    }