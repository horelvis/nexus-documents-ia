from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List
from datetime import datetime
from enum import Enum


class GraphType(str, Enum):
    """Available graph types"""
    CAG = "cag"  # Contextual Augmented Generation - handles all document Q&A needs


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