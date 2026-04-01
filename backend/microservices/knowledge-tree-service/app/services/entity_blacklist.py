"""
EntityBlacklist — filters generic concepts from entity extraction.

Loads terms from config/entity_blacklist.yaml on first access.
Matching is case-insensitive and accent-insensitive (NFD + strip combining).
"""

import logging
import unicodedata
from pathlib import Path
from typing import FrozenSet

import yaml

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "entity_blacklist.yaml"

# Module-level singleton: loaded once, shared across all instances
_loaded_terms: FrozenSet[str] | None = None


def _normalize(text: str) -> str:
    """Lowercase + strip accents for comparison."""
    nfd = unicodedata.normalize("NFD", text.strip())
    stripped = "".join(ch for ch in nfd if unicodedata.category(ch) != "Mn")
    return stripped.lower()


def _load_terms() -> FrozenSet[str]:
    """Load and normalize all blacklist terms from YAML config."""
    global _loaded_terms
    if _loaded_terms is not None:
        return _loaded_terms

    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except FileNotFoundError:
        logger.warning("Blacklist config not found at %s — using empty blacklist", _CONFIG_PATH)
        _loaded_terms = frozenset()
        return _loaded_terms

    terms = set()
    for category, items in data.items():
        if isinstance(items, list):
            for item in items:
                if isinstance(item, str) and item.strip():
                    terms.add(_normalize(item))

    _loaded_terms = frozenset(terms)
    logger.info("EntityBlacklist loaded %d terms from %s", len(_loaded_terms), _CONFIG_PATH)
    return _loaded_terms


class EntityBlacklist:
    """Check entity names against a static blacklist.

    Thread-safe singleton — terms are loaded once at module level.
    """

    @property
    def terms(self) -> FrozenSet[str]:
        return _load_terms()

    def is_blacklisted(self, name: str) -> bool:
        """Return True if the name matches a blacklisted term."""
        if not name or not name.strip():
            return False
        return _normalize(name) in self.terms
