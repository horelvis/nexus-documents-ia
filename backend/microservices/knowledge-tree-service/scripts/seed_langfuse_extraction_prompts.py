#!/usr/bin/env python3
"""
Seed TrustGraph extraction prompts to Langfuse.

Seeds 4 extraction prompts used by the LLM extractors in knowledge-tree-service:
  - trustgraph_extract_definitions
  - trustgraph_extract_relationships
  - trustgraph_extract_objects
  - trustgraph_extract_topics

SAFE BY DEFAULT: Only creates prompts that are MISSING from Langfuse.
Use --force to overwrite existing prompts (creates a new Langfuse version).

Usage:
    docker compose exec knowledge-tree-service python scripts/seed_langfuse_extraction_prompts.py
    docker compose exec knowledge-tree-service python scripts/seed_langfuse_extraction_prompts.py --force
    docker compose exec knowledge-tree-service python scripts/seed_langfuse_extraction_prompts.py --dry-run

Environment variables:
    LANGFUSE_PUBLIC_KEY  Langfuse project public key
    LANGFUSE_SECRET_KEY  Langfuse project secret key
    LANGFUSE_HOST        Langfuse server URL (default: http://langfuse:3002)
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Dict, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ── Guard: require langfuse ────────────────────────────────────────────────────
try:
    from langfuse import Langfuse
except ImportError:
    print(
        "ERROR: langfuse package is not installed.\n"
        "Install it with: pip install langfuse"
    )
    sys.exit(1)

# ── ANSI colors ────────────────────────────────────────────────────────────────
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"

# ── Prompt definitions ─────────────────────────────────────────────────────────
# Each entry: prompt_name -> (content, max_tokens)

PROMPTS: Dict[str, Tuple[str, int]] = {
    "trustgraph_extract_definitions": (
        """\
Eres un extractor de definiciones conceptuales. Dado un fragmento de texto, extrae las definiciones explícitas o implícitas de términos, conceptos, personas, organizaciones o documentos mencionados.

Return one JSON object per line (JSONL format). Do NOT wrap in an array.
Each object must have:
- "entity": nombre del término o entidad que se define
- "definition": definición o descripción extraída del texto (cita o paráfrasis fiel)

Reglas:
- Solo extrae definiciones que estén claramente expresadas en el texto
- No inventes ni inferas definiciones que no estén en el fragmento
- Usa el texto exacto o paráfrasis muy cercanas
- Return nothing if no definitions are found

Example:
{"entity": "contrato de trabajo", "definition": "acuerdo por el que una persona se obliga a prestar servicios a otra a cambio de retribución"}
{"entity": "TechCorp SL", "definition": "empresa dedicada al desarrollo de software con sede en Madrid"}

TEXT:
{{chunk_text}}""",
        4096,
    ),

    "trustgraph_extract_relationships": (
        """\
Eres un extractor de relaciones semánticas. Dado un fragmento de texto, extrae las relaciones entre entidades.

Use these predicates when they fit:
{{mini_ontology}}

If none of the above predicates fit, use a descriptive predicate in Spanish (e.g., "regula", "modifica", "pertenece-a").

Return one JSON object per line (JSONL format). Do NOT wrap in an array.
Each object must have:
- "subject": nombre de la entidad sujeto
- "predicate": nombre del predicado (prefer ontology predicates above, or a descriptive one)
- "object": nombre de la entidad u objeto de la relación
- "object-entity": true if the object is a named entity, false if it is a literal value

Return nothing if no relationships are found.

Example:
{"subject": "Juan García", "predicate": "empleado-de", "object": "TechCorp SL", "object-entity": true}
{"subject": "Contrato 2025-001", "predicate": "vigente-desde", "object": "01/01/2025", "object-entity": false}
{"subject": "Ley 31/1995", "predicate": "regula", "object": "prevención de riesgos laborales", "object-entity": false}

TEXT:
{{chunk_text}}""",
        4096,
    ),

    "trustgraph_extract_objects": (
        """\
Eres un extractor de entidades nombradas. Dado un fragmento de texto, extrae TODAS las entidades con nombre propio o identificadores únicos.

Return one JSON object per line (JSONL format). Do NOT wrap in an array.
Each object must have:
- "name": nombre exacto de la entidad tal como aparece en el texto
- "type": tipo de entidad ("person", "organization", "document", "place", "date", "legislation", "contract", "other")

Entidades a extraer:
- Personas: nombres completos con apellidos
- Organizaciones: empresas, organismos, instituciones
- Documentos: contratos, facturas, expedientes con identificador
- Lugares: ciudades, provincias, países, direcciones
- Fechas: fechas concretas (no rangos genéricos)
- Legislación: leyes, reglamentos, artículos con referencia

NO extraer:
- Valores numéricos sin contexto
- Emails, teléfonos, IBANs, NIFs (datos personales sensibles)
- Términos genéricos sin nombre propio

Return nothing if no entities are found.

Example:
{"name": "Juan García López", "type": "person"}
{"name": "TechCorp SL", "type": "organization"}
{"name": "Estatuto de los Trabajadores", "type": "legislation"}

TEXT:
{{chunk_text}}""",
        4096,
    ),

    "trustgraph_extract_topics": (
        """\
Eres un extractor de temas y áreas temáticas. Dado un fragmento de texto, identifica los temas principales tratados.

Return one JSON object per line (JSONL format). Do NOT wrap in an array.
Each object must have:
- "topic": nombre del tema (conciso, 1-4 palabras, en español)

Reglas:
- Extrae entre 1 y 8 temas por fragmento
- Usa nombres de temas en español
- Focus on substantive topics — legal areas, business domains, subject matter
- Avoid generic terms like "document" or "text"
- Return nothing if no clear topics can be identified

Example:
{"topic": "contrato laboral"}
{"topic": "protección de datos"}
{"topic": "derecho mercantil"}

TEXT:
{{chunk_text}}""",
        2048,
    ),
}


# ── Langfuse client ────────────────────────────────────────────────────────────

def get_langfuse_client() -> Tuple[Langfuse, str]:
    """Create Langfuse client from environment variables."""
    host = os.getenv("LANGFUSE_HOST", "http://langfuse:3002")
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY", "")

    if not public_key or not secret_key:
        print(f"{RED}ERROR: LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY must be set{RESET}")
        sys.exit(1)

    client = Langfuse(public_key=public_key, secret_key=secret_key, host=host)
    return client, host


# ── Per-prompt seed ────────────────────────────────────────────────────────────

def seed_prompt(
    langfuse: Langfuse,
    name: str,
    content: str,
    max_tokens: int,
    dry_run: bool,
    force: bool,
) -> bool:
    """Create or update a single prompt in Langfuse.

    Returns True on success or skip, False on error.
    """
    print(f"── {name} ──")

    exists = False
    try:
        langfuse.get_prompt(name=name)
        exists = True
    except Exception:
        pass

    if exists and not force:
        print(f"  {YELLOW}SKIP{RESET}: Already exists (use --force to overwrite)")
        return True

    action = "UPDATE" if exists else "CREATE"

    if dry_run:
        print(f"  DRY RUN: Would {action} ({len(content)} chars, max_tokens={max_tokens})")
        return True

    try:
        langfuse.create_prompt(
            name=name,
            prompt=content,
            type="text",
            labels=["production"],
            config={
                "temperature": 0.1,
                "max_tokens": max_tokens,
                "service": "knowledge-tree-service",
                "phase": "trustgraph_extraction",
                "seeded_by": "seed_langfuse_extraction_prompts",
            },
        )
        print(f"  {GREEN}OK{RESET}: {action} ({len(content)} chars, max_tokens={max_tokens})")
        return True
    except Exception as exc:
        print(f"  {RED}ERROR{RESET}: {exc}")
        return False


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Seed TrustGraph extraction prompts to Langfuse",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Prompts seeded:
  trustgraph_extract_definitions   — Entity definition extraction
  trustgraph_extract_relationships — Semantic relationship extraction (ontology-guided)
  trustgraph_extract_objects       — Named entity recognition
  trustgraph_extract_topics        — Topic and domain classification

Examples:
  # Default: seed only MISSING prompts (safe)
  python scripts/seed_langfuse_extraction_prompts.py

  # Force: overwrite all prompts (creates new Langfuse version)
  python scripts/seed_langfuse_extraction_prompts.py --force

  # Dry run: preview what would be created/skipped
  python scripts/seed_langfuse_extraction_prompts.py --dry-run
        """,
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing prompts (creates a new Langfuse version)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be created/skipped without making changes",
    )
    args = parser.parse_args()

    langfuse, host = get_langfuse_client()

    print("=" * 60)
    print(f"TrustGraph extraction prompt seed — {len(PROMPTS)} prompts")
    print(f"Langfuse: {host}")
    if args.dry_run:
        print("DRY RUN — no changes will be made")
    elif args.force:
        print("FORCE mode — will overwrite existing prompts")
    else:
        print("SAFE mode — will skip existing prompts")
    print("=" * 60)
    print()

    results = []
    for name, (content, max_tokens) in PROMPTS.items():
        ok = seed_prompt(
            langfuse=langfuse,
            name=name,
            content=content,
            max_tokens=max_tokens,
            dry_run=args.dry_run,
            force=args.force,
        )
        results.append((name, ok))
        print()

    print("=" * 60)
    print("Summary:")
    for name, ok in results:
        status = f"{GREEN}OK{RESET}" if ok else f"{RED}FAIL{RESET}"
        print(f"  {status}  {name}")

    failures = sum(1 for _, ok in results if not ok)
    print()
    if failures:
        print(f"{RED}{failures} prompt(s) failed to seed{RESET}")
        sys.exit(1)
    elif args.dry_run:
        print("Dry run complete — no changes made")
    else:
        print(f"{GREEN}All {len(PROMPTS)} prompts seeded successfully{RESET}")


if __name__ == "__main__":
    main()
