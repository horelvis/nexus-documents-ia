"""
Document Categorization Worker
Processes document categorization tasks in the background using ARQ
"""
import asyncio
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import httpx

from arq import cron
from arq.connections import RedisSettings

from app.core.config import settings
from app.db.async_database import AsyncSessionLocal
from app.db.models import Document
from sqlalchemy import select, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Redis settings for ARQ
redis_settings = RedisSettings(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    password=settings.REDIS_PASSWORD,
    database=0,
)


async def categorize_document(
    ctx: Dict[str, Any],
    document_id: str,
    tenant_id: str,
    user_id: str
) -> Dict[str, Any]:
    """
    Categorize a single document
    
    Args:
        ctx: ARQ context
        document_id: Document ID to categorize
        tenant_id: Tenant ID
        user_id: User ID who triggered the categorization
    """
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
            
            if not doc.content:
                return {
                    "success": False,
                    "error": "Document has no extracted content"
                }
            
            # Categorize using LangChain service
            category = await _categorize_with_llm(
                doc.filename,
                doc.content[:1000],
                tenant_id,
                user_id
            )
            
            if not category:
                # Fallback to rule-based
                category = _simple_categorize(doc.filename, doc.content)
            
            # Update document
            doc.category = category
            doc.document_metadata = doc.document_metadata or {}
            doc.document_metadata["auto_categorization"] = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "method": "llm" if category else "rule_based",
                "worker": "arq"
            }
            
            await db.commit()
            
            logger.info(f"Document {document_id} categorized as '{category}'")
            
            return {
                "success": True,
                "document_id": document_id,
                "category": category
            }
            
    except Exception as e:
        logger.error(f"Error categorizing document {document_id}: {e}")
        return {
            "success": False,
            "error": str(e)
        }


async def categorize_document_batch(
    ctx: Dict[str, Any],
    document_ids: List[str],
    tenant_id: str,
    user_id: str,
    batch_size: int = 10
) -> Dict[str, Any]:
    """
    Categorize multiple documents in a batch
    
    Args:
        ctx: ARQ context
        document_ids: List of document IDs to categorize
        tenant_id: Tenant ID
        user_id: User ID who triggered the categorization
        batch_size: Number of documents to process concurrently
    """
    results = []
    
    # Process in batches to avoid overwhelming the LLM service
    for i in range(0, len(document_ids), batch_size):
        batch = document_ids[i:i + batch_size]
        
        # Process batch concurrently
        tasks = [
            categorize_document(ctx, doc_id, tenant_id, user_id)
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
        
        # Small delay between batches
        if i + batch_size < len(document_ids):
            await asyncio.sleep(1)
    
    # Summary
    successful = sum(1 for r in results if r.get("success"))
    failed = len(results) - successful
    
    return {
        "total": len(document_ids),
        "successful": successful,
        "failed": failed,
        "results": results
    }


async def auto_categorize_pending_documents(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """
    Scheduled task to automatically categorize pending documents
    Runs periodically via cron
    """
    try:
        async with AsyncSessionLocal() as db:
            # Get all tenants with uncategorized documents
            stmt = select(Document.tenant_id).filter(
                or_(
                    Document.category.is_(None),
                    Document.category == "",
                    Document.category == "general"
                ),
                Document.indexed > 0
            ).distinct()
            
            result = await db.execute(stmt)
            tenant_ids = [row[0] for row in result.fetchall()]
            
            total_processed = 0
            
            for tenant_id in tenant_ids:
                # Get uncategorized documents for this tenant
                doc_stmt = select(Document.id).filter(
                    Document.tenant_id == tenant_id,
                    or_(
                        Document.category.is_(None),
                        Document.category == "",
                        Document.category == "general"
                    ),
                    Document.indexed > 0
                ).limit(50)  # Process up to 50 per tenant
                
                doc_result = await db.execute(doc_stmt)
                document_ids = [str(row[0]) for row in doc_result.fetchall()]
                
                if document_ids:
                    # Queue batch categorization
                    await ctx['redis'].enqueue_job(
                        'categorize_document_batch',
                        document_ids,
                        str(tenant_id),
                        "system",  # System user for scheduled tasks
                        10  # batch_size
                    )
                    
                    total_processed += len(document_ids)
            
            logger.info(f"Queued {total_processed} documents for categorization across {len(tenant_ids)} tenants")
            
            return {
                "success": True,
                "tenants_processed": len(tenant_ids),
                "documents_queued": total_processed
            }
            
    except Exception as e:
        logger.error(f"Error in auto categorization cron: {e}")
        return {
            "success": False,
            "error": str(e)
        }


async def _categorize_with_llm(
    filename: str,
    content_preview: str,
    tenant_id: str,
    user_id: str
) -> Optional[str]:
    """Helper function to categorize using CAG microservice"""
    try:
        prompt = (
            "Clasifica este documento en una de las categorías: "
            "contract, invoice, report, legal, financial, technical, correspondence, presentation o general. "
            "Responde solo con el nombre de la categoría.

"
            f"Nombre: {filename}
"
            f"Contenido:
{content_preview}"
        )

        async with httpx.AsyncClient(timeout=45.0) as client:
            response = await client.post(
                f"{settings.CAG_SERVICE_URL.rstrip('/')}/api/v1/cag/query",
                json={
                    "query": prompt,
                    "tenant_id": str(tenant_id),
                    "user_id": str(user_id or 'system'),
                    "context": {
                        "task": "auto_categorization",
                        "filename": filename
                    }
                },
                headers={
                    "X-API-Key": settings.MICROSERVICES_API_KEY,
                    "X-Tenant-ID": str(tenant_id)
                }
            )

            if response.status_code == 200:
                answer = response.json().get("answer", "")
                category = _normalize_category(answer)
                if category:
                    return category
            else:
                logger.warning(
                    "CAG categorization request failed | status=%s body=%s",
                    response.status_code,
                    response.text[:200]
                )

    except Exception as e:
        logger.error(f"Error in LLM categorization: {e}")

    return None


def _normalize_category(answer: str) -> Optional[str]:
    """Normalize arbitrary LLM response to one of the supported categories."""
    if not answer:
        return None
    valid_categories = [
        "contract", "invoice", "report", "legal", "financial",
        "technical", "correspondence", "presentation", "general"
    ]
    clean = answer.strip().lower()
    for category in valid_categories:
        if category in clean:
            return category
    first_word = clean.split()[0]
    return first_word if first_word in valid_categories else None

def _simple_categorize(filename: str, content: str) -> str:
    """Simple rule-based categorization as fallback"""
    filename_lower = filename.lower()
    content_lower = content.lower()[:1000]
    
    # Check filename and content for patterns
    if any(word in filename_lower for word in ["contract", "agreement", "terms"]):
        return "contract"
    elif any(word in filename_lower for word in ["invoice", "bill", "receipt"]):
        return "invoice"
    elif any(word in filename_lower for word in ["report", "analysis"]):
        return "report"
    elif any(word in content_lower for word in ["whereas", "agreement", "party", "shall"]):
        return "contract"
    elif any(word in content_lower for word in ["invoice", "total", "payment due", "bill to"]):
        return "invoice"
    elif any(word in content_lower for word in ["executive summary", "findings", "conclusion"]):
        return "report"
    elif filename_lower.endswith((".pptx", ".ppt")):
        return "presentation"
    else:
        return "general"


# Worker configuration
class WorkerSettings:
    """Settings for ARQ worker"""
    redis_settings = redis_settings
    functions = [
        categorize_document,
        categorize_document_batch,
    ]
    cron_jobs = [
        cron(auto_categorize_pending_documents, hour={0, 6, 12, 18}, minute=0)  # Run 4 times a day
    ]
    max_jobs = 10
    job_timeout = 300  # 5 minutes