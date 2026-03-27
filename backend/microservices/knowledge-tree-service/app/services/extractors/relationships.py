"""
Relationships extractor — extracts subject-predicate-object triples.

Uses a mini-ontology to guide the LLM toward known predicates.
Each relationship yields 1 triple with the correct ontology namespace.
"""

from typing import Any, Dict, List

from app.services.extractors.base import BaseExtractor

EXTRACTOR_NAME = "relationships"

# Core mini-ontology — guides the LLM to use controlled predicates
MINI_ONTOLOGY = """
PREFERRED PREDICATES (use these whenever possible):
  core:        type, label, definition, has-topic, part-of, related-to, derived-from,
               references, contains, created-by, belongs-to
  legal:       empleado-de, firmante-de, representante-de, regulado-por, salario-bruto,
               tipo-contrato, vigente-desde, vigente-hasta, clausula, obligacion, derecho,
               modifica, derogado-por, references-law
  prov:        derived-from
"""

# Predicates that belong to the "legal" ontology namespace
_LEGAL_PREDICATES = frozenset(
    [
        "empleado-de",
        "firmante-de",
        "representante-de",
        "regulado-por",
        "salario-bruto",
        "tipo-contrato",
        "vigente-desde",
        "vigente-hasta",
        "clausula",
        "obligacion",
        "derecho",
        "modifica",
        "derogado-por",
        "references-law",
    ]
)

# Predicates that belong to the "prov" namespace
_PROV_PREDICATES = frozenset(["derived-from"])

_PROMPT_TEMPLATE = """Extract all relationships between entities from the following text.

Use the mini-ontology below to choose predicates:
{mini_ontology}

Return a JSON array where each element has:
- "subject": the subject entity name (string)
- "predicate": the relationship predicate (use preferred predicates when possible)
- "object": the object value or entity name (string)
- "object-entity": true if the object is a named entity, false if it is a literal value

Return an empty array [] if no relationships are found.

Respond ONLY with a valid JSON array. Example:
[{{"subject": "Juan García", "predicate": "empleado-de", "object": "Empresa ABC S.L.", "object-entity": true}},
 {{"subject": "Contrato", "predicate": "vigente-desde", "object": "2024-01-01", "object-entity": false}}]

TEXT:
{chunk_text}"""


class RelationshipsExtractor(BaseExtractor):
    """Extracts subject-predicate-object relationships from text chunks."""

    EXTRACTOR_NAME = "relationships"

    def _build_prompt(self, chunk_text: str) -> str:
        return _PROMPT_TEMPLATE.format(
            mini_ontology=MINI_ONTOLOGY,
            chunk_text=chunk_text,
        )

    def _parse_output(
        self, llm_output: str, chunk_text: str
    ) -> List[Dict[str, Any]]:
        items = self._safe_parse_json(llm_output)
        triples: List[Dict[str, Any]] = []

        for item in items:
            if not isinstance(item, dict):
                continue
            subject = str(item.get("subject", "")).strip()
            predicate = str(item.get("predicate", "")).strip()
            obj = str(item.get("object", "")).strip()
            object_is_node = bool(item.get("object-entity", False))

            if not subject or not predicate or not obj:
                continue

            # Determine ontology namespace
            if predicate in _LEGAL_PREDICATES:
                ontology = "legal"
            elif predicate in _PROV_PREDICATES:
                ontology = "prov"
            else:
                ontology = "core"

            triples.append(
                self._make_triple(
                    subject=subject,
                    predicate_ontology=ontology,
                    predicate_name=predicate,
                    obj=obj,
                    object_is_node=object_is_node,
                    extraction_method="llm_relationships",
                    source_chunk=chunk_text,
                )
            )

        return triples
