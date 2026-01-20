"""
Summarizer Agent - Executive Summary Specialist

Specialized agent for creating clear, actionable executive summaries
from documents and multi-document analyses.

System message is loaded from YAML configuration (emma_prompts.yaml).

FRAMEWORK: Qwen-Agent
Reference: https://github.com/QwenLM/Qwen-Agent

MIGRATION NOTE:
- Migrated from MS Agent Framework ChatAgent pattern
- Uses Assistant class with function_list (tool names as strings)
"""

import logging
from typing import Any

from qwen_agent.agents import Assistant

from app.services.rag.prompt_loader import get_agent_system_message

logger = logging.getLogger(__name__)

# Fallback message if YAML config not available
DEFAULT_SUMMARIZER_MSG = """You are an expert at creating clear, actionable executive summaries.
Your role is to condense complex information into concise summaries.
Always include tenant_id in all tool calls. End with "TASK_COMPLETE" when done."""


def create_summarizer_agent(
    llm_cfg: dict,
    name: str = "SummarizerAgent",
) -> Assistant:
    """
    Create a summarization specialist agent using Qwen-Agent.

    This agent excels at creating clear, actionable executive summaries
    from documents and analyses.

    Args:
        llm_cfg: Qwen-Agent LLM configuration dict (from get_llm_config())
        name: Agent name for identification

    Returns:
        Configured Assistant for summarization

    Example:
        >>> from app.agents.model_client import get_llm_config
        >>> llm_cfg = get_llm_config()
        >>> summarizer = create_summarizer_agent(llm_cfg)
    """
    system_message = get_agent_system_message("SummarizerAgent", DEFAULT_SUMMARIZER_MSG)
    logger.debug(f"Creating SummarizerAgent: name={name}")

    return Assistant(
        llm=llm_cfg,
        name=name,
        system_message=system_message,
        function_list=[
            'rag_answer',
            'summarize_documents',
            'get_document_content',
            'hybrid_search',
        ],
    )


def create_triage_agent(
    llm_cfg: dict,
    name: str = "TriageAgent",
) -> Assistant:
    """
    Create a coordinator agent for the handoff workflow.

    This agent analyzes incoming requests and routes them to the appropriate
    specialist agent using handoff mechanisms.

    In Qwen-Agent, handoffs are managed via the orchestrator that decides
    which specialist should handle the request based on the triage analysis.

    Args:
        llm_cfg: Qwen-Agent LLM configuration dict (from get_llm_config())
        name: Agent name for identification

    Returns:
        Configured Assistant as workflow coordinator
    """
    triage_instructions = """You are the coordinator agent that routes document analysis requests to specialist agents.

AVAILABLE SPECIALISTS:
- ContractAgent: Commercial contracts, service agreements, leases
- LaborAgent: Labor contracts, payroll (nóminas), sick leaves (bajas), dismissals, Social Security
- LegalAgent: Judicial documents, legal proceedings, administrative acts
- ComplianceAgent: GDPR/RGPD compliance, privacy regulations, data protection
- TaxDeclarationAgent: Income tax declarations (IRPF), Modelo 100, tax certificates
- SearchAgent: Document search and retrieval (only for search queries)
- SummarizerAgent: Executive summaries (use AFTER analysis is complete)

ROUTING RULES (follow strictly by document type):
1. LABOR DOCUMENTS (nóminas, contratos trabajo, bajas IT, despidos, finiquitos) → LaborAgent
2. COMMERCIAL CONTRACTS (arrendamiento, servicios, compraventa) → ContractAgent
3. LEGAL DOCUMENTS (sentencias, demandas, recursos, actos administrativos) → LegalAgent
4. TAX DECLARATIONS (IRPF, Modelo 100, declaración renta) → TaxDeclarationAgent
5. COMPLIANCE/GDPR (privacidad, protección datos) → ComplianceAgent
6. Search/find specific info → SearchAgent
7. Summary requests (after analysis) → SummarizerAgent

HOW TO IDENTIFY DOCUMENT TYPE:
- Contains "contrato de trabajo", "nómina", "baja", "despido", "finiquito", "Seguridad Social", "cotización" → LaborAgent
- Contains "contrato de arrendamiento", "contrato de servicios", "partes contratantes" (no laboral) → ContractAgent
- Contains "sentencia", "demanda", "juzgado", "recurso", "resolución judicial" → LegalAgent
- Contains "IRPF", "declaración de la renta", "Modelo 100", "retenciones" → TaxDeclarationAgent
- Contains "RGPD", "protección de datos", "privacidad" → ComplianceAgent

HANDOFF FORMAT:
Say: "Handing off to [AgentName] for [task description]"

CRITICAL RULES:
- Read the document content to identify the correct specialist
- LABOR documents go to LaborAgent (not ContractAgent)
- Do NOT default to SearchAgent for document analysis
- Follow the FLUJO DE AGENTES REQUERIDO if specified in the task
- Always hand off to SummarizerAgent at the end
"""

    logger.debug(f"Creating coordinator TriageAgent: name={name}")

    # Coordinator doesn't need tools - it only routes via handoffs
    return Assistant(
        llm=llm_cfg,
        name=name,
        system_message=triage_instructions,
        function_list=[],
    )
