"""
Dynamic Prompt Loader for Emma v2

Loads specialized prompts based on detected domain.
Instead of loading ALL agent prompts (~4250 tokens), loads only what's needed (~200-750 tokens).

Architecture:
    ┌─────────────────────────────────────────────────────────────┐
    │                  Dynamic Prompt Loader                      │
    │                                                             │
    │   Domain Detection → Load Domain Prompt → Build System Msg  │
    │                                                             │
    │   Token Budget:                                             │
    │   ├── Base context (Emma identity): ~200 tokens             │
    │   └── Domain prompt (if needed): ~500-750 tokens            │
    │   ────────────────────────────────────────────              │
    │   Total: ~700-950 tokens (vs ~4250 with all agents)         │
    │                                                             │
    │   This leaves ~7000+ tokens for:                            │
    │   ├── Query                                                 │
    │   ├── RAG context (contextualized chunks)                   │
    │   ├── Conversation history                                  │
    │   └── Response                                              │
    └─────────────────────────────────────────────────────────────┘

The key insight from the plan: instead of having knowledge in prompts,
we're moving towards Contextual Retrieval where knowledge is IN the chunks.
This loader provides:
1. Emma's base identity and tools
2. Domain-specific procedural guidance (checklists, workflows)
3. NOT the full legal knowledge (that comes from contextualized RAG)
"""

import logging
from functools import lru_cache
from pathlib import Path
from typing import Dict, Optional

import yaml

from .domain_router import DomainType

logger = logging.getLogger(__name__)

# Agent name mapping for backward compatibility with emma_prompts.yaml
DOMAIN_TO_AGENT_NAME: Dict[DomainType, str] = {
    DomainType.LABOR: "LaborAgent",
    DomainType.FISCAL: "FiscalAgent",
    DomainType.PRIVACY: "PrivacyAgent",
    DomainType.REALESTATE: "RealEstateAgent",
    DomainType.CONTRACT: "ContractAgent",
    DomainType.COMPLIANCE: "ComplianceAgent",
    DomainType.EDUCATION: "EducationAgent",
    DomainType.LEGAL: "LegalAgent",
    DomainType.GENERAL: "EmmaCoordinator",
}

# Minimal Emma identity prompt (without hardcoded terminology)
# The terminology for folders/documents is learned from each tenant's data
EMMA_MINIMAL_IDENTITY = """Eres Emma, asistente de gestión documental (EDMS) para NouxCubeIA.

## HERRAMIENTAS

- `search` → Buscar documentos del usuario por contenido semántico
- `read_document` → Leer contenido completo de un documento específico
- `analyze` → Análisis profundo de documentos (riesgos, compliance, resumen)
- `legal_search` → Buscar normativas, leyes y jurisprudencia en fuentes públicas (BOE, etc.)
- `ask_user` → SOLO usar cuando realmente necesites información que NO puedes obtener de otra forma

## REGLAS

- Responde en el MISMO idioma del usuario
- Cita fuentes: [1], [2], etc.
- NUNCA inventes información - si no sabes, di que no encontraste información
- Para análisis de compliance: PRIMERO busca el documento, LUEGO usa legal_search para la normativa, FINALMENTE analiza
- NO pidas al usuario información que puedas buscar tú mismo (leyes, artículos, normativas)
- Sé PROACTIVO: busca la información necesaria en lugar de pedir clarificaciones innecesarias"""

# Token-optimized domain prompts (procedural guidance only, not full knowledge)
# Full legal knowledge comes from Contextual Retrieval chunks
DOMAIN_PROCEDURAL_GUIDANCE: Dict[DomainType, str] = {
    DomainType.LABOR: """## Labor Law Analysis Framework

When analyzing labor documents:

1. **Contract Review Checklist**
   - Identify contract type (indefinido, temporal, formación)
   - Check mandatory clauses (jornada, salario, funciones)
   - Verify legal limits (Art. 34-38 ET for time/vacations)
   - Flag any clauses that may violate worker protections

2. **Payroll Verification**
   - Base salary matches contract
   - Legal deductions (SS, IRPF) are correct
   - Extras and bonuses properly reflected

3. **Termination Analysis**
   - Verify legal cause cited
   - Check notice periods
   - Calculate severance if applicable

Reference Spanish legislation when relevant (ET, convenio colectivo).
Always verify against the specific collective agreement if mentioned.""",

    DomainType.FISCAL: """## Fiscal Document Analysis Framework

When analyzing fiscal documents:

1. **Invoice Verification**
   - Mandatory fields (NIF, fecha, base, tipo IVA)
   - IVA calculation (21%, 10%, 4%, exento)
   - Deductibility requirements

2. **Tax Declaration Review**
   - Correct forms used (303, 390, 100, 200)
   - Periods and deadlines
   - Deductions and credits applied

3. **Compliance Check**
   - Format requirements per AEAT
   - Digital signature if required
   - Retention obligations

Flag discrepancies with LGT and specific tax regulations.""",

    DomainType.PRIVACY: """## Privacy & Data Protection Framework

When analyzing privacy documents:

1. **RGPD Compliance Checklist**
   - Legal basis identified (Art. 6)
   - Purposes clearly specified
   - Data minimization principle
   - Retention periods defined

2. **Rights Verification**
   - Access, rectification, erasure procedures
   - Portability mechanisms
   - Objection process

3. **Security Assessment**
   - Technical measures described
   - Organizational measures in place
   - Breach notification process

Reference RGPD articles and LOPDGDD when applicable.""",

    DomainType.REALESTATE: """## Real Estate Document Analysis Framework

When analyzing real estate documents:

1. **Lease Agreement Checklist**
   - Parties correctly identified
   - Property description complete
   - Rent and update mechanism (IPC, índice referencia)
   - Duration and renewal terms (LAU requirements)
   - Deposit (fianza) per law

2. **Purchase Documentation**
   - Title verification
   - Encumbrances check (cargas)
   - Payment terms

3. **LAU Compliance (Residential)**
   - Minimum duration requirements
   - Tenant protections
   - Landlord obligations

Reference LAU (Ley 29/1994) for residential leases.""",

    DomainType.CONTRACT: """## General Contract Analysis Framework

When analyzing contracts:

1. **Essential Elements**
   - Parties identification (capacity, representation)
   - Object clearly defined
   - Consideration (precio, contraprestación)
   - Form requirements if any

2. **Key Clauses Review**
   - Obligations of each party
   - Duration and termination
   - Liability and indemnification
   - Dispute resolution

3. **Risk Identification**
   - Unfair terms (especially B2C)
   - Missing essential clauses
   - Ambiguous language

Apply Spanish Civil Code (Código Civil) principles.""",

    DomainType.COMPLIANCE: """## Compliance Assessment Framework

When analyzing compliance:

1. **Regulatory Mapping**
   - Identify applicable regulations
   - Check implementation requirements
   - Verify documentation

2. **Control Assessment**
   - Control existence and design
   - Operating effectiveness
   - Gap identification

3. **Risk-Based Approach**
   - Materiality assessment
   - Impact analysis
   - Remediation priorities

Reference applicable standards (ISO, industry-specific).""",

    DomainType.EDUCATION: """## Educational Document Framework

When analyzing educational documents:

1. **Academic Records**
   - Credential verification
   - ECTS/credit validation
   - Degree recognition

2. **Institutional Documents**
   - Registration requirements
   - Academic policies
   - Student rights

Reference applicable education regulations.""",

    DomainType.LEGAL: """## Legal Document Analysis Framework

When analyzing legal documents:

1. **Document Classification**
   - Type (demanda, sentencia, contrato, escritura)
   - Jurisdiction and forum
   - Parties and representation

2. **Procedural Review**
   - Deadlines and terms
   - Required formalities
   - Appeal options

3. **Substance Analysis**
   - Legal basis cited
   - Arguments structure
   - Conclusions and orders

Apply relevant procedural and substantive law.""",
}


class DynamicPromptLoader:
    """
    Loads system prompts dynamically based on detected domain.

    Key design decisions:
    1. Minimal base prompt (~200 tokens) for Emma identity
    2. Domain prompts provide PROCEDURAL guidance (~500 tokens)
    3. LEGAL KNOWLEDGE comes from Contextual Retrieval, not prompts

    This approach:
    - Reduces prompt token usage by 80%+
    - Maintains specialized guidance per domain
    - Allows SIL-detected domains to influence prompt selection
    """

    def __init__(self, prompts_path: Optional[Path] = None):
        """
        Initialize the prompt loader.

        Args:
            prompts_path: Path to emma_prompts.yaml (auto-detected if None)
        """
        self._prompts_path = prompts_path
        self._yaml_cache: Optional[Dict] = None
        self._yaml_mtime: float = 0

    def _find_prompts_file(self) -> Optional[Path]:
        """Find the emma_prompts.yaml file."""
        if self._prompts_path and self._prompts_path.exists():
            return self._prompts_path

        search_paths = [
            Path("/app/config/prompts/emma_prompts.yaml"),
            Path("./config/prompts/emma_prompts.yaml"),
            Path(__file__).parent.parent.parent / "config" / "prompts" / "emma_prompts.yaml",
        ]

        for path in search_paths:
            if path.exists():
                return path

        return None

    def _load_yaml(self, force_reload: bool = False) -> Dict:
        """Load YAML config with caching."""
        path = self._find_prompts_file()

        if path is None:
            logger.warning("emma_prompts.yaml not found, using built-in prompts")
            return {}

        current_mtime = path.stat().st_mtime

        if not force_reload and self._yaml_cache is not None:
            if self._yaml_mtime == current_mtime:
                return self._yaml_cache

        try:
            with open(path, 'r', encoding='utf-8') as f:
                self._yaml_cache = yaml.safe_load(f) or {}
                self._yaml_mtime = current_mtime
                logger.debug(f"Loaded prompts from {path}")
                return self._yaml_cache
        except Exception as e:
            logger.error(f"Error loading prompts: {e}")
            return {}

    def get_base_prompt(self) -> str:
        """
        Get Emma's base identity prompt including document management concepts.

        Returns:
            Base prompt string (~500-800 tokens) with EDMS knowledge
        """
        yaml_config = self._load_yaml()

        # Try to get context_root from YAML
        context_root = yaml_config.get("context_root", "")

        if context_root:
            # Allow more tokens for context_root since it includes important
            # document management concepts (expediente vs documento, etc.)
            return context_root[:2000]  # ~500 tokens max

        return EMMA_MINIMAL_IDENTITY

    def get_domain_prompt(self, domain: DomainType) -> str:
        """
        Get domain-specific procedural guidance.

        This provides checklists and analysis frameworks, NOT full legal knowledge.
        Legal knowledge comes from Contextual Retrieval chunks.

        Args:
            domain: Detected domain type

        Returns:
            Domain prompt string (~500 tokens) or empty for general
        """
        if domain == DomainType.GENERAL:
            return ""

        # First try YAML (for backward compatibility with existing setup)
        yaml_config = self._load_yaml()
        autogen_agents = yaml_config.get("autogen_agents", {})

        agent_name = DOMAIN_TO_AGENT_NAME.get(domain)
        if agent_name and agent_name in autogen_agents:
            agent_config = autogen_agents[agent_name]
            yaml_prompt = agent_config.get("system_message", "")
            if yaml_prompt:
                # Return truncated version to keep tokens under control
                # Original prompts are ~2500 chars each, we want ~2000 max
                return yaml_prompt[:2000]

        # Fallback to built-in procedural guidance
        return DOMAIN_PROCEDURAL_GUIDANCE.get(domain, "")

    def build_system_prompt(
        self,
        domain: DomainType,
        tenant_context: Optional[str] = None,
        additional_context: Optional[str] = None,
        learned_terminology: Optional[str] = None,
    ) -> str:
        """
        Build complete system prompt for Emma v2.

        Combines:
        1. Base identity (~200 tokens)
        2. Learned terminology from tenant data (DYNAMIC - not hardcoded!)
        3. Domain procedural guidance (~500 tokens if applicable)
        4. Tenant context (if provided)
        5. Additional context (SIL structural info)

        Total: ~700-1000 tokens (vs ~4250 with all agent prompts)

        Args:
            domain: Detected domain type
            tenant_context: Tenant-specific context string
            additional_context: Additional context (e.g., SIL structural info)
            learned_terminology: Terminology learned from tenant's data
                                (from TenantKnowledge.to_prompt_context())

        Returns:
            Complete system prompt
        """
        parts = []

        # 1. Base identity
        parts.append(self.get_base_prompt())

        # 2. Learned terminology from tenant data (CRITICAL for understanding)
        # This replaces hardcoded terms like "expediente", "contrato" with
        # what this specific tenant actually uses in their documents
        if learned_terminology:
            parts.append(f"\n\n{learned_terminology}")

        # 3. Domain guidance
        domain_prompt = self.get_domain_prompt(domain)
        if domain_prompt:
            parts.append(f"\n\n## Domain Context: {domain.value.title()}\n{domain_prompt}")

        # 4. Tenant context
        if tenant_context:
            parts.append(f"\n\n## Tenant Context\n{tenant_context}")

        # 5. Additional context
        if additional_context:
            parts.append(f"\n\n## Structural Context\n{additional_context}")

        return "\n".join(parts)

    def estimate_tokens(self, text: str) -> int:
        """
        Estimate token count for text.

        Uses simple char/4 heuristic (accurate enough for planning).

        Args:
            text: Text to estimate

        Returns:
            Estimated token count
        """
        return len(text) // 4


# Global singleton
dynamic_prompt_loader = DynamicPromptLoader()


def get_system_prompt_for_domain(
    domain: DomainType,
    tenant_context: Optional[str] = None,
    structural_context: Optional[str] = None,
    learned_terminology: Optional[str] = None,
) -> str:
    """
    Convenience function to get system prompt for a domain.

    Args:
        domain: Detected domain type
        tenant_context: Tenant-specific context
        structural_context: SIL structural context
        learned_terminology: Terminology learned from tenant's data
                            (from TenantKnowledge.to_prompt_context())

    Returns:
        Complete system prompt
    """
    return dynamic_prompt_loader.build_system_prompt(
        domain=domain,
        tenant_context=tenant_context,
        additional_context=structural_context,
        learned_terminology=learned_terminology,
    )
