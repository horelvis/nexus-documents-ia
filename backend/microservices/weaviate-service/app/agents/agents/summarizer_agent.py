"""
Summarizer Agent - Executive Summary Specialist

Specialized agent for creating clear, actionable executive summaries
from documents and multi-document analyses.

System message is loaded from YAML configuration (emma_prompts.yaml).

FRAMEWORK: Microsoft Agent Framework
"""

import logging
from typing import Any

from agent_framework import ChatAgent

from app.services.rag.prompt_loader import get_agent_system_message

logger = logging.getLogger(__name__)

# Fallback message if YAML config not available
DEFAULT_SUMMARIZER_MSG = """You are an expert at creating clear, actionable executive summaries.
Your role is to condense complex information into concise summaries.
Always include tenant_id in all tool calls. End with "TASK_COMPLETE" when done."""


def create_summarizer_agent(
    chat_client: Any,
    name: str = "SummarizerAgent",
) -> ChatAgent:
    """
    Create a summarization specialist agent using Agent Framework.

    This agent excels at creating clear, actionable executive summaries
    from documents and analyses.

    Args:
        chat_client: Agent Framework chat client (from get_chat_client())
        name: Agent name for identification

    Returns:
        Configured ChatAgent for summarization

    Example:
        >>> from app.agents.model_client import get_chat_client
        >>> client = get_chat_client()
        >>> summarizer = create_summarizer_agent(client)
    """
    from ..tools.rag_tools import rag_answer, summarize_documents, get_document_content
    from ..tools.search_tools import hybrid_search

    instructions = get_agent_system_message("SummarizerAgent", DEFAULT_SUMMARIZER_MSG)
    logger.debug(f"Creating SummarizerAgent: name={name}")

    return ChatAgent(
        name=name,
        chat_client=chat_client,
        instructions=instructions,
        tools=[
            rag_answer,
            summarize_documents,
            get_document_content,
            hybrid_search,
        ],
    )


def create_triage_agent(
    chat_client: Any,
    name: str = "TriageAgent",
) -> ChatAgent:
    """
    Create a coordinator agent for the handoff workflow.

    This agent analyzes incoming requests and routes them to the appropriate
    specialist agent using the HandoffBuilder's handoff mechanism.

    In the Microsoft Agent Framework, handoffs are triggered automatically
    when the coordinator decides which specialist should handle the request.

    Args:
        chat_client: Agent Framework chat client (from get_chat_client())
        name: Agent name for identification

    Returns:
        Configured ChatAgent as workflow coordinator
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
    return ChatAgent(
        name=name,
        chat_client=chat_client,
        instructions=triage_instructions,
        tools=[],
    )
