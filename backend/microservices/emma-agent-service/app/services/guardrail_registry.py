"""
Guardrail Registry — Single source of truth for all system guardrails.

Pattern follows prompt_registry.py: dataclass entries imported by
seed_guardrails.py (SQL + Langfuse) and guardrail_service.py (runtime merge).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class GuardrailEntry:
    """A guardrail registered in the system."""
    name: str
    description: str
    guardrail_type: str  # regex | keyword | semantic | llm_validator | length | format
    action: str  # block | warn | redact
    config: Dict[str, Any]
    sector: Optional[str] = None  # None = global
    applies_to: List[str] = field(default_factory=list)  # empty = all agents
    priority: int = 100
    is_system: bool = True
    langfuse_prompt_key: Optional[str] = None


# =============================================================================
# GUARDRAIL ENTRIES — all 18 system guardrails
# =============================================================================

GUARDRAIL_ENTRIES: List[GuardrailEntry] = [
    # ── Global (5) — all sectors ──────────────────────────────────────────
    GuardrailEntry(
        name="global_pii_email",
        description="Redact email addresses from responses",
        guardrail_type="regex",
        action="redact",
        config={"pattern": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", "flags": "i"},
        priority=10,
    ),
    GuardrailEntry(
        name="global_pii_phone",
        description="Redact phone numbers (ES and international) from responses",
        guardrail_type="regex",
        action="redact",
        config={"pattern": r"(?:\+34\s?)?(?:\d{3}\s?\d{3}\s?\d{3}|\d{2}\s?\d{3}\s?\d{2}\s?\d{2})|\+\d{1,3}[\s.-]?\(?\d{1,4}\)?[\s.-]?\d{1,4}[\s.-]?\d{1,9}", "flags": ""},
        priority=10,
    ),
    GuardrailEntry(
        name="global_pii_national_id",
        description="Redact DNI/NIE/NIF from responses",
        guardrail_type="regex",
        action="redact",
        config={"pattern": r"\b\d{8}[A-Z]\b|\b[XYZ]\d{7}[A-Z]\b|\b[A-Z]\d{7}[A-Z0-9]\b", "flags": ""},
        priority=10,
    ),
    GuardrailEntry(
        name="global_pii_financial",
        description="Redact credit card numbers and IBAN from responses",
        guardrail_type="regex",
        action="redact",
        config={"pattern": r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b|\b[A-Z]{2}\d{2}\s?\d{4}\s?\d{4}\s?\d{4}\s?\d{4}\s?\d{4}\b", "flags": ""},
        priority=10,
    ),
    GuardrailEntry(
        name="global_min_response",
        description="Warn on suspiciously short responses (possible error)",
        guardrail_type="length",
        action="warn",
        config={"min_chars": 20},
        priority=90,
    ),

    # ── Medical (7) — ACTIVE_SECTOR=medical ───────────────────────────────
    GuardrailEntry(
        name="medical_phi_nhc",
        description="Redact NHC and Historia Clínica references from responses",
        guardrail_type="regex",
        action="redact",
        config={"pattern": r"(?:H\.?\s*C\.?\s*|Historia\s+Clínica\s+)(?:n[úu]m\.?\s*)?[\w/-]+|NHC\s*[\w/-]+", "flags": "i"},
        sector="medical",
        priority=5,
    ),
    GuardrailEntry(
        name="medical_no_diagnosis",
        description="Block responses that issue direct medical diagnoses",
        guardrail_type="keyword",
        action="block",
        config={"blocked_words": [
            "el diagnóstico es", "usted tiene", "usted padece",
            "padece de", "su diagnóstico", "le diagnostico",
        ]},
        sector="medical",
        priority=20,
    ),
    GuardrailEntry(
        name="medical_no_prescription",
        description="Block responses that issue direct prescriptions",
        guardrail_type="keyword",
        action="block",
        config={"blocked_words": [
            "le receto", "debe tomar", "prescripción:",
            "le prescribo", "tome usted",
        ]},
        sector="medical",
        priority=20,
    ),
    GuardrailEntry(
        name="medical_disclaimer",
        description="Inject medical disclaimer if not already present",
        guardrail_type="format",
        action="warn",
        config={
            "inject_text": "⚕️ Esta información es documental y no sustituye el criterio médico profesional.",
            "check_absent": "no sustituye el criterio médico",
        },
        sector="medical",
        priority=80,
    ),
    GuardrailEntry(
        name="medical_dosage_check",
        description="LLM-based validation of dosage coherence in medical responses",
        guardrail_type="llm_validator",
        action="warn",
        config={"threshold": 0.9},
        sector="medical",
        priority=50,
        langfuse_prompt_key="guardrail_medical_dosage_system",
    ),
    GuardrailEntry(
        name="medical_sensitive_topics",
        description="Warn on sensitive medical topics (suicide, self-harm) — high threshold to avoid false positives",
        guardrail_type="semantic",
        action="warn",
        config={"forbidden_topics": ["suicidio", "autolesión", "eutanasia sin contexto legal"], "similarity_threshold": 0.90},
        sector="medical",
        priority=30,
    ),
    GuardrailEntry(
        name="medical_patient_data",
        description="Redact dates of birth and clinical data identifiers",
        guardrail_type="regex",
        action="redact",
        config={"pattern": r"(?:fecha\s+de\s+nacimiento|nacido\s+el|F\.?\s*N\.?\s*:?\s*)\s*\d{1,2}[/-]\d{1,2}[/-]\d{2,4}", "flags": "i"},
        sector="medical",
        priority=5,
    ),

    # ── Legal (3) — ACTIVE_SECTOR=legal ───────────────────────────────────
    GuardrailEntry(
        name="legal_disclaimer",
        description="Inject legal disclaimer if not already present",
        guardrail_type="format",
        action="warn",
        config={
            "inject_text": "⚖️ Esta información no constituye asesoramiento jurídico profesional.",
            "check_absent": "no constituye asesoramiento jurídico",
        },
        sector="legal",
        priority=80,
    ),
    GuardrailEntry(
        name="legal_no_verdict",
        description="Warn when response contains verdict-like statements",
        guardrail_type="keyword",
        action="warn",
        config={"blocked_words": [
            "el tribunal debe fallar", "la sentencia será", "el veredicto debe ser",
        ]},
        sector="legal",
        priority=50,
    ),
    GuardrailEntry(
        name="legal_source_citation",
        description="Warn if legal response lacks article/law citations",
        guardrail_type="format",
        action="warn",
        config={"require_pattern": r"Art\.?\s*\d+|Ley\s+\d+|Real\s+Decreto"},
        sector="legal",
        priority=70,
    ),

    # ── Documental (3) — ACTIVE_SECTOR=documental ─────────────────────────
    GuardrailEntry(
        name="documental_disclaimer",
        description="Inject informational disclaimer if not already present",
        guardrail_type="format",
        action="warn",
        config={
            "inject_text": "ℹ️ Esta información tiene carácter orientativo.",
            "check_absent": "carácter orientativo",
        },
        sector="documental",
        priority=80,
    ),
    GuardrailEntry(
        name="documental_source_required",
        description="Warn if response lacks source references",
        guardrail_type="format",
        action="warn",
        config={"must_contain_sources": True},
        sector="documental",
        priority=70,
    ),
    GuardrailEntry(
        name="documental_length_limit",
        description="Warn on excessively long documental responses",
        guardrail_type="length",
        action="warn",
        config={"max_chars": 8000},
        sector="documental",
        priority=90,
    ),
]


def get_guardrails_for_sector(sector: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Get guardrails applicable to a sector.

    Returns global guardrails (sector=None) + sector-specific guardrails,
    sorted by priority (lower = higher priority).

    Args:
        sector: The active sector name, or None for global-only.

    Returns:
        List of guardrail dicts compatible with GuardrailService internal format.
    """
    applicable = []
    for entry in GUARDRAIL_ENTRIES:
        if entry.sector is None or entry.sector == sector:
            applicable.append({
                "id": f"registry:{entry.name}",  # Synthetic ID for registry entries
                "tenant_id": None,
                "guardrail_name": entry.name,
                "description": entry.description,
                "guardrail_type": entry.guardrail_type,
                "config": entry.config,
                "action_on_match": entry.action,
                "applies_to": entry.applies_to,
                "priority": entry.priority,
                "is_active": True,
                "sector": entry.sector,
                "is_system": True,
            })

    applicable.sort(key=lambda g: g["priority"])
    return applicable
