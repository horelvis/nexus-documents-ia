"""
Relationships extractor — extracts subject-predicate-object triples.

Uses the OntologyRegistry to dynamically load valid predicates.
Each relationship yields 1 triple with the correct ontology namespace.

To add new predicates: update scripts/seed_ontology.py PREDICATES list
and re-run seed_ontology.py — no code changes needed here.
"""

import logging
from typing import Any, Dict, List

from app.services.extractors.base import BaseExtractor
from app.services.ontology_registry import (
    get_extractable_predicates,
    get_mini_ontology_text,
    get_namespace,
    is_valid_predicate,
)

logger = logging.getLogger(__name__)

EXTRACTOR_NAME = "relationships"

_PROMPT_TEMPLATE = """Extract all relationships between entities from the following text.

You MUST use ONLY predicates from this ontology:
{mini_ontology}

Return a JSON array where each element has:
- "subject": the subject entity name (string)
- "predicate": one of the predicates listed above (MUST be exact match)
- "object": the object value or entity name (string)
- "object-entity": true if the object is a named entity, false if it is a literal value

Return an empty array [] if no relationships are found.
Do NOT invent predicates outside the ontology.

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
            mini_ontology=get_mini_ontology_text(),
            chunk_text=chunk_text,
        )

    def _parse_output(
        self, llm_output: str, chunk_text: str
    ) -> List[Dict[str, Any]]:
        items = self._safe_parse_json(llm_output)
        triples: List[Dict[str, Any]] = []
        extractable = get_extractable_predicates()

        for item in items:
            if not isinstance(item, dict):
                continue
            subject = str(item.get("subject", "")).strip()
            predicate = str(item.get("predicate", "")).strip()
            obj = str(item.get("object", "")).strip()
            object_is_node = bool(item.get("object-entity", False))

            if not subject or not predicate or not obj:
                continue

            # Validate predicate against ontology — reject unknown predicates
            if predicate not in extractable:
                logger.debug(
                    "Rejected unknown predicate %r (subject=%r, object=%r)",
                    predicate, subject, obj,
                )
                continue

            # Namespace lookup from ontology registry
            ontology = get_namespace(predicate) or "core"

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
