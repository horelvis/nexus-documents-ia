"""
Shared Concept Extractor — LLM-based query decomposition with regex fallback.

Decomposes a user query into high-level themes (semantic concepts) and
low-level entities (names, legal refs, document types).

Used by:
- Graph RAG: concept embeddings → entity vector search in TrustGraphEntities
- SmartSearch (future): multi-concept parallel hybrid search

Pipeline:
  1. Call planner LLM with Langfuse prompt `trustgraph_extract_concepts`
  2. Parse JSON response → high_level_keywords + low_level_keywords
  3. Batch embed all concepts via intelligence-docs-service
  4. Return ConceptResult

Falls back to regex extraction on any LLM failure.
"""

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class ConceptResult:
    """Extracted concepts from a user query.

    Attributes:
        high_level: Broad thematic concepts (e.g., "derecho laboral", "contrato mercantil")
        low_level: Specific named entities, legal refs, doc types
                   (e.g., "ET", "Juan García", "factura")
        embeddings: Map from concept text → embedding vector (1024-dim BGE-M3).
                    Empty when fallback was used (LLM failure or embed failure).
    """

    high_level: List[str] = field(default_factory=list)
    low_level: List[str] = field(default_factory=list)
    embeddings: Dict[str, List[float]] = field(default_factory=dict)

    @property
    def all_concepts(self) -> List[str]:
        """All concepts combined (high + low level), deduplicated."""
        seen = set()
        result = []
        for c in self.high_level + self.low_level:
            norm = c.strip().lower()
            if norm and norm not in seen:
                seen.add(norm)
                result.append(c.strip())
        return result


# ---------------------------------------------------------------------------
# Regex patterns (Spanish legal/business domain)
# ---------------------------------------------------------------------------

# Person names preceded by prepositions or honorifics
_PERSON_PATTERN = re.compile(
    r"\b(?:de|para|sobre|empleado|trabajador[a]?|sr\.?|sra\.?|don|doña|d\.)\s+"
    r"([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+){0,3})",
    re.UNICODE,
)

# Legal acronyms and law references
_LEGAL_PATTERN = re.compile(
    r"\b(?:L(?:ey)?\.?\s*(?:Orgánica\s+)?|R\.?D\.?\s*|ET|LGT|LIRPF|LIS|LIVA|LSC|CC|LEC|LPRL|LGSS)"
    r"(?:\s+\d+/\d+)?",
    re.UNICODE | re.IGNORECASE,
)

# Document types
_DOC_TYPE_PATTERN = re.compile(
    r"\b(factura|contrato|nómina|nomina|informe|expediente|acta|presupuesto|certificado|escritura)\b",
    re.UNICODE | re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Fallback: regex-based extraction
# ---------------------------------------------------------------------------


def _fallback_regex_concepts(query: str) -> ConceptResult:
    """Extract concepts using regex patterns — no LLM, no embeddings.

    Used when the LLM is unavailable or times out.
    Returns ConceptResult with empty embeddings dict.
    """
    if not query or not query.strip():
        return ConceptResult()

    low_level: List[str] = []
    seen: set = set()

    # Person names
    for match in _PERSON_PATTERN.finditer(query):
        name = match.group(1).strip()
        key = name.lower()
        if key not in seen:
            seen.add(key)
            low_level.append(name)

    # Legal references
    for match in _LEGAL_PATTERN.finditer(query):
        ref = match.group(0).strip()
        key = ref.lower()
        if key not in seen and len(ref) >= 2:
            seen.add(key)
            low_level.append(ref.upper() if len(ref) <= 6 else ref)

    # Document types
    for match in _DOC_TYPE_PATTERN.finditer(query):
        doc_type = match.group(1).strip().lower()
        if doc_type not in seen:
            seen.add(doc_type)
            low_level.append(doc_type)

    return ConceptResult(high_level=[], low_level=low_level, embeddings={})


# ---------------------------------------------------------------------------
# LLM call
# ---------------------------------------------------------------------------


async def _call_llm(query: str) -> Any:
    """Call the planner model with the concept extraction prompt.

    Fetches the `trustgraph_extract_concepts` prompt from Langfuse and
    invokes the planner ChatOpenAI model with a system + user message.

    Returns: LangChain AIMessage response object.
    Raises: Exception on LLM or prompt fetch failure.
    """
    from langchain_core.messages import SystemMessage, HumanMessage
    from app.agents.llm_models import get_planner_model
    from app.services.langfuse_prompt_client import get_langfuse_prompt_client

    client = get_langfuse_prompt_client()
    system_cached = await client.get_prompt("trustgraph_extract_concepts")
    system_prompt = system_cached.content if system_cached else (
        "Extract high-level themes and low-level named entities from the query. "
        "Return JSON: {\"high_level_keywords\": [...], \"low_level_keywords\": [...]}"
    )

    model = get_planner_model()
    response = await model.ainvoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=query),
    ])
    return response


# ---------------------------------------------------------------------------
# Batch embed
# ---------------------------------------------------------------------------


async def _batch_embed(concepts: List[str], tenant_id: str) -> Dict[str, List[float]]:
    """Batch embed a list of concept strings via intelligence-docs-service.

    Calls POST /embed with `texts` + `task=retrieval.query`.
    Returns a map: concept_text → embedding_vector.
    On failure returns an empty dict (embeddings are optional).
    """
    if not concepts:
        return {}

    from app.core.config import settings

    # Embeddings live in intelligence-docs-service (not text_extraction_service)
    base = os.getenv(
        "INTELLIGENCE_DOCS_SERVICE_URL",
        settings.text_extraction_service_url,
    )
    url = f"{base}/embed"

    try:
        async with httpx.AsyncClient(timeout=15.0) as http_client:
            response = await http_client.post(
                url,
                json={"texts": concepts, "task": "retrieval.query"},
                headers={
                    "X-API-Key": settings.MICROSERVICES_API_KEY,
                    "X-Tenant-ID": tenant_id,
                },
            )
            response.raise_for_status()
            data = response.json()
            vectors: List[List[float]] = data.get("embeddings", [])

        if len(vectors) != len(concepts):
            logger.warning(
                f"concept_extractor: embed returned {len(vectors)} vectors for {len(concepts)} concepts"
            )
            return {}

        return {concept: vector for concept, vector in zip(concepts, vectors)}

    except Exception as e:
        logger.warning(f"concept_extractor: batch embed failed: {e}")
        return {}


# ---------------------------------------------------------------------------
# JSON parsing helpers
# ---------------------------------------------------------------------------


def _parse_concepts_json(content: str) -> Optional[Dict[str, List[str]]]:
    """Parse JSON from LLM response, handling markdown code blocks.

    Returns dict with high_level_keywords and low_level_keywords lists,
    or None on parse failure.
    """
    if not content:
        return None

    # Strip thinking tags
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
    if "<think>" in content:
        content = content[: content.find("<think>")].strip()

    # Strip markdown code blocks: ```json ... ``` or ``` ... ```
    md_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", content)
    if md_match:
        content = md_match.group(1).strip()

    # Find first JSON object in response
    json_match = re.search(r"\{[\s\S]*\}", content)
    if not json_match:
        logger.warning(f"concept_extractor: no JSON found in: {content[:200]}")
        return None

    try:
        data = json.loads(json_match.group(0))
    except json.JSONDecodeError as e:
        logger.warning(f"concept_extractor: JSON parse error: {e} — content: {content[:200]}")
        return None

    # Normalize to lists of strings
    high = data.get("high_level_keywords", [])
    low = data.get("low_level_keywords", [])

    if not isinstance(high, list):
        high = []
    if not isinstance(low, list):
        low = []

    return {
        "high_level_keywords": [str(c).strip() for c in high if c],
        "low_level_keywords": [str(c).strip() for c in low if c],
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def extract_concepts(query: str, tenant_id: str) -> ConceptResult:
    """Decompose a query into high-level themes and low-level entities.

    Pipeline:
      1. LLM call (planner model + Langfuse prompt)
      2. Parse JSON → high_level + low_level lists
      3. Batch embed all concepts
      4. Return ConceptResult

    Falls back to regex extraction (no embeddings) on any LLM failure.

    Args:
        query:     User query string to decompose.
        tenant_id: Tenant identifier (passed to embed service for auth).

    Returns:
        ConceptResult with concepts and optional embeddings.
    """
    if not query or not query.strip():
        return ConceptResult()

    try:
        response = await _call_llm(query)
        content = (response.content or "").strip()
        parsed = _parse_concepts_json(content)

        if parsed is None:
            logger.warning("concept_extractor: LLM returned unparseable response, using regex fallback")
            return _fallback_regex_concepts(query)

        high_level = parsed["high_level_keywords"]
        low_level = parsed["low_level_keywords"]
        all_concepts = list(dict.fromkeys(high_level + low_level))  # deduplicate, preserve order

        embeddings = await _batch_embed(all_concepts, tenant_id)

        return ConceptResult(
            high_level=high_level,
            low_level=low_level,
            embeddings=embeddings,
        )

    except Exception as e:
        logger.warning(f"concept_extractor: LLM extraction failed ({e}), using regex fallback")
        return _fallback_regex_concepts(query)
