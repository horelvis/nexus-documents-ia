"""
Unified Prompt Registry — Single source of truth for all Langfuse prompt names.

Langfuse is the ONLY prompt source at runtime. YAML is only used by the
seed script (scripts/seed_langfuse_prompts.py) to populate Langfuse initially.

Adding a new prompt:
    1. Add an entry to PROMPT_REGISTRY below
    2. Add the corresponding YAML content in config/prompts/emma_prompts.yaml
    3. Run: python scripts/seed_langfuse_prompts.py --dry-run  (verify)
    4. Run: python scripts/seed_langfuse_prompts.py             (seed missing only)
    5. To force-overwrite existing: python scripts/seed_langfuse_prompts.py --force
"""

from dataclasses import dataclass, field
from typing import Dict, Tuple


@dataclass(frozen=True)
class PromptEntry:
    """A prompt registered in the system."""

    yaml_path: Tuple[str, ...]
    """Path into emma_prompts.yaml (e.g., ("react_agent", "system"))."""

    description: str
    """Human-readable description of what this prompt does."""

    section: str = ""
    """Logical section for filtering in the seed script (e.g., "react", "predictive")."""

    prompt_type: str = "text"
    """Langfuse prompt type. Almost always "text"."""


# =============================================================================
# PROMPT_REGISTRY — all known Langfuse prompt names
# =============================================================================
# Merge of langfuse_prompt_client.name_mapping (runtime) and
# seed_langfuse_prompts.PROMPT_REGISTRY (seeding).
#
# Convention: emma_{feature}_{system|user|evaluator}

PROMPT_REGISTRY: Dict[str, PromptEntry] = {
    # ── Core prompts ─────────────────────────────────────────────────────────
    "emma_context_root": PromptEntry(
        yaml_path=("context_root",),
        description="Global context injected into all interactions",
        section="core",
    ),
    "emma_synthesis": PromptEntry(
        yaml_path=("system_prompts", "synthesis"),
        description="Final synthesis system prompt",
        section="core",
    ),
    "emma_planning": PromptEntry(
        yaml_path=("system_prompts", "planning"),
        description="Planning system prompt",
        section="core",
    ),

    # ── Action instructions ──────────────────────────────────────────────────
    "emma_action_generate": PromptEntry(
        yaml_path=("action_instructions", "generate"),
        description="Instruction for generate action",
        section="actions",
    ),
    "emma_action_retrieve": PromptEntry(
        yaml_path=("action_instructions", "retrieve"),
        description="Instruction for retrieve action",
        section="actions",
    ),
    "emma_action_analyze": PromptEntry(
        yaml_path=("action_instructions", "analyze"),
        description="Instruction for analyze action",
        section="actions",
    ),
    "emma_action_search": PromptEntry(
        yaml_path=("action_instructions", "search"),
        description="Instruction for search action",
        section="actions",
    ),
    "emma_action_compare": PromptEntry(
        yaml_path=("action_instructions", "compare"),
        description="Instruction for compare action",
        section="actions",
    ),

    # ── Sector system prompts ────────────────────────────────────────────────
    "emma_sector_legal": PromptEntry(
        yaml_path=("sectors", "legal", "system_prompt"),
        description="Legal sector system prompt",
        section="sectors",
    ),
    "emma_sector_medical": PromptEntry(
        yaml_path=("sectors", "medical", "system_prompt"),
        description="Medical sector system prompt",
        section="sectors",
    ),
    "emma_sector_documental": PromptEntry(
        yaml_path=("sectors", "documental", "system_prompt"),
        description="Documental sector system prompt",
        section="sectors",
    ),

    # ── Sector generation prompts ────────────────────────────────────────────
    "emma_sector_legal_generation": PromptEntry(
        yaml_path=("sectors", "legal", "generation_prompt"),
        description="Legal sector generation prompt",
        section="sectors",
    ),
    "emma_sector_medical_generation": PromptEntry(
        yaml_path=("sectors", "medical", "generation_prompt"),
        description="Medical sector generation prompt",
        section="sectors",
    ),
    "emma_sector_documental_generation": PromptEntry(
        yaml_path=("sectors", "documental", "generation_prompt"),
        description="Documental sector generation prompt",
        section="sectors",
    ),

    # ── Social channel ───────────────────────────────────────────────────────
    "emma_social_system": PromptEntry(
        yaml_path=("social_channels", "system_prompt"),
        description="Social channel agent system prompt",
        section="social",
    ),

    # ── Heartbeat ────────────────────────────────────────────────────────────
    "emma_heartbeat_evaluator": PromptEntry(
        yaml_path=("heartbeat", "evaluation_system"),
        description="Heartbeat insight evaluation prompt",
        section="heartbeat",
    ),

    # ── Fast-path (classify node — no tools) ─────────────────────────────────
    "emma_fast_conversational_system": PromptEntry(
        yaml_path=("fast_path", "conversational_system"),
        description="Fast-path system prompt for greetings, identity, farewells",
        section="fast_path",
    ),
    "emma_fast_general_knowledge_system": PromptEntry(
        yaml_path=("fast_path", "general_knowledge_system"),
        description="Fast-path system prompt for general knowledge (code, math, translations)",
        section="fast_path",
    ),

    # ── ReAct Agent (main reasoning loop) ────────────────────────────────────
    "emma_react_system": PromptEntry(
        yaml_path=("react_agent", "system"),
        description="ReAct agent system prompt",
        section="react",
    ),
    "emma_react_next_step": PromptEntry(
        yaml_path=("react_agent", "next_step"),
        description="ReAct next-step reasoning prompt",
        section="react",
    ),

    # ── Memory Recall (MemoRAG clue generation) ──────────────────────────────
    "emma_memory_recall_system": PromptEntry(
        yaml_path=("memory_recall", "system"),
        description="Memory recall clue generation system prompt",
        section="memory_recall",
    ),

    # ── Swarm Agent (parallel sub-agent execution) ───────────────────────────
    "emma_swarm_decompose": PromptEntry(
        yaml_path=("swarm", "decompose_system"),
        description="Decompose complex query into parallel sub-tasks",
        section="swarm",
    ),
    "emma_swarm_synthesize": PromptEntry(
        yaml_path=("swarm", "synthesize_system"),
        description="Synthesize swarm worker results into final answer",
        section="swarm",
    ),

    # ── Swarm Worker per-focus prompts (optional, Langfuse-only) ─────────────
    "emma_swarm_worker_document_search": PromptEntry(
        yaml_path=("swarm", "worker_document_search"),
        description="Worker profile: document search specialist",
        section="swarm",
    ),
    "emma_swarm_worker_legislation_search": PromptEntry(
        yaml_path=("swarm", "worker_legislation_search"),
        description="Worker profile: legislation search specialist",
        section="swarm",
    ),
    "emma_swarm_worker_jurisprudence_search": PromptEntry(
        yaml_path=("swarm", "worker_jurisprudence_search"),
        description="Worker profile: jurisprudence search specialist",
        section="swarm",
    ),
    "emma_swarm_worker_domain_analysis": PromptEntry(
        yaml_path=("swarm", "worker_domain_analysis"),
        description="Worker profile: domain analysis specialist",
        section="swarm",
    ),
    "emma_swarm_worker_web_search": PromptEntry(
        yaml_path=("swarm", "worker_web_search"),
        description="Worker profile: web search specialist",
        section="swarm",
    ),
    "emma_swarm_worker_structural_query": PromptEntry(
        yaml_path=("swarm", "worker_structural_query"),
        description="Worker profile: structural query specialist",
        section="swarm",
    ),

    # ── Predictive Analysis ──────────────────────────────────────────────────
    "emma_predictive_factor_system": PromptEntry(
        yaml_path=("predictive", "factor_extraction", "system"),
        description="Factor extraction system prompt",
        section="predictive",
    ),
    "emma_predictive_factor_user_first": PromptEntry(
        yaml_path=("predictive", "factor_extraction", "user_first"),
        description="First factor extraction user prompt",
        section="predictive",
    ),
    "emma_predictive_factor_user_next": PromptEntry(
        yaml_path=("predictive", "factor_extraction", "user_next"),
        description="Subsequent factor extraction user prompt",
        section="predictive",
    ),
    "emma_predictive_completion_system": PromptEntry(
        yaml_path=("predictive", "completion_check", "system"),
        description="Predictive completion check system prompt",
        section="predictive",
    ),
    "emma_predictive_completion_user": PromptEntry(
        yaml_path=("predictive", "completion_check", "user"),
        description="Predictive completion check user prompt",
        section="predictive",
    ),
    "emma_predictive_outcome_system": PromptEntry(
        yaml_path=("predictive", "outcome_evaluation", "system"),
        description="Outcome evaluation system prompt",
        section="predictive",
    ),
    "emma_predictive_outcome_user": PromptEntry(
        yaml_path=("predictive", "outcome_evaluation", "user"),
        description="Outcome evaluation user prompt",
        section="predictive",
    ),
    "emma_predictive_weight_system": PromptEntry(
        yaml_path=("predictive", "factor_weighting", "system"),
        description="Factor weighting system prompt",
        section="predictive",
    ),
    "emma_predictive_weight_user": PromptEntry(
        yaml_path=("predictive", "factor_weighting", "user"),
        description="Factor weighting user prompt",
        section="predictive",
    ),
    "emma_predictive_recommendation_system": PromptEntry(
        yaml_path=("predictive", "recommendation", "system"),
        description="Prediction recommendation system prompt",
        section="predictive",
    ),
    "emma_predictive_recommendation_user": PromptEntry(
        yaml_path=("predictive", "recommendation", "user"),
        description="Prediction recommendation user prompt",
        section="predictive",
    ),

    # ── Verified Generation ──────────────────────────────────────────────────
    "emma_verified_claim_system": PromptEntry(
        yaml_path=("verified_generation", "claim_generation", "system"),
        description="Verified claim generation system prompt",
        section="verified_generation",
    ),
    "emma_verified_claim_user_first": PromptEntry(
        yaml_path=("verified_generation", "claim_generation", "user_first"),
        description="First verified claim user prompt",
        section="verified_generation",
    ),
    "emma_verified_claim_user_next": PromptEntry(
        yaml_path=("verified_generation", "claim_generation", "user_next"),
        description="Subsequent verified claim user prompt",
        section="verified_generation",
    ),
    "emma_verified_completion_system": PromptEntry(
        yaml_path=("verified_generation", "completion_check", "system"),
        description="Verified document completion check system prompt",
        section="verified_generation",
    ),
    "emma_verified_completion_user": PromptEntry(
        yaml_path=("verified_generation", "completion_check", "user"),
        description="Verified document completion check user prompt",
        section="verified_generation",
    ),
    "emma_verified_factcheck_system": PromptEntry(
        yaml_path=("verified_generation", "fact_checking", "system"),
        description="Verified fact-checking system prompt",
        section="verified_generation",
    ),
    "emma_verified_factcheck_user": PromptEntry(
        yaml_path=("verified_generation", "fact_checking", "user"),
        description="Verified fact-checking user prompt",
        section="verified_generation",
    ),

    # ── Verified Generation — Two-Tier Verification ──────────────────────────
    "emma_verified_faithfulness_system": PromptEntry(
        yaml_path=("verified_generation", "faithfulness", "system"),
        description="Tier 1: Faithfulness NLI verification system prompt",
        section="verified_generation",
    ),
    "emma_verified_faithfulness_user": PromptEntry(
        yaml_path=("verified_generation", "faithfulness", "user"),
        description="Tier 1: Faithfulness NLI verification user prompt",
        section="verified_generation",
    ),
    "emma_verified_external_system": PromptEntry(
        yaml_path=("verified_generation", "external_verification", "system"),
        description="Tier 2: External corroboration system prompt",
        section="verified_generation",
    ),
    "emma_verified_external_user": PromptEntry(
        yaml_path=("verified_generation", "external_verification", "user"),
        description="Tier 2: External corroboration user prompt",
        section="verified_generation",
    ),
    "emma_verified_summary_system": PromptEntry(
        yaml_path=("verified_generation", "summary", "system"),
        description="Verified document summary system prompt",
        section="verified_generation",
    ),
    "emma_verified_summary_user": PromptEntry(
        yaml_path=("verified_generation", "summary", "user"),
        description="Verified document summary user prompt",
        section="verified_generation",
    ),

    # ── Retrieval Guard ──────────────────────────────────────────────────────
    "emma_guard_low_quality": PromptEntry(
        yaml_path=("retrieval_guard", "warnings", "low_quality"),
        description="Retrieval guard: low quality warning",
        section="guard",
    ),
    "emma_guard_single_source": PromptEntry(
        yaml_path=("retrieval_guard", "warnings", "single_source"),
        description="Retrieval guard: single source warning",
        section="guard",
    ),
    "emma_guard_corrective": PromptEntry(
        yaml_path=("retrieval_guard", "corrective_message"),
        description="Retrieval guard: corrective action message",
        section="guard",
    ),

    # ── Guardrail prompts ─────────────────────────────────────────────────
    "guardrail_medical_dosage_system": PromptEntry(
        yaml_path=("guardrails", "medical_dosage", "system"),
        description="System prompt for medical dosage coherence validation guardrail",
        section="guardrails",
    ),
    "guardrail_medical_dosage_user": PromptEntry(
        yaml_path=("guardrails", "medical_dosage", "user"),
        description="User prompt template for medical dosage validation",
        section="guardrails",
    ),

    # ── Rewrite node (query contextualization) ─────────────────────────────
    "emma_rewrite_system": PromptEntry(
        yaml_path=("rewrite", "system"),
        description="Rewrite node: contextualize follow-up queries using conversation history",
        section="rewrite",
    ),

    # ── Domain specialist prompts (analyze_domain tool) ────────────────────
    "emma_domain_legal": PromptEntry(
        yaml_path=("domain_specialists", "legal"),
        description="Domain specialist: Spanish law and legislation",
        section="domain_specialists",
    ),
    "emma_domain_labor": PromptEntry(
        yaml_path=("domain_specialists", "labor"),
        description="Domain specialist: Spanish labor law",
        section="domain_specialists",
    ),
    "emma_domain_fiscal": PromptEntry(
        yaml_path=("domain_specialists", "fiscal"),
        description="Domain specialist: Spanish tax and fiscal law",
        section="domain_specialists",
    ),
    "emma_domain_contract": PromptEntry(
        yaml_path=("domain_specialists", "contract"),
        description="Domain specialist: contract analysis",
        section="domain_specialists",
    ),
    "emma_domain_compliance": PromptEntry(
        yaml_path=("domain_specialists", "compliance"),
        description="Domain specialist: regulatory compliance",
        section="domain_specialists",
    ),
    "emma_domain_privacy": PromptEntry(
        yaml_path=("domain_specialists", "privacy"),
        description="Domain specialist: data protection and privacy (GDPR/LOPDGDD)",
        section="domain_specialists",
    ),
    "emma_domain_general": PromptEntry(
        yaml_path=("domain_specialists", "general"),
        description="Domain specialist: general document management",
        section="domain_specialists",
    ),
    "emma_domain_docgen": PromptEntry(
        yaml_path=("domain_specialists", "docgen"),
        description="Domain specialist: business document generation",
        section="domain_specialists",
    ),
    "emma_domain_realestate": PromptEntry(
        yaml_path=("domain_specialists", "realestate"),
        description="Domain specialist: real estate law (LAU, LPH)",
        section="domain_specialists",
    ),
    "emma_domain_education": PromptEntry(
        yaml_path=("domain_specialists", "education"),
        description="Domain specialist: education law (LOMLOE, LOE, LOU)",
        section="domain_specialists",
    ),

    # ── RLM Processor (recursive large document pipeline) ──────────────────
    "emma_rlm_chunk_system": PromptEntry(
        yaml_path=("rlm", "chunk_system"),
        description="RLM: system prompt for processing individual document chunks",
        section="rlm",
    ),
    "emma_rlm_chunk_user": PromptEntry(
        yaml_path=("rlm", "chunk_user"),
        description="RLM: user prompt template for document chunk processing",
        section="rlm",
    ),
    "emma_rlm_aggregate_system": PromptEntry(
        yaml_path=("rlm", "aggregate_system"),
        description="RLM: system prompt for aggregating chunk results",
        section="rlm",
    ),
    "emma_rlm_aggregate_user": PromptEntry(
        yaml_path=("rlm", "aggregate_user"),
        description="RLM: user prompt template for aggregating chunk results",
        section="rlm",
    ),

    # ── Guardrail fallback messages (sector-specific blocked content) ──────
    "emma_guardrail_sector_medical": PromptEntry(
        yaml_path=("guardrail_fallback", "medical"),
        description="Guardrail: blocked content message for medical sector",
        section="guardrail_fallback",
    ),
    "emma_guardrail_sector_legal": PromptEntry(
        yaml_path=("guardrail_fallback", "legal"),
        description="Guardrail: blocked content message for legal sector",
        section="guardrail_fallback",
    ),
    "emma_guardrail_sector_documental": PromptEntry(
        yaml_path=("guardrail_fallback", "documental"),
        description="Guardrail: blocked content message for documental sector",
        section="guardrail_fallback",
    ),
    "emma_guardrail_default": PromptEntry(
        yaml_path=("guardrail_fallback", "default"),
        description="Guardrail: default blocked content message (all sectors)",
        section="guardrail_fallback",
    ),

    # ── Memory Generator (document indexing memory) ────────────────────────
    "emma_memory_generator_system": PromptEntry(
        yaml_path=("memory_generator", "system"),
        description="Memory generator: system prompt for document memory extraction",
        section="memory_generator",
    ),
    "emma_memory_generator_user": PromptEntry(
        yaml_path=("memory_generator", "user"),
        description="Memory generator: user prompt template for document memory extraction",
        section="memory_generator",
    ),

    # ── Quality Gate (CRAG corrective messages) ────────────────────────────
    "emma_quality_corrective_no_tools": PromptEntry(
        yaml_path=("quality_corrective", "no_tools"),
        description="Quality gate: corrective message when LLM skips tool usage on step 0",
        section="quality_corrective",
    ),
    "emma_quality_corrective_low_quality": PromptEntry(
        yaml_path=("quality_corrective", "low_quality"),
        description="Quality gate: corrective message for incomplete/unsourced answers",
        section="quality_corrective",
    ),
    "emma_quality_corrective_low_retrieval": PromptEntry(
        yaml_path=("quality_corrective", "low_retrieval"),
        description="Quality gate: corrective message for low-quality search results",
        section="quality_corrective",
    ),
    "emma_quality_corrective_faithfulness": PromptEntry(
        yaml_path=("quality_corrective", "faithfulness"),
        description="Quality gate: corrective message for fabricated/ungrounded data",
        section="quality_corrective",
    ),
}


def get_all_sections() -> list[str]:
    """Return sorted list of unique section names."""
    return sorted({e.section for e in PROMPT_REGISTRY.values() if e.section})


def get_yaml_path_map() -> Dict[str, Tuple[str, ...]]:
    """Return {name: yaml_path} dict — drop-in replacement for old name_mapping."""
    return {name: entry.yaml_path for name, entry in PROMPT_REGISTRY.items()}
