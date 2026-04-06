#!/usr/bin/env python3
"""
Cleanup blacklisted entities from the TrustGraph.

Scans all :Node entities, checks against entity_blacklist.yaml,
and removes blacklisted nodes along with their relationships.

DRY RUN by default — use --apply to execute changes.

Usage:
    docker compose exec knowledge-tree-service python scripts/cleanup_blacklisted_entities.py
    docker compose exec knowledge-tree-service python scripts/cleanup_blacklisted_entities.py --apply
    docker compose exec knowledge-tree-service python scripts/cleanup_blacklisted_entities.py --tenant-id UUID
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.entity_blacklist import EntityBlacklist
from app.services.falkordb_client import FalkorDBClient

logging.basicConfig(level=logging.WARNING)

GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"


async def cleanup(tenant_id: str | None, apply: bool) -> dict:
    client = FalkorDBClient()
    await client.initialize()
    blacklist = EntityBlacklist()

    stats = {"scanned": 0, "blacklisted": 0, "rels_removed": 0, "nodes_removed": 0}

    try:
        user_filter = f"AND n.user = '{tenant_id}'" if tenant_id else ""
        query = (
            f"MATCH (n:Node) WHERE n.uri STARTS WITH 'nouxcube://entity/' {user_filter} "
            "RETURN n.uri AS uri"
        )
        rows = await client.execute_cypher(query)
        stats["scanned"] = len(rows)

        blacklisted_uris = []
        for row in rows:
            uri = row.get("uri", "")
            parts = uri.split("/")
            if len(parts) >= 5:
                name = parts[-1].replace("-", " ")
                if blacklist.is_blacklisted(name):
                    blacklisted_uris.append(uri)

        stats["blacklisted"] = len(blacklisted_uris)
        print(f"\n  Scanned {stats['scanned']} entity nodes")
        print(f"  Found {stats['blacklisted']} blacklisted entities\n")

        for uri in blacklisted_uris:
            count_q = "MATCH (n:Node {uri: $uri})-[r:Rel]-() RETURN count(r) AS cnt"
            cnt_rows = await client.execute_cypher(count_q, params={"uri": uri})
            rel_count = cnt_rows[0]["cnt"] if cnt_rows else 0
            stats["rels_removed"] += rel_count

            if apply:
                del_q = "MATCH (n:Node {uri: $uri}) DETACH DELETE n"
                await client.execute_cypher(del_q, params={"uri": uri})
                stats["nodes_removed"] += 1
                print(f"  {RED}DELETED{RESET}  {uri}  ({rel_count} rels)")
            else:
                print(f"  {YELLOW}WOULD DELETE{RESET}  {uri}  ({rel_count} rels)")

    finally:
        await client.close()

    return stats


def main():
    parser = argparse.ArgumentParser(description="Cleanup blacklisted entities from TrustGraph")
    parser.add_argument("--apply", action="store_true", help="Actually delete (default is dry-run)")
    parser.add_argument("--tenant-id", type=str, default=None, help="Filter by tenant ID")
    args = parser.parse_args()

    mode = "APPLY" if args.apply else "DRY RUN"
    print(f"{'=' * 60}")
    print(f"Blacklisted Entity Cleanup — {mode}")
    print(f"{'=' * 60}")

    stats = asyncio.run(cleanup(args.tenant_id, args.apply))

    print(f"\n{'=' * 60}")
    print(f"Scanned: {stats['scanned']}, Blacklisted: {stats['blacklisted']}")
    print(f"Relationships affected: {stats['rels_removed']}")
    if args.apply:
        print(f"Nodes deleted: {stats['nodes_removed']}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
