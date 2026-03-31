"""
Unified RAG Configuration

Single configuration for all domains. The knowledge graph provides
dynamic context per query — static sector configs are no longer needed.

Entity patterns from all domains (legal, medical, documental) are merged
into a single dict so any query benefits from comprehensive extraction.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Dict, List, Optional

if TYPE_CHECKING:
    from .predictive_config import PredictiveConfig

logger = logging.getLogger(__name__)

_REQUIRED_RERANK_WEIGHTS = {"similarity", "quality", "graph", "recency", "entity"}


# ── Merged entity patterns (legal + medical + documental) ───────────
UNIFIED_ENTITY_PATTERNS: Dict[str, List[str]] = {
    # Legal
    "ley": [
        r"(?:Ley\s+(?:Orgánica\s+)?\d+/\d{4})",
        r"(?:Real\s+Decreto(?:\s+Legislativo)?\s+\d+/\d{4})",
        r"(?:R\.?D\.?\s*\d+/\d{4})",
    ],
    "articulo": [
        r"(?:[Aa]rt(?:ículo)?\.?\s*\d+(?:\.\d+)*(?:\s*(?:bis|ter|quáter))?)",
    ],
    "sentencia": [
        r"(?:STS\s+\d+/\d{4})",
        r"(?:Sentencia\s+(?:del\s+)?(?:TS|TC|TSJ|AP)\s+(?:de\s+)?\d+)",
        r"(?:SAP\s+\w+\s+\d+/\d{4})",
    ],
    "boe": [
        r"(?:BOE(?:-[A-Z])?(?:\s*(?:núm\.?\s*)?\d+|-\d+))",
    ],
    "expediente": [
        r"(?:[Ee]xpediente\s+(?:n[úu]m\.?\s*)?[\w/-]+)",
    ],
    # Medical
    "cie10": [
        r"(?:[A-Z]\d{2}(?:\.\d{1,2})?)",
    ],
    "farmaco": [
        r"(?:(?:mg|ml|mcg|UI)\s*(?:/\s*(?:día|d|h|dosis))?)",
        r"(?:\d+\s*(?:mg|ml|mcg|UI))",
    ],
    "procedimiento": [
        r"(?:CIE-(?:9|10)-(?:MC|PCS)\s*[\w.]+)",
    ],
    "paciente": [
        r"(?:(?:H\.?\s*C\.?\s*|Historia\s+Clínica\s+)(?:n[úu]m\.?\s*)?[\w/-]+)",
        r"(?:NHC\s*[\w/-]+)",
    ],
    # Documental
    "persona": [
        # Spanish proper names: "Ana de la Fuente", "Pedro del Valle", "María García López"
        # Each segment: connector+Name (e.g., "de la Fuente") or just Name (e.g., "García")
        r"(?:[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+(?:de\s+la|de\s+los|del|de|y)\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+|\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)+)",
    ],
    "nif": [
        r"(?:[A-Z]\d{7}[A-Z0-9])",
        r"(?:\d{8}[A-Z])",
    ],
    "importe": [
        r"(?:\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?\s*€)",
        r"(?:€\s*\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)",
    ],
    "referencia": [
        r"(?:\b(?:Ref|REF|Expediente|Exp)\b\.?\s*(?:[:#-]\s*|\s+)(?:[A-Z0-9][A-Z0-9/_-]{2,}))",
    ],
    "fecha": [
        r"(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        r"(?:\d{1,2}\s+de\s+(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)\s+de\s+\d{4})",
    ],
}

# ── Balanced rerank weights (average of legal/medical/documental) ───
UNIFIED_RERANK_WEIGHTS: Dict[str, float] = {
    "similarity": 0.37,
    "quality": 0.18,
    "graph": 0.22,
    "recency": 0.10,
    "entity": 0.13,
}

# ── All graph search properties (union of all domains) ──────────────
UNIFIED_GRAPH_SEARCH_PROPERTIES: List[str] = [
    "name", "title", "short_name", "boe_id", "domain",
    "code", "associated_person",
]


@dataclass(frozen=True)
class SectorConfig:
    """
    Unified RAG pipeline configuration.

    Replaces per-sector configs. The knowledge graph provides dynamic
    context — this config holds balanced defaults for all domains.
    """
    name: str
    hybrid_alpha: float
    top_k: int
    rerank_enabled: bool
    entity_patterns: Dict[str, List[str]]
    rerank_weights: Dict[str, float] = field(default_factory=lambda: dict(UNIFIED_RERANK_WEIGHTS))
    graph_search_properties: List[str] = field(default_factory=lambda: list(UNIFIED_GRAPH_SEARCH_PROPERTIES))

    # Guardrail & Verification defaults
    guardrail_profile: str = "global"
    fidelity_confidence_cap: float = 0.80
    max_evidence: int = 5
    hitl_default: bool = False

    # Explanation guidance
    explain_guidance: str = "Usa lenguaje accesible. Cita fuentes por nombre completo."

    # Predictive config (resolved from predictive_config.py)
    predictive_config: Optional[PredictiveConfig] = None

    # Legacy compat — these are ignored but kept so serialized dicts don't break
    sector: str = ""
    agents: List[str] = field(default_factory=list)
    default_agent: str = ""
    chunk_strategy: str = "semantic"
    chunk_size: int = 1200
    chunk_overlap: int = 150
    system_prompt_key: str = ""
    men_domain: str = "general"
    collection_suffix: Optional[str] = None

    def __post_init__(self) -> None:
        if self.rerank_weights:
            keys = set(self.rerank_weights.keys())
            missing = _REQUIRED_RERANK_WEIGHTS - keys
            if missing:
                raise ValueError(
                    f"SectorConfig rerank_weights missing keys: {missing}. "
                    f"Required: {_REQUIRED_RERANK_WEIGHTS}"
                )
