#!/usr/bin/env python3
"""
Re-index existing monolithic Public Knowledge documents as chunked objects.

For each document where content > CHUNK_THRESHOLD and has no parent_document_id:
  1. Fetch full document from Weaviate
  2. Delete the monolithic object
  3. Re-insert via the weaviate-service /public-knowledge/documents API
     (which now auto-chunks via SemanticChunker)

Usage:
    python scripts/reindex_public_knowledge.py [--weaviate-url URL] [--dry-run]
"""
import argparse
import sys
import time
import httpx

DEFAULT_URL = "http://localhost:8007"
CHUNK_THRESHOLD = 3000
BATCH_SIZE = 100  # fetch this many docs per page


def get_api_key():
    import os
    return os.getenv("MICROSERVICES_API_KEY", "")


def fetch_all_documents(base_url: str, api_key: str) -> list:
    """Fetch all PublicKnowledge documents via search with empty-ish query."""
    headers = {"X-API-Key": api_key} if api_key else {}
    all_docs = []
    # Use keyword search with a broad query to get all docs
    # Weaviate bm25 with "*" doesn't work, so we fetch via stats + iterate
    # Instead, use the search endpoint with high limit
    offset = 0
    while True:
        resp = httpx.post(
            f"{base_url}/public-knowledge/search",
            json={
                "query": "ley decreto artículo legislación",
                "limit": BATCH_SIZE,
                "search_type": "keyword",
                "current_version_only": False,
            },
            headers=headers,
            timeout=60.0,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        if not results:
            break
        all_docs.extend(results)
        # BM25 doesn't support offset natively, so we do one big fetch
        break

    # Deduplicate by id
    seen = set()
    unique = []
    for doc in all_docs:
        if doc["id"] not in seen:
            seen.add(doc["id"])
            unique.append(doc)
    return unique


def main():
    parser = argparse.ArgumentParser(description="Re-index PublicKnowledge docs as chunks")
    parser.add_argument("--weaviate-url", default=DEFAULT_URL, help="Weaviate service base URL")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without making changes")
    parser.add_argument("--limit", type=int, default=0, help="Max documents to re-index (0=all)")
    args = parser.parse_args()

    base_url = args.weaviate_url.rstrip("/")
    api_key = get_api_key()
    headers = {"X-API-Key": api_key} if api_key else {}

    print(f"Connecting to {base_url}...")

    # 1. Get stats
    stats_resp = httpx.get(f"{base_url}/public-knowledge/stats", headers=headers, timeout=30.0)
    stats_resp.raise_for_status()
    stats = stats_resp.json()
    print(f"Total documents in PublicKnowledge: {stats['total_documents']}")

    # 2. Fetch all docs
    print("Fetching documents...")
    all_docs = fetch_all_documents(base_url, api_key)
    print(f"Fetched {len(all_docs)} documents")

    # 3. Filter: monolithic (content > threshold, no parent_document_id)
    candidates = []
    for doc in all_docs:
        content = doc.get("content", "")
        has_parent = doc.get("parent_document_id")
        if len(content) > CHUNK_THRESHOLD and not has_parent:
            candidates.append(doc)

    print(f"Found {len(candidates)} monolithic documents to re-index (content > {CHUNK_THRESHOLD} chars)")

    if args.limit > 0:
        candidates = candidates[:args.limit]
        print(f"  (limited to {args.limit})")

    if not candidates:
        print("Nothing to do.")
        return

    # 4. Re-index each
    success = 0
    failed = 0
    total_chunks = 0

    for i, doc in enumerate(candidates, 1):
        doc_id = doc["id"]
        title = doc.get("title", "?")
        content_len = len(doc.get("content", ""))
        print(f"\n[{i}/{len(candidates)}] {title[:80]}  ({content_len:,} chars)")

        if args.dry_run:
            print(f"  DRY RUN: would delete {doc_id} and re-insert as chunks")
            continue

        try:
            # Delete the monolithic object
            del_resp = httpx.delete(
                f"{base_url}/public-knowledge/documents/{doc_id}",
                headers=headers,
                timeout=30.0,
            )
            del_resp.raise_for_status()

            # Re-insert (the API now auto-chunks)
            create_payload = {
                "title": doc.get("title", ""),
                "content": doc.get("content", ""),
                "summary": doc.get("summary"),
                "category": doc.get("category", "legislation"),
                "subcategory": doc.get("subcategory"),
                "jurisdiction": doc.get("jurisdiction", "es"),
                "legal_reference": doc.get("legal_reference"),
                "keywords": doc.get("keywords", []),
                "topics": doc.get("topics", []),
                "related_documents": doc.get("related_documents", []),
                "source_url": doc.get("source_url"),
                "source_name": doc.get("source_name"),
                "verified": doc.get("verified", False),
                "version": doc.get("version", "1.0"),
                "version_number": doc.get("version_number", 1),
                "is_current_version": doc.get("is_current_version", True),
                "modification_type": doc.get("modification_type", "original"),
                "legal_status": doc.get("legal_status", "vigente"),
                "boe_id": doc.get("boe_id"),
                "eli_uri": doc.get("eli_uri"),
            }
            # Remove None values
            create_payload = {k: v for k, v in create_payload.items() if v is not None}

            add_resp = httpx.post(
                f"{base_url}/public-knowledge/documents",
                json=create_payload,
                headers=headers,
                timeout=120.0,
            )
            add_resp.raise_for_status()

            est_chunks = max(1, content_len // 1500)
            total_chunks += est_chunks
            success += 1
            print(f"  ✓ Re-indexed (~{est_chunks} chunks)")

            # Small delay to avoid overwhelming TEI
            time.sleep(0.5)

        except Exception as e:
            failed += 1
            print(f"  ✗ FAILED: {e}")

    # 5. Summary
    print("\n" + "=" * 60)
    print(f"Re-indexing complete:")
    print(f"  Success: {success}")
    print(f"  Failed:  {failed}")
    print(f"  Est. chunks created: {total_chunks}")
    if args.dry_run:
        print("  (DRY RUN — no changes were made)")


if __name__ == "__main__":
    main()
