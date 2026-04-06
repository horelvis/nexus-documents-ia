"""
Sector-aware Entity Extractor

Extracts domain entities from queries using regex patterns defined
in the active SectorConfig. No LLM calls — pure regex for speed.

Usage:
    from app.agents.langgraph.sectors.entity_extractor import extract_entities

    entities = extract_entities(
        query="Art. 1902 del Código Civil",
        patterns=sector_config.entity_patterns,
    )
    # Returns: {"articulo": ["Art. 1902"], ...}
"""

import logging
import re
import unicodedata
from typing import Dict, List

logger = logging.getLogger(__name__)

_PERSON_CONNECTORS = {"de", "del", "la", "las", "los", "y"}
_PERSON_STOPWORDS = {
    "ley", "real", "decreto", "codigo", "civil", "proteccion", "datos",
    "normativa", "reglamento", "estatuto", "articulo", "boe",
    "factura", "contrato", "nomina", "informe", "expediente",
    "documento", "archivo", "carpeta", "empresa", "departamento",
    "compliance", "rgpd", "lopdgdd", "lprl", "lisos", "et", "lgss",
}


def _normalize_token(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    no_accents = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return re.sub(r"[^\w]", "", no_accents).lower()


def _is_valid_person_candidate(text: str) -> bool:
    """Reject non-person entities accidentally matched by broad name regex."""
    tokens = [t.strip(".,;:()[]{}\"'") for t in text.split() if t.strip(".,;:()[]{}\"'")]
    if len(tokens) < 2 or len(tokens) > 5:
        return False

    normalized_tokens = [_normalize_token(t) for t in tokens]
    has_stopword = any(t in _PERSON_STOPWORDS for t in normalized_tokens)
    if has_stopword:
        return False

    # Require at least 2 capitalized non-connector tokens (e.g., "Ana de la Fuente")
    proper_count = 0
    for original, normalized in zip(tokens, normalized_tokens):
        if normalized in _PERSON_CONNECTORS:
            continue
        if original[:1].isupper() and len(normalized) > 1:
            proper_count += 1
    return proper_count >= 2


def extract_entities(
    query: str,
    patterns: Dict[str, List[str]],
) -> Dict[str, List[str]]:
    """
    Extract entities from a query using sector-specific regex patterns.

    Args:
        query: User query text
        patterns: Dict mapping entity type to list of regex patterns

    Returns:
        Dict mapping entity type to list of matched strings.
        Only types with matches are included.
    """
    results: Dict[str, List[str]] = {}

    # Types that rely on capitalization for accuracy (must NOT use IGNORECASE)
    _CASE_SENSITIVE_TYPES = {"persona"}

    for entity_type, regex_list in patterns.items():
        matches: List[str] = []
        for pattern_str in regex_list:
            try:
                flags = 0 if entity_type in _CASE_SENSITIVE_TYPES else re.IGNORECASE
                compiled = re.compile(pattern_str, flags)
                for match in compiled.finditer(query):
                    matched_text = match.group(0).strip()
                    if entity_type == "persona" and not _is_valid_person_candidate(matched_text):
                        continue
                    if matched_text and matched_text not in matches:
                        matches.append(matched_text)
            except re.error as e:
                logger.warning(f"Invalid regex for {entity_type}: {pattern_str} — {e}")

        if matches:
            results[entity_type] = matches

    if results:
        total = sum(len(v) for v in results.values())
        logger.debug(f"Extracted {total} entities: {results}")

    return results
