#!/usr/bin/env python3
"""
Migration: Add generate_knowledge_report to emma_react_system prompt.

The tool exists in the registry but the system prompt doesn't mention it,
so Qwen3.5-9B at temp=0.0 never selects it — responds directly instead.

Usage:
    docker compose exec emma-agent-service python scripts/migrate_knowledge_report_prompt.py --dry-run
    docker compose exec emma-agent-service python scripts/migrate_knowledge_report_prompt.py --apply
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# The line to add after the graph_rag line in the "2. BUSCAR" section
SEARCH_SECTION_OLD = """\
- RELACIONES entre personas/empresas/leyes → `graph_rag` (usar ANTES que smart_search)
- Contenido completo de un documento → `get_document_content`"""

SEARCH_SECTION_NEW = """\
- RELACIONES entre personas/empresas/leyes → `graph_rag` (usar ANTES que smart_search)
- INFORME/PERFIL/REPORTE de una entidad → `generate_knowledge_report` (NO necesita graph_rag previo)
- Contenido completo de un documento → `get_document_content`"""


def get_langfuse_client():
    from langfuse import Langfuse

    host = os.getenv("LANGFUSE_HOST", "http://langfuse:3000")
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY", "")

    if not public_key or not secret_key:
        print("ERROR: LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY must be set")
        sys.exit(1)

    return Langfuse(public_key=public_key, secret_key=secret_key, host=host)


def migrate(dry_run: bool) -> bool:
    langfuse = get_langfuse_client()
    print("── emma_react_system: adding generate_knowledge_report ──")

    try:
        existing = langfuse.get_prompt(name="emma_react_system", label="production")
        current = existing.prompt
    except Exception as e:
        print(f"  ERROR: Could not fetch emma_react_system: {e}")
        return False

    if "generate_knowledge_report" in current:
        print("  SKIP: generate_knowledge_report already in prompt")
        return True

    if SEARCH_SECTION_OLD not in current:
        print("  ERROR: Could not find expected search section in prompt")
        print(f"  Looking for: {SEARCH_SECTION_OLD[:80]}...")
        return False

    new_prompt = current.replace(SEARCH_SECTION_OLD, SEARCH_SECTION_NEW)

    print(f"  Current: {len(current)} chars (~{len(current)//3} tokens)")
    print(f"  New:     {len(new_prompt)} chars (~{len(new_prompt)//3} tokens)")
    print(f"  Added:   1 line (generate_knowledge_report routing)")

    if dry_run:
        print("  DRY RUN — no changes made")
        return True

    langfuse.create_prompt(
        name="emma_react_system",
        prompt=new_prompt,
        labels=["production"],
        type="text",
    )
    print("  ✅ Prompt updated (new version created with production label)")
    return True


def main():
    parser = argparse.ArgumentParser(description="Add generate_knowledge_report to ReAct prompt")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="Show changes without applying")
    group.add_argument("--apply", action="store_true", help="Apply changes to Langfuse")
    args = parser.parse_args()

    success = migrate(dry_run=args.dry_run)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
