"""
OntologyRegistry — dynamic predicate validation from seed data.

Loads the predicate catalog from seed_ontology.PREDICATES and provides
lookup by predicate name → ontology namespace. This is the single source
of truth for predicate validation — no hardcoded frozensets in extractors.

To add a new predicate:
1. Add it to scripts/seed_ontology.py PREDICATES list
2. Run `python scripts/seed_ontology.py` to persist in FalkorDB
3. The registry auto-loads on next import — no code changes in extractors
"""

import logging
from difflib import SequenceMatcher
from typing import Dict, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# Lazy-loaded registry: predicate_name → ontology_namespace
_PREDICATE_MAP: Optional[Dict[str, str]] = None
_ALL_PREDICATES: Optional[Set[str]] = None

# Predicates that are system-only (prov/*) — not offered to the LLM for extraction
_SYSTEM_ONLY_NAMESPACES = frozenset(["prov"])


def _load_registry() -> Dict[str, str]:
    """Load predicate catalog from seed_ontology.PREDICATES."""
    global _PREDICATE_MAP, _ALL_PREDICATES
    if _PREDICATE_MAP is not None:
        return _PREDICATE_MAP

    try:
        import importlib
        import sys
        from pathlib import Path

        # Import PREDICATES from the seed script — try multiple paths
        # (container: /app/scripts/, dev: ../../scripts/)
        scripts_dir = str(Path(__file__).resolve().parent.parent / "scripts")
        alt_scripts_dir = "/app/scripts"
        for d in [scripts_dir, alt_scripts_dir]:
            if d not in sys.path:
                sys.path.insert(0, d)
        # Force re-import in case module was cached without the path
        if "seed_ontology" in sys.modules:
            importlib.reload(sys.modules["seed_ontology"])
        from seed_ontology import PREDICATES  # noqa: E402

        _PREDICATE_MAP = {}
        for ontology, name, *_ in PREDICATES:
            _PREDICATE_MAP[name] = ontology

        _ALL_PREDICATES = set(_PREDICATE_MAP.keys())
        logger.debug("OntologyRegistry loaded %d predicates", len(_PREDICATE_MAP))

    except Exception as exc:
        logger.warning("Failed to load ontology registry: %s — using empty registry", exc)
        _PREDICATE_MAP = {}
        _ALL_PREDICATES = set()

    return _PREDICATE_MAP


def get_namespace(predicate_name: str) -> Optional[str]:
    """Return the ontology namespace for a predicate, or None if unknown."""
    registry = _load_registry()
    return registry.get(predicate_name)


def is_valid_predicate(predicate_name: str) -> bool:
    """Check if a predicate is in the ontology."""
    registry = _load_registry()
    return predicate_name in registry


def get_extractable_predicates() -> Set[str]:
    """Return predicates available for LLM extraction (excludes prov/*)."""
    registry = _load_registry()
    return {name for name, ns in registry.items() if ns not in _SYSTEM_ONLY_NAMESPACES}


def fuzzy_match(predicate_name: str, threshold: float = 0.8) -> Optional[Tuple[str, str]]:
    """Fuzzy-match a predicate against the ontology.

    Normalizes by replacing underscores with hyphens and lowercasing,
    then uses SequenceMatcher for similarity scoring.

    Returns (matched_name, namespace) if similarity >= threshold, else None.
    """
    registry = _load_registry()
    if not registry:
        return None
    normalized = predicate_name.strip().lower().replace("_", "-")
    if normalized in registry:
        return (normalized, registry[normalized])
    best_name: Optional[str] = None
    best_score = 0.0
    extractable = {name for name, ns in registry.items() if ns not in _SYSTEM_ONLY_NAMESPACES}
    for name in extractable:
        score = SequenceMatcher(None, normalized, name).ratio()
        if score > best_score:
            best_score = score
            best_name = name
    if best_name and best_score >= threshold:
        return (best_name, registry[best_name])
    return None


def get_mini_ontology_text() -> str:
    """Generate the mini-ontology prompt text dynamically from the registry.

    Groups predicates by namespace and formats for LLM consumption.
    """
    registry = _load_registry()

    # Group by namespace, excluding system-only
    groups: Dict[str, list] = {}
    for name, ns in sorted(registry.items()):
        if ns in _SYSTEM_ONLY_NAMESPACES:
            continue
        groups.setdefault(ns, []).append(name)

    lines = ["REQUIRED PREDICATES (you MUST use ONLY these predicates, do not invent new ones):"]
    for ns in sorted(groups.keys()):
        predicates = ", ".join(sorted(groups[ns]))
        lines.append(f"  {ns}:{' ' * max(1, 13 - len(ns))}{predicates}")

    return "\n".join(lines)
