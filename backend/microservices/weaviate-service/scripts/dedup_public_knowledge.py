#!/usr/bin/env python3
"""
Remove duplicate Public Knowledge documents (same boe_id + version).

When the BOE downloader ran multiple times, the same law was ingested 2+ times,
creating duplicate parents and chunks. This script keeps one copy per
(boe_id, version_number) and deletes the rest.

It does NOT delete different versions of the same law — those are kept intact.

Usage:
    python scripts/dedup_public_knowledge.py [--weaviate-url URL] [--dry-run]
"""
import argparse
import httpx
from collections import defaultdict

DEFAULT_URL = "http://localhost:8007"


def get_api_key():
    import os
    return os.getenv("MICROSERVICES_API_KEY", "")


def main():
    parser = argparse.ArgumentParser(description="Deduplicate PublicKnowledge by boe_id+version")
    parser.add_argument("--weaviate-url", default=DEFAULT_URL)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    base_url = args.weaviate_url.rstrip("/")
    api_key = get_api_key()
    headers = {"X-API-Key": api_key} if api_key else {}

    print(f"Connecting to {base_url}...")

    # Fetch all docs (high limit keyword search)
    resp = httpx.post(
        f"{base_url}/public-knowledge/search",
        json={
            "query": "ley decreto legislación artículo real",
            "limit": 1000,
            "search_type": "keyword",
            "current_version_only": False,
        },
        headers=headers,
        timeout=120.0,
    )
    resp.raise_for_status()
    all_docs = resp.json().get("results", [])
    print(f"Fetched {len(all_docs)} objects")

    # Separate parents from chunks
    parents = [d for d in all_docs if not d.get("parent_document_id")]
    chunks = [d for d in all_docs if d.get("parent_document_id")]

    print(f"  Parents: {len(parents)}  |  Chunks: {len(chunks)}")

    # Group parents by (boe_id, version_number)
    groups = defaultdict(list)
    for p in parents:
        boe_id = p.get("boe_id", "")
        version = p.get("version_number", 1)
        if boe_id:
            groups[(boe_id, version)].append(p)

    # Find groups with duplicates
    dupes = {k: v for k, v in groups.items() if len(v) > 1}
    print(f"\nFound {len(dupes)} boe_id+version groups with duplicates:")

    total_to_delete = 0
    delete_ids = []

    for (boe_id, version), parent_list in sorted(dupes.items()):
        keep = parent_list[0]
        remove = parent_list[1:]
        remove_parent_ids = {p["id"] for p in remove}

        # Find chunks belonging to duplicate parents
        dup_chunks = [c for c in chunks if c.get("parent_document_id") in remove_parent_ids]

        ids_to_remove = [p["id"] for p in remove] + [c["id"] for c in dup_chunks]
        delete_ids.extend(ids_to_remove)
        total_to_delete += len(ids_to_remove)

        title = keep.get("title", "?")[:60]
        print(f"  {boe_id} v{version}: {len(parent_list)} copies → keep 1, "
              f"delete {len(remove)} parents + {len(dup_chunks)} chunks = {len(ids_to_remove)} objects")
        print(f"    {title}")

    if not delete_ids:
        print("\nNo duplicates found. Nothing to do.")
        return

    print(f"\nTotal objects to delete: {total_to_delete}")

    if args.dry_run:
        print("DRY RUN — no changes made.")
        return

    # Delete
    success = 0
    failed = 0
    for uid in delete_ids:
        try:
            r = httpx.delete(
                f"{base_url}/public-knowledge/documents/{uid}",
                headers=headers,
                timeout=30.0,
            )
            r.raise_for_status()
            success += 1
        except Exception as e:
            failed += 1

    print(f"\nDeleted: {success}  |  Failed: {failed}")

    # Verify
    stats = httpx.get(f"{base_url}/public-knowledge/stats", headers=headers, timeout=30.0).json()
    print(f"Remaining objects: {stats['total_documents']}")


if __name__ == "__main__":
    main()
