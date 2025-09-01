"""Pydantic schemas for Elysia operations"""
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional, Union
from datetime import datetime
from enum import Enum


class QueryType(str, Enum):
    """Types of Elysia queries"""
    SEARCH = "search"
    ANALYZE = "analyze"
    EXTRACT = "extract"
    SUMMARIZE = "summarize"
    COMPARE = "compare"
    RECOMMEND = "recommend"


class VisualizationType(str, Enum):
    """Types of data visualization"""
    TABLE = "table"
    CHART = "chart"
    GRAPH = "graph"
    LIST = "list"
    CARDS = "cards"
    TREE = "tree"
    TIMELINE = "timeline"


class ElysiaQuery(BaseModel):
    """Schema for Elysia agentic queries"""
    query: str
    query_type: Optional[QueryType] = QueryType.SEARCH
    tenant_id: str
    session_id: Optional[str] = None
    collections: List[str] = Field(default_factory=list)
    context: Optional[Dict[str, Any]] = Field(default_factory=dict)
    max_iterations: int = Field(default=3, ge=1, le=10)
    enable_learning: bool = True
    preferred_visualization: Optional[VisualizationType] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "query": "What are the most expensive items in the product catalog?",
                "query_type": "analyze",
                "tenant_id": "tenant-123",
                "collections": ["products", "pricing"],
                "max_iterations": 3,
                "enable_learning": True,
                "preferred_visualization": "table"
            }
        }


class ToolInfo(BaseModel):
    """Information about an available tool"""
    name: str
    description: str
    parameters: Dict[str, Any]
    return_type: str
    category: str


class DecisionNode(BaseModel):
    """Represents a node in the decision tree"""
    node_id: str
    name: str
    description: str
    tools: List[str]
    conditions: Dict[str, Any]
    children: List[str] = Field(default_factory=list)
    parent: Optional[str] = None


class DecisionTreeState(BaseModel):
    """Current state of a decision tree execution"""
    session_id: str
    current_node: str
    visited_nodes: List[str]
    execution_path: List[Dict[str, Any]]
    context: Dict[str, Any]
    tools_executed: List[str]
    start_time: datetime
    last_update: datetime


class ToolExecution(BaseModel):
    """Schema for tool execution requests"""
    tool_name: str
    parameters: Dict[str, Any]
    session_id: Optional[str] = None
    tenant_id: str
    context: Optional[Dict[str, Any]] = Field(default_factory=dict)


class ElysiaResponse(BaseModel):
    """Schema for Elysia query responses"""
    query: str
    answer: str
    session_id: str
    tenant_id: str
    decision_path: List[str]
    tools_used: List[str]
    data: Optional[Dict[str, Any]] = None
    visualization: Optional[Dict[str, Any]] = None
    confidence_score: float = Field(ge=0.0, le=1.0)
    execution_time_ms: int
    iterations: int
    learning_applied: bool = False
    
    class Config:
        json_schema_extra = {
            "example": {
                "query": "What are the most expensive items?",
                "answer": "Based on the product catalog analysis, here are the top 5 most expensive items...",
                "session_id": "session-abc123",
                "tenant_id": "tenant-123",
                "decision_path": ["analyze_query", "select_collections", "execute_aggregation", "format_results"],
                "tools_used": ["collection_analyzer", "aggregation_tool", "visualization_generator"],
                "confidence_score": 0.95,
                "execution_time_ms": 1250,
                "iterations": 2,
                "learning_applied": True
            }
        }


class FeedbackRequest(BaseModel):
    """Schema for user feedback"""
    session_id: str
    query: str
    response: str
    rating: int = Field(ge=1, le=5)
    feedback_text: Optional[str] = None
    tenant_id: str
    timestamp: datetime = Field(default_factory=datetime.now)
    improvement_suggestions: Optional[List[str]] = Field(default_factory=list)


class VisualizationRequest(BaseModel):
    """Schema for visualization generation requests"""
    data: Union[List[Dict[str, Any]], Dict[str, Any]]
    data_type: str
    visualization_type: Optional[VisualizationType] = None
    title: Optional[str] = None
    tenant_id: str
    preferences: Optional[Dict[str, Any]] = Field(default_factory=dict)
    
    class Config:
        json_schema_extra = {
            "example": {
                "data": [
                    {"name": "Product A", "price": 299.99, "category": "Electronics"},
                    {"name": "Product B", "price": 199.99, "category": "Books"}
                ],
                "data_type": "product_list",
                "visualization_type": "table",
                "title": "Product Catalog",
                "tenant_id": "tenant-123",
                "preferences": {"sort_by": "price", "limit": 10}
            }
        }


class MigrationStatus(BaseModel):
    """Schema for migration status"""
    migration_id: str
    source_collection: str
    target_collection: str
    tenant_id: str
    status: str  # pending, running, completed, failed
    progress_percentage: int = Field(ge=0, le=100)
    documents_migrated: int = 0
    total_documents: int = 0
    start_time: datetime
    end_time: Optional[datetime] = None
    error_message: Optional[str] = None