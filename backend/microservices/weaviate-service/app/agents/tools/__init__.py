"""
Agent Framework Tools - RAG Pipeline Wrappers

Tools are plain Python functions that agents can call to interact with the
document intelligence system. They wrap the existing RAG pipeline functionality.

In Agent Framework, tools are defined as regular async functions with:
- Type hints using Annotated[type, Field(description="...")]
- Comprehensive docstrings explaining what the tool does
- JSON-serializable return values (strings for complex data)

The @ai_function decorator registers them as callable tools.

FRAMEWORK: Microsoft Agent Framework

Example usage:
    from app.agents.tools import semantic_search, rag_answer

    agent = ChatAgent(
        name="SearchAgent",
        chat_client=client,
        tools=[semantic_search, hybrid_search, rag_answer],
    )
"""

from .search_tools import (
    semantic_search,
    hybrid_search,
    keyword_search,
)
from .analysis_tools import (
    analyze_document,
    compare_documents,
    extract_entities,
)
from .rag_tools import (
    rag_answer,
    get_document_content,
)
from .planning_tool import (
    PlanningTool,
    PlanStepStatus,
    Plan,
    PlanStep,
    get_planning_tool,
)

__all__ = [
    # Search tools
    "semantic_search",
    "hybrid_search",
    "keyword_search",
    # Analysis tools
    "analyze_document",
    "compare_documents",
    "extract_entities",
    # RAG tools
    "rag_answer",
    "get_document_content",
    # Planning tools (OpenManus-style)
    "PlanningTool",
    "PlanStepStatus",
    "Plan",
    "PlanStep",
    "get_planning_tool",
]
