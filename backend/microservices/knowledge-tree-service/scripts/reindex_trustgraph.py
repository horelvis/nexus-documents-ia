#!/usr/bin/env python3
"""
Reindex TrustGraph for a tenant.

Clears the FalkorDB graph for the given tenant, bootstraps the schema +
ontology, fetches all documents from weaviate-service, and runs
ExtractionCoordinator.extract_document() for each document.

Usage:
    docker compose exec knowledge-tree-service \
        python scripts/reindex_trustgraph.py --tenant-id TENANT_ID

    docker compose exec knowledge-tree-service \
        python scripts/reindex_trustgraph.py --tenant-id TENANT_ID --dry-run

    docker compose exec knowledge-tree-service \
        python scripts/reindex_trustgraph.py --tenant-id TENANT_ID --collection legal

    docker compose exec knowledge-tree-service \
        python scripts/reindex_trustgraph.py --tenant-id TENANT_ID --skip-clear

Environment:
    WEAVIATE_SERVICE_URL          Base URL for weaviate-service (default: http://weaviate-service:8000)
    INTELLIGENCE_DOCS_SERVICE_URL Base URL for intelligence-docs-service (default: http://intelligence-docs-service:8012)
    MICROSERVICES_API_KEY         API key for service-to-service auth
"""

import argparse
import asyncio
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

# Allow imports from app when running inside the container
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings
from app.services.falkordb_client import FalkorDBClient
from app.services.triple_store import TripleStore
from app.services.extractors.coordinator import ExtractionCoordinator

# Import the seed_ontology function from the sibling script
SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))
from seed_ontology import seed_ontology  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("reindex_trustgraph")

# ── Colour helpers ─────────────────────────────────────────────────────────────

GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"

# ── Weaviate helpers ───────────────────────────────────────────────────────────

WEAVIATE_SERVICE_URL = settings.WEAVIATE_SERVICE_URL.rstrip("/")
INTELLIGENCE_DOCS_SERVICE_URL = os.environ.get(
    "INTELLIGENCE_DOCS_SERVICE_URL", "http://intelligence-docs-service:8000"
).rstrip("/")
MICROSERVICES_API_KEY = settings.MICROSERVICES_API_KEY

WEAVIATE_HEADERS = {
    "X-API-Key": MICROSERVICES_API_KEY,
    "Content-Type": "application/json",
}

EMBED_BATCH_SIZE = 64


def _collection_name(tenant_id: str) -> str:
    """Mirror weaviate-service's get_tenant_collection_name convention."""
    tenant_normalized = tenant_id.replace("-", "_")
    # collection_prefix is typically "Nouxcube_" — we read it from weaviate-service indirectly
    # by using the same env var convention; fall back to common default.
    prefix = "Nouxcube_"
    return f"{prefix}{tenant_normalized}_documents"


async def _fetch_documents(
    client: httpx.AsyncClient,
    tenant_id: str,
) -> List[Dict[str, Any]]:
    """Fetch all indexed documents for a tenant from weaviate-service.

    Tries the canonical list endpoint first:
        GET /weaviate/documents?tenant_id=TENANT_ID&limit=100

    If that returns 404 (endpoint not yet added), falls back to paginated
    search on the tenant's Weaviate collection:
        POST /weaviate/collections/{collection}/search

    Returns a list of document dicts with at least "id" and optional
    "title", "file_path", "semantic_type", "domain" keys.
    """
    PAGE_SIZE = 100  # weaviate-service max limit

    # ── Primary: list endpoint ─────────────────────────────────────────────────
    url = f"{WEAVIATE_SERVICE_URL}/weaviate/documents"
    params = {"tenant_id": tenant_id, "limit": PAGE_SIZE}
    resp = await client.get(url, params=params, headers=WEAVIATE_HEADERS)

    if resp.status_code == 200:
        data = resp.json()
        docs = data if isinstance(data, list) else data.get("documents", data.get("results", []))
        logger.info("  Fetched %d documents via /weaviate/documents list endpoint", len(docs))
        return docs

    if resp.status_code != 404:
        logger.warning(
            "  /weaviate/documents returned HTTP %d — falling back to collection search",
            resp.status_code,
        )

    # ── Fallback: paginated search on tenant collection ────────────────────────
    collection = _collection_name(tenant_id)
    search_url = f"{WEAVIATE_SERVICE_URL}/weaviate/collections/{collection}/search"

    seen_doc_ids: set = set()
    docs: List[Dict[str, Any]] = []
    offset = 0
    total_chunks = 0

    while True:
        payload = {
            "query": "",
            "tenant_id": tenant_id,
            "limit": PAGE_SIZE,
            "offset": offset,
            "search_type": "keyword",
            "filters": {},
        }
        search_resp = await client.post(search_url, json=payload, headers=WEAVIATE_HEADERS)

        if search_resp.status_code != 200:
            if offset == 0:
                raise RuntimeError(
                    f"Could not list documents for tenant {tenant_id!r}: "
                    f"search returned HTTP {search_resp.status_code} — {search_resp.text[:300]}"
                )
            # Non-first page error — stop pagination gracefully
            logger.warning("  Pagination stopped at offset %d: HTTP %d", offset, search_resp.status_code)
            break

        search_data = search_resp.json()
        raw_results = search_data.get("results", [])
        total_chunks += len(raw_results)

        if not raw_results:
            break  # No more results

        # Deduplicate by document_id — search returns chunks, not docs
        for item in raw_results:
            doc_id = item.get("document_id") or item.get("id")
            if doc_id and doc_id not in seen_doc_ids:
                seen_doc_ids.add(doc_id)
                docs.append({
                    "id": doc_id,
                    "title": item.get("title", ""),
                    "file_path": item.get("file_path", ""),
                    "semantic_type": item.get("semantic_type", ""),
                    "domain": item.get("domain", ""),
                })

        offset += PAGE_SIZE
        if len(raw_results) < PAGE_SIZE:
            break  # Last page

    logger.info(
        "  Fetched %d unique documents via paginated collection search "
        "(%d raw chunks from %r)",
        len(docs),
        total_chunks,
        collection,
    )
    return docs


async def _fetch_chunks(
    client: httpx.AsyncClient,
    tenant_id: str,
    document_id: str,
    limit: int = 500,
) -> List[str]:
    """Fetch text chunks for a document from weaviate-service.

    GET /weaviate/documents/{tenant_id}/{document_id}/chunks?limit=500
    Returns list of chunk text strings (ordered).
    """
    url = f"{WEAVIATE_SERVICE_URL}/weaviate/documents/{tenant_id}/{document_id}/chunks"
    params = {"offset": 0, "limit": limit}
    resp = await client.get(url, params=params, headers=WEAVIATE_HEADERS)

    if resp.status_code == 200:
        data = resp.json()
        raw_chunks = data.get("chunks", [])
        # Each chunk is a dict with a "content" or "text" key
        texts: List[str] = []
        for c in raw_chunks:
            if isinstance(c, str):
                texts.append(c)
            elif isinstance(c, dict):
                texts.append(c.get("content") or c.get("text") or c.get("chunk_text") or "")
        texts = [t for t in texts if t.strip()]
        return texts

    if resp.status_code == 404:
        logger.warning("    No chunks found for document %s (HTTP 404)", document_id)
        return []

    logger.warning(
        "    Chunk fetch returned HTTP %d for document %s — skipping",
        resp.status_code,
        document_id,
    )
    return []


# ── Entity resolution ─────────────────────────────────────────────────────────

async def _resolve_duplicate_entities(
    client: FalkorDBClient,
    tenant_id: str,
    collection: str,
) -> int:
    """Merge near-duplicate entity :Nodes after extraction.

    Strategy: group entity nodes by their URI slug (last segment). If two nodes
    have the same slug but different URIs (shouldn't happen with normalize_name,
    but can if older data exists), merge their relationships into one node and
    delete the duplicate.

    Also detects nodes that differ only by word order in the slug
    (e.g., "juan-garcia" vs "garcia-juan" from "García, Juan" vs "Juan García")
    by comparing sorted token sets.
    """
    # Fetch all entity node URIs for this tenant+collection
    rows = await client.execute_cypher(
        "MATCH (n:Node {user: $user, collection: $collection}) "
        "WHERE n.uri STARTS WITH 'nouxcube://entity/' "
        "RETURN n.uri AS uri",
        {"user": tenant_id, "collection": collection},
    )

    if not rows:
        return 0

    # Group by sorted token set → detect word-order duplicates
    # "nouxcube://entity/default/juan-garcia" → tokens = {"garcia", "juan"}
    from collections import defaultdict

    groups: Dict[str, List[str]] = defaultdict(list)
    for row in rows:
        uri = row["uri"]
        # Extract the slug (last segment after collection/)
        slug = uri.rsplit("/", 1)[-1]
        tokens = frozenset(slug.split("-"))
        group_key = "-".join(sorted(tokens))
        groups[group_key].append(uri)

    merged_count = 0
    for group_key, uris in groups.items():
        if len(uris) <= 1:
            continue

        # Keep the first URI as canonical, merge others into it
        canonical = sorted(uris)[0]  # deterministic: alphabetically first
        duplicates = [u for u in uris if u != canonical]

        for dup_uri in duplicates:
            try:
                # Move all outgoing rels from duplicate → canonical
                await client.execute_cypher(
                    "MATCH (dup:Node {uri: $dup_uri, user: $user, collection: $col})-[r:Rel]->(o) "
                    "MATCH (canon:Node {uri: $canon_uri, user: $user, collection: $col}) "
                    "MERGE (canon)-[r2:Rel {uri: r.uri, user: r.user, collection: r.collection}]->(o) "
                    "ON CREATE SET r2.extraction_method = r.extraction_method, "
                    "r2.source_chunk = r.source_chunk "
                    "DELETE r",
                    {"dup_uri": dup_uri, "canon_uri": canonical,
                     "user": tenant_id, "col": collection},
                )
                # Move all incoming rels to duplicate → canonical
                await client.execute_cypher(
                    "MATCH (s)-[r:Rel]->(dup:Node {uri: $dup_uri, user: $user, collection: $col}) "
                    "MATCH (canon:Node {uri: $canon_uri, user: $user, collection: $col}) "
                    "MERGE (s)-[r2:Rel {uri: r.uri, user: r.user, collection: r.collection}]->(canon) "
                    "ON CREATE SET r2.extraction_method = r.extraction_method, "
                    "r2.source_chunk = r.source_chunk "
                    "DELETE r",
                    {"dup_uri": dup_uri, "canon_uri": canonical,
                     "user": tenant_id, "col": collection},
                )
                # Delete the orphaned duplicate node
                await client.execute_cypher(
                    "MATCH (n:Node {uri: $uri, user: $user, collection: $col}) "
                    "WHERE NOT (n)-[:Rel]-() AND NOT ()-[:Rel]->(n) "
                    "DELETE n",
                    {"uri": dup_uri, "user": tenant_id, "col": collection},
                )
                merged_count += 1
                logger.info(
                    "  Merged duplicate: %s → %s", dup_uri, canonical
                )
            except Exception as exc:
                logger.warning(
                    "  Failed to merge %s → %s: %s", dup_uri, canonical, exc
                )

    return merged_count


# ── Entity embeddings ─────────────────────────────────────────────────────────

async def _populate_entity_embeddings(tenant_id: str, collection: str) -> int:
    """Query all :Node entities from FalkorDB, embed via intelligence-docs, upsert to Weaviate.

    Steps:
    1. Query entity nodes with label/type/definition properties from FalkorDB.
    2. Build an embed text per entity.
    3. Batch-embed via intelligence-docs-service /embed endpoint (batches of EMBED_BATCH_SIZE).
    4. Delete existing entity embeddings for this tenant from weaviate-service.
    5. Batch-upsert entities + embeddings to weaviate-service /entities/batch-upsert.

    Returns the total number of entities upserted.
    """
    falkordb = FalkorDBClient()
    await falkordb.initialize()

    try:
        rows = await falkordb.execute_cypher(
            "MATCH (n:Node {user: $user}) "
            "OPTIONAL MATCH (n)-[r1:Rel {uri: 'nouxcube://predicate/core/label'}]->(l:Literal) "
            "OPTIONAL MATCH (n)-[r2:Rel {uri: 'nouxcube://predicate/core/type'}]->(t:Literal) "
            "OPTIONAL MATCH (n)-[r3:Rel {uri: 'nouxcube://predicate/core/definition'}]->(d:Literal) "
            "RETURN n.uri AS uri, l.value AS label, t.value AS type, d.value AS definition",
            {"user": tenant_id},
        )
    finally:
        await falkordb.close()

    if not rows:
        logger.info("  No :Node entities found for tenant=%s — skipping embeddings", tenant_id)
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
            "collection": "default",
        })
        embed_texts.append(text)

    if not entities:
        logger.info("  No valid entities after filtering — skipping embeddings")
        return 0

    # Batch embed via intelligence-docs-service
    all_embeddings: List[List[float]] = []
    async with httpx.AsyncClient(timeout=120) as http:
        for batch_start in range(0, len(embed_texts), EMBED_BATCH_SIZE):
            batch = embed_texts[batch_start: batch_start + EMBED_BATCH_SIZE]
            resp = await http.post(
                f"{INTELLIGENCE_DOCS_SERVICE_URL}/embed",
                json={"texts": batch, "task": "retrieval.passage"},
                headers=WEAVIATE_HEADERS,
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

    # Delete existing entity embeddings for this tenant
    async with httpx.AsyncClient(timeout=60) as http:
        del_resp = await http.delete(
            f"{WEAVIATE_SERVICE_URL}/weaviate/entities/delete",
            params={"tenant_id": tenant_id},
            headers=WEAVIATE_HEADERS,
        )
        if del_resp.status_code not in (200, 204, 404):
            logger.warning(
                "  DELETE /entities/delete returned HTTP %d — proceeding with upsert",
                del_resp.status_code,
            )
        else:
            logger.info("  Deleted existing entity embeddings for tenant=%s", tenant_id)

        # Batch upsert entities + embeddings
        upserted = 0
        for batch_start in range(0, len(entities), EMBED_BATCH_SIZE):
            batch_entities = entities[batch_start: batch_start + EMBED_BATCH_SIZE]
            batch_embeddings = all_embeddings[batch_start: batch_start + EMBED_BATCH_SIZE]
            upsert_resp = await http.post(
                f"{WEAVIATE_SERVICE_URL}/weaviate/entities/batch-upsert",
                json={
                    "entities": batch_entities,
                    "embeddings": batch_embeddings,
                    "tenant_id": tenant_id,
                },
                headers=WEAVIATE_HEADERS,
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


# ── Schema bootstrap ───────────────────────────────────────────────────────────

async def _bootstrap_schema(client: FalkorDBClient) -> None:
    """Ensure FalkorDB schema indexes exist (idempotent via client.bootstrap_schema())."""
    await client.bootstrap_schema()


# ── Clear ──────────────────────────────────────────────────────────────────────

async def _clear_tenant(client: FalkorDBClient, tenant_id: str) -> int:
    """Delete all nodes/rels for a tenant. Returns deleted node count."""
    store = TripleStore(client)
    try:
        rows = await client.execute_cypher(
            "MATCH (n) WHERE n.user = $user RETURN count(n) AS cnt",
            {"user": tenant_id},
        )
        count = int(rows[0]["cnt"]) if rows else 0
    except Exception:
        count = 0

    await store.clear_tenant(user=tenant_id)
    return count


# ── Main reindex logic ─────────────────────────────────────────────────────────

async def reindex(
    tenant_id: str,
    collection: str = "default",
    dry_run: bool = False,
    skip_clear: bool = False,
) -> None:
    t_total = time.monotonic()

    print(f"\n{BOLD}TrustGraph Reindexation{RESET}")
    print(f"  tenant_id  : {tenant_id}")
    print(f"  collection : {collection}")
    print(f"  dry_run    : {dry_run}")
    print(f"  skip_clear : {skip_clear}")
    print()

    # ── Step 1: Connect to FalkorDB ────────────────────────────────────────────
    logger.info("Connecting to FalkorDB...")
    falkordb = FalkorDBClient()
    await falkordb.initialize()

    try:
        # ── Step 2: Clear graph for tenant ────────────────────────────────────
        if skip_clear:
            print(f"  {YELLOW}SKIP{RESET}  Clear graph (--skip-clear)")
        elif dry_run:
            print(f"  {YELLOW}DRY-RUN{RESET}  Would clear graph for tenant={tenant_id}")
        else:
            logger.info("Clearing graph for tenant=%s...", tenant_id)
            deleted = await _clear_tenant(falkordb, tenant_id)
            print(f"  {GREEN}OK{RESET}    Cleared graph — {deleted} nodes removed")

        # ── Step 3: Bootstrap schema ───────────────────────────────────────────
        if dry_run:
            print(f"  {YELLOW}DRY-RUN{RESET}  Would bootstrap FalkorDB schema indexes")
        else:
            logger.info("Bootstrapping FalkorDB schema indexes...")
            await _bootstrap_schema(falkordb)
            print(f"  {GREEN}OK{RESET}    Schema indexes verified")

        # ── Step 4: Seed ontology ──────────────────────────────────────────────
        if dry_run:
            print(f"  {YELLOW}DRY-RUN{RESET}  Would seed ontology predicates")
        else:
            logger.info("Seeding ontology predicates (skip-if-exists)...")
            created, skipped, errors = await seed_ontology(dry_run=False, force=False)
            print(
                f"  {GREEN}OK{RESET}    Ontology seeded — "
                f"created={created} skipped={skipped} errors={errors}"
            )
            if errors:
                print(f"  {YELLOW}WARN{RESET}  Ontology had {errors} error(s) — check logs")

        # ── Step 5: Fetch document list from weaviate-service ──────────────────
        logger.info("Fetching document list from weaviate-service...")
        async with httpx.AsyncClient(timeout=60) as http:
            documents = await _fetch_documents(http, tenant_id)

        if not documents:
            print(f"  {YELLOW}WARN{RESET}  No documents found for tenant={tenant_id} — nothing to reindex")
            return

        print(f"\n  Found {BOLD}{len(documents)}{RESET} document(s) to reindex\n")

        if dry_run:
            for i, doc in enumerate(documents[:5], 1):
                doc_id = doc.get("id", "?")
                title = doc.get("title", "")
                print(f"    [{i}] {doc_id}  {title}")
            if len(documents) > 5:
                print(f"    ... and {len(documents) - 5} more")
            print(f"\n  {YELLOW}DRY-RUN{RESET}  Would extract triples for all {len(documents)} documents")
            return

        # ── Step 6: Extract triples for each document ──────────────────────────
        coordinator = ExtractionCoordinator(TripleStore(falkordb))

        success_count = 0
        error_count = 0
        total_triples = 0
        total_contradictions = 0
        total_parse_failures = 0
        total_empty_responses = 0
        total_validation_failures = 0

        async with httpx.AsyncClient(timeout=120) as http:
            for idx, doc in enumerate(documents, 1):
                doc_id = doc.get("id", "")
                title = doc.get("title", "")
                file_path = doc.get("file_path", "")
                semantic_type = doc.get("semantic_type", "")
                domain = doc.get("domain", "")

                if not doc_id:
                    logger.warning("  [%d/%d] Skipping document with no id", idx, len(documents))
                    error_count += 1
                    continue

                logger.info(
                    "  [%d/%d] Fetching chunks for document %s (%s)",
                    idx,
                    len(documents),
                    doc_id,
                    title or "(no title)",
                )

                chunks = await _fetch_chunks(http, tenant_id, doc_id)
                if not chunks:
                    logger.warning(
                        "    [%d/%d] No chunks for document %s — skipping",
                        idx,
                        len(documents),
                        doc_id,
                    )
                    error_count += 1
                    continue

                logger.info(
                    "    Extracting triples from %d chunk(s)...", len(chunks)
                )
                t_doc = time.monotonic()
                try:
                    result = await coordinator.extract_document(
                        chunks=chunks,
                        document_id=doc_id,
                        user=tenant_id,
                        collection=collection,
                        title=title,
                        file_path=file_path,
                        semantic_type=semantic_type,
                        domain=domain,
                    )
                    elapsed_s = time.monotonic() - t_doc
                    triples = result.get("triples_created", 0)
                    contradictions = result.get("contradictions_found", 0)
                    doc_errors = result.get("errors", [])

                    total_triples += triples
                    total_contradictions += contradictions
                    parse_fails = result.get("parse_failures", 0)
                    empty_resps = result.get("empty_responses", 0)
                    validation_fails = result.get("validation_failures", 0)
                    total_parse_failures += parse_fails
                    total_empty_responses += empty_resps
                    total_validation_failures += validation_fails
                    success_count += 1

                    status = f"{GREEN}OK{RESET}" if not doc_errors else f"{YELLOW}WARN{RESET}"
                    print(
                        f"  {status}  [{idx}/{len(documents)}] "
                        f"{doc_id[:8]}…  "
                        f"triples={triples}  contradictions={contradictions}  "
                        f"time={elapsed_s:.1f}s"
                        + (f"  errors={len(doc_errors)}" if doc_errors else "")
                    )
                    if doc_errors:
                        for e in doc_errors[:3]:
                            logger.warning("      %s", e)
                        if len(doc_errors) > 3:
                            logger.warning("      … and %d more", len(doc_errors) - 3)

                except Exception as exc:
                    error_count += 1
                    elapsed_s = time.monotonic() - t_doc
                    print(
                        f"  {RED}ERROR{RESET}  [{idx}/{len(documents)}] "
                        f"{doc_id[:8]}…  {exc}  time={elapsed_s:.1f}s"
                    )
                    logger.exception("    Exception for document %s", doc_id)

        # ── Step 7: Cross-document entity resolution ─────────────────────────
        if not dry_run:
            logger.info("Running cross-document entity resolution...")
            merged_count = await _resolve_duplicate_entities(falkordb, tenant_id, collection)
            if merged_count:
                print(f"  {GREEN}OK{RESET}    Entity resolution — merged {merged_count} duplicate node(s)")
            else:
                print(f"  {GREEN}OK{RESET}    Entity resolution — no duplicates found")

        # ── Step 8: Entity embeddings ─────────────────────────────────────────
        embed_count = 0
        if not dry_run:
            logger.info("── Phase 2: Entity Embeddings ──")
            try:
                embed_count = await _populate_entity_embeddings(tenant_id, collection)
                print(f"  {GREEN}OK{RESET}    Entity embeddings — {embed_count} entities upserted")
                logger.info("Entity embeddings: %d entities", embed_count)
            except Exception as exc:
                print(f"  {YELLOW}WARN{RESET}  Entity embeddings failed: {exc}")
                logger.warning("Entity embeddings phase failed: %s", exc, exc_info=True)

        # ── Summary ────────────────────────────────────────────────────────────
        elapsed_total = time.monotonic() - t_total
        print()
        print(f"{BOLD}── Summary ───────────────────────────────────────────{RESET}")
        print(f"  Documents processed : {success_count + error_count}")
        print(f"  Success             : {GREEN}{success_count}{RESET}")
        print(f"  Errors              : {RED if error_count else ''}{error_count}{RESET}")
        print(f"  Triples created     : {total_triples}")
        print(f"  Contradictions      : {total_contradictions}")
        print(f"  Parse failures    : {total_parse_failures}")
        print(f"  Empty responses   : {total_empty_responses}")
        print(f"  Validation fails  : {total_validation_failures}")
        print(f"  Merged duplicates   : {merged_count if not dry_run else 'N/A'}")
        print(f"  Entity embeddings   : {embed_count if not dry_run else 'N/A'}")
        print(f"  Total time          : {elapsed_total:.1f}s")
        print()

        if error_count:
            sys.exit(1)

    finally:
        # Close shared HTTP client used by extractors
        from app.services.extractors.base import BaseExtractor
        await BaseExtractor.close_shared_client()
        await falkordb.close()


# ── CLI ────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reindex TrustGraph for a tenant",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full reindex (clear + ontology + extract all docs)
  python scripts/reindex_trustgraph.py --tenant-id 00000000-0000-0000-0000-000000000001

  # Preview — show what would be done without touching the graph
  python scripts/reindex_trustgraph.py --tenant-id TENANT_ID --dry-run

  # Re-extract without clearing existing triples
  python scripts/reindex_trustgraph.py --tenant-id TENANT_ID --skip-clear

  # Use a custom collection scope
  python scripts/reindex_trustgraph.py --tenant-id TENANT_ID --collection legal
""",
    )
    parser.add_argument(
        "--tenant-id",
        required=True,
        help="Tenant UUID to reindex",
    )
    parser.add_argument(
        "--collection",
        default="default",
        help="Collection scope for triples (default: 'default')",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview actions without modifying the graph",
    )
    parser.add_argument(
        "--skip-clear",
        action="store_true",
        help="Skip the graph clear step (append-only re-extraction)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable DEBUG-level logging",
    )
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    asyncio.run(
        reindex(
            tenant_id=args.tenant_id,
            collection=args.collection,
            dry_run=args.dry_run,
            skip_clear=args.skip_clear,
        )
    )


if __name__ == "__main__":
    main()
