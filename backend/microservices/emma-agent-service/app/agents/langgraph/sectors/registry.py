"""
Sector Registry — Pre-built configurations and singleton accessor.

Loads the active sector from ACTIVE_SECTOR env var once at import time.
If ACTIVE_SECTOR is not set or empty, get_active_sector_config() returns None
and the system runs in generic mode (all agents, default params).
"""

import logging
import os
from typing import Dict, Optional

from .config import Sector, SectorConfig
from .predictive_config import PREDICTIVE_CONFIGS

logger = logging.getLogger(__name__)

# =============================================================================
# Pre-built Sector Configurations
# =============================================================================

SECTOR_CONFIGS: Dict[str, SectorConfig] = {
    # -----------------------------------------------------------------
    # LEGAL sector — Spanish legal document management
    # -----------------------------------------------------------------
    Sector.LEGAL.value: SectorConfig(
        name="Legal (Derecho Español)",
        sector=Sector.LEGAL,
        agents=[
            "legal_agent",
            "labor_agent",
            "fiscal_agent",
            "contract_agent",
            "compliance_agent",
            "privacy_agent",
            "docgen_agent",
        ],
        default_agent="legal_agent",
        hybrid_alpha=0.7,
        top_k=12,
        rerank_enabled=True,
        chunk_strategy="legal_sections",
        chunk_size=1500,
        chunk_overlap=200,
        entity_patterns={
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
                r"(?:BOE(?:-[A-Z])?\s*(?:núm\.?\s*)?\d+)",
            ],
            "expediente": [
                r"(?:[Ee]xpediente\s+(?:n[úu]m\.?\s*)?[\w/-]+)",
            ],
        },
        graph_name="",
        graph_schema="",
        system_prompt_key="sectors.legal",
        men_domain="legal",
        predictive_config=PREDICTIVE_CONFIGS.get("legal"),
        rerank_weights={
            "similarity": 0.35, "quality": 0.15, "graph": 0.30,
            "recency": 0.05, "entity": 0.15,
        },
        graph_search_properties=["title", "short_name", "boe_id", "domain"],
        guardrail_profile="legal",
        fidelity_confidence_cap=0.80,
        max_evidence=5,
        hitl_default=False,
        explain_guidance="Usa terminología jurídica. Cita artículos y leyes por nombre completo.",
    ),

    # -----------------------------------------------------------------
    # MEDICAL sector — Healthcare document management
    # -----------------------------------------------------------------
    Sector.MEDICAL.value: SectorConfig(
        name="Medical (Gestión Sanitaria)",
        sector=Sector.MEDICAL,
        agents=[
            "general_agent",  # Until dedicated medical_agent is built
        ],
        default_agent="general_agent",
        hybrid_alpha=0.6,
        top_k=15,
        rerank_enabled=True,
        chunk_strategy="paragraph",
        chunk_size=1200,
        chunk_overlap=150,
        entity_patterns={
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
        },
        graph_name="",
        graph_schema="",
        system_prompt_key="sectors.medical",
        men_domain="technical",
        predictive_config=PREDICTIVE_CONFIGS.get("medical"),
        rerank_weights={
            "similarity": 0.40, "quality": 0.25, "graph": 0.15,
            "recency": 0.10, "entity": 0.10,
        },
        graph_search_properties=["name", "code", "title"],
        guardrail_profile="medical",
        fidelity_confidence_cap=0.60,
        max_evidence=15,
        hitl_default=True,
        explain_guidance="Usa terminología clínica. Referencia protocolos y normativa sanitaria.",
    ),

    # -----------------------------------------------------------------
    # DOCUMENTAL sector — General document/records management
    # -----------------------------------------------------------------
    Sector.DOCUMENTAL.value: SectorConfig(
        name="Documental (Gestión Documental)",
        sector=Sector.DOCUMENTAL,
        agents=[
            "general_agent",
            "education_agent",
            "realestate_agent",
        ],
        default_agent="general_agent",
        hybrid_alpha=0.5,
        top_k=10,
        rerank_enabled=False,
        chunk_strategy="semantic",
        chunk_size=1000,
        chunk_overlap=100,
        entity_patterns={
            "persona": [
                # Spanish/international proper names: "Javier Martinez", "María García López",
                # "Ana de la Fuente" (with common prepositions)
                r"(?:[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+(?:de(?:\s+la)?|del|y)\s+)*(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)+)",
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
                # Strict reference extractor: avoids matching verbs like "Explica"
                # by requiring a full token prefix and a structured reference value.
                r"(?:\b(?:Ref|REF|Expediente|Exp)\b\.?\s*(?:[:#-]\s*|\s+)(?:[A-Z0-9][A-Z0-9/_-]{2,}))",
            ],
            "fecha": [
                r"(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
                r"(?:\d{1,2}\s+de\s+(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)\s+de\s+\d{4})",
            ],
        },
        graph_name="",
        graph_schema="",
        system_prompt_key="sectors.documental",
        men_domain="general",
        predictive_config=PREDICTIVE_CONFIGS.get("documental"),
        rerank_weights={
            "similarity": 0.35, "quality": 0.15, "graph": 0.20,
            "recency": 0.15, "entity": 0.15,
        },
        graph_search_properties=["name", "associated_person", "title"],
        guardrail_profile="documental",
        fidelity_confidence_cap=0.80,
        max_evidence=5,
        hitl_default=False,
    ),
}


# =============================================================================
# Singleton accessor
# =============================================================================

_active_sector_config: Optional[SectorConfig] = None
_initialized: bool = False


def get_active_sector_config() -> Optional[SectorConfig]:
    """
    Get the active sector configuration (singleton).

    Reads ACTIVE_SECTOR from environment on first call and caches the result.
    Returns None if no sector is configured (generic mode).

    Returns:
        SectorConfig for the active sector, or None for generic mode.
    """
    global _active_sector_config, _initialized

    if _initialized:
        return _active_sector_config

    _initialized = True

    active_sector = os.getenv("ACTIVE_SECTOR", "").strip().lower()

    if not active_sector:
        logger.info("No ACTIVE_SECTOR configured — running in generic mode")
        _active_sector_config = None
        return None

    if active_sector not in SECTOR_CONFIGS:
        valid = ", ".join(SECTOR_CONFIGS.keys())
        logger.error(
            f"Invalid ACTIVE_SECTOR='{active_sector}'. "
            f"Valid values: {valid}. Falling back to generic mode."
        )
        _active_sector_config = None
        return None

    _active_sector_config = SECTOR_CONFIGS[active_sector]
    logger.info(
        f"Active sector: {_active_sector_config.name} | "
        f"agents={_active_sector_config.agents} | "
        f"hybrid_alpha={_active_sector_config.hybrid_alpha} | "
        f"top_k={_active_sector_config.top_k}"
    )
    return _active_sector_config
