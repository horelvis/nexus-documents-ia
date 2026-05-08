#!/usr/bin/env python3
"""
Seed mini-ontology predicate definitions into FalkorDB.

Seeds ~32 predicate definitions as triples in the `_ontology` collection
(user="_system"). For each predicate, creates a :Node and 5 triples:
  onto/label, onto/description, onto/domain, onto/range, onto/sector.

SAFE BY DEFAULT: Only creates predicates that are MISSING from the graph.
Use --force to clear the _ontology collection and recreate all predicates.

Usage:
    docker compose exec knowledge-tree-service python scripts/seed_ontology.py
    docker compose exec knowledge-tree-service python scripts/seed_ontology.py --force
    docker compose exec knowledge-tree-service python scripts/seed_ontology.py --dry-run
    docker compose exec knowledge-tree-service python scripts/seed_ontology.py --list
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path
from typing import List, Tuple

# Allow imports from app when running inside the container
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.falkordb_client import FalkorDBClient
from app.services.triple_store import TripleStore
from app.services.uri_builder import URIBuilder

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

ONTOLOGY_USER = "_system"
ONTOLOGY_COLLECTION = "_ontology"

GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"

# ── Predicate definitions ──────────────────────────────────────────────────────
# Each entry: (sector, predicate_name, description, domain_type, range_type)
# sector: "core" | "legal" | "prov"

PREDICATES: List[Tuple[str, str, str, str, str]] = [
    # ── Core (~15) ─────────────────────────────────────────────────────────────
    ("core", "label",         "Human-readable name of an entity",                              "any",          "literal"),
    ("core", "definition",    "Formal definition or description of an entity",                 "any",          "literal"),
    ("core", "type",          "Semantic type classification of an entity",                     "any",          "literal"),
    ("core", "has-topic",     "Associates an entity with a topic or subject area",             "document",     "topic"),
    ("core", "mentioned-in",  "Entity appears in the referenced document or chunk",            "entity",       "document"),
    ("core", "contained-in",  "Document or folder is contained within a parent folder",        "document",     "folder"),
    ("core", "part-of",       "Entity or section is a structural part of a larger entity",     "any",          "any"),
    ("core", "instance-of",   "Entity is an instance of a class or category",                  "entity",       "class"),
    ("core", "supports",      "Claim or argument provides evidence supporting another claim",  "claim",        "claim"),
    ("core", "contradicts",   "Claim or argument is in conflict with another claim",           "claim",        "claim"),
    ("core", "semantic-type", "Fine-grained document type (factura, contrato, nomina, etc.)",  "document",     "literal"),
    ("core", "domain",        "Business domain classification (legal, fiscal, medical, etc.)", "document",     "literal"),
    ("core", "same-as",       "Two entities are the same real-world entity (dedup audit)",     "entity",       "entity"),
    ("core", "supersedes",    "This entity or version replaces an older one",                  "any",          "any"),
    ("core", "related-to",    "General semantic relationship between two entities",            "any",          "any"),

    # ── Legal (~25) ────────────────────────────────────────────────────────────
    ("legal", "empleado-de",       "Relacion laboral entre persona y empresa",                          "person",       "organization"),
    ("legal", "firmante-de",       "Persona que firma un contrato o documento",                         "person",       "document"),
    ("legal", "representante-de",  "Persona que actua como representante legal de una organizacion",    "person",       "organization"),
    ("legal", "regulado-por",      "Entidad o actividad que esta regulada por una norma juridica",      "any",          "legislation"),
    ("legal", "salario-bruto",     "Importe del salario bruto anual o mensual pactado",                "contract",     "literal"),
    ("legal", "tipo-contrato",     "Modalidad o tipo de contrato laboral",                             "contract",     "literal"),
    ("legal", "vigente-desde",     "Fecha de inicio de vigencia de un contrato o norma",               "contract",     "literal"),
    ("legal", "vigente-hasta",     "Fecha de finalizacion de vigencia de un contrato o norma",         "contract",     "literal"),
    ("legal", "clausula",          "Clausula o disposicion especifica de un contrato",                 "contract",     "literal"),
    ("legal", "obligacion",        "Obligacion impuesta por un contrato o norma",                      "any",          "literal"),
    ("legal", "derecho",           "Derecho reconocido a una parte por un contrato o norma",           "any",          "literal"),
    ("legal", "modifica",          "Norma que modifica o enmienda otra norma juridica",                "legislation",  "legislation"),
    ("legal", "derogado-por",      "Norma que ha sido derogada por otra posterior",                    "legislation",  "legislation"),
    ("legal", "references-law",    "Document or clause that references a specific law or article",     "document",     "legislation"),
    ("legal", "parte-de-contrato", "Persona u organizacion que es parte en un contrato",               "any",          "contract"),
    ("legal", "beneficiario-de",   "Persona o entidad que recibe un beneficio de un contrato o norma", "any",          "any"),
    ("legal", "garante-de",        "Persona o entidad que garantiza una obligacion",                   "any",          "any"),
    ("legal", "obligacion-de",     "Obligacion especifica que recae sobre una parte",                  "any",          "literal"),
    ("legal", "duracion",          "Periodo de duracion de un contrato o relacion",                    "contract",     "literal"),
    ("legal", "importe",           "Cantidad economica asociada a un contrato o transaccion",          "any",          "literal"),
    ("legal", "cargo-de",          "Persona que ocupa un cargo en una organizacion",                   "person",       "organization"),
    ("legal", "filial-de",         "Organizacion que es filial o subsidiaria de otra",                 "organization", "organization"),
    ("legal", "administrador-de",  "Persona que es administrador de una sociedad",                     "person",       "organization"),
    ("legal", "sujeto-a",          "Entidad sujeta a una norma o regulacion",                          "any",          "legislation"),
    ("legal", "sancion",           "Sancion o penalizacion prevista por incumplimiento",               "any",          "literal"),

    # ── Trust (~4) ─────────────────────────────────────────────────────────────
    ("trust", "authority-weight",    "Peso de autoridad 0.0-1.0 por tipo de documento fuente",       "document-type", "literal"),
    ("trust", "source-reliability",  "Fiabilidad de la fuente de extraccion (manual/llm/imported)",  "extraction",    "literal"),
    ("trust", "temporal-validity",   "Indica si el triple sigue vigente temporalmente",              "triple",        "literal"),
    ("trust", "consensus-score",     "Numero de fuentes independientes que confirman el triple",     "triple",        "literal"),

    # ── Medical (~12) ──────────────────────────────────────────────────────────
    ("medical", "diagnosticado-con",   "Paciente diagnosticado con una enfermedad o condicion",       "person",    "condition"),
    ("medical", "prescrito-por",       "Medicamento o tratamiento prescrito por un profesional",      "treatment", "person"),
    ("medical", "tratado-en",          "Paciente tratado en un centro o servicio medico",             "person",    "facility"),
    ("medical", "alergia-a",           "Paciente con alergia documentada a una sustancia",           "person",    "substance"),
    ("medical", "medicacion",          "Medicamento activo en el tratamiento del paciente",          "person",    "literal"),
    ("medical", "antecedente",         "Antecedente medico relevante del paciente",                  "person",    "literal"),
    ("medical", "resultado-de",        "Resultado de una prueba diagnostica o analisis",             "test",      "literal"),
    ("medical", "derivado-a",          "Paciente derivado a un especialista o servicio",             "person",    "person"),
    ("medical", "fecha-ingreso",       "Fecha de ingreso hospitalario",                              "person",    "literal"),
    ("medical", "fecha-alta",          "Fecha de alta hospitalaria",                                 "person",    "literal"),
    ("medical", "grupo-sanguineo",     "Grupo sanguineo del paciente",                               "person",    "literal"),
    ("medical", "profesional-responsable", "Profesional medico responsable del paciente",            "person",    "person"),

    # ── Documental (~10) ───────────────────────────────────────────────────────
    ("documental", "autor-de",        "Persona autora de un documento o informe",                    "person",    "document"),
    ("documental", "revisado-por",    "Persona que reviso o valido un documento",                    "document",  "person"),
    ("documental", "aprobado-por",    "Persona que aprobo formalmente un documento",                 "document",  "person"),
    ("documental", "version-de",      "Documento que es una version de otro anterior",               "document",  "document"),
    ("documental", "fecha-creacion",  "Fecha de creacion del documento",                             "document",  "literal"),
    ("documental", "fecha-revision",  "Fecha de ultima revision del documento",                      "document",  "literal"),
    ("documental", "destinatario-de", "Persona o entidad destinataria de un documento",              "document",  "any"),
    ("documental", "clasificado-como", "Clasificacion documental (confidencial, publico, etc.)",     "document",  "literal"),
    ("documental", "referencia",      "Codigo o numero de referencia del documento",                 "document",  "literal"),
    ("documental", "adjunto-a",       "Documento adjunto a otro documento principal",                "document",  "document"),

    # ── Prov (~6) ──────────────────────────────────────────────────────────────
    ("prov", "derived-from",   "Triple or entity derived from a source document or chunk",      "triple",       "document"),
    ("prov", "method",         "Extraction method used to produce this triple or entity",        "triple",       "literal"),
    ("prov", "model",          "LLM or model name used during extraction",                       "triple",       "literal"),
    ("prov", "timestamp",      "ISO 8601 timestamp when the triple was extracted",               "triple",       "literal"),
    ("prov", "chunk-text",     "Raw text of the source chunk that yielded this triple",          "triple",       "literal"),
    ("prov", "chunk-offset",   "Character offset of the source chunk within the document",       "triple",       "literal"),
]


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _fetch_existing_predicate_uris(client: FalkorDBClient) -> set:
    """Return the set of predicate URIs already present in the _ontology collection."""
    query = (
        "MATCH (n:Node {collection: $collection}) "
        "RETURN n.uri AS uri"
    )
    rows = await client.execute_cypher(
        query,
        params={"collection": ONTOLOGY_COLLECTION},
    )
    return {row["uri"] for row in rows if row.get("uri")}


async def _clear_ontology(client: FalkorDBClient) -> None:
    """DETACH DELETE all ontology nodes and literals (for --force mode)."""
    query = (
        "MATCH (n) "
        "WHERE (n:Node OR n:Literal) "
        "AND n.collection = $collection "
        "DETACH DELETE n"
    )
    await client.execute_cypher(
        query,
        params={"collection": ONTOLOGY_COLLECTION},
    )


async def _seed_predicate(
    store: TripleStore,
    sector: str,
    name: str,
    description: str,
    domain_type: str,
    range_type: str,
) -> None:
    """Create a :Node for the predicate and store its 5 descriptive triples."""
    pred_uri = URIBuilder.predicate(sector, name)

    # Ensure the predicate node itself exists in the ontology collection
    await store.merge_node(pred_uri, ONTOLOGY_USER, ONTOLOGY_COLLECTION)

    # 5 triples: label, description, domain, range, sector
    triples = [
        ("onto", "label",       name,         False),
        ("onto", "description", description,  False),
        ("onto", "domain",      domain_type,  False),
        ("onto", "range",       range_type,   False),
        ("onto", "sector",      sector,        False),
    ]

    for pred_ontology, pred_name, value, is_node in triples:
        await store.merge_literal(value, ONTOLOGY_USER, ONTOLOGY_COLLECTION)
        pred_uri_onto = URIBuilder.predicate(pred_ontology, pred_name)
        await store.create_rel(
            subject_uri=pred_uri,
            predicate_uri=pred_uri_onto,
            object_value=value,

            collection=ONTOLOGY_COLLECTION,
            object_is_node=is_node,
            extraction_method="seed",
        )


# ── Main seed function ─────────────────────────────────────────────────────────

async def seed_ontology(dry_run: bool = False, force: bool = False) -> tuple:
    """Seed ontology predicates into FalkorDB.

    Returns:
        (created, skipped, errors) counts.
    """
    client = FalkorDBClient()
    await client.initialize()
    store = TripleStore(client)

    created = 0
    skipped = 0
    errors = 0

    try:
        existing_uris: set = set()

        if force and not dry_run:
            print(f"  {YELLOW}FORCE mode: clearing _ontology collection...{RESET}")
            await _clear_ontology(client)
            print(f"  {YELLOW}Cleared.{RESET}")
        else:
            existing_uris = await _fetch_existing_predicate_uris(client)
            if existing_uris:
                print(f"  Found {len(existing_uris)} existing predicate(s) in _ontology\n")

        for sector, name, description, domain_type, range_type in PREDICATES:
            pred_uri = URIBuilder.predicate(sector, name)
            label = f"{sector}/{name}"

            if not force and pred_uri in existing_uris:
                print(f"  {YELLOW}SKIP{RESET}  {label} — already exists (use --force to recreate)")
                skipped += 1
                continue

            if dry_run:
                action = "WOULD CREATE" if pred_uri not in existing_uris else "WOULD RECREATE"
                print(f"  {action}  {label}  [{domain_type} -> {range_type}]")
                created += 1
                continue

            try:
                await _seed_predicate(store, sector, name, description, domain_type, range_type)
                print(f"  {GREEN}OK{RESET}  {label}  [{domain_type} -> {range_type}]")
                created += 1
            except Exception as exc:
                print(f"  {RED}ERROR{RESET}  {label} — {exc}")
                errors += 1

    finally:
        await client.close()

    return created, skipped, errors


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Seed mini-ontology predicate definitions into FalkorDB",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Default: seed only MISSING predicates (safe)
  python scripts/seed_ontology.py

  # Force: clear _ontology collection and recreate all predicates
  python scripts/seed_ontology.py --force

  # Dry run: preview what would be created/skipped
  python scripts/seed_ontology.py --dry-run

  # List all predicate definitions (no DB operations)
  python scripts/seed_ontology.py --list
        """,
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Clear _ontology collection and recreate all predicates",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be created/skipped without making changes",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all predicate definitions and exit (no DB operations)",
    )
    args = parser.parse_args()

    # ── List mode ─────────────────────────────────────────────
    if args.list:
        print(f"{BOLD}Mini-ontology predicates ({len(PREDICATES)} total){RESET}\n")
        current_sector = None
        for sector, name, description, domain_type, range_type in PREDICATES:
            if sector != current_sector:
                current_sector = sector
                print(f"\n{BOLD}[{sector}]{RESET}")
            print(f"  {name:<22}  {domain_type:<14} -> {range_type:<14}  {description}")
        print()
        return

    # ── Seed mode ──────────────────────────────────────────────
    print("=" * 60)
    print(f"Mini-ontology seed — {len(PREDICATES)} predicates")
    if dry_run := args.dry_run:
        print("DRY RUN — no changes will be made")
    elif args.force:
        print("FORCE mode — will clear and recreate all predicates")
    else:
        print("SAFE mode — will skip existing predicates")
    print("=" * 60)
    print()

    created, skipped, errors = asyncio.run(
        seed_ontology(dry_run=args.dry_run, force=args.force)
    )

    print()
    print("=" * 60)
    print(f"Results: {created} created, {skipped} skipped, {errors} errors")

    if errors > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
