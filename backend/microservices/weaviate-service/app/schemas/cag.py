"""Schemas to keep backwards compatibility with legacy CAG endpoints."""
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AnalysisType(str, Enum):
    """Types of document analysis"""

    COMPREHENSIVE = "comprehensive"
    CONTRACT = "contract"
    COMPLIANCE = "compliance"
    FINANCIAL = "financial"
    LEGAL = "legal"


class CAGQueryRequest(BaseModel):
    """Request payload for the legacy CAG query endpoint."""

    query: str = Field(..., description="The query to process")
    tenant_id: str = Field(..., description="Tenant ID")
    user_id: str = Field(..., description="User ID")
    context: Optional[Dict[str, Any]] = Field(
        None, description="Additional execution context"
    )


class CAGQueryResponse(BaseModel):
    """Response contract expected by backend callers."""

    success: bool
    query: str
    answer: Optional[str]
    quality_score: float = Field(0.0, ge=0.0, le=1.0)
    iterations: int = Field(0, ge=0)
    gaps_identified: int = Field(0, ge=0)
    context_chunks_used: int = Field(0, ge=0)
    execution_time: float = Field(0.0, ge=0.0)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None


class DocumentAnalysisRequest(BaseModel):
    """Document analysis request."""

    document_content: str = Field(..., description="Document content to analyze")
    document_id: str = Field(..., description="Document ID")
    tenant_id: str = Field(..., description="Tenant ID")
    user_id: str = Field(..., description="User ID")
    analysis_type: AnalysisType = Field(
        AnalysisType.COMPREHENSIVE, description="Type of analysis to perform"
    )


class DocumentAnalysisResponse(BaseModel):
    """Document analysis response."""

    success: bool
    document_id: str
    document_type: Optional[str] = None
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    analysis_type: str
    analysis: Optional[str]
    quality_score: float = Field(0.0, ge=0.0, le=1.0)
    execution_time: float = Field(0.0, ge=0.0)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None


class TaskExecutionRequest(BaseModel):
    """Request for executing long-running tasks."""

    task_description: str
    expected_output: Optional[str] = None
    agent_roles: Optional[List[str]] = None
    tenant_id: str
    user_id: str
    context: Dict[str, Any] = Field(default_factory=dict)


class HealthCheckResponse(BaseModel):
    """Health check payload."""

    status: str
    service: str
    checks: Dict[str, bool]
    error: Optional[str] = None
