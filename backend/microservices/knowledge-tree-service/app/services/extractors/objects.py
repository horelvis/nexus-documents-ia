"""
Objects extractor — extracts named entities with their types.

Each entity yields 2 triples:
  (entity, core/label, name)
  (entity, core/type, type)
"""

from typing import Any, Dict, List

from app.services.extractors.base import BaseExtractor

EXTRACTOR_NAME = "objects"

_PROMPT_TEMPLATE = """Extract all named entities (people, organizations, laws, places, dates, etc.) from the following text.

Return a JSON array where each element has:
- "name": the full canonical name of the entity (string)
- "type": entity type — one of: person, organization, law, place, date, amount, product, event, other

Return an empty array [] if no entities are found.

Respond ONLY with a valid JSON array. Example:
[{{"name": "María López", "type": "person"}},
 {{"name": "Empresa XYZ S.L.", "type": "organization"}},
 {{"name": "Estatuto de los Trabajadores", "type": "law"}}]

TEXT:
{chunk_text}"""


class ObjectsExtractor(BaseExtractor):
    """Extracts named entities with their types from text chunks."""

    EXTRACTOR_NAME = "objects"

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
            name = str(item.get("name", "")).strip()
            entity_type = str(item.get("type", "other")).strip()
            if not name:
                continue

            # Triple 1: label
            triples.append(
                self._make_triple(
                    subject=name,
                    predicate_ontology="core",
                    predicate_name="label",
                    obj=name,
                    object_is_node=False,
                    extraction_method="llm_objects",
                    source_chunk=chunk_text,
                )
            )
            # Triple 2: type
            triples.append(
                self._make_triple(
                    subject=name,
                    predicate_ontology="core",
                    predicate_name="type",
                    obj=entity_type,
                    object_is_node=False,
                    extraction_method="llm_objects",
                    source_chunk=chunk_text,
                )
            )

        return triples
