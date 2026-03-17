#!/usr/bin/env python3
"""
Migration: Explain prompts for humanized query trace.

Pushes prompt changes directly to Langfuse.
Langfuse DB is the single source of truth for all prompts.

Changes:
  1. emma_explain_system — NEW prompt for humanized explanation of verified facts
  2. emma_explain_user   — NEW prompt (user template) with facts + tools + sources

Usage:
    # Inside Docker container:
    docker compose exec emma-agent-service python scripts/migrate_explain_prompts.py

    # Dry run:
    docker compose exec emma-agent-service python scripts/migrate_explain_prompts.py --dry-run

    # From host (with env vars):
    LANGFUSE_HOST=http://localhost:3002 \\
    LANGFUSE_PUBLIC_KEY=pk-lf-xxx \\
    LANGFUSE_SECRET_KEY=sk-lf-xxx \\
    python scripts/migrate_explain_prompts.py
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ── System prompt ────────────────────────────────────────────────────────────

EXPLAIN_SYSTEM_PROMPT = """\
Eres un asistente que explica su proceso de investigación a profesionales.
Reformula los siguientes hechos verificados en 2-4 frases naturales y claras.

Sector del usuario: {sector}
Adaptación de tono: {sector_guidance}

Reglas estrictas:
- NO inventes pasos, fuentes ni datos que no estén en la lista de hechos.
- Si un hecho menciona un documento, cítalo por nombre exacto.
- Si un hecho menciona un artículo de ley, cítalo con su número y nombre de ley.
- Usa conectores naturales ("Para ello", "A continuación", "Finalmente").
- Escribe en el mismo idioma que los hechos proporcionados."""


# ── User prompt ──────────────────────────────────────────────────────────────

EXPLAIN_USER_PROMPT = """\
Hechos verificados:
{facts_formatted}

Herramientas utilizadas: {tools_human_names}
Fuentes consultadas: {source_names}"""


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


def migrate_explain_system(langfuse, dry_run: bool) -> bool:
    """Create emma_explain_system prompt."""
    print("── emma_explain_system: creating new prompt ──")

    # Check if already exists
    try:
        langfuse.get_prompt(name="emma_explain_system")
        print("  SKIP: Prompt already exists in Langfuse")
        return True
    except Exception:
        pass  # Expected: prompt doesn't exist yet

    if dry_run:
        print(f"  DRY RUN: Would create prompt ({len(EXPLAIN_SYSTEM_PROMPT)} chars)")
        return True

    langfuse.create_prompt(
        name="emma_explain_system",
        prompt=EXPLAIN_SYSTEM_PROMPT,
        type="text",
        labels=["production"],
        config={"section": "explain", "migrated_by": "humanized_query_trace"},
    )
    print(f"  OK: Created emma_explain_system ({len(EXPLAIN_SYSTEM_PROMPT)} chars)")
    return True


def migrate_explain_user(langfuse, dry_run: bool) -> bool:
    """Create emma_explain_user prompt."""
    print("── emma_explain_user: creating new prompt ──")

    # Check if already exists
    try:
        langfuse.get_prompt(name="emma_explain_user")
        print("  SKIP: Prompt already exists in Langfuse")
        return True
    except Exception:
        pass  # Expected: prompt doesn't exist yet

    if dry_run:
        print(f"  DRY RUN: Would create prompt ({len(EXPLAIN_USER_PROMPT)} chars)")
        return True

    langfuse.create_prompt(
        name="emma_explain_user",
        prompt=EXPLAIN_USER_PROMPT,
        type="text",
        labels=["production"],
        config={"section": "explain", "migrated_by": "humanized_query_trace"},
    )
    print(f"  OK: Created emma_explain_user ({len(EXPLAIN_USER_PROMPT)} chars)")
    return True


def main():
    parser = argparse.ArgumentParser(description="Migrate Explain prompts to Langfuse")
    parser.add_argument("--dry-run", action="store_true", help="Show what would change without modifying Langfuse")
    args = parser.parse_args()

    langfuse, host = get_langfuse_client()
    print(f"Connected to Langfuse at {host}\n")

    results = []
    results.append(("emma_explain_system", migrate_explain_system(langfuse, args.dry_run)))
    results.append(("emma_explain_user", migrate_explain_user(langfuse, args.dry_run)))

    print("\n── Summary ──")
    for name, ok in results:
        status = "✅" if ok else "❌"
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
