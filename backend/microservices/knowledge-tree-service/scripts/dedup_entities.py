#!/usr/bin/env python3
"""
Entity deduplication for TrustGraph.

Finds duplicate entities by applying canonical name resolution
(honorific/suffix stripping) and groups them. Optionally merges
duplicates by re-pointing relationships and creating same-as edges.

DRY RUN by default — use --apply to execute merges.

Usage:
    docker compose exec knowledge-tree-service python scripts/dedup_entities.py
    docker compose exec knowledge-tree-service python scripts/dedup_entities.py --apply
"""

import argparse
import asyncio
import json
import logging
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.falkordb_client import FalkorDBClient
from app.services.uri_builder import URIBuilder

logging.basicConfig(level=logging.WARNING)

GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"


async def find_duplicates(client: FalkorDBClient) -> list:
    """Find entity nodes that resolve to the same canonical name."""
    query = (
        "MATCH (n:Node) WHERE n.uri STARTS WITH 'nouxcube://entity/' "
        "RETURN n.uri AS uri, n.created_at AS created_at"
    )
    rows = await client.execute_cypher(query)

    groups: dict[str, list] = defaultdict(list)
    for row in rows:
        uri = row.get("uri", "")
        parts = uri.split("/")
        if len(parts) < 5:
            continue
        raw_name = parts[-1].replace("-", " ")
        canonical = URIBuilder.normalize_name(raw_name)
        if canonical:
            groups[canonical].append({
                "uri": uri,
                "created_at": row.get("created_at"),
            })

    return [
        {"canonical": name, "entities": entities}
        for name, entities in groups.items()
        if len(entities) > 1
    ]


async def merge_group(
    client: FalkorDBClient,
    group: dict,
    user: str,
    collection: str,
) -> dict:
    """Merge a duplicate group: keep canonical, re-point relationships."""
    entities = group["entities"]
    canonical = sorted(entities, key=lambda e: e.get("created_at") or "")[0]
    canonical_uri = canonical["uri"]
    duplicates = [e for e in entities if e["uri"] != canonical_uri]

    stats = {"rels_repointed": 0, "same_as_created": 0}

    for dup in duplicates:
        dup_uri = dup["uri"]

        # Re-point outgoing relationships
        await client.execute_cypher(
            "MATCH (old:Node {uri: $old_uri})-[r:Rel]->(o) "
            "MATCH (new:Node {uri: $new_uri}) "
            "CREATE (new)-[r2:Rel]->(o) "
            "SET r2 = properties(r) "
            "DELETE r",
            params={"old_uri": dup_uri, "new_uri": canonical_uri},
        )
        # Re-point incoming relationships
        await client.execute_cypher(
            "MATCH (s)-[r:Rel]->(old:Node {uri: $old_uri}) "
            "MATCH (new:Node {uri: $new_uri}) "
            "CREATE (s)-[r2:Rel]->(new) "
            "SET r2 = properties(r) "
            "DELETE r",
            params={"old_uri": dup_uri, "new_uri": canonical_uri},
        )
        # Create same-as audit edge
        await client.execute_cypher(
            "MATCH (canon:Node {uri: $canon}), (dup:Node {uri: $dup}) "
            "MERGE (canon)-[:Rel {uri: 'nouxcube://predicate/core/same-as', "
            "user: $user, collection: $collection, extraction_method: 'dedup_script'}]->(dup) "
            "SET dup.merged = true",
            params={"canon": canonical_uri, "dup": dup_uri, "user": user, "collection": collection},
        )
        stats["same_as_created"] += 1

    return stats


async def run(apply: bool, output_json: str | None) -> dict:
    client = FalkorDBClient()
    await client.initialize()

    try:
        groups = await find_duplicates(client)
        print(f"\n  Found {len(groups)} duplicate groups\n")

        total_stats = {"groups": len(groups), "merged": 0}

        for group in groups:
            canonical = group["canonical"]
            entities = group["entities"]

            if apply:
                await merge_group(
                    client, group,
                    user="EVERYONE",
                    collection="default",
                )
                total_stats["merged"] += 1
                print(f"  {GREEN}MERGED{RESET}  {canonical}  ({len(entities)} -> 1)")
            else:
                print(f"  {YELLOW}WOULD MERGE{RESET}  {canonical}  ({len(entities)} entities)")
                for e in entities:
                    print(f"    - {e['uri']}")

        if output_json:
            with open(output_json, "w") as f:
                json.dump(groups, f, indent=2, default=str)
            print(f"\n  Wrote {len(groups)} groups to {output_json}")

        return total_stats

    finally:
        await client.close()


def main():
    parser = argparse.ArgumentParser(description="Entity deduplication for TrustGraph")
    parser.add_argument("--apply", action="store_true", help="Execute merges (default is dry-run)")
    parser.add_argument("--output", type=str, default=None, help="Write duplicate groups to JSON file")
    args = parser.parse_args()

    mode = "APPLY" if args.apply else "DRY RUN"
    print(f"{'=' * 60}")
    print(f"Entity Deduplication — {mode}")
    print(f"{'=' * 60}")

    stats = asyncio.run(run(args.apply, args.output))

    print(f"\n{'=' * 60}")
    print(f"Groups: {stats['groups']}, Merged: {stats['merged']}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
