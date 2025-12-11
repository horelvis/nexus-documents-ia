"""
Specialized Agents for Document Intelligence

This module contains specialized agents, each designed for
specific document processing tasks.

FRAMEWORK: Microsoft Agent Framework
All agents use ChatAgent from agent-framework package.

CORE AGENTS:
- SearchAgent: Document search and retrieval
- AnalystAgent: Deep document analysis
- ContractAgent: Contract review and clause analysis
- ComplianceAgent: GDPR/RGPD compliance verification
- SummarizerAgent: Executive summary generation
- TriageAgent: Request routing to specialists

SPECIALIZED AGENTS (Spanish Legal Domain):
- LegalAgent: General legal documents (judicial, administrative)
- LaborAgent: Labor law (Estatuto de los Trabajadores)
- FiscalAgent: Tax law (Ley General Tributaria)
- TaxDeclarationAgent: Income tax declarations (IRPF)
- RealEstateAgent: Property law (LAU)
- PrivacyAgent: Data protection (RGPD/LOPDGDD)
- EducationAgent: Education law (LOMLOE/LOE)

Usage:
    from app.agents.agents import create_search_agent
    from app.agents.model_client import get_chat_client

    client = get_chat_client()
    search = create_search_agent(client)
"""

# Core agents
from .search_agent import create_search_agent, create_search_agent_with_metadata
from .analyst_agent import create_analyst_agent
from .contract_agent import create_contract_agent
from .compliance_agent import create_compliance_agent
from .summarizer_agent import create_summarizer_agent, create_triage_agent

# Specialized agents (Spanish legal domain)
from .legal_agent import create_legal_agent
from .labor_agent import create_labor_agent
from .fiscal_agent import create_fiscal_agent
from .tax_declaration_agent import create_tax_declaration_agent
from .real_estate_agent import create_real_estate_agent
from .privacy_agent import create_privacy_agent
from .education_agent import create_education_agent

__all__ = [
    # Core agents
    "create_search_agent",
    "create_search_agent_with_metadata",
    "create_analyst_agent",
    "create_contract_agent",
    "create_compliance_agent",
    "create_summarizer_agent",
    "create_triage_agent",
    # Specialized agents
    "create_legal_agent",
    "create_labor_agent",
    "create_fiscal_agent",
    "create_tax_declaration_agent",
    "create_real_estate_agent",
    "create_privacy_agent",
    "create_education_agent",
]
