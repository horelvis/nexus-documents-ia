"""
Alfresco Sync & Indexing Service for MCP Alfresco Server.

Ported from:
- background-worker/worker_app/tasks/connector_tasks.py (AlfrescoSyncService)
- app/services/unified_indexing_service.py (_index_single_document, _send_to_weaviate_pipeline)

Uses asyncpg directly (no SQLAlchemy) since mcp-alfresco-server is lightweight.
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

from ..core.config import settings
from .job_manager import JobState

logger = logging.getLogger(__name__)

# Weaviate service URL (for indexing phase)
WEAVIATE_SERVICE_URL = os.getenv("WEAVIATE_SERVICE_URL", "http://weaviate-service:8000")
MICROSERVICES_API_KEY = os.getenv("MICROSERVICES_API_KEY", "")


# =============================================================================
# Database helpers
# =============================================================================

async def _get_db_pool() -> asyncpg.Pool:
    """Create a connection pool."""
    db_url = settings.database_url
    if db_url.startswith("postgresql+asyncpg://"):
        db_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
    return await asyncpg.create_pool(db_url, min_size=2, max_size=10)


_db_pool: Optional[asyncpg.Pool] = None


async def _get_db_pool() -> asyncpg.Pool:
    """Get or create a connection pool."""
    global _db_pool
    if _db_pool is None:
        db_url = settings.database_url
        if db_url.startswith("postgresql+asyncpg://"):
            db_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
        _db_pool = await asyncpg.create_pool(db_url, min_size=2, max_size=10)
    return _db_pool


async def _get_db_connection() -> asyncpg.Connection:
    """Get a single database connection."""
    pool = await _get_db_pool()
    return await pool.acquire()


# =============================================================================
# AFTS Query Builder (ported from AlfrescoConfig.build_sync_afts_query)
# =============================================================================

def build_sync_afts_query(config: Dict[str, Any]) -> str:
    """
    Build AFTS query from connector config dict.

    Ported from app/schemas/connector.py AlfrescoConfig.build_sync_afts_query()
    """
    parts = []

    # Type filter
    afts_type_filter = config.get("afts_type_filter")
    if afts_type_filter:
        type_conditions = " OR ".join(f'TYPE:"{t}"' for t in afts_type_filter)
        parts.append(f"({type_conditions})")
    else:
        parts.append('TYPE:"cm:content"')

    # Folder filter
    default_folder_id = config.get("default_folder_id")
    default_site_id = config.get("default_site_id")
    if default_folder_id:
        parts.append(f'ANCESTOR:"workspace://SpacesStore/{default_folder_id}"')
    elif default_site_id:
        parts.append(f'SITE:"{default_site_id}"')

    # Path filter
    afts_path_filter = config.get("afts_path_filter")
    if afts_path_filter:
        parts.append(f'PATH:"{afts_path_filter}"')

    # Aspect filters
    afts_aspect_filter = config.get("afts_aspect_filter")
    if afts_aspect_filter:
        for aspect in afts_aspect_filter:
            parts.append(f'ASPECT:"{aspect}"')

    # MIME type filter
    afts_mime_types = config.get("afts_mime_types")
    if afts_mime_types:
        mime_conditions = " OR ".join(
            f'@cm\\:content.mimetype:"{mt}"' for mt in afts_mime_types
        )
        parts.append(f"({mime_conditions})")

    # Custom query
    afts_custom_query = config.get("afts_custom_query")
    if afts_custom_query:
        parts.append(f"({afts_custom_query})")

    # Exclude paths
    afts_exclude_paths = config.get("afts_exclude_paths")
    if afts_exclude_paths:
        for exclude_path in afts_exclude_paths:
            parts.append(f'-PATH:"{exclude_path}"')

    return " AND ".join(parts)


# =============================================================================
# Alfresco Search (ported from AlfrescoSyncService.search_documents)
# =============================================================================

async def search_documents(
    config: Dict[str, Any],
    modified_after: Optional[datetime] = None,
    max_items: int = 100,
    skip_count: int = 0,
) -> Dict[str, Any]:
    """
    Search Alfresco using AFTS query built from config filters.

    Ported from connector_tasks.py AlfrescoSyncService.search_documents()
    """
    base_url = config["url"].rstrip("/")
    search_api_path = config.get(
        "search_api_path",
        "/alfresco/api/-default-/public/search/versions/1",
    )

    afts_query = build_sync_afts_query(config)

    if modified_after:
        date_str = modified_after.strftime("%Y-%m-%dT%H:%M:%S")
        afts_query = f"({afts_query}) AND @cm\\:modified:['{date_str}' TO MAX]"

    logger.info(f"Executing AFTS query: {afts_query}")

    search_body = {
        "query": {"query": afts_query, "language": "afts"},
        "paging": {"maxItems": max_items, "skipCount": skip_count},
        "include": ["properties", "path", "aspectNames", "permissions"],
        "sort": [{"type": "FIELD", "field": "cm:modified", "ascending": True}],
    }

    auth_headers = _get_auth_headers(config)
    timeout_seconds = config.get("timeout_seconds", 60)

    async with httpx.AsyncClient(
        headers=auth_headers,
        timeout=httpx.Timeout(connect=10.0, read=float(timeout_seconds), write=30.0, pool=5.0),
    ) as client:
        response = await client.post(
            f"{base_url}{search_api_path}/search",
            json=search_body,
        )
        response.raise_for_status()
        return response.json()


def _get_auth_headers(config: Dict[str, Any]) -> Dict[str, str]:
    """Get Basic Auth headers for Alfresco."""
    auth_str = f"{config['username']}:{config['password']}"
    auth_bytes = base64.b64encode(auth_str.encode()).decode()
    return {
        "Authorization": f"Basic {auth_bytes}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


# =============================================================================
# Document Content Download
# =============================================================================

async def download_document_content(config: Dict[str, Any], node_id: str) -> bytes:
    """Download document content from Alfresco by node ID."""
    base_url = config["url"].rstrip("/")
    api_path = config.get(
        "api_path",
        "/alfresco/api/-default-/public/alfresco/versions/1",
    )
    download_timeout = config.get("download_timeout_seconds", 300)

    async with httpx.AsyncClient(
        headers=_get_auth_headers(config),
        timeout=httpx.Timeout(connect=10.0, read=float(download_timeout), write=30.0, pool=5.0),
    ) as client:
        response = await client.get(
            f"{base_url}{api_path}/nodes/{node_id}/content"
        )
        response.raise_for_status()
        return response.content


# =============================================================================
# Process Document (ported from AlfrescoSyncService._process_document)
# =============================================================================

async def _process_document(
    conn: asyncpg.Connection,
    entry: Dict[str, Any],
    tenant_id: UUID,
    connector_id: UUID,
    owner_id: UUID,
    base_url: str,
    stats: Dict[str, Any],
) -> None:
    """
    Process a single document from Alfresco search results.
    Creates or updates IndexedDocument record via asyncpg.

    Ported from connector_tasks.py AlfrescoSyncService._process_document()
    """
    node_id = entry.get("id")
    name = entry.get("name")
    properties = entry.get("properties", {})
    path_info = entry.get("path", {})
    content_info = entry.get("content", {})
    permissions_info = entry.get("permissions", {})

    # Build external path
    path_elements = path_info.get("elements", [])
    path_parts = [elem.get("name", "") for elem in path_elements]
    external_path = "/" + "/".join(path_parts) if path_parts else "/"

    # Document metadata
    title = properties.get("cm:title") or name
    description = properties.get("cm:description")
    mime_type = content_info.get("mimeType")
    size_bytes = content_info.get("sizeInBytes", 0)

    # File extension
    file_extension = None
    if name and "." in name:
        file_extension = name.rsplit(".", 1)[-1].lower()

    # External URL
    external_url = f"{base_url}/share/page/document-details?nodeRef=workspace://SpacesStore/{node_id}"

    # Parse dates
    source_created = _parse_alfresco_date(properties.get("cm:created"))
    source_modified = _parse_alfresco_date(properties.get("cm:modified"))

    # Extract Alfresco permissions → shared_with_users / shared_with_groups
    shared_with_users = []
    shared_with_groups = []
    all_perms = (permissions_info.get("locallySet") or []) + (permissions_info.get("inherited") or [])
    for perm in all_perms:
        authority = perm.get("authorityId", "")
        if authority.startswith("GROUP_"):
            group_name = authority.removeprefix("GROUP_")
            if group_name not in shared_with_groups:
                shared_with_groups.append(group_name)
        elif authority and authority not in shared_with_users:
            shared_with_users.append(authority)
    shared_users_json = json.dumps(shared_with_users)
    shared_groups_json = json.dumps(shared_with_groups)

    # Check if document already exists
    existing = await conn.fetchrow(
        """
        SELECT id FROM indexed_documents
        WHERE connector_id = $1 AND external_id = $2
        """,
        connector_id,
        node_id,
    )

    if existing:
        # Update existing
        await conn.execute(
            """
            UPDATE indexed_documents SET
                title = $1,
                description = $2,
                external_path = $3,
                external_url = $4,
                mime_type = $5,
                size_bytes = $6,
                file_extension = $7,
                source_modified_at = $8,
                shared_with_users = $9::jsonb,
                shared_with_groups = $10::jsonb,
                updated_at = $11
            WHERE connector_id = $12 AND external_id = $13
            """,
            title, description, external_path, external_url,
            mime_type, size_bytes, file_extension, source_modified,
            shared_users_json, shared_groups_json,
            datetime.now(timezone.utc),
            connector_id, node_id,
        )
        stats["items_updated"] += 1
    else:
        # Create new
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
            node_id, tenant_id, connector_id, node_id, external_url,
            external_path, owner_id, True, title,
            description, mime_type, file_extension, size_bytes,
            source_created, source_modified, "pending",
            shared_users_json, shared_groups_json,
        )
        stats["items_new"] += 1


def _parse_alfresco_date(date_str: Optional[str]) -> Optional[datetime]:
    """Parse Alfresco ISO date string."""
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except Exception:
        return None


# =============================================================================
# Sync Job (ported from _sync_connector in connector_tasks.py)
# =============================================================================

async def run_sync_job(
    job_state: JobState,
    connector_id: str,
    full_sync: bool = False,
    batch_size: int = 10,
) -> Dict[str, Any]:
    """
    Execute sync job: fetch metadata from Alfresco → create IndexedDocument records.

    Ported from connector_tasks.py _sync_connector()
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
        if row["connector_type"] != "alfresco":
            return {"success": False, "error": f"Sync not implemented for {row['connector_type']}"}

        # Parse config
        raw_config = row["config"]
        if isinstance(raw_config, str):
            config = json.loads(raw_config) if raw_config else {}
        else:
            config = raw_config or {}

        tenant_id = row["tenant_id"]

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

        # Determine modified_after for incremental sync
        modified_after = None if full_sync else row["last_health_check"]

        # Stats
        stats = {
            "items_found": 0,
            "items_new": 0,
            "items_updated": 0,
            "items_failed": 0,
            "errors": [],
        }

        # Pagination loop
        skip_count = 0
        max_items = config.get("max_results", 100)
        has_more = True
        base_url = config["url"].rstrip("/")

        while has_more:
            try:
                result = await search_documents(
                    config=config,
                    modified_after=modified_after,
                    max_items=max_items,
                    skip_count=skip_count,
                )

                entries = result.get("list", {}).get("entries", [])
                pagination = result.get("list", {}).get("pagination", {})

                stats["items_found"] += len(entries)
                has_more = pagination.get("hasMoreItems", False)
                skip_count += len(entries)

                for entry_wrapper in entries:
                    entry = entry_wrapper.get("entry", {})
                    try:
                        await _process_document(
                            conn=conn,
                            entry=entry,
                            tenant_id=tenant_id,
                            connector_id=UUID(connector_id),
                            owner_id=owner_id,
                            base_url=base_url,
                            stats=stats,
                        )
                    except Exception as e:
                        stats["items_failed"] += 1
                        stats["errors"].append({
                            "node_id": entry.get("id"),
                            "name": entry.get("name"),
                            "error": str(e),
                        })
                        logger.error(f"Error processing document {entry.get('name')}: {e}")

                # Update progress on job state
                job_state.progress = {
                    "found": stats["items_found"],
                    "processed": stats["items_new"] + stats["items_updated"],
                    "failed": stats["items_failed"],
                }

            except httpx.HTTPStatusError as e:
                logger.error(f"Alfresco API error: {e.response.status_code}")
                stats["errors"].append({
                    "type": "api_error",
                    "status_code": e.response.status_code,
                    "error": str(e),
                })
                break
            except Exception as e:
                logger.exception(f"Error during sync: {e}")
                stats["errors"].append({"type": "sync_error", "error": str(e)})
                break

        # Update connector health status
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


# =============================================================================
# Index Pending Job (ported from unified_indexing_service)
# =============================================================================

async def run_index_pending_job(
    job_state: JobState,
    connector_id: str,
    batch_size: int = 10,
    max_documents: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Index pending documents: download content from Alfresco → send to Weaviate.

    Ported from unified_indexing_service.index_pending_documents() and
    _index_single_document() / _send_to_weaviate_pipeline()
    """
    pool = await _get_db_pool()
    conn = await pool.acquire()
    try:
        # Get connector
        row = await conn.fetchrow(
            "SELECT id, tenant_id, config, is_active, connector_type FROM connectors WHERE id = $1",
            UUID(connector_id),
        )
        if not row:
            return {"success": False, "error": "Connector not found"}
        if not row["is_active"]:
            return {"success": False, "error": "Connector not active"}

        raw_config = row["config"]
        if isinstance(raw_config, str):
            config = json.loads(raw_config) if raw_config else {}
        else:
            config = raw_config or {}

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

        # Reset historical avg so stats reflect current run only
        await conn.execute(
            "UPDATE indexed_documents SET indexing_duration_seconds = NULL WHERE connector_id = $1 AND indexing_duration_seconds IS NOT NULL",
            UUID(connector_id),
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
                            success = await _index_single_document(doc_conn, doc, config)
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


# Extensions that textextract-service can process (whitelist)
_INDEXABLE_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".txt", ".md", ".csv", ".ppt", ".pptx",
    ".xlsx", ".xls", ".html", ".odt", ".rtf", ".epub", ".xml", ".json",
    ".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp", ".gif",
}


async def _index_single_document(
    conn: asyncpg.Connection,
    doc: asyncpg.Record,
    config: Dict[str, Any],
) -> bool:
    """
    Index a single document: download from Alfresco, send to Weaviate.

    Ported from unified_indexing_service._index_single_document()
    """
    doc_id = doc["id"]
    processing_start = time.time()

    # Early skip: avoid downloading files that textextract cannot process
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

    # Early skip: files larger than textextract max (50MB)
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

    # Mark as processing
    await conn.execute(
        "UPDATE indexed_documents SET indexing_status = 'processing' WHERE id = $1",
        doc_id,
    )

    try:
        # Step 1: Download content from Alfresco
        logger.debug(f"Downloading {doc['title']} ({doc['size_bytes']} bytes)")
        content = await download_document_content(config, doc["external_id"])

        if not content:
            raise ValueError("Empty content downloaded")

        # Step 2: Send to Weaviate Service
        logger.debug(f"Sending to Weaviate pipeline ({len(content)} bytes)")
        weaviate_result = await _send_to_weaviate_pipeline(
            document_id=str(doc_id),
            file_bytes=content,
            filename=doc["title"],
            mime_type=doc["mime_type"],
            tenant_id=str(doc["tenant_id"]),
            owner_id=str(doc["owner_id"]),
            metadata={
                "external_id": doc["external_id"],
                "external_url": doc["external_url"],
                "external_path": doc["external_path"],
                "connector_id": str(doc["connector_id"]),
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
    """
    Send document to Weaviate Service for indexing.

    Ported from unified_indexing_service._send_to_weaviate_pipeline()
    """
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
