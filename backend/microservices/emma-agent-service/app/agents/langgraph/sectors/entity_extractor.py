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
from typing import Dict, List

logger = logging.getLogger(__name__)


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

    for entity_type, regex_list in patterns.items():
        matches: List[str] = []
        for pattern_str in regex_list:
            try:
                compiled = re.compile(pattern_str, re.IGNORECASE)
                for match in compiled.finditer(query):
                    matched_text = match.group(0).strip()
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
