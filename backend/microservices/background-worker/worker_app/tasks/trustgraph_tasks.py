"""
Celery tasks for TrustGraph triple extraction.

Task Flow:
    extract_document_task:
        1. POST to /extract/triples on knowledge-tree-service
        2. Passes document_id, chunks, collection, and metadata
        3. Retries up to 2 times on failure (10s delay)

    reindex_graph_task:
        1. DELETE /triples/clear on knowledge-tree-service (wipes graph)
        2. Logs that re-indexing will happen via the normal indexing pipeline

    refresh_entity_embeddings_task:
        1. POST to /triples/refresh-embeddings on knowledge-tree-service
        2. Drift safety net for the per-extraction auto-embed hook —
           covers cases where the hook was disabled, failed, or hadn't
           caught up to the latest entities
"""

import logging
import os
from typing import Any, Dict, List, Optional

import httpx

from worker_app.celery_app import celery_app

logger = logging.getLogger(__name__)

# Configuration from environment
KTS_URL = os.getenv("KNOWLEDGE_TREE_SERVICE_URL", "http://knowledge-tree-service:8011")
MICROSERVICES_API_KEY = os.getenv("MICROSERVICES_API_KEY", "")

# Timeout for extraction requests — LLM calls can take a while
EXTRACTION_TIMEOUT = 260  # seconds (soft_time_limit is 280)
CLEAR_TIMEOUT = 60  # seconds
# Embed-refresh covers the full graph: query FalkorDB → batch embed
# every entity via intelligence-docs → DELETE+INSERT in Weaviate. With
# a few thousand entities this stays under a minute, but we leave room
# for slower fleets.
REFRESH_EMBEDDINGS_TIMEOUT = 600  # seconds


def _get_headers() -> Dict[str, str]:
    """Return auth headers for knowledge-tree-service."""
    return {"X-API-Key": MICROSERVICES_API_KEY, "Content-Type": "application/json"}


@celery_app.task(
    name="trustgraph.extract_document",
    bind=True,
    max_retries=2,
    default_retry_delay=10,
    time_limit=300,
    soft_time_limit=280,
)
def extract_document_task(
    self,
    document_id: str,
    chunks: List[str],
    collection: str = "default",
    title: str = "",
    file_path: str = "",
    semantic_type: str = "",
) -> Dict[str, Any]:
    """Extract and store TrustGraph triples for a document.

    POSTs to /extract/triples on knowledge-tree-service.  The KTS runs
    4 parallel LLM extractors (definitions, relationships, objects, topics),
    deduplicates the resulting triples, stores them in FalkorDB and records
    PROV-O provenance.

    Args:
        document_id:   Unique document ID.
        chunks:        Ordered list of text chunks from the document.
        collection:    Collection scope (default: "default").
        title:         Human-readable document title.
        file_path:     Storage path (used to derive folder URI).
        semantic_type: Document semantic type (e.g. "factura").

    Returns:
        KTS TripleExtractionResponse dict on success.

    Raises:
        Retries up to 2 times with a 10s delay on any exception.
    """
    url = f"{KTS_URL}/extract/triples"
    payload = {
        "document_id": document_id,
        "chunks": chunks,
        "collection": collection,
        "title": title,
        "file_path": file_path,
        "semantic_type": semantic_type,
    }

    logger.info(
        "trustgraph.extract_document: doc=%s chunks=%d collection=%s",
        document_id,
        len(chunks),
        collection,
    )

    try:
        with httpx.Client(timeout=EXTRACTION_TIMEOUT) as client:
            response = client.post(url, json=payload, headers=_get_headers())

        if response.status_code == 200:
            result = response.json()
            logger.info(
                "trustgraph.extract_document: OK — doc=%s triples=%d contradictions=%d errors=%d",
                document_id,
                result.get("triples_created", 0),
                result.get("contradictions_found", 0),
                len(result.get("errors", [])),
            )
            return result
        else:
            msg = f"KTS returned HTTP {response.status_code}: {response.text[:300]}"
            logger.error("trustgraph.extract_document: %s", msg)
            raise ValueError(msg)

    except Exception as exc:
        logger.warning(
            "trustgraph.extract_document: attempt %d/%d failed for doc=%s: %s",
            self.request.retries + 1,
            self.max_retries + 1,
            document_id,
            exc,
        )
        raise self.retry(exc=exc)


@celery_app.task(
    name="trustgraph.reindex_graph",
    bind=True,
    max_retries=0,
    time_limit=3600,
    soft_time_limit=3500,
)
def reindex_graph_task(
    self,
    collection: str = "default",
) -> Dict[str, Any]:
    """Clear the TrustGraph and trigger re-indexation.

    Step 1: DELETEs all triples via /triples/clear.
    Step 2: Logs that documents will be re-extracted by the indexing
            pipeline (each document.indexed event triggers
            trustgraph.extract_document via the event bus / Celery).

    Args:
        collection: Collection scope (default: "default").

    Returns:
        Dict with keys:
          success     — True when clear completed
          deleted     — number of nodes deleted
          message     — human-readable summary
    """
    url = f"{KTS_URL}/triples/clear"

    logger.info(
        "trustgraph.reindex_graph: clearing graph collection=%s",
        collection,
    )

    try:
        with httpx.Client(timeout=CLEAR_TIMEOUT) as client:
            response = client.delete(url, headers=_get_headers())

        if response.status_code == 200:
            result = response.json()
            deleted = result.get("deleted", 0)
            logger.info(
                "trustgraph.reindex_graph: cleared %d nodes — "
                "documents will be re-extracted as they are re-indexed via the pipeline",
                deleted,
            )
            return {
                "success": True,
                "deleted": deleted,
                "message": (
                    f"Graph cleared ({deleted} nodes removed). "
                    "Re-indexation will proceed via the document indexing pipeline."
                ),
            }
        else:
            msg = f"KTS returned HTTP {response.status_code}: {response.text[:300]}"
            logger.error("trustgraph.reindex_graph: %s", msg)
            return {"success": False, "deleted": 0, "message": msg}

    except Exception as exc:
        logger.exception(
            "trustgraph.reindex_graph: failed: %s", exc
        )
        return {"success": False, "deleted": 0, "message": str(exc)}


@celery_app.task(
    name="trustgraph.refresh_entity_embeddings",
    bind=True,
    max_retries=1,
    default_retry_delay=300,
    time_limit=900,
    soft_time_limit=850,
)
def refresh_entity_embeddings_task(
    self,
    collection: str = "default",
) -> Dict[str, Any]:
    """Re-embed every :Node entity into Weaviate (TrustGraphEntities).

    Drift safety net for the per-extraction auto-embed hook on
    knowledge-tree-service. Runs weekly via Celery beat so any entity
    that escaped the hook (disabled flag, hook failure, race condition)
    becomes searchable in graph_rag without manual intervention.

    Args:
        collection: Collection scope (default: "default").

    Returns:
        Dict with keys:
          success           — True on HTTP 200
          entities_upserted — count returned by KTS
          message           — human-readable summary
    """
    url = f"{KTS_URL}/triples/refresh-embeddings"
    payload = {"collection": collection}

    logger.info(
        "trustgraph.refresh_entity_embeddings: collection=%s",
        collection,
    )

    try:
        with httpx.Client(timeout=REFRESH_EMBEDDINGS_TIMEOUT) as client:
            response = client.post(url, json=payload, headers=_get_headers())

        if response.status_code == 200:
            result = response.json()
            upserted = result.get("entities_upserted", 0)
            logger.info(
                "trustgraph.refresh_entity_embeddings: OK — %d entities upserted",
                upserted,
            )
            return {
                "success": True,
                "entities_upserted": upserted,
                "message": f"Refreshed {upserted} entity embeddings.",
            }
        else:
            msg = f"KTS returned HTTP {response.status_code}: {response.text[:300]}"
            logger.error("trustgraph.refresh_entity_embeddings: %s", msg)
            raise ValueError(msg)

    except Exception as exc:
        logger.warning(
            "trustgraph.refresh_entity_embeddings: attempt %d/%d failed: %s",
            self.request.retries + 1,
            self.max_retries + 1,
            exc,
        )
        raise self.retry(exc=exc)
