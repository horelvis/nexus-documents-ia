#!/usr/bin/env python3
"""
Migration: Retrieval Intelligence prompts (Phase 1 + Phase 3).

Pushes prompt changes directly to Langfuse.
Langfuse DB is the single source of truth for all prompts.

Changes:
  1. emma_react_system — appends filter guidance section + {current_date} placeholder
  2. emma_smart_search_decompose — NEW prompt for Phase 3 query decomposition

Usage:
    # Inside Docker container:
    docker compose exec emma-agent-service python scripts/migrate_retrieval_intelligence_prompts.py

    # Dry run:
    docker compose exec emma-agent-service python scripts/migrate_retrieval_intelligence_prompts.py --dry-run

    # From host (with env vars):
    LANGFUSE_HOST=http://localhost:3002 \
    LANGFUSE_PUBLIC_KEY=pk-lf-xxx \
    LANGFUSE_SECRET_KEY=sk-lf-xxx \
    python scripts/migrate_retrieval_intelligence_prompts.py
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ── Filter guidance block to append to emma_react_system ────────────────

FILTER_GUIDANCE_BLOCK = """

    ### Filtros de búsqueda (IMPORTANTE)
    Cuando el usuario mencione fechas, períodos, personas, empresas o tipos de documento,
    SIEMPRE usa los parámetros de filtro de smart_search:
    - date_from / date_to: Fechas ISO 8601 (ej: "facturas de 2024" → date_from="2024-01-01", date_to="2024-12-31")
    - person_filter: Nombre de persona o empresa (ej: "contratos de ACME" → person_filter="ACME")
    - semantic_type_filter: Tipo de documento (ej: "facturas" → semantic_type_filter="factura")
    - domain_filter: Dominio (ej: "documentos laborales" → domain_filter="laboral")

    Hoy es {current_date}. Para fechas relativas:
    - "último mes" → date_from/date_to del mes anterior completo
    - "este año" → date_from del 1 de enero del año actual
    - "últimos 3 meses" → date_from = hace 3 meses desde hoy
    - "del primer trimestre" → date_from enero, date_to marzo

    ⚠️ NO uses filtros temporales para búsquedas de legislación (scope=legislation).
    La legislación no tiene fecha de creación en el sistema."""


# ── New decomposition prompt (Phase 3) ──────────────────────────────────

DECOMPOSE_PROMPT = """\
Descompón esta búsqueda en sub-consultas independientes para buscar en paralelo.
Preserva el contexto compartido (fechas, personas, filtros) en cada sub-consulta.

Responde SOLO con un array JSON (sin markdown, sin explicaciones):
[
  {"query": "sub-consulta 1", "scope": "documents|legislation|auto"},
  {"query": "sub-consulta 2", "scope": "documents|legislation|auto"}
]
O [] si la búsqueda no necesita descomposición (es simple).

Reglas:
- Máximo 3 sub-consultas
- Cada sub-consulta debe ser autocontenida (incluir fechas, persona si aplica)
- Si la búsqueda mezcla documentos + legislación, separar por scope
- NO descompongas búsquedas simples de un solo tema

Búsqueda: {query}"""


# ── Marker to detect if filter guidance was already appended ────────────

FILTER_MARKER = "### Filtros de búsqueda (IMPORTANTE)"


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


def migrate_react_system(langfuse, dry_run: bool) -> bool:
    """Append filter guidance to emma_react_system prompt."""
    print("── emma_react_system: adding filter guidance + {current_date} ──")

    try:
        existing = langfuse.get_prompt(name="emma_react_system", label="production")
        content = existing.prompt
    except Exception as e:
        print(f"  ERROR: Could not fetch emma_react_system: {e}")
        return False

    # Check if already migrated
    if FILTER_MARKER in content:
        print("  SKIP: Filter guidance already present in prompt")
        return True

    # Find insertion point: after "Paso 2: BUSCAR" block, before "Paso 3: EVALUAR"
    insertion_marker = "### Paso 3: EVALUAR"
    if insertion_marker not in content:
        print(f"  ERROR: Could not find '{insertion_marker}' in prompt content")
        return False

    new_content = content.replace(
        insertion_marker,
        FILTER_GUIDANCE_BLOCK + "\n\n    " + insertion_marker,
    )

    if dry_run:
        print(f"  DRY RUN: Would update prompt ({len(content)} → {len(new_content)} chars)")
        print(f"  Added {len(new_content) - len(content)} chars of filter guidance")
        return True

    langfuse.create_prompt(
        name="emma_react_system",
        prompt=new_content,
        type="text",
        labels=["production"],
        config={"section": "react", "migrated_by": "retrieval_intelligence_phase1"},
    )
    print(f"  OK: Updated emma_react_system ({len(content)} → {len(new_content)} chars)")
    return True


def migrate_decompose_prompt(langfuse, dry_run: bool) -> bool:
    """Create emma_smart_search_decompose prompt."""
    print("── emma_smart_search_decompose: creating new prompt ──")

    # Check if already exists
    try:
        langfuse.get_prompt(name="emma_smart_search_decompose")
        print("  SKIP: Prompt already exists in Langfuse")
        return True
    except Exception:
        pass  # Expected: prompt doesn't exist yet

    if dry_run:
        print(f"  DRY RUN: Would create prompt ({len(DECOMPOSE_PROMPT)} chars)")
        return True

    langfuse.create_prompt(
        name="emma_smart_search_decompose",
        prompt=DECOMPOSE_PROMPT,
        type="text",
        labels=["production"],
        config={"section": "smart_search", "migrated_by": "retrieval_intelligence_phase3"},
    )
    print(f"  OK: Created emma_smart_search_decompose ({len(DECOMPOSE_PROMPT)} chars)")
    return True


def main():
    parser = argparse.ArgumentParser(description="Migrate Retrieval Intelligence prompts to Langfuse")
    parser.add_argument("--dry-run", action="store_true", help="Show what would change without modifying Langfuse")
    args = parser.parse_args()

    langfuse, host = get_langfuse_client()
    print(f"Connected to Langfuse at {host}\n")

    results = []
    results.append(("emma_react_system", migrate_react_system(langfuse, args.dry_run)))
    results.append(("emma_smart_search_decompose", migrate_decompose_prompt(langfuse, args.dry_run)))

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
