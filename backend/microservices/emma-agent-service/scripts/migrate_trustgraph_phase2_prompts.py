#!/usr/bin/env python3
"""
Migration: TrustGraph Phase 2 prompts for Graph RAG and edge scoring.

Pushes prompt changes directly to Langfuse.
These prompts are consumed by knowledge-tree-service and weaviate-service for
Graph RAG retrieval and knowledge graph edge scoring.

Changes:
  1. trustgraph_extract_concepts   — Extract high/low-level concepts from query
  2. trustgraph_edge_scoring       — Score knowledge graph edges for relevance

Usage:
    docker compose exec emma-agent-service python scripts/migrate_trustgraph_phase2_prompts.py
    docker compose exec emma-agent-service python scripts/migrate_trustgraph_phase2_prompts.py --dry-run
    docker compose exec emma-agent-service python scripts/migrate_trustgraph_phase2_prompts.py --force
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ── Concept extraction prompt ────────────────────────────────────────────────

TRUSTGRAPH_EXTRACT_CONCEPTS = """\
You are a query analysis expert for a document management and legal knowledge system.
Extract key concepts from the user query for knowledge graph and document retrieval.

Return TWO types of concepts:
1. high_level_keywords: overarching themes, subject areas, legal domains, business topics
   Examples: "derecho laboral", "fiscalidad empresarial", "protección de datos"
2. low_level_keywords: specific entities, proper nouns, legal references, dates, amounts, document types
   Examples: "LGT", "Juan García", "contrato temporal", "Art. 54 ET"

Query: {query}

Respond ONLY with valid JSON:
{{"high_level_keywords": ["..."], "low_level_keywords": ["..."]}}\
"""


# ── Edge scoring prompt ──────────────────────────────────────────────────────

TRUSTGRAPH_EDGE_SCORING = """\
Score the relevance of each knowledge graph edge to the user query.
Score 0 (irrelevant) to 10 (highly relevant).
Only consider edges that directly help answer the question.

Query: {query}

Edges (format: id | subject → predicate → object):
{edges_json}

Respond ONLY with a JSON array. Only include edges with score > 0:
[{{"id": "edge_id", "score": N}}, ...]\
"""


def get_langfuse_client():
    """Create Langfuse client from environment."""
    from langfuse import Langfuse

    host = os.getenv("LANGFUSE_HOST", "http://langfuse:3000")
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY", "")

    if not public_key or not secret_key:
        print("ERROR: LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY must be set")
        sys.exit(1)

    return Langfuse(public_key=public_key, secret_key=secret_key, host=host), host


def migrate_prompt(langfuse, name: str, content: str, dry_run: bool, force: bool) -> bool:
    """Create or update a prompt in Langfuse."""
    print(f"── {name} ──")

    exists = False
    try:
        langfuse.get_prompt(name=name)
        exists = True
    except Exception:
        pass

    if exists and not force:
        print("  SKIP: Prompt already exists (use --force to overwrite)")
        return True

    action = "UPDATE" if exists else "CREATE"

    if dry_run:
        print(f"  DRY RUN: Would {action} prompt ({len(content)} chars)")
        return True

    langfuse.create_prompt(
        name=name,
        prompt=content,
        type="text",
        labels=["production"],
        config={"section": "trustgraph", "service": "knowledge-tree-service,weaviate-service", "migrated_by": "migrate_trustgraph_phase2_prompts"},
    )
    print(f"  OK: {action} {name} ({len(content)} chars)")
    return True


def main():
    parser = argparse.ArgumentParser(description="Migrate TrustGraph Phase 2 prompts to Langfuse")
    parser.add_argument("--dry-run", action="store_true", help="Show what would change without modifying Langfuse")
    parser.add_argument("--force", action="store_true", help="Overwrite existing prompts (creates new version)")
    args = parser.parse_args()

    langfuse, host = get_langfuse_client()
    print(f"Connected to Langfuse at {host}\n")

    results = []
    results.append(("trustgraph_extract_concepts", migrate_prompt(langfuse, "trustgraph_extract_concepts", TRUSTGRAPH_EXTRACT_CONCEPTS, args.dry_run, args.force)))
    results.append(("trustgraph_edge_scoring", migrate_prompt(langfuse, "trustgraph_edge_scoring", TRUSTGRAPH_EDGE_SCORING, args.dry_run, args.force)))

    print("\n── Summary ──")
    for name, ok in results:
        status = "OK" if ok else "FAIL"
        print(f"  {status} {name}")

    failures = sum(1 for _, ok in results if not ok)
    if failures:
        print(f"\n{failures} migration(s) failed")
        sys.exit(1)
    elif args.dry_run:
        print("\nDry run complete — no changes made")
    else:
        print("\nAll migrations applied successfully")


if __name__ == "__main__":
    main()
