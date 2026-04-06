#!/usr/bin/env python3
"""
Deduplicate :Literal nodes for definition/label predicates in TrustGraph.

For each :Node that has multiple definition or label Literals, keeps only
the shortest one (cleanest) and deletes the rest along with their :Rel edges.

Usage:
    docker compose exec knowledge-tree-service \
        python scripts/dedup_literals.py

    docker compose exec knowledge-tree-service \
        python scripts/dedup_literals.py --dry-run

    docker compose exec knowledge-tree-service \
        python scripts/dedup_literals.py --tenant-id TENANT_ID
"""

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.falkordb_client import FalkorDBClient

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

# Predicates to deduplicate (one value per subject)
UNIQUE_PREDICATES = [
    "nouxcube://predicate/core/definition",
    "nouxcube://predicate/core/label",
]


async def find_duplicates(client: FalkorDBClient, predicate: str, user: str | None):
    """Find subjects with multiple Literals for the given predicate."""
    user_filter = "AND r.user = $user" if user else ""
    params = {"p_uri": predicate}
    if user:
        params["user"] = user

    query = (
        "MATCH (s:Node)-[r:Rel {uri: $p_uri}]->(lit:Literal) "
        f"WHERE true {user_filter} "
        "WITH s, collect(lit) AS lits, collect(r) AS rels "
        "WHERE size(lits) > 1 "
        "RETURN s.uri AS subject, "
        "[l IN lits | l.value] AS values, "
        "size(lits) AS count"
    )
    results = await client.execute_cypher(query, params)
    return results


async def delete_duplicate_literals(
    client: FalkorDBClient, predicate: str, user: str | None, dry_run: bool
):
    """For each subject with duplicates, keep shortest value, delete rest."""
    user_filter = "AND r.user = $user" if user else ""
    params = {"p_uri": predicate}
    if user:
        params["user"] = user

    # Find all subjects with >1 literal for this predicate
    duplicates = await find_duplicates(client, predicate, user)
    if not duplicates:
        logger.info("  No duplicates found for %s", predicate)
        return 0

    total_removed = 0
    for row in duplicates:
        subject = row[0]
        values = row[1]
        count = row[2]

        # Keep the shortest value (tends to be the cleanest)
        keep = min(values, key=len)
        remove = [v for v in values if v != keep]

        logger.info(
            "  %s: %d literals → keep %r, remove %d",
            subject, count, keep[:80], len(remove),
        )

        if dry_run:
            for v in remove:
                logger.info("    [DRY-RUN] would remove: %r", v[:100])
            total_removed += len(remove)
            continue

        # Delete the duplicate Rel edges and orphaned Literal nodes
        for val in remove:
            del_params = {"s_uri": subject, "p_uri": predicate, "val": val}
            if user:
                del_params["user"] = user
            user_filter_del = "AND r.user = $user" if user else ""

            # Delete the Rel edge
            await client.execute_cypher(
                "MATCH (s:Node {uri: $s_uri})-[r:Rel {uri: $p_uri}]->(lit:Literal {value: $val}) "
                f"WHERE true {user_filter_del} "
                "DELETE r",
                del_params,
            )

            # Delete orphaned Literal (no remaining incoming edges)
            await client.execute_cypher(
                "MATCH (lit:Literal {value: $val}) "
                "WHERE NOT EXISTS(()-[:Rel]->(lit)) "
                "DELETE lit",
                {"val": val},
            )
            total_removed += 1

    return total_removed


async def main():
    parser = argparse.ArgumentParser(description="Deduplicate TrustGraph definition/label Literals")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be deleted without deleting")
    parser.add_argument("--tenant-id", help="Filter by tenant/user ID (default: all tenants)")
    args = parser.parse_args()

    client = FalkorDBClient()
    await client.initialize()

    try:
        total = 0
        for pred in UNIQUE_PREDICATES:
            pred_name = pred.split("/")[-1]
            logger.info("Processing predicate: %s", pred_name)
            removed = await delete_duplicate_literals(client, pred, args.tenant_id, args.dry_run)
            total += removed
            logger.info("  %s: removed %d duplicates", pred_name, removed)

        action = "would remove" if args.dry_run else "removed"
        logger.info("Done — %s %d duplicate Literals total", action, total)
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
