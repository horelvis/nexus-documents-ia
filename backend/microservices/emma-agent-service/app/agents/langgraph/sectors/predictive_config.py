"""
Predictive Analysis Configuration per Sector.

Defines PredictiveConfig dataclass and pre-built configurations for each sector.
The active config is resolved from ACTIVE_SECTOR env var via get_predictive_config().

Each sector defines:
- factor_types: What kinds of factors to extract
- outcome_labels: How to label predictions (sector-specific language)
- verification_sources: Where to search for supporting evidence
- system_prompt_key: Which prompts to use from predictive_prompts.yaml
- disclaimer: Legal/medical/technical disclaimer text
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class PredictiveConfig:
    """Configuration for predictive analysis per sector."""
    factor_types: List[str]
    outcome_labels: Dict[str, str]  # {key: display_label}
    verification_sources: List[str]  # "weaviate", "graph", "web"
    max_factors: int = 10
    confidence_threshold: float = 0.7
    system_prompt_key: str = ""
    disclaimer: str = ""


# =============================================================================
# Pre-built Predictive Configurations per Sector
# =============================================================================

PREDICTIVE_CONFIGS: Dict[str, PredictiveConfig] = {
    # -----------------------------------------------------------------
    # LEGAL — Predict judicial outcome based on jurisprudence
    # -----------------------------------------------------------------
    "legal": PredictiveConfig(
        factor_types=[
            "contract_breach",
            "statute_violation",
            "precedent",
            "procedural_defect",
            "evidence_strength",
        ],
        outcome_labels={
            "favorable": "Favorable",
            "unfavorable": "Desfavorable",
            "mixed": "Parcialmente estimado",
        },
        verification_sources=["weaviate", "graph", "jurisprudence", "web"],
        system_prompt_key="predictive.legal",
        disclaimer=(
            "⚠️ Esta predicción es orientativa y NO sustituye el criterio profesional. "
            "Consulte con un abogado cualificado antes de tomar decisiones legales."
        ),
    ),

    # -----------------------------------------------------------------
    # MEDICAL — Analyze clinical report against protocols
    # -----------------------------------------------------------------
    "medical": PredictiveConfig(
        factor_types=[
            "diagnosis_accuracy",
            "protocol_compliance",
            "medication_risk",
            "contraindication",
            "procedure_adherence",
        ],
        outcome_labels={
            "conforme": "Conforme",
            "no_conforme": "No Conforme",
            "observacion": "Con Observaciones",
        },
        verification_sources=["weaviate"],
        system_prompt_key="predictive.medical",
        disclaimer=(
            "⚠️ Este análisis es orientativo y NO constituye diagnóstico médico. "
            "Consulte con un profesional sanitario cualificado."
        ),
    ),

    # -----------------------------------------------------------------
    # DOCUMENTAL — Verify report against standards/regulations
    # -----------------------------------------------------------------
    "documental": PredictiveConfig(
        factor_types=[
            "regulatory_compliance",
            "standard_adherence",
            "completeness",
            "accuracy",
            "timeliness",
        ],
        outcome_labels={
            "cumple": "Cumple",
            "no_cumple": "No Cumple",
            "parcial": "Cumplimiento Parcial",
        },
        verification_sources=["weaviate", "web"],
        system_prompt_key="predictive.documental",
        disclaimer=(
            "⚠️ Este análisis es orientativo. "
            "Verifique el cumplimiento con un auditor o técnico cualificado."
        ),
    ),

    # -----------------------------------------------------------------
    # GENERIC — Fallback when no sector is configured
    # -----------------------------------------------------------------
    "generic": PredictiveConfig(
        factor_types=[
            "risk_factor",
            "compliance_factor",
            "quality_factor",
            "impact_factor",
            "probability_factor",
        ],
        outcome_labels={
            "positive": "Favorable",
            "negative": "Desfavorable",
            "neutral": "Neutro",
        },
        verification_sources=["weaviate", "web"],
        system_prompt_key="predictive.generic",
        disclaimer=(
            "⚠️ Este análisis es orientativo y se basa en los documentos disponibles. "
            "Consulte con un profesional cualificado para decisiones importantes."
        ),
    ),
}


# =============================================================================
# Accessor
# =============================================================================

_predictive_config: Optional[PredictiveConfig] = None
_predictive_initialized: bool = False


def get_predictive_config(sector_override: Optional[str] = None) -> PredictiveConfig:
    """
    Get the predictive analysis configuration.

    Args:
        sector_override: Optional sector to use instead of ACTIVE_SECTOR.

    Returns:
        PredictiveConfig for the active/overridden sector, or generic fallback.
    """
    if sector_override:
        return PREDICTIVE_CONFIGS.get(sector_override, PREDICTIVE_CONFIGS["generic"])

    global _predictive_config, _predictive_initialized

    if _predictive_initialized:
        return _predictive_config

    _predictive_initialized = True

    import os
    active_sector = os.getenv("ACTIVE_SECTOR", "").strip().lower()

    if active_sector and active_sector in PREDICTIVE_CONFIGS:
        _predictive_config = PREDICTIVE_CONFIGS[active_sector]
    else:
        _predictive_config = PREDICTIVE_CONFIGS["generic"]

    return _predictive_config
