"""
Tool Integration Service for Emma Agent

Provides integration between Emma's agent framework and available tools.
Tools are exposed via the weaviate-service HTTP API.
"""

import logging
from typing import List, Dict, Any, Optional
from functools import lru_cache

from app.schemas.emma import ToolInfo
from app.clients import get_weaviate_client

logger = logging.getLogger(__name__)


class ToolIntegration:
    """
    Tool integration layer for Emma Agent.

    This class manages the tools available to Emma, fetching them from
    weaviate-service which provides RAG capabilities.
    """

    def __init__(self):
        self._initialized = False
        self._tools: List[ToolInfo] = []

    async def initialize(self):
        """Initialize tool integration by discovering available tools."""
        if self._initialized:
            return

        try:
            # Get available tools from weaviate-service
            client = get_weaviate_client()

            # Define built-in tools available through weaviate-service
            self._tools = [
                ToolInfo(
                    name="search_documents",
                    description="Search documents using semantic vector search",
                    parameters={
                        "query": {"type": "string", "description": "Search query"},
                        "limit": {"type": "integer", "description": "Max results", "default": 10},
                    },
                    return_type="list[Document]",
                    category="retrieval"
                ),
                ToolInfo(
                    name="get_document_content",
                    description="Get full content of a specific document",
                    parameters={
                        "document_id": {"type": "string", "description": "Document UUID"},
                    },
                    return_type="DocumentContent",
                    category="retrieval"
                ),
                ToolInfo(
                    name="analyze_document",
                    description="Analyze a document for key insights, risks, and recommendations",
                    parameters={
                        "document_id": {"type": "string", "description": "Document UUID"},
                        "analysis_type": {"type": "string", "description": "Type of analysis", "default": "general"},
                    },
                    return_type="AnalysisResult",
                    category="analysis"
                ),
                ToolInfo(
                    name="compare_documents",
                    description="Compare two or more documents",
                    parameters={
                        "document_ids": {"type": "list[string]", "description": "Document UUIDs to compare"},
                    },
                    return_type="ComparisonResult",
                    category="analysis"
                ),
                ToolInfo(
                    name="structural_query",
                    description="Query the knowledge graph for structural information",
                    parameters={
                        "query": {"type": "string", "description": "Natural language query about document structure"},
                    },
                    return_type="GraphResult",
                    category="graph"
                ),
            ]

            self._initialized = True
            logger.info(f"✅ Tool integration initialized with {len(self._tools)} tools")

        except Exception as e:
            logger.warning(f"⚠️ Tool integration initialization failed: {e}")
            self._initialized = True  # Mark as initialized to avoid retry loops

    def get_tool_info(self) -> List[ToolInfo]:
        """Get information about all available tools."""
        return self._tools

    def get_tool_names(self) -> List[str]:
        """Get list of available tool names."""
        return [tool.name for tool in self._tools]

    def get_tool_by_name(self, name: str) -> Optional[ToolInfo]:
        """Get tool info by name."""
        for tool in self._tools:
            if tool.name == name:
                return tool
        return None

    def get_tools_by_category(self, category: str) -> List[ToolInfo]:
        """Get tools filtered by category."""
        return [tool for tool in self._tools if tool.category == category]


# Singleton instance
_tool_integration: Optional[ToolIntegration] = None


def get_tool_integration() -> ToolIntegration:
    """Get or create the tool integration singleton."""
    global _tool_integration
    if _tool_integration is None:
        _tool_integration = ToolIntegration()
    return _tool_integration
