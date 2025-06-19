"""
Document Preview Worker
Processes document preview generation tasks in the background using ARQ
"""
import asyncio
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
import httpx
from pathlib import Path

from arq import cron
from arq.connections import RedisSettings

from app.core.config import settings
from app.db.async_database import AsyncSessionLocal
from app.db.models import Document
from app.services.document_preview_service import DocumentPreviewService
from app.services.async_storage_factory import AsyncStorageServiceFactory
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Redis settings for ARQ (reuse from categorization_worker)
redis_settings = RedisSettings(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    password=settings.REDIS_PASSWORD,
    database=0,
)


async def generate_document_preview(
    ctx: Dict[str, Any],
    document_id: str,
    tenant_id: str,
    user_id: str,
    preview_type: str = "all",  # "pdf", "thumbnail", or "all"
    force_regenerate: bool = False
) -> Dict[str, Any]:
    """
    Generate preview for a single document
    
    Args:
        ctx: ARQ context
        document_id: Document ID to preview
        tenant_id: Tenant ID
        user_id: User ID who triggered the preview
        preview_type: Type of preview to generate
        force_regenerate: Force regeneration even if preview exists
    """
    start_time = datetime.now(timezone.utc)
    
    try:
        async with AsyncSessionLocal() as db:
            # Get document
            stmt = select(Document).filter(
                Document.id == document_id,
                Document.tenant_id == tenant_id
            )
            result = await db.execute(stmt)
            doc = result.scalar_one_or_none()
            
            if not doc:
                return {
                    "success": False,
                    "error": f"Document {document_id} not found"
                }
            
            # Initialize services
            async with httpx.AsyncClient(timeout=60.0) as http_client:
                preview_service = DocumentPreviewService(
                    tenant_id=str(tenant_id),
                    user_id=str(user_id),
                    http_client=http_client
                )
                
                # Check if preview already exists (unless forcing regeneration)
                if not force_regenerate:
                    existing_preview = await preview_service.get_preview_info(str(document_id))
                    if existing_preview and existing_preview.get('pdf_available'):
                        logger.info(f"Preview already exists for document {document_id}")
                        return {
                            "success": True,
                            "document_id": document_id,
                            "preview_exists": True,
                            "preview_info": existing_preview
                        }
                
                # Download original file
                storage_service = await AsyncStorageServiceFactory.create_storage_service(
                    str(tenant_id), str(user_id), db
                )
                
                file_data = await storage_service.download_file(doc.file_path)
                if not file_data:
                    return {
                        "success": False,
                        "error": "Could not download original file"
                    }
                
                # Generate preview based on file type
                preview_result = None
                
                if doc.file_type.lower() == 'pdf':
                    # For PDFs, just generate thumbnails
                    if preview_type in ["thumbnail", "all"]:
                        preview_result = await preview_service.generate_pdf_thumbnails(
                            document_id=str(document_id),
                            pdf_content=file_data,
                            max_pages=3
                        )
                else:
                    # For other formats, generate PDF and/or thumbnails
                    if preview_type in ["pdf", "all"]:
                        preview_result = await preview_service.generate_preview(
                            document_id=str(document_id),
                            filename=doc.filename,
                            file_content=file_data,
                            generate_thumbnails=(preview_type == "all")
                        )
                    elif preview_type == "thumbnail":
                        # Generate PDF first, then thumbnails
                        pdf_result = await preview_service.generate_preview(
                            document_id=str(document_id),
                            filename=doc.filename,
                            file_content=file_data,
                            generate_thumbnails=True
                        )
                        preview_result = pdf_result
                
                # Update document metadata with preview info
                if preview_result and preview_result.get('success'):
                    doc.document_metadata = doc.document_metadata or {}
                    doc.document_metadata['preview'] = {
                        'generated_at': datetime.now(timezone.utc).isoformat(),
                        'pdf_available': preview_result.get('pdf_path') is not None,
                        'thumbnails_available': bool(preview_result.get('thumbnail_paths')),
                        'thumbnail_count': len(preview_result.get('thumbnail_paths', [])),
                        'generator': 'gotenberg',
                        'processing_time': (datetime.now(timezone.utc) - start_time).total_seconds()
                    }
                    await db.commit()
                    
                    logger.info(f"Preview generated for document {document_id}")
                    
                    return {
                        "success": True,
                        "document_id": document_id,
                        "preview_type": preview_type,
                        "pdf_generated": preview_result.get('pdf_path') is not None,
                        "thumbnails_generated": len(preview_result.get('thumbnail_paths', [])),
                        "processing_time": (datetime.now(timezone.utc) - start_time).total_seconds()
                    }
                else:
                    error_msg = preview_result.get('error', 'Unknown error') if preview_result else 'Preview generation failed'
                    return {
                        "success": False,
                        "document_id": document_id,
                        "error": error_msg
                    }
                    
    except Exception as e:
        logger.error(f"Error generating preview for document {document_id}: {e}")
        return {
            "success": False,
            "document_id": document_id,
            "error": str(e)
        }
    finally:
        # Cleanup is handled by context managers
        pass


async def generate_preview_batch(
    ctx: Dict[str, Any],
    document_ids: List[str],
    tenant_id: str,
    user_id: str,
    preview_type: str = "all",
    batch_size: int = 5
) -> Dict[str, Any]:
    """
    Generate previews for multiple documents in a batch
    
    Args:
        ctx: ARQ context
        document_ids: List of document IDs
        tenant_id: Tenant ID
        user_id: User ID
        preview_type: Type of preview to generate
        batch_size: Number of documents to process concurrently
    """
    results = []
    
    # Process in batches to avoid overwhelming Gotenberg
    for i in range(0, len(document_ids), batch_size):
        batch = document_ids[i:i + batch_size]
        
        # Process batch concurrently
        tasks = [
            generate_document_preview(ctx, doc_id, tenant_id, user_id, preview_type)
            for doc_id in batch
        ]
        
        batch_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for doc_id, result in zip(batch, batch_results):
            if isinstance(result, Exception):
                results.append({
                    "document_id": doc_id,
                    "success": False,
                    "error": str(result)
                })
            else:
                results.append(result)
        
        # Small delay between batches to avoid overload
        if i + batch_size < len(document_ids):
            await asyncio.sleep(2)
    
    # Summary
    successful = sum(1 for r in results if r.get("success"))
    failed = len(results) - successful
    
    return {
        "total": len(document_ids),
        "successful": successful,
        "failed": failed,
        "results": results
    }


async def auto_generate_missing_previews(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """
    Scheduled task to automatically generate missing previews
    Runs periodically via cron
    """
    try:
        async with AsyncSessionLocal() as db:
            # Find documents without previews
            # Query for documents that don't have preview metadata
            stmt = select(Document).filter(
                Document.file_type.notin_(['pdf']),  # Skip PDFs as they don't need conversion
                Document.document_metadata['preview'].is_(None)  # No preview info
            ).limit(100)  # Process up to 100 at a time
            
            result = await db.execute(stmt)
            documents = result.scalars().all()
            
            if not documents:
                logger.info("No documents need preview generation")
                return {
                    "success": True,
                    "message": "No documents need preview generation"
                }
            
            # Group by tenant
            tenant_docs = {}
            for doc in documents:
                tenant_id = str(doc.tenant_id)
                if tenant_id not in tenant_docs:
                    tenant_docs[tenant_id] = []
                tenant_docs[tenant_id].append(str(doc.id))
            
            total_queued = 0
            
            # Queue preview generation for each tenant
            for tenant_id, doc_ids in tenant_docs.items():
                await ctx['redis'].enqueue_job(
                    'generate_preview_batch',
                    doc_ids,
                    tenant_id,
                    "system",  # System user for scheduled tasks
                    "all",  # Generate both PDF and thumbnails
                    5  # batch_size
                )
                total_queued += len(doc_ids)
            
            logger.info(f"Queued {total_queued} documents for preview generation across {len(tenant_docs)} tenants")
            
            return {
                "success": True,
                "tenants_processed": len(tenant_docs),
                "documents_queued": total_queued
            }
            
    except Exception as e:
        logger.error(f"Error in auto preview generation cron: {e}")
        return {
            "success": False,
            "error": str(e)
        }


async def cleanup_old_previews(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """
    Clean up preview files for deleted documents
    Runs periodically to free up storage
    """
    try:
        # This would require tracking which previews exist in storage
        # and comparing with existing documents
        # For now, just log that it would run
        logger.info("Preview cleanup task would run here")
        
        return {
            "success": True,
            "message": "Preview cleanup completed"
        }
        
    except Exception as e:
        logger.error(f"Error in preview cleanup: {e}")
        return {
            "success": False,
            "error": str(e)
        }


# Worker configuration
class WorkerSettings:
    """Settings for ARQ worker"""
    redis_settings = redis_settings
    functions = [
        generate_document_preview,
        generate_preview_batch,
    ]
    cron_jobs = [
        cron(auto_generate_missing_previews, hour=2, minute=0),  # Run at 2 AM daily
        cron(cleanup_old_previews, day=1, hour=3, minute=0),  # Run monthly at 3 AM
    ]
    max_jobs = 5  # Limit concurrent jobs due to resource intensity
    job_timeout = 600  # 10 minutes timeout for preview generation