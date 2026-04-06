#!/usr/bin/env python3
"""
Predicate promotion pipeline for TrustGraph.

Analyzes predicates in the 'extracted/' namespace, groups by frequency
and confidence, and identifies candidates for promotion to the official
ontology or merging with existing predicates.

DRY RUN by default — outputs analysis only.

Usage:
    docker compose exec knowledge-tree-service python scripts/promote_predicates.py
    docker compose exec knowledge-tree-service python scripts/promote_predicates.py --min-freq 5 --min-confidence 0.65
"""

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.falkordb_client import FalkorDBClient

logging.basicConfig(level=logging.WARNING)

GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"


async def analyze_extracted_predicates(
    client: FalkorDBClient,
    min_freq: int,
    min_confidence: float,
) -> list:
    """Find extracted/ predicates with their frequency and avg confidence."""
    query = (
        "MATCH ()-[r:Rel]->() "
        "WHERE r.uri STARTS WITH 'nouxcube://predicate/extracted/' "
        "RETURN r.uri AS predicate_uri, "
        "count(r) AS frequency, "
        "avg(r.confidence) AS avg_confidence "
        "ORDER BY frequency DESC"
    )
    rows = await client.execute_cypher(query)

    candidates = []
    for row in rows:
        uri = row.get("predicate_uri", "")
        freq = row.get("frequency", 0)
        avg_conf = row.get("avg_confidence", 0.0)

        parts = uri.split("/")
        name = parts[-1] if parts else uri

        candidates.append({
            "uri": uri,
            "name": name,
            "frequency": freq,
            "avg_confidence": round(avg_conf, 3) if avg_conf else 0.0,
            "qualifies": freq >= min_freq and (avg_conf or 0) >= min_confidence,
        })

    return candidates


async def run(min_freq: int, min_confidence: float, output_json: str | None) -> None:
    client = FalkorDBClient()
    await client.initialize()

    try:
        candidates = await analyze_extracted_predicates(client, min_freq, min_confidence)

        qualified = [c for c in candidates if c["qualifies"]]
        unqualified = [c for c in candidates if not c["qualifies"]]

        print(f"\n  Total extracted/ predicates: {len(candidates)}")
        print(f"  Qualify for promotion (freq>={min_freq}, conf>={min_confidence}): {len(qualified)}")
        print(f"  Below threshold: {len(unqualified)}\n")

        if qualified:
            print(f"  {BOLD}=== PROMOTION CANDIDATES ==={RESET}\n")
            for c in qualified:
                print(f"  {GREEN}PROMOTE{RESET}  {c['name']:<30}  freq={c['frequency']:<4}  conf={c['avg_confidence']}")

        if unqualified:
            print(f"\n  {BOLD}=== BELOW THRESHOLD ==={RESET}\n")
            for c in unqualified[:20]:
                print(f"  {YELLOW}KEEP{RESET}    {c['name']:<30}  freq={c['frequency']:<4}  conf={c['avg_confidence']}")
            if len(unqualified) > 20:
                print(f"  ... and {len(unqualified) - 20} more")

        if output_json:
            with open(output_json, "w") as f:
                json.dump({"qualified": qualified, "unqualified": unqualified}, f, indent=2)
            print(f"\n  Wrote analysis to {output_json}")

    finally:
        await client.close()


def main():
    parser = argparse.ArgumentParser(description="Analyze extracted predicates for promotion")
    parser.add_argument("--min-freq", type=int, default=3, help="Minimum frequency (default: 3)")
    parser.add_argument("--min-confidence", type=float, default=0.65, help="Minimum avg confidence (default: 0.65)")
    parser.add_argument("--output", type=str, default=None, help="Write results to JSON")
    args = parser.parse_args()

    print(f"{'=' * 60}")
    print(f"Predicate Promotion Analysis")
    print(f"  min_freq={args.min_freq}  min_confidence={args.min_confidence}")
    print(f"{'=' * 60}")

    asyncio.run(run(args.min_freq, args.min_confidence, args.output))


if __name__ == "__main__":
    main()
