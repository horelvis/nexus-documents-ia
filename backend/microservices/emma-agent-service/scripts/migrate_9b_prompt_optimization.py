#!/usr/bin/env python3
"""
Migration: Optimize emma_react_system prompt for Qwen3.5-9B.

Replaces the verbose ~2700 token system prompt with a streamlined ~1500 token
version. Smaller models follow short, structured instructions better than
long paragraphs with procedural tutorials.

Key changes:
- Remove redundant "Tus capacidades" section (tools already describe capabilities)
- Remove "Paso 5" forge_document tutorial (moved to tool description)
- Condense filter guidance from ~200 tokens to ~50
- Merge anti-hallucination + per-turn verification into single rules block
- Deduplicate rules that repeat earlier strategy sections

Usage:
    # Dry run (show diff):
    docker compose exec emma-agent-service python scripts/migrate_9b_prompt_optimization.py --dry-run

    # Apply:
    docker compose exec emma-agent-service python scripts/migrate_9b_prompt_optimization.py --apply

    # Rollback (restore previous version):
    docker compose exec emma-agent-service python scripts/migrate_9b_prompt_optimization.py --rollback
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ── New optimized prompt for 9B ─────────────────────────────────────────

OPTIMIZED_PROMPT = """\
Eres Emma, la IA del sistema NouxCubeIA (gestor documental empresarial).
Accedes a documentos indexados, legislación española (BOE), grafo de conocimiento,
conectores externos y búsqueda web para responder con información verificada.

## Herramientas disponibles
{tools_description}

## Estrategia de razonamiento

### 1. ENTENDER
Identifica qué necesita el usuario antes de actuar.

### 2. BUSCAR
- CONTAR documentos (cuántos, total) → `structural_query`
- BUSCAR documentos por contenido → `smart_search`
- RELACIONES entre personas/empresas/leyes → `graph_rag` (usar ANTES que smart_search)
- Contenido completo de un documento → `get_document_content`
- Información externa → `web_search`
- Fuentes disponibles → `list_sources`

### 3. EVALUAR
Después de cada búsqueda: ¿los resultados responden a la pregunta?
- Si NO son relevantes → reformula o usa otra herramienta
- Si `structural_query` no distingue tipos → complementa con `smart_search`
- Si un artículo no aparece → busca por nombre completo de la ley
- Tras 3+ intentos sin éxito → dilo honestamente

### 4. RESPONDER
Usa `terminate` cuando tengas información verificada. Cita fuentes.

## Filtros de smart_search
Hoy es {current_date}. Usa parámetros de filtro cuando el usuario mencione fechas/personas/tipos:
- `date_from`/`date_to`: ISO 8601. "último mes"→mes anterior, "este año"→desde enero
- `person_filter`: nombre de persona o empresa
- `semantic_type_filter`: tipo de documento (factura, contrato, nómina...)
- NO uses filtros temporales en legislación (scope=legislation)

## Reglas (OBLIGATORIAS)

**Anti-alucinación**: Tu respuesta SOLO puede contener datos que aparezcan
TEXTUALMENTE en los resultados de herramientas. Si encontraste 2 facturas,
dices "2 facturas" — NO "12 facturas". Si no hay datos, dilo.

**Verificación por turno**: Para cada nueva pregunta, BUSCA de nuevo.
NO respondas con resultados de preguntas anteriores.

**Documentos**:
- Modificar existente (renovar, cambiar fecha) → `forge_document`
- Crear nuevo desde cero → `generate_document`
- Enviar email → `send_email(confirmed=false)` primero, `confirmed=true` tras confirmación

**Formato**:
- Responde en el mismo idioma que el usuario
- Sé directo y conciso
- NUNCA escribas tool calls como texto — usa function calling
- NUNCA sugieras al usuario que busque él mismo — usa tus herramientas"""


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


def show_diff(old: str, new: str):
    """Show a simple character/token count comparison."""
    old_tokens = len(old) // 3
    new_tokens = len(new) // 3
    saved = old_tokens - new_tokens
    print(f"  Current: {len(old)} chars (~{old_tokens} tokens)")
    print(f"  New:     {len(new)} chars (~{new_tokens} tokens)")
    print(f"  Saved:   {saved} tokens ({saved * 100 // old_tokens}% reduction)")


def migrate_optimize(langfuse, dry_run: bool) -> bool:
    """Replace emma_react_system with optimized 9B version."""
    print("── emma_react_system: optimizing for Qwen3.5-9B ──")

    try:
        existing = langfuse.get_prompt(name="emma_react_system", label="production")
        current_content = existing.prompt
    except Exception as e:
        print(f"  ERROR: Could not fetch emma_react_system: {e}")
        return False

    # Check if already optimized (detect our marker)
    if current_content.startswith("Eres Emma, la IA del sistema NouxCubeIA (gestor documental empresarial)."):
        print("  SKIP: Prompt already optimized (9B version detected)")
        return True

    show_diff(current_content, OPTIMIZED_PROMPT)

    if dry_run:
        print(f"\n  --- NEW PROMPT PREVIEW ---")
        print(OPTIMIZED_PROMPT[:500] + "\n  ...")
        return True

    langfuse.create_prompt(
        name="emma_react_system",
        prompt=OPTIMIZED_PROMPT,
        type="text",
        labels=["production"],
        config={"section": "react", "migrated_by": "9b_prompt_optimization", "model": "Qwen3.5-9B"},
    )
    print(f"  OK: Updated emma_react_system (new version created in Langfuse)")
    return True


def rollback(langfuse) -> bool:
    """Rollback to previous version by fetching version history."""
    print("── emma_react_system: rolling back to previous version ──")

    try:
        # Langfuse keeps version history — fetch all and use the second-latest
        current = langfuse.get_prompt(name="emma_react_system", label="production")
        current_version = current.version if hasattr(current, 'version') else None
        print(f"  Current version: {current_version}")

        if current_version and current_version > 1:
            previous = langfuse.get_prompt(name="emma_react_system", version=current_version - 1)
            langfuse.create_prompt(
                name="emma_react_system",
                prompt=previous.prompt,
                type="text",
                labels=["production"],
                config={"section": "react", "migrated_by": "rollback_from_9b_optimization"},
            )
            print(f"  OK: Rolled back to version {current_version - 1}")
            return True
        else:
            print(f"  ERROR: No previous version to roll back to")
            return False
    except Exception as e:
        print(f"  ERROR: Rollback failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Optimize emma_react_system for Qwen3.5-9B")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="Show what would change")
    group.add_argument("--apply", action="store_true", help="Apply the optimization")
    group.add_argument("--rollback", action="store_true", help="Rollback to previous version")
    args = parser.parse_args()

    langfuse, host = get_langfuse_client()
    print(f"Connected to Langfuse at {host}\n")

    if args.rollback:
        ok = rollback(langfuse)
    else:
        ok = migrate_optimize(langfuse, dry_run=args.dry_run)

    if not ok:
        sys.exit(1)
    elif args.dry_run:
        print("\nDry run complete — no changes made. Run with --apply to update.")
    else:
        print("\nDone. Restart emma-agent-service to pick up cached prompt:")
        print("  docker compose restart emma-agent-service")


if __name__ == "__main__":
    main()
