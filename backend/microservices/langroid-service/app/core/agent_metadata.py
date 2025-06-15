"""
Built-in agent metadata configuration
"""
from typing import Dict, List, Any


BUILTIN_AGENTS_METADATA: Dict[str, Dict[str, Any]] = {
    "digital_signature_agent": {
        "display_name": "Digital Signature Agent",
        "description": "Handles digital signature workflows and document signing processes",
        "capabilities": [
            "signature_requests",
            "status_tracking", 
            "signer_management"
        ],
        "category": "document_processing"
    },
    "document_analyzer_agent": {
        "display_name": "Document Analyzer Agent",
        "description": "Analyzes documents for various purposes (legal, financial, etc.)",
        "capabilities": [
            "content_analysis",
            "extraction",
            "summarization"
        ],
        "category": "document_processing"
    },
    "rag_assistant_agent": {
        "display_name": "RAG Assistant Agent",
        "description": "Retrieval-Augmented Generation assistant for document Q&A",
        "capabilities": [
            "document_search",
            "context_qa",
            "knowledge_retrieval"
        ],
        "category": "ai_assistance"
    },
    "legal_compliance_agent": {
        "display_name": "Legal Compliance Agent",
        "description": "Analyzes documents for legal compliance and regulatory requirements",
        "capabilities": [
            "compliance_check",
            "risk_assessment",
            "regulatory_analysis"
        ],
        "category": "compliance"
    },
    "financial_analysis_agent": {
        "display_name": "Financial Analysis Agent",
        "description": "Analyzes financial documents and provides insights",
        "capabilities": [
            "financial_metrics",
            "trend_analysis",
            "report_generation"
        ],
        "category": "financial"
    }
}


def get_agent_metadata(agent_key: str) -> Dict[str, Any]:
    """
    Get metadata for a built-in agent
    
    Args:
        agent_key: The agent identifier key
        
    Returns:
        Dictionary containing agent metadata
    """
    if agent_key in BUILTIN_AGENTS_METADATA:
        return BUILTIN_AGENTS_METADATA[agent_key].copy()
    
    # Default metadata for unknown agents
    formatted_name = agent_key.replace("_agent", "").replace("_", " ").title() + " Agent"
    return {
        "display_name": formatted_name,
        "description": "AI assistant for specialized tasks",
        "capabilities": ["general_assistance"],
        "category": "general"
    }


def get_all_builtin_agents() -> Dict[str, Dict[str, Any]]:
    """
    Get all built-in agent metadata
    
    Returns:
        Dictionary of all built-in agents and their metadata
    """
    return BUILTIN_AGENTS_METADATA.copy()


def get_agent_categories() -> List[str]:
    """
    Get unique agent categories
    
    Returns:
        List of unique category names
    """
    categories = set()
    for agent_data in BUILTIN_AGENTS_METADATA.values():
        if "category" in agent_data:
            categories.add(agent_data["category"])
    return sorted(list(categories))