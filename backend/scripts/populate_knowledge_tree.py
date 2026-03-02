#!/usr/bin/env python3
"""
Unified Knowledge Tree population script.

Populates the structural knowledge graph (Apache AGE) from indexed documents
in PostgreSQL. Works for ALL connector types (Alfresco, Google Drive, OneDrive,
Database, etc.) by deriving folder hierarchy from document paths.

Replaces the deprecated scripts:
- docker/sync_alfresco_to_sil.py (Alfresco-only folder sync)
- scripts/index_structural_metadata.py (document-only, SIL naming)

Strategy:
1. Query indexed_documents.external_path to derive folder hierarchy
2. Index folders first (sorted by depth - parents before children)
3. Index documents with their metadata and learned context
4. Uses batch endpoint (/tree/index/batch) to minimize HTTP overhead

Usage:
    # All connectors, incremental (skip already-indexed)
    python scripts/populate_knowledge_tree.py

    # Full rebuild for one tenant
    python scripts/populate_knowledge_tree.py --tenant-id UUID --full-reindex

    # Specific connector type only
    python scripts/populate_knowledge_tree.py --connector-type alfresco

    # Specific connector
    python scripts/populate_knowledge_tree.py --connector-id UUID

    # Dry run
    python scripts/populate_knowledge_tree.py --dry-run

    # Custom batch size
    python scripts/populate_knowledge_tree.py --batch-size 50
"""

import asyncio
import argparse
import logging
import os
import sys
from typing import Any, Dict, List, Optional, Set

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import httpx
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def get_database_url() -> str:
    return os.getenv(
        "DATABASE_URL",
        "postgresql://nexus_user:nexus_password@localhost:5432/nexus_db",
    )


def get_knowledge_tree_url() -> str:
    return os.getenv(
        "KNOWLEDGE_TREE_SERVICE_URL",
        "http://localhost:8011",
    )


def get_api_key() -> str:
    return os.getenv("MICROSERVICES_API_KEY", "test-api-key")


def derive_folders_from_paths(paths: List[str]) -> List[str]:
    """
    Given a list of document paths, derive all intermediate folder paths.

    Example:
        ["/a/b/c/file.pdf", "/a/b/d/other.txt"]
        -> ["/a", "/a/b", "/a/b/c", "/a/b/d"]  (sorted by depth)
    """
    folder_paths: set = set()
    for path in paths:
        if not path:
            continue
        normalized = path.replace("\\", "/")
        parts = [p for p in normalized.split("/") if p]
        # Remove filename (last segment)
        folder_parts = parts[:-1]
        for i in range(1, len(folder_parts) + 1):
            folder_paths.add("/" + "/".join(folder_parts[:i]))

    return sorted(folder_paths, key=lambda p: p.count("/"))


async def get_indexed_document_ids(api_key: str, tenant_id: Optional[str] = None) -> Set[str]:
    """Get document IDs already in the knowledge graph."""
    kt_url = get_knowledge_tree_url()
    try:
        async with httpx.AsyncClient() as client:
            params = {"limit": 10000}
            if tenant_id:
                params["tenant_id"] = tenant_id
            response = await client.get(
                f"{kt_url}/tree/graph/document-ids",
                headers={"X-API-Key": api_key},
                params=params,
                timeout=30.0,
            )
            if response.status_code == 200:
                return set(response.json().get("document_ids", []))
    except Exception as e:
        logger.debug(f"Could not fetch indexed IDs: {e}")
    return set()


async def clear_graph(api_key: str, tenant_id: Optional[str] = None) -> bool:
    """Clear the knowledge graph for a tenant."""
    kt_url = get_knowledge_tree_url()
    try:
        async with httpx.AsyncClient() as client:
            params = {}
            if tenant_id:
                params["tenant_id"] = tenant_id
            response = await client.delete(
                f"{kt_url}/tree/graph/clear",
                headers={"X-API-Key": api_key},
                params=params,
                timeout=60.0,
            )
            if response.status_code in (200, 204, 404):
                logger.info("Graph cleared successfully")
                return True
            else:
                logger.warning(f"Could not clear graph: {response.status_code}")
                return True  # Continue anyway
    except Exception as e:
        logger.warning(f"Could not clear graph (continuing): {e}")
        return True


async def index_batch(
    client: httpx.AsyncClient,
    items: List[Dict[str, Any]],
    api_key: str,
) -> Dict[str, int]:
    """Index a batch of items via /tree/index/batch."""
    kt_url = get_knowledge_tree_url()
    try:
        response = await client.post(
            f"{kt_url}/tree/index/batch",
            json={"items": items},
            headers={"X-API-Key": api_key, "Content-Type": "application/json"},
            timeout=60.0,
        )
        if response.status_code == 200:
            data = response.json()
            return {"success": data.get("success", 0), "errors": data.get("errors", 0)}
        else:
            logger.warning(f"Batch index returned {response.status_code}: {response.text[:200]}")
            return {"success": 0, "errors": len(items)}
    except Exception as e:
        logger.warning(f"Batch index error: {e}")
        return {"success": 0, "errors": len(items)}


async def index_single(
    client: httpx.AsyncClient,
    item: Dict[str, Any],
    api_key: str,
) -> bool:
    """Fallback: index a single item via /tree/index."""
    kt_url = get_knowledge_tree_url()
    try:
        response = await client.post(
            f"{kt_url}/tree/index",
            json=item,
            headers={"X-API-Key": api_key, "Content-Type": "application/json"},
            timeout=30.0,
        )
        return response.status_code == 200
    except Exception:
        return False


async def main(
    tenant_id: Optional[str] = None,
    connector_id: Optional[str] = None,
    connector_type: Optional[str] = None,
    full_reindex: bool = False,
    dry_run: bool = False,
    batch_size: int = 50,
):
    engine = create_engine(get_database_url())
    Session = sessionmaker(bind=engine)
    session = Session()

    api_key = get_api_key()
    kt_url = get_knowledge_tree_url()

    logger.info(f"Knowledge Tree URL: {kt_url}")
    logger.info(f"Mode: {'FULL RE-INDEX' if full_reindex else 'INCREMENTAL'}")
    logger.info(f"Batch size: {batch_size}")
    if tenant_id:
        logger.info(f"Tenant filter: {tenant_id}")
    if connector_id:
        logger.info(f"Connector filter: {connector_id}")
    if connector_type:
        logger.info(f"Connector type filter: {connector_type}")
    logger.info(f"Dry run: {dry_run}")

    # Clear graph if full reindex
    if full_reindex and not dry_run:
        logger.info("Clearing graph for full re-index...")
        await clear_graph(api_key, tenant_id)

    # Get already-indexed IDs for incremental mode
    already_indexed: Set[str] = set()
    if not full_reindex:
        logger.info("Fetching already-indexed document IDs...")
        already_indexed = await get_indexed_document_ids(api_key, tenant_id)
        logger.info(f"Found {len(already_indexed)} documents already in graph")

    # Query connectors
    connector_query = """
        SELECT id, tenant_id, connector_type, is_active
        FROM connectors
        WHERE is_active = true
    """
    filters = []
    if tenant_id:
        filters.append(f"tenant_id = '{tenant_id}'")
    if connector_id:
        filters.append(f"id = '{connector_id}'")
    if connector_type:
        filters.append(f"connector_type = '{connector_type}'")
    if filters:
        connector_query += " AND " + " AND ".join(filters)

    connectors = [dict(row._mapping) for row in session.execute(text(connector_query))]
    if not connectors:
        logger.warning("No matching active connectors found")
        session.close()
        return

    logger.info(f"Found {len(connectors)} connector(s)")

    # Global stats
    total_folders_indexed = 0
    total_folders_errors = 0
    total_docs_indexed = 0
    total_docs_errors = 0
    total_docs_skipped = 0

    # Check if batch endpoint is available
    batch_available = True
    try:
        async with httpx.AsyncClient() as client:
            probe = await client.post(
                f"{kt_url}/tree/index/batch",
                json={"items": []},
                headers={"X-API-Key": api_key, "Content-Type": "application/json"},
                timeout=10.0,
            )
            batch_available = probe.status_code == 200
    except Exception:
        batch_available = False

    if batch_available:
        logger.info("Batch endpoint available - using batched indexing")
    else:
        logger.info("Batch endpoint not available - falling back to single indexing")

    for conn in connectors:
        conn_id = str(conn["id"])
        conn_tenant = str(conn["tenant_id"])
        conn_type = conn["connector_type"]

        logger.info(f"\n=== Connector: {conn_id} (type={conn_type}) ===")

        # --- Phase 1: Derive and index folders from document paths ---
        doc_path_query = f"""
            SELECT DISTINCT external_path
            FROM indexed_documents
            WHERE connector_id = '{conn_id}'
            AND indexing_status = 'indexed'
            AND external_path IS NOT NULL
            AND external_path != ''
        """
        paths = [row[0] for row in session.execute(text(doc_path_query))]
        folder_paths = derive_folders_from_paths(paths)

        logger.info(f"  Derived {len(folder_paths)} folders from {len(paths)} document paths")

        if dry_run:
            for fp in folder_paths[:10]:
                logger.info(f"    [FOLDER] {fp}")
            if len(folder_paths) > 10:
                logger.info(f"    ... and {len(folder_paths) - 10} more folders")
        else:
            # Build folder payloads
            folder_payloads = []
            for fp in folder_paths:
                folder_name = fp.rsplit("/", 1)[-1]
                folder_payloads.append({
                    "document_id": f"folder:{fp}",
                    "tenant_id": conn_tenant,
                    "file_path": fp,
                    "connector_metadata": {
                        "is_folder": True,
                        "folder_name": folder_name,
                    },
                    "learned_context": {},
                    "connector_id": conn_id,
                    "connector_type": conn_type,
                })

            # Index folders in batches
            async with httpx.AsyncClient() as client:
                for i in range(0, len(folder_payloads), batch_size):
                    batch = folder_payloads[i : i + batch_size]
                    if batch_available:
                        result = await index_batch(client, batch, api_key)
                    else:
                        success = 0
                        errors = 0
                        for item in batch:
                            if await index_single(client, item, api_key):
                                success += 1
                            else:
                                errors += 1
                        result = {"success": success, "errors": errors}

                    total_folders_indexed += result["success"]
                    total_folders_errors += result["errors"]

            logger.info(
                f"  Folders: {total_folders_indexed} indexed, {total_folders_errors} errors"
            )

        # --- Phase 2: Index documents ---
        doc_query = f"""
            SELECT
                id, tenant_id, connector_id, title, external_path,
                source_metadata, learned_context, weaviate_id
            FROM indexed_documents
            WHERE connector_id = '{conn_id}'
            AND indexing_status = 'indexed'
            AND weaviate_id IS NOT NULL
            ORDER BY created_at
        """
        documents = [dict(row._mapping) for row in session.execute(text(doc_query))]

        # Filter for incremental mode
        if not full_reindex:
            before_count = len(documents)
            documents = [d for d in documents if str(d["id"]) not in already_indexed]
            skipped = before_count - len(documents)
            total_docs_skipped += skipped
            if skipped > 0:
                logger.info(f"  Skipping {skipped} already-indexed documents")

        logger.info(f"  Documents to index: {len(documents)}")

        if dry_run:
            for doc in documents[:10]:
                has_meta = "+" if doc.get("source_metadata") else "-"
                logger.info(f"    [{has_meta}] {doc['title']}")
            if len(documents) > 10:
                logger.info(f"    ... and {len(documents) - 10} more documents")
            continue

        if not documents:
            continue

        # Build document payloads
        doc_payloads = []
        for doc in documents:
            doc_payloads.append({
                "document_id": str(doc["id"]),
                "tenant_id": str(doc["tenant_id"]),
                "file_path": doc.get("external_path") or doc.get("title", ""),
                "connector_metadata": doc.get("source_metadata") or {},
                "learned_context": doc.get("learned_context") or {},
                "weaviate_document_id": str(doc["weaviate_id"]) if doc.get("weaviate_id") else None,
                "connector_id": str(doc["connector_id"]) if doc.get("connector_id") else None,
                "connector_type": conn_type,
            })

        # Index documents in batches
        async with httpx.AsyncClient() as client:
            for i in range(0, len(doc_payloads), batch_size):
                batch = doc_payloads[i : i + batch_size]
                batch_num = i // batch_size + 1
                total_batches = (len(doc_payloads) + batch_size - 1) // batch_size

                if batch_available:
                    result = await index_batch(client, batch, api_key)
                else:
                    success = 0
                    errors = 0
                    for item in batch:
                        if await index_single(client, item, api_key):
                            success += 1
                        else:
                            errors += 1
                    result = {"success": success, "errors": errors}

                total_docs_indexed += result["success"]
                total_docs_errors += result["errors"]

                logger.info(
                    f"  Batch {batch_num}/{total_batches}: "
                    f"{result['success']} ok, {result['errors']} errors"
                )

    session.close()

    logger.info("\n=== Summary ===")
    logger.info(f"Folders indexed: {total_folders_indexed}")
    logger.info(f"Folder errors:   {total_folders_errors}")
    logger.info(f"Docs indexed:    {total_docs_indexed}")
    logger.info(f"Docs skipped:    {total_docs_skipped}")
    logger.info(f"Doc errors:      {total_docs_errors}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Populate Knowledge Tree graph from indexed documents (all connector types)",
    )
    parser.add_argument("--tenant-id", type=str, help="Filter by tenant ID")
    parser.add_argument("--connector-id", type=str, help="Filter by connector ID")
    parser.add_argument("--connector-type", type=str, help="Filter by connector type (alfresco, google_drive, onedrive, database)")
    parser.add_argument("--full-reindex", action="store_true", help="Clear graph and re-index everything")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be indexed without indexing")
    parser.add_argument("--batch-size", type=int, default=50, help="Number of items per batch (default: 50)")

    args = parser.parse_args()

    asyncio.run(main(
        tenant_id=args.tenant_id,
        connector_id=args.connector_id,
        connector_type=args.connector_type,
        full_reindex=args.full_reindex,
        dry_run=args.dry_run,
        batch_size=args.batch_size,
    ))
