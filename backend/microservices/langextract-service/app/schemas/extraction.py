"""
Pydantic schemas for LangExtract service
"""
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
from enum import Enum


class DocumentType(str, Enum):
    """Supported document types"""
    CONTRACT = "contract"
    INVOICE = "invoice"
    REPORT = "report"
    LEGAL = "legal"
    FINANCIAL = "financial"
    TECHNICAL = "technical"
    HR = "hr"
    GENERAL = "general"


class Provider(str, Enum):
    """Available LLM providers"""
    OLLAMA = "ollama"
    GEMINI = "gemini"
    OPENAI = "openai"


class ExtractionRequest(BaseModel):
    """Request model for document extraction"""
    text: str = Field(..., description="Document text to extract from")
    document_type: DocumentType = Field(
        DocumentType.GENERAL, 
        description="Type of document for specialized extraction"
    )
    filename: Optional[str] = Field(None, description="Optional filename for context")
    provider: Optional[Provider] = Field(None, description="LLM provider to use")
    tenant_id: Optional[str] = Field(None, description="Tenant ID for multi-tenancy")
    user_id: Optional[str] = Field(None, description="User ID for tracking")


class ExtractedEntity(BaseModel):
    """Model for extracted entity"""
    class_name: str = Field(..., description="Entity class/type")
    text: str = Field(..., description="Extracted text")
    attributes: Dict[str, Any] = Field(default_factory=dict, description="Entity attributes")
    source_indices: Optional[List[int]] = Field(None, description="Source text indices")


class ExtractionSummary(BaseModel):
    """Summary of extraction results"""
    parties: List[str] = Field(default_factory=list, description="Parties in contracts")
    dates: Dict[str, str] = Field(default_factory=dict, description="Important dates")
    amounts: List[str] = Field(default_factory=list, description="Monetary amounts")
    obligations: List[str] = Field(default_factory=list, description="Obligations/actions")
    key_entities: List[str] = Field(default_factory=list, description="Key entities")
    findings: List[str] = Field(default_factory=list, description="Report findings")
    recommendations: List[str] = Field(default_factory=list, description="Recommendations")


class ExtractionResponse(BaseModel):
    """Response model for extraction results"""
    success: bool = Field(..., description="Whether extraction succeeded")
    extractions: List[Dict[str, Any]] = Field(
        default_factory=list, 
        description="Raw extraction results"
    )
    entities: Dict[str, List[Dict[str, Any]]] = Field(
        default_factory=dict,
        description="Entities grouped by class"
    )
    summary: Dict[str, Any] = Field(
        default_factory=dict,
        description="Summarized extraction results"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Extraction metadata"
    )
    visualization_html: Optional[str] = Field(
        None,
        description="HTML visualization of extractions"
    )
    error: Optional[str] = Field(None, description="Error message if failed")


class HealthResponse(BaseModel):
    """Health check response"""
    status: str = Field(..., description="Service status")
    service: str = Field(..., description="Service name")
    version: str = Field(..., description="Service version")
    providers: List[str] = Field(..., description="Available providers")
    default_provider: str = Field(..., description="Default provider")


class StatsResponse(BaseModel):
    """Statistics response"""
    supported_document_types: List[str] = Field(..., description="Supported document types")
    default_provider: str = Field(..., description="Default LLM provider")
    available_providers: List[str] = Field(..., description="Available providers")
    extraction_passes: int = Field(..., description="Number of extraction passes")
    max_char_buffer: int = Field(..., description="Maximum characters per chunk")
    confidence_threshold: float = Field(..., description="Confidence threshold")