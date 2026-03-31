"""
Unified Config Registry — Singleton accessor.

Returns a single unified SectorConfig for all queries. The knowledge graph
provides dynamic per-query context; static sector selection is no longer used.

ACTIVE_SECTOR env var is ignored. All domains use the same balanced defaults.
"""

import logging
from typing import Dict, Optional

from .config import (
    SectorConfig,
    UNIFIED_ENTITY_PATTERNS,
    UNIFIED_RERANK_WEIGHTS,
    UNIFIED_GRAPH_SEARCH_PROPERTIES,
)
from .predictive_config import PREDICTIVE_CONFIGS

logger = logging.getLogger(__name__)

# =============================================================================
# Unified Configuration (replaces per-sector SECTOR_CONFIGS)
# =============================================================================

_UNIFIED_CONFIG = SectorConfig(
    name="Unified (Graph-Dynamic)",
    hybrid_alpha=0.6,
    top_k=12,
    rerank_enabled=True,
    entity_patterns=UNIFIED_ENTITY_PATTERNS,
    rerank_weights=UNIFIED_RERANK_WEIGHTS,
    graph_search_properties=UNIFIED_GRAPH_SEARCH_PROPERTIES,
    guardrail_profile="global",
    fidelity_confidence_cap=0.80,
    max_evidence=5,
    hitl_default=False,
    explain_guidance="Usa lenguaje accesible. Cita fuentes por nombre completo.",
    predictive_config=PREDICTIVE_CONFIGS.get("generic"),
)

# Legacy compat: code that does SECTOR_CONFIGS.get("legal") still works
SECTOR_CONFIGS: Dict[str, SectorConfig] = {
    "legal": _UNIFIED_CONFIG,
    "medical": _UNIFIED_CONFIG,
    "documental": _UNIFIED_CONFIG,
}


# =============================================================================
# Singleton accessor
# =============================================================================

def get_active_sector_config() -> Optional[SectorConfig]:
    """
    Get the unified configuration (always returns the same config).

    The knowledge graph provides dynamic context per query, so there is
    no need for per-sector static configs. ACTIVE_SECTOR is ignored.
    """
    return _UNIFIED_CONFIG
