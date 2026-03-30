"""
Relationships extractor — extracts subject-predicate-object triples.

Uses the OntologyRegistry for guided predicate matching with 3-tier fallback:
  1. Exact match → ontology namespace
  2. Fuzzy match (>0.8 similarity) → ontology namespace + _fuzzy method tag
  3. Free-form → "extracted" namespace + _freeform method tag
"""

import logging
import re
import unicodedata
from typing import Any, Dict, List

from app.services.extractors.base import BaseExtractor
from app.services.ontology_registry import (
    fuzzy_match,
    get_extractable_predicates,
    get_mini_ontology_text,
    get_namespace,
)

logger = logging.getLogger(__name__)

EXTRACTOR_NAME = "relationships"
LANGFUSE_PROMPT_NAME = "trustgraph_extract_relationships"

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "subject": {"type": "string", "minLength": 1},
        "predicate": {"type": "string", "minLength": 1},
        "object": {"type": "string", "minLength": 1},
        "object-entity": {"type": "boolean"},
    },
    "required": ["subject", "predicate", "object"],
}

_PROMPT_TEMPLATE = """Extract all relationships between entities from the following text.

Use these predicates when they fit:
{mini_ontology}

If none of the above predicates fit, use a descriptive predicate in Spanish (e.g., "regula", "modifica", "pertenece-a").

Return one JSON object per line (JSONL format). Do NOT wrap in an array.
Each object must have:
- "subject": the subject entity name (string)
- "predicate": predicate name (prefer ontology predicates above, or a descriptive one)
- "object": the object value or entity name (string)
- "object-entity": true if the object is a named entity, false if it is a literal value

Example:
{{"subject": "Juan García", "predicate": "empleado-de", "object": "Empresa ABC S.L.", "object-entity": true}}
{{"subject": "Contrato 2025-001", "predicate": "vigente-desde", "object": "2025-01-01", "object-entity": false}}
{{"subject": "Ley 31/1995", "predicate": "regula", "object": "prevención de riesgos laborales", "object-entity": false}}

Return nothing if no relationships are found.

TEXT:
{chunk_text}"""


def _normalize_predicate_name(predicate: str) -> str:
    """Normalize a free-form predicate to a URI-safe slug."""
    nfd = unicodedata.normalize("NFD", predicate.strip())
    ascii_approx = "".join(ch for ch in nfd if unicodedata.category(ch) != "Mn")
    lowered = ascii_approx.lower()
    return re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")


class RelationshipsExtractor(BaseExtractor):
    """Extracts subject-predicate-object relationships from text chunks."""

    EXTRACTOR_NAME = "relationships"
    RESPONSE_SCHEMA = RESPONSE_SCHEMA

    def _build_prompt(self, chunk_text: str) -> str:
        langfuse_prompt = self._get_langfuse_prompt(LANGFUSE_PROMPT_NAME)
        if langfuse_prompt:
            return langfuse_prompt.replace("{{chunk_text}}", chunk_text).replace(
                "{{mini_ontology}}", get_mini_ontology_text()
            )
        return _PROMPT_TEMPLATE.format(
            mini_ontology=get_mini_ontology_text(),
            chunk_text=chunk_text,
        )

    def _parse_output(
        self, llm_output: str, chunk_text: str
    ) -> List[Dict[str, Any]]:
        items = self._parse_jsonl(llm_output)
        items = self._validate_items(items)
        triples: List[Dict[str, Any]] = []

        for item in items:
            subject = str(item.get("subject", "")).strip()
            predicate = str(item.get("predicate", "")).strip()
            obj = str(item.get("object", "")).strip()
            object_is_node = bool(item.get("object-entity", False))

            if not subject or not predicate or not obj:
                continue

            # 3-tier predicate resolution: exact → fuzzy → free-form
            extraction_method = "llm_relationships"
            ontology = get_namespace(predicate)

            if ontology:
                # Tier 1: exact match
                predicate_name = predicate
            else:
                # Tier 2: fuzzy match
                fuzzy = fuzzy_match(predicate, threshold=0.8)
                if fuzzy:
                    predicate_name = fuzzy[0]
                    ontology = fuzzy[1]
                    extraction_method = "llm_relationships_fuzzy"
                else:
                    # Tier 3: free-form → generate URI
                    predicate_name = _normalize_predicate_name(predicate)
                    if not predicate_name:
                        continue
                    ontology = "extracted"
                    extraction_method = "llm_relationships_freeform"

            triples.append(
                self._make_triple(
                    subject=subject,
                    predicate_ontology=ontology,
                    predicate_name=predicate_name,
                    obj=obj,
                    object_is_node=object_is_node,
                    extraction_method=extraction_method,
                    source_chunk=chunk_text,
                )
            )

        return triples
