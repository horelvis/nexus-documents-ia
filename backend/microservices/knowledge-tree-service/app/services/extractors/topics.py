"""
Topics extractor — extracts thematic topics from text chunks.

Each topic yields 1 triple:
  ("", core/has-topic, topic)

Subject is intentionally empty — the coordinator sets it to the document URI.
"""

from typing import Any, Dict, List

from app.services.extractors.base import BaseExtractor

EXTRACTOR_NAME = "topics"

_PROMPT_TEMPLATE = """Identify the main topics and themes present in the following text.

Return a JSON array where each element has:
- "topic": a concise topic label in the same language as the text (string)

Focus on substantive topics — legal areas, business domains, subject matter.
Avoid generic terms like "document" or "text".
Return an empty array [] if no clear topics can be identified.

Respond ONLY with a valid JSON array. Example:
[{{"topic": "derecho laboral"}},
 {{"topic": "contrato de trabajo"}},
 {{"topic": "jornada laboral"}}]

TEXT:
{chunk_text}"""


class TopicsExtractor(BaseExtractor):
    """Extracts thematic topics from text chunks."""

    EXTRACTOR_NAME = "topics"

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
            topic = str(item.get("topic", "")).strip()
            if not topic:
                continue

            # Subject is empty — coordinator will set it to document_uri
            triples.append(
                self._make_triple(
                    subject="",
                    predicate_ontology="core",
                    predicate_name="has-topic",
                    obj=topic,
                    object_is_node=False,
                    extraction_method="llm_topics",
                    source_chunk=chunk_text,
                )
            )

        return triples
