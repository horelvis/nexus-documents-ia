"""
Definitions extractor — extracts named entities with their definitions.

Each entity yields 2 triples:
  (entity, core/label, entity_name)
  (entity, core/definition, definition_text)
"""

import logging
from typing import Any, Dict, List

from app.services.extractors.base import BaseExtractor

logger = logging.getLogger(__name__)

EXTRACTOR_NAME = "definitions"
LANGFUSE_PROMPT_NAME = "trustgraph_extract_definitions"

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "entity": {"type": "string", "minLength": 1},
        "definition": {"type": "string"},
    },
    "required": ["entity"],
}

_PROMPT_TEMPLATE = """Extract all named entities and their definitions from the following text.

Return one JSON object per line (JSONL format). Do NOT wrap in an array.
Each object must have:
- "entity": the canonical name of the entity (string)
- "definition": a concise description or definition of the entity from the text (string)

Only include entities that are explicitly defined or described in the text.
Return nothing if no definitions are found.

Example:
{{"entity": "Contrato de Trabajo", "definition": "Acuerdo entre empleador y trabajador que regula las condiciones laborales"}}
{{"entity": "Empresa ABC S.L.", "definition": "Sociedad limitada dedicada al desarrollo de software"}}

TEXT:
{chunk_text}"""


class DefinitionsExtractor(BaseExtractor):
    """Extracts entity definitions from text chunks."""

    EXTRACTOR_NAME = "definitions"
    RESPONSE_SCHEMA = RESPONSE_SCHEMA

    def _build_prompt(self, chunk_text: str) -> str:
        langfuse_prompt = self._get_langfuse_prompt(LANGFUSE_PROMPT_NAME)
        if langfuse_prompt:
            return langfuse_prompt.replace("{{chunk_text}}", chunk_text)
        return _PROMPT_TEMPLATE.format(chunk_text=chunk_text)

    def _parse_output(
        self, llm_output: str, chunk_text: str
    ) -> List[Dict[str, Any]]:
        items = self._parse_jsonl(llm_output)
        items = self._validate_items(items)
        triples: List[Dict[str, Any]] = []

        for item in items:
            entity = str(item.get("entity", "")).strip()
            definition = str(item.get("definition", "")).strip()
            if not entity:
                continue

            # Triple 1: label
            triples.append(
                self._make_triple(
                    subject=entity,
                    predicate_ontology="core",
                    predicate_name="label",
                    obj=entity,
                    object_is_node=False,
                    extraction_method="llm_definitions",
                    source_chunk=chunk_text,
                )
            )
            # Triple 2: definition
            if definition:
                triples.append(
                    self._make_triple(
                        subject=entity,
                        predicate_ontology="core",
                        predicate_name="definition",
                        obj=definition,
                        object_is_node=False,
                        extraction_method="llm_definitions",
                        source_chunk=chunk_text,
                    )
                )

        return triples
