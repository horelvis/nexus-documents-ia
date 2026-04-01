#!/usr/bin/env python3
"""
Seed authority weight triples into FalkorDB.

Creates :Node entities for each document semantic_type and links them
to a :Literal authority weight via trust/authority-weight predicate.

These triples are queried by graph_rag to weight edges by source quality.
Zero hardcode — all weights live in the graph.

Usage:
    docker compose exec knowledge-tree-service python scripts/seed_authority_weights.py
    docker compose exec knowledge-tree-service python scripts/seed_authority_weights.py --force
    docker compose exec knowledge-tree-service python scripts/seed_authority_weights.py --dry-run
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.falkordb_client import FalkorDBClient
from app.services.triple_store import TripleStore
from app.services.uri_builder import URIBuilder

logging.basicConfig(level=logging.WARNING)

GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"

AUTHORITY_USER = "_system"
AUTHORITY_COLLECTION = "_authority"

# (semantic_type_slug, authority_weight, description)
AUTHORITY_WEIGHTS = [
    ("escritura-publica",  "0.95", "Notarized document"),
    ("contrato",           "0.90", "Signed agreement"),
    ("sentencia",          "0.95", "Court ruling"),
    ("legislacion",        "1.00", "Standing law"),
    ("factura",            "0.85", "Fiscal document"),
    ("nomina",             "0.85", "Payroll document"),
    ("informe",            "0.70", "Internal analysis"),
    ("acta",               "0.80", "Official minutes"),
    ("certificado",        "0.85", "Official certificate"),
    ("resolucion",         "0.90", "Administrative resolution"),
    ("email",              "0.40", "Informal communication"),
    ("nota",               "0.30", "Internal note"),
    ("borrador",           "0.25", "Draft document"),
    ("desconocido",        "0.50", "Unknown document type"),
]


async def seed_authority_weights(dry_run: bool = False, force: bool = False) -> tuple:
    """Seed authority weight triples. Returns (created, skipped, errors)."""
    client = FalkorDBClient()
    await client.initialize()
    store = TripleStore(client)

    created = 0
    skipped = 0
    errors = 0

    try:
        if force and not dry_run:
            await client.execute_cypher(
                "MATCH (n) WHERE (n:Node OR n:Literal) "
                "AND n.user = $user AND n.collection = $collection "
                "DETACH DELETE n",
                params={"user": AUTHORITY_USER, "collection": AUTHORITY_COLLECTION},
            )
            print(f"  {YELLOW}Cleared existing authority weights{RESET}")

        existing = set()
        if not force:
            rows = await client.execute_cypher(
                "MATCH (n:Node {user: $user, collection: $collection}) "
                "RETURN n.uri AS uri",
                params={"user": AUTHORITY_USER, "collection": AUTHORITY_COLLECTION},
            )
            existing = {r["uri"] for r in rows if r.get("uri")}

        for slug, weight, description in AUTHORITY_WEIGHTS:
            entity_uri = f"nouxcube://entity/_system/{slug}"

            if not force and entity_uri in existing:
                print(f"  {YELLOW}SKIP{RESET}  {slug} — already exists")
                skipped += 1
                continue

            if dry_run:
                print(f"  WOULD CREATE  {slug}  authority={weight}")
                created += 1
                continue

            try:
                await store.merge_node(entity_uri, AUTHORITY_USER, AUTHORITY_COLLECTION)

                await store.merge_literal(slug, AUTHORITY_USER, AUTHORITY_COLLECTION)
                await store.create_rel(
                    subject_uri=entity_uri,
                    predicate_uri=URIBuilder.predicate("core", "label"),
                    object_value=slug,
                    user=AUTHORITY_USER,
                    collection=AUTHORITY_COLLECTION,
                    object_is_node=False,
                    extraction_method="seed",
                )

                await store.merge_literal(weight, AUTHORITY_USER, AUTHORITY_COLLECTION)
                await store.create_rel(
                    subject_uri=entity_uri,
                    predicate_uri=URIBuilder.predicate("trust", "authority-weight"),
                    object_value=weight,
                    user=AUTHORITY_USER,
                    collection=AUTHORITY_COLLECTION,
                    object_is_node=False,
                    extraction_method="seed",
                )

                print(f"  {GREEN}OK{RESET}  {slug}  authority={weight}  ({description})")
                created += 1
            except Exception as exc:
                print(f"  {RED}ERROR{RESET}  {slug}: {exc}")
                errors += 1

    finally:
        await client.close()

    return created, skipped, errors


def main():
    parser = argparse.ArgumentParser(description="Seed authority weight triples")
    parser.add_argument("--force", action="store_true", help="Clear and reseed")
    parser.add_argument("--dry-run", action="store_true", help="Preview only")
    args = parser.parse_args()

    print("=" * 60)
    print(f"Authority Weight Seed — {len(AUTHORITY_WEIGHTS)} document types")
    print("=" * 60)

    created, skipped, errors = asyncio.run(
        seed_authority_weights(dry_run=args.dry_run, force=args.force)
    )

    print(f"\nResults: {created} created, {skipped} skipped, {errors} errors")
    if errors > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
