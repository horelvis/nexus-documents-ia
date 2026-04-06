"""
Topics extractor — extracts thematic topics from text chunks.

Each topic yields 1 triple:
  ("", core/has-topic, topic)

Subject is intentionally empty — the coordinator sets it to the document URI.
"""

import logging
from typing import Any, Dict, List

from app.services.extractors.base import BaseExtractor

logger = logging.getLogger(__name__)

EXTRACTOR_NAME = "topics"
LANGFUSE_PROMPT_NAME = "trustgraph_extract_topics"

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "topic": {"type": "string", "minLength": 1},
    },
    "required": ["topic"],
}

_PROMPT_TEMPLATE = """Identify the main topics and themes present in the following text.

Return one JSON object per line (JSONL format). Do NOT wrap in an array.
Each object must have:
- "topic": a concise topic label in the same language as the text (string)

Focus on substantive topics — legal areas, business domains, subject matter.
Avoid generic terms like "document" or "text".
Return nothing if no clear topics can be identified.

Example:
{{"topic": "derecho laboral"}}
{{"topic": "contrato de trabajo"}}
{{"topic": "jornada laboral"}}

TEXT:
{chunk_text}"""


class TopicsExtractor(BaseExtractor):
    """Extracts thematic topics from text chunks."""

    EXTRACTOR_NAME = "topics"
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
            topic = str(item.get("topic", "")).strip()
            if not topic:
                continue

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
