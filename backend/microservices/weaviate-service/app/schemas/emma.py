"""Pydantic schemas for Emma AI operations"""
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional, Union
from datetime import datetime
from enum import Enum


class QueryType(str, Enum):
    """Types of Emma queries"""
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


class EmmaQuery(BaseModel):
    """Schema for Emma AI agentic queries"""
    query: str
    query_type: Optional[QueryType] = QueryType.SEARCH
    tenant_id: str
    user_id: Optional[str] = Field(default=None, description="User ID for memory and personalization")
    user_role_ids: Optional[List[str]] = Field(default=None, description="User role IDs for ACL filtering")
    is_admin: bool = Field(default=False, description="Whether user is admin (bypasses ACL)")
    session_id: Optional[str] = None
    collections: List[str] = Field(default_factory=list)
    context: Optional[Dict[str, Any]] = Field(default_factory=dict)
    max_iterations: int = Field(default=3, ge=1, le=10)
    enable_learning: bool = True
    enable_debug: bool = Field(default=False, description="Enable chain-of-thought debugging for admin users")
    deep_reasoning: bool = Field(default=True, description="Enable deep reasoning mode for complex analysis (slower but more thorough)")
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


class Suggestion(BaseModel):
    """A contextual suggestion for the user"""
    text: str
    action: Optional[str] = None  # Optional action identifier
    icon: Optional[str] = None    # Optional icon name


class EmmaResponse(BaseModel):
    """Schema for Emma AI query responses"""
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
    suggestions: List[Suggestion] = Field(default_factory=list, description="Contextual suggestions based on available tools and user context")
    available_tools: List[str] = Field(default_factory=list, description="List of available tool names")

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
                "learning_applied": True,
                "suggestions": [
                    {"text": "Analyze document contracts", "action": "analyze_contracts", "icon": "file-text"},
                    {"text": "Search in my documents", "action": "search", "icon": "search"}
                ],
                "available_tools": ["analyze_contract_risks", "search_web", "compare_documents"]
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


# ============================================================================
# Schemas for Document Analysis with PDF Annotations
# ============================================================================


class AnalysisRisk(BaseModel):
    """A risk identified in document analysis"""
    id: str
    type: str = "risk"  # "risk" | "recommendation" | "info"
    severity: Optional[str] = "medium"  # "high" | "medium" | "low"
    title: str
    description: str
    quote: Optional[str] = None  # Exact quote from document for precise annotation
    clause: Optional[str] = None  # Referenced clause/section
    recommendation: Optional[str] = None  # Suggested action


class AnalysisRecommendation(BaseModel):
    """A recommendation from document analysis"""
    id: str
    type: str = "recommendation"
    title: str
    description: str
    quote: Optional[str] = None  # Exact quote from document for precise annotation
    priority: Optional[str] = "medium"  # "high" | "medium" | "low"
    action_required: Optional[str] = None


class DocumentAnalysisResult(BaseModel):
    """Result of document analysis"""
    document_id: str
    summary: str
    risks: List[AnalysisRisk] = Field(default_factory=list)
    recommendations: List[AnalysisRecommendation] = Field(default_factory=list)
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0)
    analysis_type: str = "legal"
    metadata: Optional[Dict[str, Any]] = None


class AnnotationRect(BaseModel):
    """Rectangle coordinates for PDF annotation"""
    x0: float
    y0: float
    x1: float
    y1: float


class PDFAnnotation(BaseModel):
    """A single annotation on a PDF"""
    id: str
    type: str  # "risk" | "recommendation" | "info"
    severity: Optional[str] = None
    title: str
    description: str
    page_number: int  # 1-indexed for UI
    rect: AnnotationRect
    text_found: str
    confidence: float = Field(ge=0.0, le=1.0)


class AnnotatedPDFResponse(BaseModel):
    """Response with annotated PDF and analysis"""
    annotated_pdf: str  # Base64 encoded PDF
    annotations: List[PDFAnnotation]
    pages_annotated: int
    total_annotations: int
    failed_annotations: int
    analysis: DocumentAnalysisResult


class AnalyzeWithAnnotationsRequest(BaseModel):
    """Request for document analysis with PDF annotations"""
    document_id: str
    tenant_id: str
    analysis_type: str = "legal"
    include_recommendations: bool = True


class MarkdownPage(BaseModel):
    """A single page of Markdown content"""
    page_number: int
    content: str
    char_count: int


class DocumentMarkdownResponse(BaseModel):
    """Response with document converted to Markdown"""
    document_id: str
    full_markdown: str
    pages: List[MarkdownPage]
    total_pages: int
    total_chars: int
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AnalysisWithMarkdownResponse(BaseModel):
    """Analysis results with Markdown document view instead of PDF"""
    markdown: DocumentMarkdownResponse
    annotations: List[PDFAnnotation]
    annotated_markdown: str  # Markdown with inline annotations
    analysis: DocumentAnalysisResult


