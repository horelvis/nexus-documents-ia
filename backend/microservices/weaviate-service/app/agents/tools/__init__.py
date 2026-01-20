"""
Agent Framework Tools - RAG Pipeline Wrappers

Tools are plain Python functions that agents can call to interact with the
document intelligence system. They wrap the existing RAG pipeline functionality.

In Agent Framework, tools are defined as regular async functions with:
- Type hints using Annotated[type, Field(description="...")]
- Comprehensive docstrings explaining what the tool does
- JSON-serializable return values (strings for complex data)

The @ai_function decorator registers them as callable tools.

FRAMEWORK: Qwen-Agent (migrated from Microsoft Agent Framework)

Example usage:
    from app.agents.tools import get_search_tools, SEARCH_TOOL_NAMES
    from qwen_agent.agents import Assistant

    agent = Assistant(
        llm=llm_cfg,
        function_list=get_search_tools(),  # Returns ['nexus_semantic_search', ...]
        system_message="..."
    )
"""

from .search_tools import (
    SemanticSearchTool,
    HybridSearchTool,
    KeywordSearchTool,
    SearchByMetadataTool,
    SearchPublicKnowledgeTool,
    SearchWithLegalContextTool,
    SEARCH_TOOLS,
    SEARCH_TOOL_NAMES,
    get_search_tools,
)
from .analysis_tools import (
    AnalyzeDocumentTool,
    CompareDocumentsTool,
    ExtractEntitiesTool,
    ANALYSIS_TOOLS,
    ANALYSIS_TOOL_NAMES,
    get_analysis_tools,
)
from .rag_tools import (
    RAGAnswerTool,
    GetDocumentContentTool,
    SummarizeDocumentsTool,
    AnswerWithContextTool,
    RAG_TOOLS,
    RAG_TOOL_NAMES,
    get_rag_tools,
)
from .planning_tool import (
    PlanningTool,
    PlanStepStatus,
    Plan,
    PlanStep,
    get_planning_tool,
)
from .sharing_insights_tools import (
    QueryRecentSharesTool,
    QuerySharesToRecipientTool,
    QuerySharingStatisticsTool,
    QuerySiteGuestsTool,
    QueryGuestDocumentsTool,
    QueryGuestActivityTool,
    QueryGuestStatisticsTool,
    QuerySharingOverviewTool,
    SHARING_INSIGHTS_TOOLS,
    SHARING_INSIGHTS_TOOL_NAMES,
    get_sharing_insights_tools,
)
from .clarification_tools import (
    AskUserClarificationTool,
    AskConfirmationTool,
    SuggestFollowUpTool,
    CLARIFICATION_TOOLS,
    CLARIFICATION_TOOL_NAMES,
    get_clarification_tools,
    # Utility functions
    is_clarification_response,
    parse_clarification_response,
    extract_selected_document,
)

__all__ = [
    # Search tools (Qwen-Agent class-based)
    "SemanticSearchTool",
    "HybridSearchTool",
    "KeywordSearchTool",
    "SearchByMetadataTool",
    "SearchPublicKnowledgeTool",
    "SearchWithLegalContextTool",
    "SEARCH_TOOLS",
    "SEARCH_TOOL_NAMES",
    "get_search_tools",
    # Analysis tools (Qwen-Agent class-based)
    "AnalyzeDocumentTool",
    "CompareDocumentsTool",
    "ExtractEntitiesTool",
    "ANALYSIS_TOOLS",
    "ANALYSIS_TOOL_NAMES",
    "get_analysis_tools",
    # RAG tools (Qwen-Agent class-based)
    "RAGAnswerTool",
    "GetDocumentContentTool",
    "SummarizeDocumentsTool",
    "AnswerWithContextTool",
    "RAG_TOOLS",
    "RAG_TOOL_NAMES",
    "get_rag_tools",
    # Planning tools (OpenManus-style)
    "PlanningTool",
    "PlanStepStatus",
    "Plan",
    "PlanStep",
    "get_planning_tool",
    # Sharing insights tools (Qwen-Agent class-based)
    "QueryRecentSharesTool",
    "QuerySharesToRecipientTool",
    "QuerySharingStatisticsTool",
    "QuerySiteGuestsTool",
    "QueryGuestDocumentsTool",
    "QueryGuestActivityTool",
    "QueryGuestStatisticsTool",
    "QuerySharingOverviewTool",
    "SHARING_INSIGHTS_TOOLS",
    "SHARING_INSIGHTS_TOOL_NAMES",
    "get_sharing_insights_tools",
    # Human-in-the-Loop clarification tools (Qwen-Agent class-based)
    "AskUserClarificationTool",
    "AskConfirmationTool",
    "SuggestFollowUpTool",
    "CLARIFICATION_TOOLS",
    "CLARIFICATION_TOOL_NAMES",
    "get_clarification_tools",
    # Clarification utility functions
    "is_clarification_response",
    "parse_clarification_response",
    "extract_selected_document",
]
