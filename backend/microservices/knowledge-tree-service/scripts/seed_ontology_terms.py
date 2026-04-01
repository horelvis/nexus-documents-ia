#!/usr/bin/env python3
"""
Seed OntologyTerms Weaviate collection with vectorized predicate definitions.

For each predicate in seed_ontology.PREDICATES (excluding prov/*),
generates an embedding via intelligence-docs-service and inserts into
the OntologyTerms collection via weaviate-service API.

Usage:
    docker compose exec knowledge-tree-service python scripts/seed_ontology_terms.py
    docker compose exec knowledge-tree-service python scripts/seed_ontology_terms.py --dry-run
"""

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.seed_ontology import PREDICATES

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"

SKIP_NAMESPACES = {"prov"}

WEAVIATE_SERVICE_URL = os.environ.get("WEAVIATE_SERVICE_URL", "http://weaviate-service:8007")
INTELLIGENCE_DOCS_URL = os.environ.get("INTELLIGENCE_DOCS_URL", "http://intelligence-docs-service:8012")
API_KEY = os.environ.get("MICROSERVICES_API_KEY", "")


async def _embed_text(client: httpx.AsyncClient, text: str) -> list[float] | None:
    """Generate embedding via intelligence-docs-service."""
    resp = await client.post(
        f"{INTELLIGENCE_DOCS_URL}/embed",
        json={"text": text, "task": "retrieval.passage"},
    )
    if resp.status_code == 200:
        data = resp.json()
        return data.get("embedding") or data.get("embeddings", [None])[0]
    return None


async def seed_ontology_terms(dry_run: bool = False) -> tuple:
    """Seed OntologyTerms. Returns (created, skipped, errors)."""
    extractable = [p for p in PREDICATES if p[0] not in SKIP_NAMESPACES]
    print(f"  {len(extractable)} extractable predicates (excluded: {SKIP_NAMESPACES})")

    created = 0
    skipped = 0
    errors = 0

    headers = {"X-API-Key": API_KEY} if API_KEY else {}

    async with httpx.AsyncClient(timeout=30.0, headers=headers) as client:
        if not dry_run:
            # Ensure collection exists
            resp = await client.post(f"{WEAVIATE_SERVICE_URL}/trustgraph/ensure-ontology-terms")
            if resp.status_code != 200:
                print(f"  {RED}Failed to ensure OntologyTerms collection: {resp.text}{RESET}")
                return 0, 0, 1

        for sector, name, description, domain_type, range_type in extractable:
            label = f"{sector}/{name}"
            embed_text = f"{name}: {description}"

            if dry_run:
                print(f"  WOULD SEED  {label}")
                created += 1
                continue

            try:
                embedding = await _embed_text(client, embed_text)
                if not embedding:
                    print(f"  {RED}EMBED FAIL{RESET}  {label}")
                    errors += 1
                    continue

                resp = await client.post(
                    f"{WEAVIATE_SERVICE_URL}/trustgraph/ontology-terms",
                    json={
                        "predicate_name": name,
                        "namespace": sector,
                        "description": description,
                        "domain_type": domain_type,
                        "range_type": range_type,
                        "embed_text": embed_text,
                        "embedding": embedding,
                    },
                )
                if resp.status_code in (200, 201):
                    print(f"  {GREEN}OK{RESET}  {label}  ({len(embedding)} dims)")
                    created += 1
                else:
                    print(f"  {RED}UPSERT FAIL{RESET}  {label}: {resp.text}")
                    errors += 1
            except Exception as exc:
                print(f"  {RED}ERROR{RESET}  {label}: {exc}")
                errors += 1

    return created, skipped, errors


def main():
    parser = argparse.ArgumentParser(description="Seed OntologyTerms Weaviate collection")
    parser.add_argument("--dry-run", action="store_true", help="Preview without changes")
    args = parser.parse_args()

    print("=" * 60)
    print("OntologyTerms Weaviate seed")
    print("=" * 60)

    created, skipped, errors = asyncio.run(seed_ontology_terms(dry_run=args.dry_run))

    print(f"\nResults: {created} created, {skipped} skipped, {errors} errors")
    if errors > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
