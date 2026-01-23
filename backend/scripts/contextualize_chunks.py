#!/usr/bin/env python3
"""
Contextual Retrieval Batch Reindexing Script

This script reprocesses existing documents to apply Anthropic's Contextual Retrieval
pattern, which prepends domain-specific legal context to each chunk.

Based on Anthropic research showing 35-67% improvement in retrieval accuracy:
https://www.anthropic.com/news/contextual-retrieval

Usage:
    # Reindex all documents for a tenant
    python scripts/contextualize_chunks.py --tenant-id tenant-123

    # Reindex specific documents
    python scripts/contextualize_chunks.py --document-ids doc1,doc2,doc3

    # Dry run (analyze without modifying)
    python scripts/contextualize_chunks.py --tenant-id tenant-123 --dry-run

    # Use LLM for enhanced context generation
    python scripts/contextualize_chunks.py --tenant-id tenant-123 --use-llm

Environment:
    DATABASE_URL: PostgreSQL connection string
    WEAVIATE_URL: Weaviate server URL
    VLLM_BASE_URL: vLLM server URL (if --use-llm)

Author: NouxCubeIA
Date: 2026-01
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "microservices" / "weaviate-service"))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Results tracking
class ReindexResults:
    def __init__(self):
        self.total_documents = 0
        self.processed = 0
        self.skipped = 0
        self.errors = 0
        self.chunks_updated = 0
        self.domains_detected = {}
        self.errors_list = []
        self.start_time = datetime.now()

    def add_success(self, doc_id: str, domain: str, chunks_count: int):
        self.processed += 1
        self.chunks_updated += chunks_count
        self.domains_detected[domain] = self.domains_detected.get(domain, 0) + 1

    def add_error(self, doc_id: str, error: str):
        self.errors += 1
        self.errors_list.append({"document_id": doc_id, "error": error})

    def add_skip(self, doc_id: str, reason: str):
        self.skipped += 1
        logger.debug(f"Skipped {doc_id}: {reason}")

    def to_dict(self) -> Dict[str, Any]:
        elapsed = (datetime.now() - self.start_time).total_seconds()
        return {
            "summary": {
                "total_documents": self.total_documents,
                "processed": self.processed,
                "skipped": self.skipped,
                "errors": self.errors,
                "chunks_updated": self.chunks_updated,
                "elapsed_seconds": elapsed,
                "docs_per_second": self.processed / elapsed if elapsed > 0 else 0,
            },
            "domains_detected": self.domains_detected,
            "errors": self.errors_list[:20],  # First 20 errors
        }


async def get_weaviate_client():
    """Get Weaviate client."""
    import weaviate

    weaviate_url = os.getenv("WEAVIATE_URL", "http://localhost:8080")

    client = weaviate.Client(weaviate_url)

    # Test connection
    if not client.is_ready():
        raise ConnectionError(f"Cannot connect to Weaviate at {weaviate_url}")

    return client


async def get_documents_to_reindex(
    tenant_id: Optional[str] = None,
    document_ids: Optional[List[str]] = None,
    limit: int = 1000
) -> List[Dict[str, Any]]:
    """
    Get list of documents to reindex from Weaviate.

    Args:
        tenant_id: Filter by tenant (if provided)
        document_ids: Specific document IDs (if provided)
        limit: Maximum documents to return

    Returns:
        List of document metadata dicts
    """
    client = await get_weaviate_client()

    # Build query
    collection_name = f"Document_{tenant_id}" if tenant_id else "Document"

    try:
        # Query documents
        where_filter = {}
        if document_ids:
            where_filter = {
                "operator": "Or",
                "operands": [
                    {"path": ["document_id"], "operator": "Equal", "valueText": doc_id}
                    for doc_id in document_ids
                ]
            }
        elif tenant_id:
            where_filter = {
                "path": ["tenant_id"],
                "operator": "Equal",
                "valueText": tenant_id
            }

        query = client.query.get(
            collection_name,
            ["document_id", "tenant_id", "title", "document_type", "content"]
        ).with_additional(["id"])

        if where_filter:
            query = query.with_where(where_filter)

        query = query.with_limit(limit)

        result = query.do()

        documents = result.get("data", {}).get("Get", {}).get(collection_name, [])

        return documents

    except Exception as e:
        logger.error(f"Error querying documents: {e}")
        return []


async def contextualize_document(
    doc: Dict[str, Any],
    contextual_service,
    use_llm: bool = False
) -> Dict[str, Any]:
    """
    Apply contextual retrieval to a single document.

    Args:
        doc: Document metadata and content
        contextual_service: ContextualRetrievalService instance
        use_llm: Whether to use LLM for enhanced context

    Returns:
        Dict with contextualization results
    """
    document_id = doc.get("document_id", doc.get("_additional", {}).get("id"))
    tenant_id = doc.get("tenant_id", "default")
    content = doc.get("content", "")
    document_type = doc.get("document_type", "")

    if not content:
        return {
            "document_id": document_id,
            "success": False,
            "error": "No content found",
        }

    # Analyze document
    context_result = await contextual_service.analyze_document(
        document_id=document_id,
        text=content,
        metadata={
            "document_type": document_type,
            "title": doc.get("title", ""),
        },
        tenant_id=tenant_id,
        use_llm=use_llm,
    )

    return {
        "document_id": document_id,
        "success": True,
        "domain": context_result.domain.value,
        "context_prefix": context_result.context_prefix,
        "applicable_laws": [l.to_citation() for l in context_result.applicable_laws],
        "confidence": context_result.metadata.get("domain_confidence", 0),
    }


async def update_document_chunks(
    client,
    document_id: str,
    tenant_id: str,
    context_prefix: str,
    domain: str,
    applicable_laws: List[str],
    dry_run: bool = False
) -> int:
    """
    Update document chunks in Weaviate with contextual information.

    Args:
        client: Weaviate client
        document_id: Document ID
        tenant_id: Tenant ID
        context_prefix: Context to prepend
        domain: Detected domain
        applicable_laws: List of applicable law citations
        dry_run: If True, don't actually update

    Returns:
        Number of chunks updated
    """
    collection_name = f"Document_{tenant_id}" if tenant_id else "Document"

    # Find all chunks for this document
    where_filter = {
        "path": ["document_id"],
        "operator": "Equal",
        "valueText": document_id
    }

    try:
        result = client.query.get(
            collection_name,
            ["document_id", "chunk_index", "text"]
        ).with_where(where_filter).with_additional(["id"]).with_limit(1000).do()

        chunks = result.get("data", {}).get("Get", {}).get(collection_name, [])

        if not chunks:
            return 0

        if dry_run:
            logger.info(f"  [DRY RUN] Would update {len(chunks)} chunks for {document_id}")
            return len(chunks)

        # Update each chunk
        updated = 0
        for chunk in chunks:
            chunk_id = chunk.get("_additional", {}).get("id")
            original_text = chunk.get("text", "")

            if not chunk_id:
                continue

            # Skip if already contextualized
            if original_text.startswith("[CONTEXTO]"):
                continue

            # Create contextualized text
            new_text = f"{context_prefix} {original_text}"

            # Update chunk
            try:
                client.data_object.update(
                    uuid=chunk_id,
                    class_name=collection_name,
                    data_object={
                        "text": new_text,
                        "contextual_domain": domain,
                        "contextual_laws": applicable_laws,
                        "contextual_prefix_applied": True,
                    }
                )
                updated += 1
            except Exception as e:
                logger.warning(f"Failed to update chunk {chunk_id}: {e}")

        return updated

    except Exception as e:
        logger.error(f"Error updating chunks for {document_id}: {e}")
        return 0


async def main(
    tenant_id: Optional[str] = None,
    document_ids: Optional[List[str]] = None,
    use_llm: bool = False,
    dry_run: bool = False,
    batch_size: int = 10,
    limit: int = 1000
):
    """
    Main reindexing function.

    Args:
        tenant_id: Tenant ID to process
        document_ids: Specific document IDs (optional)
        use_llm: Use LLM for enhanced context
        dry_run: Don't modify, just analyze
        batch_size: Documents per batch
        limit: Maximum documents to process
    """
    logger.info("=" * 60)
    logger.info("Contextual Retrieval Batch Reindexing")
    logger.info("=" * 60)
    logger.info(f"Tenant ID: {tenant_id or 'all'}")
    logger.info(f"Document IDs: {document_ids or 'all'}")
    logger.info(f"Use LLM: {use_llm}")
    logger.info(f"Dry Run: {dry_run}")
    logger.info(f"Batch Size: {batch_size}")
    logger.info(f"Limit: {limit}")
    logger.info("-" * 60)

    results = ReindexResults()

    # Import contextual retrieval service
    try:
        from app.services.rag.contextual_retrieval import contextual_retrieval
    except ImportError as e:
        logger.error(f"Failed to import contextual_retrieval: {e}")
        logger.error("Make sure you're running from the correct directory")
        return

    # Get Weaviate client
    try:
        client = await get_weaviate_client()
        logger.info("✅ Connected to Weaviate")
    except Exception as e:
        logger.error(f"❌ Failed to connect to Weaviate: {e}")
        return

    # Get documents to reindex
    logger.info("Fetching documents...")
    documents = await get_documents_to_reindex(
        tenant_id=tenant_id,
        document_ids=document_ids,
        limit=limit
    )

    results.total_documents = len(documents)
    logger.info(f"Found {len(documents)} documents to process")

    if not documents:
        logger.warning("No documents found to reindex")
        return

    # Process in batches
    for i in range(0, len(documents), batch_size):
        batch = documents[i:i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (len(documents) + batch_size - 1) // batch_size

        logger.info(f"\nProcessing batch {batch_num}/{total_batches}...")

        for doc in batch:
            doc_id = doc.get("document_id", doc.get("_additional", {}).get("id", "unknown"))

            try:
                # Analyze document
                context_result = await contextualize_document(
                    doc, contextual_retrieval, use_llm
                )

                if not context_result.get("success"):
                    results.add_skip(doc_id, context_result.get("error", "Unknown"))
                    continue

                domain = context_result["domain"]
                context_prefix = context_result["context_prefix"]
                applicable_laws = context_result.get("applicable_laws", [])

                # Update chunks in Weaviate
                tenant = doc.get("tenant_id", tenant_id or "default")
                chunks_updated = await update_document_chunks(
                    client=client,
                    document_id=doc_id,
                    tenant_id=tenant,
                    context_prefix=context_prefix,
                    domain=domain,
                    applicable_laws=applicable_laws,
                    dry_run=dry_run,
                )

                results.add_success(doc_id, domain, chunks_updated)

                logger.info(
                    f"  ✅ {doc_id}: domain={domain}, "
                    f"chunks={chunks_updated}, laws={len(applicable_laws)}"
                )

            except Exception as e:
                results.add_error(doc_id, str(e))
                logger.error(f"  ❌ {doc_id}: {e}")

        # Progress update
        logger.info(
            f"Progress: {results.processed}/{results.total_documents} "
            f"({results.processed * 100 / results.total_documents:.1f}%)"
        )

    # Final report
    logger.info("\n" + "=" * 60)
    logger.info("REINDEXING COMPLETE")
    logger.info("=" * 60)

    report = results.to_dict()

    logger.info(f"Total documents: {report['summary']['total_documents']}")
    logger.info(f"Processed: {report['summary']['processed']}")
    logger.info(f"Skipped: {report['summary']['skipped']}")
    logger.info(f"Errors: {report['summary']['errors']}")
    logger.info(f"Chunks updated: {report['summary']['chunks_updated']}")
    logger.info(f"Elapsed time: {report['summary']['elapsed_seconds']:.1f}s")
    logger.info(f"Speed: {report['summary']['docs_per_second']:.2f} docs/sec")

    logger.info("\nDomains detected:")
    for domain, count in report['domains_detected'].items():
        logger.info(f"  - {domain}: {count}")

    if report['errors']:
        logger.info("\nFirst errors:")
        for err in report['errors'][:5]:
            logger.info(f"  - {err['document_id']}: {err['error']}")

    # Save report
    report_path = f"/tmp/contextual_reindex_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2)
    logger.info(f"\nFull report saved to: {report_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Reindex documents with Contextual Retrieval"
    )
    parser.add_argument(
        "--tenant-id",
        type=str,
        help="Tenant ID to process"
    )
    parser.add_argument(
        "--document-ids",
        type=str,
        help="Comma-separated list of specific document IDs"
    )
    parser.add_argument(
        "--use-llm",
        action="store_true",
        help="Use LLM for enhanced context generation"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Analyze without modifying (dry run)"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Documents per batch (default: 10)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=1000,
        help="Maximum documents to process (default: 1000)"
    )

    args = parser.parse_args()

    document_ids = None
    if args.document_ids:
        document_ids = [d.strip() for d in args.document_ids.split(",")]

    asyncio.run(main(
        tenant_id=args.tenant_id,
        document_ids=document_ids,
        use_llm=args.use_llm,
        dry_run=args.dry_run,
        batch_size=args.batch_size,
        limit=args.limit,
    ))
