#!/usr/bin/env python3
"""
Reindex TrustGraph (all data).

Clears the FalkorDB graph, bootstraps the schema + ontology, fetches all
documents from weaviate-service, and runs
ExtractionCoordinator.extract_document() for each document.

After the multi-tenancy removal refactor, the graph holds a single scope
so there is no per-tenant iteration.

Usage:
    docker compose exec knowledge-tree-service \
        python scripts/reindex_trustgraph.py

    docker compose exec knowledge-tree-service \
        python scripts/reindex_trustgraph.py --dry-run

    docker compose exec knowledge-tree-service \
        python scripts/reindex_trustgraph.py --collection legal

    docker compose exec knowledge-tree-service \
        python scripts/reindex_trustgraph.py --skip-clear

Environment:
    WEAVIATE_SERVICE_URL          Base URL for weaviate-service (default: http://weaviate-service:8000)
    INTELLIGENCE_DOCS_SERVICE_URL Base URL for intelligence-docs-service (default: http://intelligence-docs-service:8000)
    MICROSERVICES_API_KEY         API key for service-to-service auth

The entity-embedding step is delegated to app.services.entity_embedding.
"""

import argparse
import asyncio
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

# Allow imports from app when running inside the container
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.auth_headers import EVERYONE_ROLE
from app.core.config import settings
from app.services.falkordb_client import FalkorDBClient
from app.services.triple_store import TripleStore
from app.services.extractors.coordinator import ExtractionCoordinator
from app.services.entity_embedding import populate_entity_embeddings

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
MICROSERVICES_API_KEY = settings.MICROSERVICES_API_KEY

WEAVIATE_HEADERS = {
    "X-API-Key": MICROSERVICES_API_KEY,
    "Content-Type": "application/json",
}


async def _fetch_documents(
    client: httpx.AsyncClient,
) -> List[Dict[str, Any]]:
    """Fetch all indexed documents from weaviate-service.

    After multi-tenancy removal there is a single unified document collection
    and the list endpoint returns all documents without a scope parameter.

    Returns a list of document dicts with at least "id" and optional
    "title", "file_path", "semantic_type", "domain" keys.
    """
    PAGE_SIZE = 100  # weaviate-service max limit

    url = f"{WEAVIATE_SERVICE_URL}/weaviate/documents"
    params = {"limit": PAGE_SIZE}
    resp = await client.get(url, params=params, headers=WEAVIATE_HEADERS)

    if resp.status_code == 200:
        data = resp.json()
        docs = data if isinstance(data, list) else data.get("documents", data.get("results", []))
        logger.info("  Fetched %d documents via /weaviate/documents list endpoint", len(docs))
        return docs

    raise RuntimeError(
        f"Could not list documents: /weaviate/documents returned HTTP "
        f"{resp.status_code} — {resp.text[:300]}"
    )


async def _fetch_chunks(
    client: httpx.AsyncClient,
    document_id: str,
    limit: int = 500,
) -> List[str]:
    """Fetch text chunks for a document from weaviate-service.

    GET /weaviate/documents/{document_id}/chunks?limit=500
    Returns list of chunk text strings (ordered).
    """
    url = f"{WEAVIATE_SERVICE_URL}/weaviate/documents/{document_id}/chunks"
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
    scope: str,
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
    # Fetch all entity node URIs for this scope+collection
    rows = await client.execute_cypher(
        "MATCH (n:Node {user: $user, collection: $collection}) "
        "WHERE n.uri STARTS WITH 'nouxcube://entity/' "
        "RETURN n.uri AS uri",
        {"user": scope, "collection": collection},
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
                     "user": scope, "col": collection},
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
                     "user": scope, "col": collection},
                )
                # Delete the orphaned duplicate node
                await client.execute_cypher(
                    "MATCH (n:Node {uri: $uri, user: $user, collection: $col}) "
                    "WHERE NOT (n)-[:Rel]-() AND NOT ()-[:Rel]->(n) "
                    "DELETE n",
                    {"uri": dup_uri, "user": scope, "col": collection},
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


# ── Schema bootstrap ───────────────────────────────────────────────────────────

async def _bootstrap_schema(client: FalkorDBClient) -> None:
    """Ensure FalkorDB schema indexes exist (idempotent via client.bootstrap_schema())."""
    await client.bootstrap_schema()


# ── Clear ──────────────────────────────────────────────────────────────────────

async def _clear_graph(client: FalkorDBClient, scope: str) -> int:
    """Delete all nodes/rels for the given scope. Returns deleted node count."""
    store = TripleStore(client)
    try:
        rows = await client.execute_cypher(
            "MATCH (n) WHERE n.user = $user RETURN count(n) AS cnt",
            {"user": scope},
        )
        count = int(rows[0]["cnt"]) if rows else 0
    except Exception:
        count = 0

    await store.clear_tenant(user=scope)
    return count


# ── Main reindex logic ─────────────────────────────────────────────────────────

async def reindex(
    collection: str = "default",
    dry_run: bool = False,
    skip_clear: bool = False,
) -> None:
    t_total = time.monotonic()

    scope = EVERYONE_ROLE

    print(f"\n{BOLD}TrustGraph Reindexation{RESET}")
    print(f"  scope      : {scope}")
    print(f"  collection : {collection}")
    print(f"  dry_run    : {dry_run}")
    print(f"  skip_clear : {skip_clear}")
    print()

    # ── Step 1: Connect to FalkorDB ────────────────────────────────────────────
    logger.info("Connecting to FalkorDB...")
    falkordb = FalkorDBClient()
    await falkordb.initialize()

    try:
        # ── Step 2: Clear graph ───────────────────────────────────────────────
        if skip_clear:
            print(f"  {YELLOW}SKIP{RESET}  Clear graph (--skip-clear)")
        elif dry_run:
            print(f"  {YELLOW}DRY-RUN{RESET}  Would clear graph for scope={scope}")
        else:
            logger.info("Clearing graph for scope=%s...", scope)
            deleted = await _clear_graph(falkordb, scope)
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
            documents = await _fetch_documents(http)

        if not documents:
            print(f"  {YELLOW}WARN{RESET}  No documents found — nothing to reindex")
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

                chunks = await _fetch_chunks(http, doc_id)
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
                        user=scope,
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
            merged_count = await _resolve_duplicate_entities(falkordb, scope, collection)
            if merged_count:
                print(f"  {GREEN}OK{RESET}    Entity resolution — merged {merged_count} duplicate node(s)")
            else:
                print(f"  {GREEN}OK{RESET}    Entity resolution — no duplicates found")

        # ── Step 8: Entity embeddings ─────────────────────────────────────────
        embed_count = 0
        if not dry_run:
            logger.info("── Phase 2: Entity Embeddings ──")
            try:
                embed_count = await populate_entity_embeddings(scope, collection)
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
        description="Reindex TrustGraph (all data)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full reindex (clear + ontology + extract all docs)
  python scripts/reindex_trustgraph.py

  # Preview — show what would be done without touching the graph
  python scripts/reindex_trustgraph.py --dry-run

  # Re-extract without clearing existing triples
  python scripts/reindex_trustgraph.py --skip-clear

  # Use a custom collection scope
  python scripts/reindex_trustgraph.py --collection legal
""",
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
            collection=args.collection,
            dry_run=args.dry_run,
            skip_clear=args.skip_clear,
        )
    )


if __name__ == "__main__":
    main()
