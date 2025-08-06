"""CAG API schemas"""
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
from enum import Enum


class AnalysisType(str, Enum):
    """Types of document analysis"""
    COMPREHENSIVE = "comprehensive"
    CONTRACT = "contract"
    COMPLIANCE = "compliance"
    FINANCIAL = "financial"
    LEGAL = "legal"


class CAGQueryRequest(BaseModel):
    """Request for CAG query processing"""
    query: str = Field(..., description="The query to process")
    tenant_id: str = Field(..., description="Tenant ID")
    user_id: str = Field(..., description="User ID")
    context: Optional[Dict[str, Any]] = Field(None, description="Additional context")


class CAGQueryResponse(BaseModel):
    """Response from CAG query processing"""
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
    """Request for document analysis"""
    document_content: str = Field(..., description="Document content to analyze")
    document_id: str = Field(..., description="Document ID")
    tenant_id: str = Field(..., description="Tenant ID")
    user_id: str = Field(..., description="User ID")
    analysis_type: AnalysisType = Field(
        AnalysisType.COMPREHENSIVE,
        description="Type of analysis to perform"
    )


class DocumentAnalysisResponse(BaseModel):
    """Response from document analysis"""
    success: bool
    document_id: str
    document_type: Optional[str] = None  # Add document type
    confidence: float = Field(0.0, ge=0.0, le=1.0)  # Add confidence score
    analysis_type: str
    analysis: Optional[str]
    quality_score: float = Field(0.0, ge=0.0, le=1.0)
    execution_time: float = Field(0.0, ge=0.0)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None


class HealthCheckResponse(BaseModel):
    """Health check response"""
    status: str
    service: str
    checks: Dict[str, bool]
    error: Optional[str] = None