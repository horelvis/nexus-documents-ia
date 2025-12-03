#!/usr/bin/env python3
"""
Weaviate Reindexer Script

Reindexes documents from PostgreSQL into Weaviate with proper tenant separation.
Each tenant gets their own collection: Nexus_{tenant_id}_documents

The script fetches document content from Elasticsearch (where it's already indexed)
and reindexes it into Weaviate for semantic search with Elysia.

Usage:
    docker compose exec background-worker python -m scripts.reindex_weaviate
    docker compose exec background-worker python -m scripts.reindex_weaviate --tenant <tenant_id>
    docker compose exec background-worker python -m scripts.reindex_weaviate --dry-run
"""

import asyncio
import os
import sys
import logging
import argparse
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Optional, Tuple, Dict, Any

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from app.db.database import SessionLocal
from app.db.models import Document, Tenant
from app.core.config import settings

# Direct Elasticsearch client for faster reads
from elasticsearch import AsyncElasticsearch

ES_URL = os.getenv("ELASTICSEARCH_URL", "http://elasticsearch:9200")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy.pool").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


# Configuration
WEAVIATE_SERVICE_URL = os.getenv("WEAVIATE_SERVICE_URL", "http://weaviate-service:8007")
MICROSERVICES_API_KEY = os.getenv("MICROSERVICES_API_KEY", settings.MICROSERVICES_API_KEY)
BATCH_SIZE = int(os.getenv("REINDEX_BATCH_SIZE", "50"))


def normalize_tenant_id(tenant_id: str) -> str:
    """Normalize tenant ID for collection name (replace - with _)"""
    return tenant_id.replace("-", "_")


def get_collection_name(tenant_id: str) -> str:
    """Get Weaviate collection name for tenant"""
    return f"Nexus_{normalize_tenant_id(tenant_id)}_documents"


class WeaviateReindexer:
    """Handles reindexing documents to Weaviate"""

    def __init__(self, dry_run: bool = False):
        self.base_url = WEAVIATE_SERVICE_URL
        self.headers = {
            "Authorization": f"Bearer {MICROSERVICES_API_KEY}",
            "Content-Type": "application/json"
        }
        self.dry_run = dry_run
        self.stats = {
            "collections_created": 0,
            "documents_indexed": 0,
            "documents_failed": 0,
            "documents_skipped": 0
        }

    async def check_health(self) -> bool:
        """Check if Weaviate service is available"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.base_url}/health", headers=self.headers)
                response.raise_for_status()
                data = response.json()
                return data.get("status") == "healthy"
        except Exception as e:
            logger.error(f"Weaviate health check failed: {e}")
            return False

    async def collection_exists(self, collection_name: str) -> bool:
        """Check if collection exists in Weaviate"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.base_url}/weaviate/collections", headers=self.headers)
                response.raise_for_status()
                data = response.json()
                collections = data.get("collections", [])
                return collection_name in collections
        except Exception as e:
            logger.error(f"Failed to check collection existence: {e}")
            return False

    async def create_collection(self, collection_name: str) -> bool:
        """Create a new collection in Weaviate"""
        if self.dry_run:
            logger.info(f"[DRY-RUN] Would create collection: {collection_name}")
            return True

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.base_url}/weaviate/collections/{collection_name}/create",
                    json={},
                    headers=self.headers
                )
                response.raise_for_status()
                self.stats["collections_created"] += 1
                logger.info(f"Created collection: {collection_name}")
                return True
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 409:  # Already exists
                logger.info(f"Collection already exists: {collection_name}")
                return True
            logger.error(f"Failed to create collection {collection_name}: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to create collection {collection_name}: {e}")
            return False

    async def delete_collection(self, collection_name: str) -> bool:
        """Delete a collection from Weaviate"""
        if self.dry_run:
            logger.info(f"[DRY-RUN] Would delete collection: {collection_name}")
            return True

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Use direct Weaviate API through the service
                response = await client.delete(
                    f"{self.base_url}/weaviate/collections/{collection_name}",
                    headers=self.headers
                )
                if response.status_code in [200, 204, 404]:
                    logger.info(f"Deleted collection: {collection_name}")
                    return True
                response.raise_for_status()
                return True
        except Exception as e:
            logger.warning(f"Failed to delete collection {collection_name}: {e}")
            return False

    async def get_document_content_from_es(self, tenant_id: str, doc_id: str) -> Optional[str]:
        """Fetch document content from Elasticsearch directly"""
        try:
            # Build index name same way as ES service does
            index_name = f"nexus_{tenant_id}_documents".lower().replace("-", "_")

            # Use async client directly
            async with AsyncElasticsearch([ES_URL]) as es:
                result = await es.get(index=index_name, id=doc_id)
                if result and result.get("found"):
                    source = result.get("_source", {})
                    return source.get("content", "")
            return None
        except Exception as e:
            logger.warning(f"Failed to get content from ES for {doc_id}: {e}")
            return None

    async def index_document(self, collection_name: str, document: Document, content: str) -> bool:
        """Index a single document to Weaviate"""
        if self.dry_run:
            logger.debug(f"[DRY-RUN] Would index document: {document.id}")
            self.stats["documents_indexed"] += 1
            return True

        try:
            # Prepare document data
            if not content or not content.strip():
                logger.warning(f"Document {document.id} has no content, skipping")
                self.stats["documents_skipped"] += 1
                return False

            # Format dates properly
            created_at = None
            updated_at = None
            if document.created_at:
                created_at = document.created_at.isoformat() if document.created_at.tzinfo else document.created_at.replace(tzinfo=timezone.utc).isoformat()
            if document.updated_at:
                updated_at = document.updated_at.isoformat() if document.updated_at.tzinfo else document.updated_at.replace(tzinfo=timezone.utc).isoformat()

            # Get tags
            tags = []
            if hasattr(document, "tags") and document.tags:
                tags = [tag.name for tag in document.tags if hasattr(tag, "name")]

            doc_data = {
                "title": document.title or document.filename or "Untitled",
                "content": content,
                "document_id": str(document.id),
                "tenant_id": str(document.tenant_id),
                "document_type": document.category or "general",
                "tags": tags,
                "created_at": created_at,
                "updated_at": updated_at
            }

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.base_url}/weaviate/collections/{collection_name}/documents",
                    json=doc_data,
                    headers=self.headers
                )
                response.raise_for_status()
                self.stats["documents_indexed"] += 1
                return True

        except Exception as e:
            logger.error(f"Failed to index document {document.id}: {e}")
            self.stats["documents_failed"] += 1
            return False

    async def reindex_tenant(self, tenant: Tenant, recreate: bool = True) -> Tuple[int, int]:
        """Reindex all documents for a tenant"""
        tenant_id = str(tenant.id)
        collection_name = get_collection_name(tenant_id)

        logger.info(f"{'='*60}")
        logger.info(f"Processing tenant: {tenant.name} ({tenant_id})")
        logger.info(f"Collection: {collection_name}")

        # Delete existing collection if recreating
        if recreate:
            await self.delete_collection(collection_name)

        # Create collection
        if not await self.create_collection(collection_name):
            logger.error(f"Failed to create collection for tenant {tenant_id}")
            return 0, 0

        # Get documents for this tenant
        with SessionLocal() as db:
            documents = (
                db.query(Document)
                .options(selectinload(Document.tags))
                .filter(Document.tenant_id == tenant.id)
                .order_by(Document.created_at)
                .all()
            )

            total = len(documents)
            if total == 0:
                logger.info(f"No documents for tenant {tenant_id}")
                return 0, 0

            logger.info(f"Found {total} documents to index")

            success = 0
            failed = 0
            skipped = 0

            for i, doc in enumerate(documents, 1):
                logger.info(f"Indexing [{i}/{total}] {doc.id} - {doc.title or doc.filename}")

                # Get content from Elasticsearch
                content = await self.get_document_content_from_es(tenant_id, str(doc.id))

                if not content:
                    logger.warning(f"No content in ES for document {doc.id}, skipping")
                    skipped += 1
                    continue

                if await self.index_document(collection_name, doc, content):
                    success += 1
                else:
                    failed += 1

                # Small delay to avoid overwhelming the service
                if i % 10 == 0:
                    await asyncio.sleep(0.1)

            logger.info(f"Tenant {tenant_id}: {success} indexed, {failed} failed, {skipped} skipped (no content)")
            return success, failed

    async def reindex_all(self, recreate: bool = True) -> dict:
        """Reindex all tenants"""
        logger.info("Starting Weaviate reindex for all tenants")

        # Check health first
        if not await self.check_health():
            logger.error("Weaviate service is not healthy, aborting")
            return self.stats

        logger.info("Weaviate service is healthy")

        with SessionLocal() as db:
            tenants = db.query(Tenant).order_by(Tenant.created_at).all()

        if not tenants:
            logger.info("No tenants found")
            return self.stats

        logger.info(f"Found {len(tenants)} tenants to process")

        total_success = 0
        total_failed = 0

        for tenant in tenants:
            success, failed = await self.reindex_tenant(tenant, recreate=recreate)
            total_success += success
            total_failed += failed

        self.stats["documents_indexed"] = total_success
        self.stats["documents_failed"] = total_failed

        return self.stats

    async def reindex_single_tenant(self, tenant_id: str, recreate: bool = True) -> dict:
        """Reindex a single tenant"""
        logger.info(f"Starting Weaviate reindex for tenant: {tenant_id}")

        # Check health first
        if not await self.check_health():
            logger.error("Weaviate service is not healthy, aborting")
            return self.stats

        with SessionLocal() as db:
            tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()

        if not tenant:
            logger.error(f"Tenant not found: {tenant_id}")
            return self.stats

        success, failed = await self.reindex_tenant(tenant, recreate=recreate)
        self.stats["documents_indexed"] = success
        self.stats["documents_failed"] = failed

        return self.stats


async def main():
    parser = argparse.ArgumentParser(description="Reindex documents to Weaviate")
    parser.add_argument("--tenant", type=str, help="Specific tenant ID to reindex")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without making changes")
    parser.add_argument("--no-recreate", action="store_true", help="Don't delete existing collections before reindexing")
    args = parser.parse_args()

    reindexer = WeaviateReindexer(dry_run=args.dry_run)

    if args.dry_run:
        logger.info("DRY-RUN MODE - No changes will be made")

    try:
        if args.tenant:
            stats = await reindexer.reindex_single_tenant(
                args.tenant,
                recreate=not args.no_recreate
            )
        else:
            stats = await reindexer.reindex_all(recreate=not args.no_recreate)

        logger.info("="*60)
        logger.info("REINDEX COMPLETE")
        logger.info(f"  Collections created: {stats['collections_created']}")
        logger.info(f"  Documents indexed: {stats['documents_indexed']}")
        logger.info(f"  Documents failed: {stats['documents_failed']}")
        logger.info(f"  Documents skipped: {stats['documents_skipped']}")

    except KeyboardInterrupt:
        logger.info("Reindex interrupted by user")
    except Exception as e:
        logger.exception(f"Reindex failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
