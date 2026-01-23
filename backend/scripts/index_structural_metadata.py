#!/usr/bin/env python3
"""
Script to index structural metadata for indexed documents.

This script:
1. Queries indexed documents from PostgreSQL
2. For each document, calls the SIL /index-structural endpoint
3. Creates structural metadata in Weaviate StructuralDocument collection
4. Creates nodes in Apache AGE knowledge graph

Usage:
    python scripts/index_structural_metadata.py [options]

Options:
    --tenant-id UUID    Filter by tenant ID
    --limit N           Limit number of documents to process
    --full-reindex      Clear graph and re-index ALL documents from scratch
    --dry-run           Show what would be indexed without actually indexing

Examples:
    # Index only NEW documents (not already in graph) - DEFAULT
    python scripts/index_structural_metadata.py

    # Full re-index: clear graph and re-index everything
    python scripts/index_structural_metadata.py --full-reindex

    # Index specific tenant
    python scripts/index_structural_metadata.py --tenant-id 00000000-0000-0000-0000-000000000001

    # Dry run to see what would be indexed
    python scripts/index_structural_metadata.py --dry-run
"""

import asyncio
import argparse
import logging
import sys
import os
from typing import Optional

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import httpx
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def get_database_url() -> str:
    """Get database URL from environment."""
    return os.getenv(
        "DATABASE_URL",
        "postgresql://nexus_user:nexus_password@localhost:5432/nexus_db"
    )


def get_weaviate_service_url() -> str:
    """Get Weaviate service URL."""
    return os.getenv("WEAVIATE_SERVICE_URL", "http://localhost:8007")


def get_api_key() -> str:
    """Get microservices API key."""
    return os.getenv("MICROSERVICES_API_KEY", "test-api-key")


async def index_document_structural(
    client: httpx.AsyncClient,
    document: dict,
    api_key: str,
) -> dict:
    """
    Index structural metadata for a single document.

    Args:
        client: HTTP client
        document: Document data from PostgreSQL
        api_key: API key for authentication

    Returns:
        Response from SIL service
    """
    weaviate_url = get_weaviate_service_url()

    # Build request payload
    payload = {
        "document_id": str(document["id"]),
        "tenant_id": str(document["tenant_id"]),
        "file_path": document.get("external_path") or document.get("title", ""),
        "connector_metadata": document.get("source_metadata"),
        "learned_context": document.get("learned_context"),
        "weaviate_document_id": str(document["weaviate_id"]) if document.get("weaviate_id") else None,
        "connector_id": str(document["connector_id"]) if document.get("connector_id") else None,
    }

    try:
        response = await client.post(
            f"{weaviate_url}/sil/index-structural",
            json=payload,
            headers={"X-API-Key": api_key},
            timeout=30.0,
        )

        if response.status_code == 200:
            return {"success": True, "data": response.json()}
        else:
            return {
                "success": False,
                "error": f"HTTP {response.status_code}: {response.text[:200]}"
            }
    except Exception as e:
        return {"success": False, "error": str(e)}


async def clear_sil_graph(api_key: str, tenant_id: Optional[str] = None) -> bool:
    """
    Clear the SIL graph for a fresh re-index.

    Args:
        api_key: API key for authentication
        tenant_id: Optional tenant ID to clear only that tenant's data

    Returns:
        True if successful, False otherwise
    """
    weaviate_url = get_weaviate_service_url()

    try:
        async with httpx.AsyncClient() as client:
            # Call the graph clear endpoint
            params = {}
            if tenant_id:
                params["tenant_id"] = tenant_id

            response = await client.delete(
                f"{weaviate_url}/sil/graph/clear",
                headers={"X-API-Key": api_key},
                params=params,
                timeout=60.0,
            )

            if response.status_code in (200, 204, 404):
                logger.info("✓ SIL graph cleared successfully")
                return True
            else:
                logger.warning(f"Could not clear graph: {response.status_code} - {response.text[:100]}")
                # Continue anyway - might not have clear endpoint
                return True

    except Exception as e:
        logger.warning(f"Could not clear graph (continuing anyway): {e}")
        return True


async def get_indexed_document_ids(api_key: str, tenant_id: Optional[str] = None) -> set:
    """
    Get set of document IDs already indexed in the SIL graph.

    Args:
        api_key: API key for authentication
        tenant_id: Optional tenant ID filter

    Returns:
        Set of document IDs already in the graph
    """
    weaviate_url = get_weaviate_service_url()

    try:
        async with httpx.AsyncClient() as client:
            params = {"limit": 10000}
            if tenant_id:
                params["tenant_id"] = tenant_id

            response = await client.get(
                f"{weaviate_url}/sil/graph/document-ids",
                headers={"X-API-Key": api_key},
                params=params,
                timeout=30.0,
            )

            if response.status_code == 200:
                data = response.json()
                return set(data.get("document_ids", []))
            else:
                # If endpoint doesn't exist, return empty set
                logger.debug(f"Could not get indexed IDs: {response.status_code}")
                return set()

    except Exception as e:
        logger.debug(f"Could not get indexed IDs: {e}")
        return set()


async def main(
    tenant_id: Optional[str] = None,
    limit: Optional[int] = None,
    dry_run: bool = False,
    full_reindex: bool = False,
):
    """
    Main function to index documents to SIL.

    Args:
        tenant_id: Optional tenant ID filter
        limit: Maximum documents to process
        dry_run: Show what would be done without doing it
        full_reindex: Clear graph and re-index everything
    """

    # Connect to database
    engine = create_engine(get_database_url())
    Session = sessionmaker(bind=engine)
    session = Session()

    api_key = get_api_key()
    weaviate_url = get_weaviate_service_url()

    logger.info(f"Weaviate Service URL: {weaviate_url}")
    logger.info(f"Mode: {'FULL RE-INDEX' if full_reindex else 'INCREMENTAL (new only)'}")
    logger.info(f"Dry run: {dry_run}")

    # If full re-index, clear the graph first
    if full_reindex and not dry_run:
        logger.info("Clearing SIL graph for full re-index...")
        await clear_sil_graph(api_key, tenant_id)

    # Get already indexed document IDs (for incremental mode)
    already_indexed = set()
    if not full_reindex:
        logger.info("Fetching already indexed document IDs...")
        already_indexed = await get_indexed_document_ids(api_key, tenant_id)
        logger.info(f"Found {len(already_indexed)} documents already in graph")

    # Build query
    query = """
        SELECT
            id,
            tenant_id,
            connector_id,
            title,
            external_path,
            source_metadata,
            learned_context,
            weaviate_id
        FROM indexed_documents
        WHERE indexing_status = 'indexed'
        AND weaviate_id IS NOT NULL
    """

    if tenant_id:
        query += f" AND tenant_id = '{tenant_id}'"

    query += " ORDER BY created_at DESC"

    if limit:
        query += f" LIMIT {limit}"

    # Fetch documents
    result = session.execute(text(query))
    all_documents = [dict(row._mapping) for row in result]

    # Filter to only new documents (if incremental mode)
    if full_reindex:
        documents = all_documents
    else:
        documents = [
            doc for doc in all_documents
            if str(doc["id"]) not in already_indexed
        ]

    logger.info(f"Found {len(all_documents)} total documents")
    logger.info(f"Documents to index: {len(documents)} {'(all)' if full_reindex else '(new only)'}")

    if dry_run:
        logger.info("Dry run - not indexing")
        for doc in documents[:10]:
            has_meta = "✓" if doc.get("source_metadata") else "✗"
            logger.info(f"  [{has_meta}] {doc['title']} ({doc['id']})")
        if len(documents) > 10:
            logger.info(f"  ... and {len(documents) - 10} more")
        return

    if not documents:
        logger.info("No new documents to index")
        session.close()
        return

    # Index documents
    success_count = 0
    error_count = 0

    async with httpx.AsyncClient() as client:
        for i, doc in enumerate(documents):
            logger.info(f"[{i+1}/{len(documents)}] Indexing: {doc['title']}")

            result = await index_document_structural(client, doc, api_key)

            if result["success"]:
                success_count += 1
                data = result["data"]
                logger.info(
                    f"  ✓ Type: {data.get('semantic_type', 'unknown')}, "
                    f"Domain: {data.get('domain', 'unknown')}, "
                    f"Weaviate: {data.get('indexed_to_weaviate')}, "
                    f"Graph: {data.get('indexed_to_graph')}"
                )
            else:
                error_count += 1
                logger.error(f"  ✗ Error: {result['error']}")

    session.close()

    logger.info(f"\n=== Summary ===")
    logger.info(f"Total in DB: {len(all_documents)}")
    logger.info(f"Processed: {len(documents)}")
    logger.info(f"Success: {success_count}")
    logger.info(f"Errors: {error_count}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Index structural metadata for indexed documents"
    )
    parser.add_argument(
        "--tenant-id",
        type=str,
        help="Filter by tenant ID",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit number of documents to process",
    )
    parser.add_argument(
        "--full-reindex",
        action="store_true",
        help="Clear graph and re-index ALL documents from scratch",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be indexed without actually indexing",
    )

    args = parser.parse_args()

    asyncio.run(main(
        tenant_id=args.tenant_id,
        limit=args.limit,
        dry_run=args.dry_run,
        full_reindex=args.full_reindex,
    ))
