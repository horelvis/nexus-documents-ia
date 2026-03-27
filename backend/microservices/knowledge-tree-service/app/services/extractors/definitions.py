"""
Definitions extractor — extracts named entities with their definitions.

Each entity yields 2 triples:
  (entity, core/label, entity_name)
  (entity, core/definition, definition_text)
"""

from typing import Any, Dict, List

from app.services.extractors.base import BaseExtractor

EXTRACTOR_NAME = "definitions"

_PROMPT_TEMPLATE = """Extract all named entities and their definitions from the following text.

Return a JSON array where each element has:
- "entity": the canonical name of the entity (string)
- "definition": a concise description or definition of the entity from the text (string)

Only include entities that are explicitly defined or described in the text.
Return an empty array [] if no definitions are found.

Respond ONLY with a valid JSON array. Example:
[{{"entity": "Contrato de Trabajo", "definition": "Acuerdo entre empleador y trabajador que regula las condiciones laborales"}}]

TEXT:
{chunk_text}"""


class DefinitionsExtractor(BaseExtractor):
    """Extracts entity definitions from text chunks."""

    EXTRACTOR_NAME = "definitions"

    def _build_prompt(self, chunk_text: str) -> str:
        return _PROMPT_TEMPLATE.format(chunk_text=chunk_text)

    def _parse_output(
        self, llm_output: str, chunk_text: str
    ) -> List[Dict[str, Any]]:
        items = self._safe_parse_json(llm_output)
        triples: List[Dict[str, Any]] = []

        for item in items:
            if not isinstance(item, dict):
                continue
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
