"""Heartbeat Stats API — Provides statistics for Emma Heartbeat System.

These endpoints are consumed by emma-agent-service's Heartbeat System
to gather context for proactive insight generation.
"""
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import func, select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.async_dependencies import get_async_db
from app.core.config import settings


async def verify_api_key(x_api_key: str = Header(..., alias="X-API-Key")) -> str:
    """Verify the microservices API key."""
    if x_api_key != settings.MICROSERVICES_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key


router = APIRouter(
    prefix="/stats",
    tags=["heartbeat-stats"],
    dependencies=[Depends(verify_api_key)],
)


@router.get("")
async def get_stats(
    db: AsyncSession = Depends(get_async_db),
) -> Dict[str, Any]:
    """Get document statistics.

    Returns:
        - total_documents: Total indexed documents
        - indexed_7d: Documents indexed in last 7 days
        - by_collection: Document counts by Weaviate collection
        - recent_documents: List of recently indexed documents (last 24h)
    """
    from app.db.models import IndexedDocument

    now = datetime.now(timezone.utc)
    cutoff_24h = now - timedelta(hours=24)
    cutoff_7d = now - timedelta(days=7)

    # Total documents
    total_result = await db.execute(
        select(func.count(IndexedDocument.id)).where(
            IndexedDocument.indexing_status == "indexed"
        )
    )
    total = total_result.scalar() or 0

    # Documents indexed in last 7 days
    indexed_7d_result = await db.execute(
        select(func.count(IndexedDocument.id)).where(
            and_(
                IndexedDocument.indexing_status == "indexed",
                IndexedDocument.indexed_at >= cutoff_7d,
            )
        )
    )
    indexed_7d = indexed_7d_result.scalar() or 0

    # By collection
    collection_result = await db.execute(
        select(
            IndexedDocument.weaviate_collection,
            func.count(IndexedDocument.id).label("count"),
        )
        .where(IndexedDocument.indexing_status == "indexed")
        .group_by(IndexedDocument.weaviate_collection)
    )
    by_collection = {
        row.weaviate_collection or "unknown": row.count
        for row in collection_result.all()
    }

    # Recent documents (last 24h)
    recent_result = await db.execute(
        select(IndexedDocument)
        .where(
            and_(
                IndexedDocument.indexing_status == "indexed",
                IndexedDocument.indexed_at >= cutoff_24h,
            )
        )
        .order_by(IndexedDocument.indexed_at.desc())
        .limit(20)
    )
    recent_docs = recent_result.scalars().all()

    recent_documents = [
        {
            "id": str(doc.id),
            "title": doc.title or doc.external_path,
            "collection": doc.weaviate_collection,
            "indexed_at": doc.indexed_at.isoformat() if doc.indexed_at else None,
            "metadata": doc.source_metadata or {},
        }
        for doc in recent_docs
    ]

    return {
        "total_documents": total,
        "indexed_7d": indexed_7d,
        "by_collection": by_collection,
        "recent_documents": recent_documents,
    }


@router.get("/contracts/expiring")
async def get_expiring_contracts(
    days: int = Query(default=30, ge=1, le=365),
    db: AsyncSession = Depends(get_async_db),
) -> Dict[str, Any]:
    """Get contracts expiring within specified days.

    Looks for documents with contract_end_date or expiry_date in source_metadata.

    Returns:
        - contracts: List of expiring contracts with expiry dates
    """
    from app.db.models import IndexedDocument

    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(days=days)

    # Query documents that might be contracts with expiry dates
    result = await db.execute(
        select(IndexedDocument)
        .where(
            and_(
                IndexedDocument.indexing_status == "indexed",
                or_(
                    IndexedDocument.source_metadata["contract_end_date"].isnot(None),
                    IndexedDocument.source_metadata["expiry_date"].isnot(None),
                    IndexedDocument.source_metadata["fecha_vencimiento"].isnot(None),
                ),
            )
        )
        .limit(100)
    )
    docs = result.scalars().all()

    contracts = []
    for doc in docs:
        metadata = doc.source_metadata or {}

        # Try different date field names
        expiry_str = (
            metadata.get("contract_end_date")
            or metadata.get("expiry_date")
            or metadata.get("fecha_vencimiento")
        )

        if not expiry_str:
            continue

        try:
            # Parse date (handle various formats)
            if isinstance(expiry_str, str):
                if "T" in expiry_str:
                    expiry_date = datetime.fromisoformat(expiry_str.replace("Z", "+00:00"))
                else:
                    expiry_date = datetime.strptime(expiry_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            else:
                continue

            # Check if within range and not already expired
            if now <= expiry_date <= cutoff:
                contracts.append({
                    "document_id": str(doc.id),
                    "title": doc.title or doc.external_path,
                    "expiry_date": expiry_date.isoformat(),
                    "counterparty": metadata.get("counterparty") or metadata.get("contraparte"),
                    "contract_type": metadata.get("contract_type") or metadata.get("tipo_contrato"),
                })
        except Exception:
            continue

    # Sort by expiry date
    contracts.sort(key=lambda c: c["expiry_date"])

    return {
        "days": days,
        "contracts": contracts,
    }


@router.get("/analyses/pending")
async def get_pending_analyses(
    db: AsyncSession = Depends(get_async_db),
) -> Dict[str, Any]:
    """Get count of pending document analyses.

    Returns:
        - pending_count: Documents pending analysis
        - stale_count: Documents pending for more than 7 days
    """
    from app.db.models import IndexedDocument

    now = datetime.now(timezone.utc)
    stale_cutoff = now - timedelta(days=7)

    # Pending analyses (indexing_status = 'pending' or 'queued')
    pending_result = await db.execute(
        select(func.count(IndexedDocument.id)).where(
            IndexedDocument.indexing_status.in_(["pending", "queued"])
        )
    )
    pending_count = pending_result.scalar() or 0

    # Stale (pending for >7 days)
    stale_result = await db.execute(
        select(func.count(IndexedDocument.id)).where(
            and_(
                IndexedDocument.indexing_status.in_(["pending", "queued"]),
                IndexedDocument.created_at <= stale_cutoff,
            )
        )
    )
    stale_count = stale_result.scalar() or 0

    return {
        "pending_count": pending_count,
        "stale_count": stale_count,
    }


@router.get("/anomalies/recent")
async def get_recent_anomalies(
    hours: int = Query(default=24, ge=1, le=168),
    db: AsyncSession = Depends(get_async_db),
) -> Dict[str, Any]:
    """Get recent anomalies (duplicates, indexing failures).

    Returns:
        - anomalies: List of detected anomalies
    """
    from app.db.models import IndexedDocument

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=hours)

    anomalies = []

    # 1. Indexing failures in last N hours
    failures_result = await db.execute(
        select(IndexedDocument)
        .where(
            and_(
                IndexedDocument.indexing_status == "failed",
                IndexedDocument.indexed_at >= cutoff,
            )
        )
        .limit(50)
    )
    failures = failures_result.scalars().all()

    if failures:
        anomalies.append({
            "type": "indexing_failure",
            "description": f"{len(failures)} documentos fallaron al indexar en las últimas {hours} horas",
            "document_ids": [str(f.id) for f in failures],
        })

    # 2. Duplicate content_hash detection
    duplicates_result = await db.execute(
        select(
            IndexedDocument.content_hash,
            func.count(IndexedDocument.id).label("count"),
            func.array_agg(IndexedDocument.id).label("ids"),
        )
        .where(
            and_(
                IndexedDocument.content_hash.isnot(None),
                IndexedDocument.indexing_status == "indexed",
            )
        )
        .group_by(IndexedDocument.content_hash)
        .having(func.count(IndexedDocument.id) > 1)
        .limit(20)
    )

    for row in duplicates_result.all():
        anomalies.append({
            "type": "duplicate",
            "description": f"Documento duplicado ({row.count} copias)",
            "document_ids": [str(id) for id in (row.ids or [])[:5]],
        })

    return {
        "hours": hours,
        "anomalies": anomalies,
    }
