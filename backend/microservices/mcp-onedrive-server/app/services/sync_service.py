"""
OneDrive Sync & Indexing Service.

Same pattern as mcp-google-drive-server sync_service.py:
1. run_sync_job(): Lists files in OneDrive → creates/updates indexed_documents
2. run_index_pending_job(): Downloads from OneDrive → sends to Weaviate pipeline

Key difference from Google Drive: OneDrive files are native Office formats,
so no export/conversion is needed (no GOOGLE_EXPORT_TYPES equivalent).
"""
import asyncio
import base64
import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

import asyncpg
import httpx

from ..core.config import settings, load_connector_from_db
from .onedrive_service import OneDriveService, SUPPORTED_MIME_TYPES
from .oauth_service import oauth_service
from .job_manager import JobState

logger = logging.getLogger(__name__)

WEAVIATE_SERVICE_URL = os.getenv("WEAVIATE_SERVICE_URL", "http://weaviate-service:8000")
MICROSERVICES_API_KEY = os.getenv("MICROSERVICES_API_KEY", "")


# =============================================================================
# Database helpers
# =============================================================================

_db_pool: Optional[asyncpg.Pool] = None


async def _get_db_pool() -> asyncpg.Pool:
    global _db_pool
    if _db_pool is None:
        db_url = settings.database_url
        if db_url.startswith("postgresql+asyncpg://"):
            db_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
        _db_pool = await asyncpg.create_pool(db_url, min_size=2, max_size=10)
    return _db_pool


# =============================================================================
# Sync Job
# =============================================================================

async def run_sync_job(
    job_state: JobState,
    connector_id: str,
    full_sync: bool = False,
    batch_size: int = 10,
) -> Dict[str, Any]:
    """
    Execute sync job: fetch metadata from OneDrive → create IndexedDocument records.
    """
    pool = await _get_db_pool()
    conn = await pool.acquire()
    try:
        # Get connector
        row = await conn.fetchrow(
            """
            SELECT id, tenant_id, name, config, is_active, sync_enabled,
                   last_health_check, created_by_id, connector_type
            FROM connectors WHERE id = $1
            """,
            UUID(connector_id),
        )

        if not row:
            return {"success": False, "error": "Connector not found"}
        if not row["is_active"]:
            return {"success": False, "error": "Connector not active"}
        if not row["sync_enabled"]:
            return {"success": False, "error": "Sync disabled"}
        if row["connector_type"] != "onedrive":
            return {"success": False, "error": f"Not an onedrive connector: {row['connector_type']}"}

        tenant_id = row["tenant_id"]

        # Load full config with decrypted tokens
        config = await load_connector_from_db(UUID(connector_id), tenant_id)
        if not config:
            return {"success": False, "error": "Failed to load connector config"}

        if not config.is_authenticated:
            return {"success": False, "error": "Connector not authenticated. Please authorize via OAuth."}

        # Ensure fresh token
        access_token = await oauth_service.ensure_fresh_token(config)

        # Get owner
        owner_id = row["created_by_id"]
        if not owner_id:
            admin_row = await conn.fetchrow(
                "SELECT id FROM users WHERE tenant_id = $1 AND is_active = true LIMIT 1",
                tenant_id,
            )
            if admin_row:
                owner_id = admin_row["id"]
            else:
                return {"success": False, "error": "No owner found for documents"}

        # Create OneDrive service
        onedrive = OneDriveService(access_token, config)

        # Stats
        stats = {
            "items_found": 0,
            "items_new": 0,
            "items_updated": 0,
            "items_failed": 0,
            "errors": [],
        }

        try:
            # List files from OneDrive
            folder_id = config.folder_id  # None means root
            items = await onedrive.list_items(
                folder_id=folder_id,
                include_subfolders=config.include_subfolders,
                file_types=config.file_types,
            )

            stats["items_found"] = len(items)

            for item in items:
                try:
                    await _process_onedrive_item(
                        conn=conn,
                        item=item,
                        tenant_id=tenant_id,
                        connector_id=UUID(connector_id),
                        owner_id=owner_id,
                        stats=stats,
                        full_sync=full_sync,
                    )
                except Exception as e:
                    stats["items_failed"] += 1
                    stats["errors"].append({
                        "item_id": item.id,
                        "name": item.name,
                        "error": str(e),
                    })
                    logger.error(f"Error processing item {item.name}: {e}")

                # Update progress
                job_state.progress = {
                    "found": stats["items_found"],
                    "processed": stats["items_new"] + stats["items_updated"],
                    "failed": stats["items_failed"],
                }

        finally:
            await onedrive.close()

        # Update connector health
        health_status = "healthy" if stats["items_failed"] == 0 else "degraded"
        health_message = (
            f"Synced {stats['items_new']} new, {stats['items_updated']} updated, "
            f"{stats['items_failed']} failed"
        )
        await conn.execute(
            """
            UPDATE connectors SET
                last_health_check = $1,
                health_status = $2,
                health_message = $3
            WHERE id = $4
            """,
            datetime.now(timezone.utc),
            health_status,
            health_message,
            UUID(connector_id),
        )

        logger.info(
            f"Connector sync completed: {connector_id} - "
            f"found={stats['items_found']}, new={stats['items_new']}, "
            f"updated={stats['items_updated']}, failed={stats['items_failed']}"
        )

        stats["success"] = True
        return stats

    finally:
        await pool.release(conn)


async def _process_onedrive_item(
    conn: asyncpg.Connection,
    item,
    tenant_id: UUID,
    connector_id: UUID,
    owner_id: UUID,
    stats: Dict[str, Any],
    full_sync: bool = False,
) -> None:
    """Process a single item from OneDrive into IndexedDocument."""
    title = item.name
    mime_type = item.mime_type or "application/octet-stream"
    size_bytes = item.size_bytes or 0

    # File extension
    file_extension = None
    if item.name and "." in item.name:
        file_extension = item.name.rsplit(".", 1)[-1].lower()
    elif mime_type in SUPPORTED_MIME_TYPES:
        file_extension = SUPPORTED_MIME_TYPES[mime_type]

    external_url = item.web_url or ""

    # Build path from parent reference
    if item.parent_path:
        external_path = f"{item.parent_path}/{item.name}"
    else:
        external_path = f"/OneDrive/{item.name}"

    # Check if document already exists
    existing = await conn.fetchrow(
        """
        SELECT id FROM indexed_documents
        WHERE connector_id = $1 AND external_id = $2
        """,
        connector_id,
        item.id,
    )

    if existing:
        if full_sync:
            await conn.execute(
                """
                UPDATE indexed_documents SET
                    title = $1,
                    external_url = $2,
                    external_path = $3,
                    mime_type = $4,
                    size_bytes = $5,
                    file_extension = $6,
                    source_modified_at = $7,
                    updated_at = $8,
                    indexing_status = 'pending',
                    indexing_error = NULL
                WHERE connector_id = $9 AND external_id = $10
                """,
                title, external_url, external_path,
                mime_type, size_bytes, file_extension,
                item.modified_at,
                datetime.now(timezone.utc),
                connector_id, item.id,
            )
        else:
            await conn.execute(
                """
                UPDATE indexed_documents SET
                    title = $1,
                    external_url = $2,
                    external_path = $3,
                    mime_type = $4,
                    size_bytes = $5,
                    file_extension = $6,
                    source_modified_at = $7,
                    updated_at = $8
                WHERE connector_id = $9 AND external_id = $10
                """,
                title, external_url, external_path,
                mime_type, size_bytes, file_extension,
                item.modified_at,
                datetime.now(timezone.utc),
                connector_id, item.id,
            )
        stats["items_updated"] += 1
    else:
        import uuid as uuid_mod
        doc_id = uuid_mod.uuid4()
        await conn.execute(
            """
            INSERT INTO indexed_documents (
                id, tenant_id, connector_id, external_id, external_url,
                external_path, owner_id, is_tenant_public, title,
                description, mime_type, file_extension, size_bytes,
                source_created_at, source_modified_at, indexing_status,
                shared_with_users, shared_with_groups
            ) VALUES (
                $1::uuid, $2, $3, $4, $5, $6, $7, $8, $9,
                $10, $11, $12, $13, $14, $15, $16,
                $17::jsonb, $18::jsonb
            )
            """,
            doc_id, tenant_id, connector_id, item.id, external_url,
            external_path, owner_id, True, title,
            None, mime_type, file_extension, size_bytes,
            item.created_at, item.modified_at, "pending",
            json.dumps([]), json.dumps([]),
        )
        stats["items_new"] += 1


# =============================================================================
# Index Pending Job
# =============================================================================

async def run_index_pending_job(
    job_state: JobState,
    connector_id: str,
    batch_size: int = 10,
    max_documents: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Index pending documents: download content from OneDrive → send to Weaviate.
    """
    pool = await _get_db_pool()
    conn = await pool.acquire()
    try:
        row = await conn.fetchrow(
            "SELECT id, tenant_id, config, is_active, connector_type FROM connectors WHERE id = $1",
            UUID(connector_id),
        )
        if not row:
            return {"success": False, "error": "Connector not found"}
        if not row["is_active"]:
            return {"success": False, "error": "Connector not active"}

        tenant_id = row["tenant_id"]

        # Load config with decrypted tokens
        config = await load_connector_from_db(UUID(connector_id), tenant_id)
        if not config or not config.is_authenticated:
            return {"success": False, "error": "Connector not authenticated"}

        # Ensure fresh token
        access_token = await oauth_service.ensure_fresh_token(config)

        # Get pending documents
        limit = max_documents or 1000
        pending_docs = await conn.fetch(
            """
            SELECT id, tenant_id, connector_id, external_id, external_url,
                   external_path, owner_id, is_tenant_public, title, description,
                   mime_type, file_extension, size_bytes, source_created_at,
                   source_modified_at, shared_with_users, shared_with_groups
            FROM indexed_documents
            WHERE connector_id = $1 AND indexing_status = 'pending'
            ORDER BY created_at
            LIMIT $2
            """,
            UUID(connector_id),
            limit,
        )

        stats = {
            "total": len(pending_docs),
            "indexed": 0,
            "failed": 0,
            "errors": [],
        }

        if not pending_docs:
            logger.info(f"[{connector_id}] No pending documents to index")
            stats["success"] = True
            return stats

        concurrency = min(batch_size, 20)
        logger.info(f"[{connector_id}] Found {len(pending_docs)} pending documents (concurrency={concurrency})")

        semaphore = asyncio.Semaphore(concurrency)
        processed = 0

        async def _index_one(doc):
            nonlocal processed
            try:
                pool = await _get_db_pool()
                async with semaphore:
                    async with pool.acquire() as doc_conn:
                        try:
                            success = await _index_single_document(
                                doc_conn, doc, config, access_token
                            )
                            if success:
                                stats["indexed"] += 1
                            else:
                                stats["failed"] += 1
                        except Exception as e:
                            logger.error(f"Error indexing document {doc['id']}: {e}")
                            stats["failed"] += 1
                            try:
                                await doc_conn.execute(
                                    """
                                    UPDATE indexed_documents SET
                                        indexing_status = 'failed',
                                        indexing_error = $1
                                    WHERE id = $2
                                    """,
                                    str(e)[:500],
                                    doc["id"],
                                )
                            except Exception:
                                pass
            except Exception as e:
                logger.error(f"Fatal error indexing {doc['id']}: {e}")
                stats["failed"] += 1
            finally:
                processed += 1
                job_state.progress = {
                    "total": stats["total"],
                    "indexed": stats["indexed"],
                    "failed": stats["failed"],
                    "current": processed,
                }

        await asyncio.gather(*[_index_one(doc) for doc in pending_docs])

        logger.info(
            f"[{connector_id}] Indexing completed: indexed={stats['indexed']}, "
            f"failed={stats['failed']}"
        )

        stats["success"] = True
        return stats

    finally:
        await pool.release(conn)


# Extensions that intelligence-docs-service can process (whitelist)
_INDEXABLE_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".txt", ".md", ".csv", ".ppt", ".pptx",
    ".xlsx", ".xls", ".html", ".odt", ".rtf", ".epub", ".xml", ".json",
    ".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp", ".gif",
}


async def _index_single_document(
    conn: asyncpg.Connection,
    doc: asyncpg.Record,
    config,
    access_token: str = "",  # Deprecated: token is now refreshed per-document
) -> bool:
    """Index a single document: download from OneDrive, send to Weaviate."""
    doc_id = doc["id"]
    processing_start = time.time()

    # Early skip: avoid downloading files that intelligence-docs-service cannot process
    ext = (doc.get("file_extension") or "").lower()
    if ext and not ext.startswith("."):
        ext = f".{ext}"
    if ext and ext not in _INDEXABLE_EXTENSIONS:
        logger.info(f"Skipping unsupported extension '{ext}' for {doc['title']}")
        await conn.execute(
            """UPDATE indexed_documents SET
                indexing_status = 'skipped',
                indexing_error = $1
            WHERE id = $2""",
            f"Unsupported file type: {ext}",
            doc_id,
        )
        return False

    # Early skip: files larger than 50MB limit
    _MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
    size_bytes = doc.get("size_bytes") or 0
    if size_bytes > _MAX_FILE_SIZE:
        size_mb = size_bytes / (1024 * 1024)
        logger.info(f"Skipping oversized file ({size_mb:.0f}MB) for {doc['title']}")
        await conn.execute(
            """UPDATE indexed_documents SET
                indexing_status = 'skipped',
                indexing_error = $1
            WHERE id = $2""",
            f"File too large: {size_mb:.0f}MB > 50MB limit",
            doc_id,
        )
        return False

    await conn.execute(
        "UPDATE indexed_documents SET indexing_status = 'processing' WHERE id = $1",
        doc_id,
    )

    # Always get a fresh token — prevents 401 errors during long-running jobs
    fresh_token = await oauth_service.ensure_fresh_token(config)
    onedrive = OneDriveService(fresh_token, config)
    try:
        # Step 1: Download content from OneDrive
        # OneDrive files are native formats — no export conversion needed
        logger.debug(f"Downloading {doc['title']} ({doc['size_bytes']} bytes)")

        content, effective_mime = await onedrive.download_item(doc["external_id"])

        if not content:
            raise ValueError("Empty content downloaded")

        # Step 2: Send to Weaviate Service
        logger.debug(f"Sending to Weaviate pipeline ({len(content)} bytes)")
        weaviate_result = await _send_to_weaviate_pipeline(
            document_id=str(doc_id),
            file_bytes=content,
            filename=doc["title"],
            mime_type=effective_mime,
            tenant_id=str(doc["tenant_id"]),
            owner_id=str(doc["owner_id"]),
            metadata={
                "external_id": doc["external_id"],
                "external_url": doc["external_url"],
                "external_path": doc["external_path"],
                "connector_id": str(doc["connector_id"]),
                "connector_type": "onedrive",
                "source_created_at": doc["source_created_at"].isoformat() if doc["source_created_at"] else None,
                "source_modified_at": doc["source_modified_at"].isoformat() if doc["source_modified_at"] else None,
            },
            acl={
                "is_tenant_public": doc["is_tenant_public"],
                "shared_with_users": doc["shared_with_users"] or [],
                "shared_with_groups": doc["shared_with_groups"] or [],
            },
        )

        duration = time.time() - processing_start

        # Step 3: Update status
        if weaviate_result.get("success"):
            content_hash = hashlib.sha256(content).hexdigest()
            await conn.execute(
                """
                UPDATE indexed_documents SET
                    indexing_status = 'indexed',
                    weaviate_id = $1,
                    weaviate_collection = $2,
                    indexed_at = $3,
                    indexing_error = NULL,
                    indexing_duration_seconds = $4,
                    content_hash = $5
                WHERE id = $6
                """,
                weaviate_result.get("weaviate_id"),
                weaviate_result.get("collection"),
                datetime.now(timezone.utc),
                duration,
                content_hash,
                doc_id,
            )
            logger.info(f"Indexed {doc['title']} -> Weaviate ID: {weaviate_result.get('weaviate_id')}")
            return True
        else:
            error_msg = weaviate_result.get("error", "Unknown error")
            await conn.execute(
                """
                UPDATE indexed_documents SET
                    indexing_status = 'failed',
                    indexing_error = $1,
                    indexing_duration_seconds = $2
                WHERE id = $3
                """,
                error_msg[:500],
                duration,
                doc_id,
            )
            logger.error(f"Indexing failed for {doc['title']}: {error_msg}")
            return False

    except Exception as e:
        duration = time.time() - processing_start
        await conn.execute(
            """
            UPDATE indexed_documents SET
                indexing_status = 'failed',
                indexing_error = $1,
                indexing_duration_seconds = $2
            WHERE id = $3
            """,
            str(e)[:500],
            duration,
            doc_id,
        )
        raise
    finally:
        await onedrive.close()


async def _send_to_weaviate_pipeline(
    document_id: str,
    file_bytes: bytes,
    filename: str,
    mime_type: Optional[str],
    tenant_id: str,
    owner_id: str,
    metadata: Dict[str, Any],
    acl: Dict[str, Any],
) -> Dict[str, Any]:
    """Send document to Weaviate Service for indexing."""
    headers = {"Content-Type": "application/json"}
    if MICROSERVICES_API_KEY:
        headers["X-API-Key"] = MICROSERVICES_API_KEY

    file_base64 = base64.b64encode(file_bytes).decode("utf-8")

    payload = {
        "document_id": document_id,
        "file_bytes_base64": file_base64,
        "filename": filename,
        "mime_type": mime_type,
        "tenant_id": tenant_id,
        "owner_id": owner_id,
        "metadata": metadata,
        "acl": acl,
    }

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(connect=10.0, read=300.0, write=30.0, pool=5.0)
    ) as client:
        try:
            response = await client.post(
                f"{WEAVIATE_SERVICE_URL}/weaviate/index/from-connector",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Weaviate pipeline error: {e.response.status_code}")
            return {
                "success": False,
                "error": f"HTTP {e.response.status_code}: {e.response.text[:200]}",
            }
        except Exception as e:
            logger.error(f"Weaviate pipeline error: {e}")
            return {"success": False, "error": str(e)}
