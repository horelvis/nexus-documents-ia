from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List
from datetime import datetime
from enum import Enum


class GraphType(str, Enum):
    """Available graph types"""
    TAG_GENERATION = "tag_generation"
    DOCUMENT_PROCESSING = "document_processing"
    CAG = "cag"  # Contextual Augmented Generation (includes RAG capabilities)
    CONVERSATIONAL = "conversational"
    ANALYTICAL = "analytical"
    CREW_ORCHESTRATION = "crew_orchestration"
    DOCUMENT_ANALYSIS_CREW = "document_analysis_crew"


class GraphExecutionMode(str, Enum):
    """Execution modes for graphs"""
    RUN = "run"  # Run to completion
    STREAM = "stream"  # Stream results
    STEP = "step"  # Execute one step at a time


class GraphRunRequest(BaseModel):
    """Request to run a graph"""
    graph_type: GraphType
    input_data: Dict[str, Any]
    config: Optional[Dict[str, Any]] = Field(default_factory=dict)
    mode: GraphExecutionMode = GraphExecutionMode.RUN
    thread_id: Optional[str] = None
    checkpoint_id: Optional[str] = None
    tenant_id: str
    user_id: Optional[str] = None


class GraphStepRequest(BaseModel):
    """Request to execute a single step in a graph"""
    run_id: str
    action: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


class GraphState(BaseModel):
    """Current state of a graph execution"""
    run_id: str
    graph_type: GraphType
    current_node: Optional[str] = None
    state_data: Dict[str, Any]
    iteration: int = 0
    status: str = "running"  # running, completed, failed, paused
    created_at: datetime
    updated_at: datetime
    thread_id: Optional[str] = None
    checkpoint_id: Optional[str] = None


class GraphNode(BaseModel):
    """Information about a graph node"""
    id: str
    name: str
    type: str
    description: Optional[str] = None
    inputs: List[str] = Field(default_factory=list)
    outputs: List[str] = Field(default_factory=list)


class GraphStructure(BaseModel):
    """Structure of a graph"""
    graph_type: GraphType
    nodes: List[GraphNode]
    edges: List[Dict[str, str]]
    entry_point: str
    description: Optional[str] = None


class GraphRunResult(BaseModel):
    """Result of a graph execution"""
    run_id: str
    graph_type: GraphType
    status: str
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    execution_time: float
    iterations: int
    final_state: Optional[Dict[str, Any]] = None
    thread_id: Optional[str] = None
    checkpoint_id: Optional[str] = None


class TagGenerationInput(BaseModel):
    """Input for tag generation graph"""
    text: str
    max_tags: int = 5
    tag_type: str = "general"  # general, technical, business


class TagGenerationOutput(BaseModel):
    """Output from tag generation graph"""
    tags: List[str]
    confidence_scores: Optional[Dict[str, float]] = None
    reasoning: Optional[str] = None


class DocumentProcessingInput(BaseModel):
    """Input for document processing graph"""
    document_id: str
    content: str
    filename: str
    tenant_id: str
    user_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class DocumentProcessingOutput(BaseModel):
    """Output from document processing graph"""
    document_id: str
    chunks: List[Dict[str, Any]]
    embeddings_generated: bool
    metadata: Dict[str, Any]
    quality_score: Optional[float] = None
    processing_notes: Optional[List[str]] = None


class RAGInput(BaseModel):
    """Input for RAG graph"""
    query: str
    tenant_id: str
    user_id: Optional[str] = None
    max_results: int = 5
    filters: Optional[Dict[str, Any]] = None
    include_sources: bool = True


class RAGOutput(BaseModel):
    """Output from RAG graph"""
    answer: str
    sources: Optional[List[Dict[str, Any]]] = None
    confidence_score: float
    search_results: Optional[List[Dict[str, Any]]] = None
    refinement_notes: Optional[str] = None


class CAGInput(BaseModel):
    """Input for CAG (Contextual Augmented Generation) graph"""
    query: str
    tenant_id: str
    user_id: Optional[str] = None
    enable_cag: bool = True
    max_iterations: int = 5
    quality_threshold: float = 0.8
    initial_context: Optional[List[Dict[str, Any]]] = None
    filters: Optional[Dict[str, Any]] = None


class CAGOutput(BaseModel):
    """Output from CAG graph"""
    answer: str
    confidence_score: float
    sources: List[Dict[str, Any]]
    metadata: Dict[str, Any]
    # CAG-specific metadata
    cag_iterations: Optional[int] = None
    gaps_identified: Optional[int] = None
    gaps_filled: Optional[int] = None
    context_expansion_count: Optional[int] = None
    quality_metrics: Optional[Dict[str, float]] = None


class CrewOrchestrationInput(BaseModel):
    """Input for CrewAI orchestration graph"""
    query: str
    task_type: Optional[str] = "general"
    metadata: Optional[Dict[str, Any]] = None
    preferred_agents: Optional[List[str]] = None
    max_agents: int = 3


class CrewOrchestrationOutput(BaseModel):
    """Output from CrewAI orchestration"""
    synthesis: str
    confidence_score: float
    agents_used: List[str]
    memory_insights: int
    success: bool
    agent_contributions: Optional[Dict[str, str]] = None