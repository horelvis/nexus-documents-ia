"""Embed FalkorDB :Node entities into Weaviate TrustGraphEntities collection.

Two flows are exposed:

- ``populate_entity_embeddings(scope, collection)``: full re-embed of every
  :Node in the scope. Used by ``scripts/reindex_trustgraph.py`` and by the
  weekly drift-safety cron. Wipes the collection and rebuilds it, so
  obsolete entities (deleted from FalkorDB since the last run) drop out.

- ``populate_entity_embeddings_subset(scope, collection, subset_uris)``:
  incremental, idempotent upsert of just the URIs in ``subset_uris``.
  Used by ``ExtractionCoordinator.extract_document`` so the graph_rag
  entity index reflects new extractions without paying the cost of a
  full re-embed. Backed by the weaviate-service ``/entities/upsert-subset``
  endpoint, which uses replace-or-insert per object and therefore tolerates
  re-runs against existing UUIDs.
"""

import asyncio
import logging
from typing import Any, Dict, Iterable, List, Optional

import httpx

from app.core.config import settings
from app.services.falkordb_client import FalkorDBClient

logger = logging.getLogger(__name__)

EMBED_BATCH_SIZE = 64

# Serializes the full re-embed against itself and against subset upserts.
# A full re-embed runs DELETE+INSERT on the collection; if a subset upsert
# raced through that window, anything it just wrote could be wiped by the
# DELETE. The subset path is cheap (per-object replace), so making it
# wait for the rare full re-embed is the right trade.
_lock = asyncio.Lock()

_HEADERS = {
    "X-API-Key": settings.MICROSERVICES_API_KEY,
    "Content-Type": "application/json",
}


async def populate_entity_embeddings(scope: str, collection: str) -> int:
    """Re-embed all :Node entities for a scope and upsert to Weaviate.

    Steps:
    1. Query entity nodes with label/type/definition properties from FalkorDB.
    2. Build an embed text per entity.
    3. Batch-embed via intelligence-docs-service /embed endpoint.
    4. Delete existing entity embeddings from weaviate-service.
    5. Batch-upsert entities + embeddings to weaviate-service /entities/batch-upsert.

    Returns the total number of entities upserted. Serialized via _lock.
    """
    async with _lock:
        return await _populate_entity_embeddings_impl(scope, collection)


async def _populate_entity_embeddings_impl(scope: str, collection: str) -> int:
    falkordb = FalkorDBClient()
    await falkordb.initialize()

    try:
        rows = await falkordb.execute_cypher(
            "MATCH (n:Node {user: $user}) "
            "OPTIONAL MATCH (n)-[r1:Rel {uri: 'nouxcube://predicate/core/label'}]->(l:Literal) "
            "OPTIONAL MATCH (n)-[r2:Rel {uri: 'nouxcube://predicate/core/type'}]->(t:Literal) "
            "OPTIONAL MATCH (n)-[r3:Rel {uri: 'nouxcube://predicate/core/definition'}]->(d:Literal) "
            "RETURN n.uri AS uri, l.value AS label, t.value AS type, d.value AS definition",
            {"user": scope},
        )
    finally:
        await falkordb.close()

    if not rows:
        logger.info("  No :Node entities found for scope=%s — skipping embeddings", scope)
        return 0

    logger.info("  Found %d entity nodes to embed", len(rows))

    # Build embed texts
    entities: List[Dict[str, Any]] = []
    embed_texts: List[str] = []

    for row in rows:
        uri: str = row.get("uri") or ""
        label: Optional[str] = row.get("label")
        entity_type: Optional[str] = row.get("type")
        definition: Optional[str] = row.get("definition")

        if not uri:
            continue

        # Humanize fallback label from URI last segment
        if not label:
            slug = uri.rsplit("/", 1)[-1]
            label = slug.replace("-", " ").replace("_", " ").title()

        type_str = entity_type or "entity"

        if definition:
            text = f"{label} ({type_str}). {definition}"
        else:
            text = f"{label} ({type_str})"

        entities.append({
            "entity_uri": uri,
            "label": label,
            "entity_type": type_str,
            "definition": definition or "",
            "collection": collection,
        })
        embed_texts.append(text)

    if not entities:
        logger.info("  No valid entities after filtering — skipping embeddings")
        return 0

    weaviate_url = settings.WEAVIATE_SERVICE_URL.rstrip("/")
    intelligence_url = settings.INTELLIGENCE_DOCS_SERVICE_URL.rstrip("/")

    # Batch embed via intelligence-docs-service
    all_embeddings: List[List[float]] = []
    async with httpx.AsyncClient(timeout=120) as http:
        for batch_start in range(0, len(embed_texts), EMBED_BATCH_SIZE):
            batch = embed_texts[batch_start: batch_start + EMBED_BATCH_SIZE]
            resp = await http.post(
                f"{intelligence_url}/embed",
                json={"texts": batch, "task": "retrieval.passage"},
                headers=_HEADERS,
            )
            if resp.status_code != 200:
                raise RuntimeError(
                    f"intelligence-docs-service /embed returned HTTP {resp.status_code}: "
                    f"{resp.text[:300]}"
                )
            data = resp.json()
            batch_embeddings: List[List[float]] = data.get("embeddings", data)
            all_embeddings.extend(batch_embeddings)
            logger.info(
                "  Embedded batch %d-%d / %d",
                batch_start + 1,
                min(batch_start + EMBED_BATCH_SIZE, len(embed_texts)),
                len(embed_texts),
            )

    if len(all_embeddings) != len(entities):
        raise RuntimeError(
            f"Embedding count mismatch: got {len(all_embeddings)} for {len(entities)} entities"
        )

    # Delete existing entity embeddings (non-idempotent endpoint workaround)
    async with httpx.AsyncClient(timeout=60) as http:
        del_resp = await http.delete(
            f"{weaviate_url}/weaviate/entities/delete",
            headers=_HEADERS,
        )
        if del_resp.status_code not in (200, 204, 404):
            logger.warning(
                "  DELETE /entities/delete returned HTTP %d — proceeding with upsert",
                del_resp.status_code,
            )
        else:
            logger.info("  Deleted existing entity embeddings")

        # Batch upsert entities + embeddings
        upserted = 0
        for batch_start in range(0, len(entities), EMBED_BATCH_SIZE):
            batch_entities = entities[batch_start: batch_start + EMBED_BATCH_SIZE]
            batch_embeddings = all_embeddings[batch_start: batch_start + EMBED_BATCH_SIZE]
            upsert_resp = await http.post(
                f"{weaviate_url}/weaviate/entities/batch-upsert",
                json={
                    "entities": batch_entities,
                    "embeddings": batch_embeddings,
                },
                headers=_HEADERS,
            )
            if upsert_resp.status_code not in (200, 201):
                raise RuntimeError(
                    f"weaviate-service /entities/batch-upsert returned HTTP "
                    f"{upsert_resp.status_code}: {upsert_resp.text[:300]}"
                )
            upserted += len(batch_entities)
            logger.info(
                "  Upserted batch %d-%d / %d",
                batch_start + 1,
                min(batch_start + EMBED_BATCH_SIZE, len(entities)),
                len(entities),
            )

    return upserted


async def populate_entity_embeddings_subset(
    scope: str,
    collection: str,
    subset_uris: Iterable[str],
) -> int:
    """Idempotent re-embed of just the entities whose URIs are in ``subset_uris``.

    Designed for the per-document hook in ExtractionCoordinator: keeps
    the graph_rag entity index in sync with new extractions without
    re-processing the whole scope. Skips any URI that does not resolve
    to a :Node (already deleted, or filtered out by blacklist).
    """
    uri_list = [u for u in subset_uris if u]
    if not uri_list:
        return 0

    async with _lock:
        return await _populate_entity_embeddings_subset_impl(
            scope=scope, collection=collection, uri_list=uri_list,
        )


async def _populate_entity_embeddings_subset_impl(
    scope: str, collection: str, uri_list: List[str],
) -> int:
    falkordb = FalkorDBClient()
    await falkordb.initialize()

    try:
        rows = await falkordb.execute_cypher(
            "MATCH (n:Node {user: $user}) WHERE n.uri IN $uris "
            "OPTIONAL MATCH (n)-[r1:Rel {uri: 'nouxcube://predicate/core/label'}]->(l:Literal) "
            "OPTIONAL MATCH (n)-[r2:Rel {uri: 'nouxcube://predicate/core/type'}]->(t:Literal) "
            "OPTIONAL MATCH (n)-[r3:Rel {uri: 'nouxcube://predicate/core/definition'}]->(d:Literal) "
            "RETURN n.uri AS uri, l.value AS label, t.value AS type, d.value AS definition",
            {"user": scope, "uris": uri_list},
        )
    finally:
        await falkordb.close()

    if not rows:
        logger.info(
            "  Subset upsert: no :Node entities resolved for %d URIs (scope=%s) — skipping",
            len(uri_list),
            scope,
        )
        return 0

    entities, embed_texts = _build_embed_payload(rows, collection)
    if not entities:
        return 0

    weaviate_url = settings.WEAVIATE_SERVICE_URL.rstrip("/")
    intelligence_url = settings.INTELLIGENCE_DOCS_SERVICE_URL.rstrip("/")
    all_embeddings = await _embed_texts(intelligence_url, embed_texts)

    if len(all_embeddings) != len(entities):
        raise RuntimeError(
            f"Embedding count mismatch: got {len(all_embeddings)} for {len(entities)} entities"
        )

    upserted = 0
    async with httpx.AsyncClient(timeout=120) as http:
        for batch_start in range(0, len(entities), EMBED_BATCH_SIZE):
            batch_entities = entities[batch_start: batch_start + EMBED_BATCH_SIZE]
            batch_embeddings = all_embeddings[batch_start: batch_start + EMBED_BATCH_SIZE]
            resp = await http.post(
                f"{weaviate_url}/weaviate/entities/upsert-subset",
                json={
                    "entities": batch_entities,
                    "embeddings": batch_embeddings,
                },
                headers=_HEADERS,
            )
            if resp.status_code not in (200, 201):
                raise RuntimeError(
                    f"weaviate-service /entities/upsert-subset returned HTTP "
                    f"{resp.status_code}: {resp.text[:300]}"
                )
            upserted += len(batch_entities)

    logger.info(
        "  Subset upsert: %d entities (replace-or-insert) for scope=%s",
        upserted,
        scope,
    )
    return upserted


# ---------------------------------------------------------------------------
# Internal helpers shared by full and subset paths
# ---------------------------------------------------------------------------


def _build_embed_payload(
    rows: List[Dict[str, Any]],
    collection: str,
) -> tuple[List[Dict[str, Any]], List[str]]:
    """Turn FalkorDB rows into the (entities, embed_texts) tuple expected
    by intelligence-docs and weaviate-service.
    """
    entities: List[Dict[str, Any]] = []
    embed_texts: List[str] = []
    for row in rows:
        uri: str = row.get("uri") or ""
        if not uri:
            continue
        label: Optional[str] = row.get("label")
        entity_type: Optional[str] = row.get("type")
        definition: Optional[str] = row.get("definition")

        if not label:
            slug = uri.rsplit("/", 1)[-1]
            label = slug.replace("-", " ").replace("_", " ").title()

        type_str = entity_type or "entity"
        text = (
            f"{label} ({type_str}). {definition}"
            if definition
            else f"{label} ({type_str})"
        )

        entities.append({
            "entity_uri": uri,
            "label": label,
            "entity_type": type_str,
            "definition": definition or "",
            "collection": collection,
        })
        embed_texts.append(text)
    return entities, embed_texts


async def _embed_texts(
    intelligence_url: str,
    embed_texts: List[str],
) -> List[List[float]]:
    """Batch-embed via intelligence-docs-service /embed endpoint."""
    all_embeddings: List[List[float]] = []
    async with httpx.AsyncClient(timeout=120) as http:
        for batch_start in range(0, len(embed_texts), EMBED_BATCH_SIZE):
            batch = embed_texts[batch_start: batch_start + EMBED_BATCH_SIZE]
            resp = await http.post(
                f"{intelligence_url}/embed",
                json={"texts": batch, "task": "retrieval.passage"},
                headers=_HEADERS,
            )
            if resp.status_code != 200:
                raise RuntimeError(
                    f"intelligence-docs-service /embed returned HTTP {resp.status_code}: "
                    f"{resp.text[:300]}"
                )
            data = resp.json()
            batch_embeddings: List[List[float]] = data.get("embeddings", data)
            all_embeddings.extend(batch_embeddings)
    return all_embeddings
