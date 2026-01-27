"""
Pydantic schemas for MEN service API.

Defines request/response models for all endpoints.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ============================================================
# Query Endpoints
# ============================================================

class QueryRequest(BaseModel):
    """Request model for /men/query endpoint."""
    query: str = Field(..., description="User's query text", min_length=1, max_length=4096)
    tenant_id: str = Field(..., description="Tenant identifier")
    session_id: str = Field(default="default", description="Session ID for conversational memory")
    tenant_schema: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Tenant metadata (document_types, known_clients, terminology)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "query": "¿Cuántos contratos tiene ACME?",
                "tenant_id": "tenant-123",
                "session_id": "session-abc",
                "tenant_schema": {
                    "document_types": ["contrato", "factura", "acuerdo"],
                    "known_clients": ["ACME", "GlobalCorp"]
                }
            }
        }


class QueryResponse(BaseModel):
    """Response model for /men/query endpoint."""
    response: str = Field(..., description="Generated response")
    domain: str = Field(..., description="Classified domain")
    expert_used: Optional[str] = Field(None, description="Expert source (tenant:domain or generic:domain)")
    has_expert_data: bool = Field(..., description="Whether expert data was used")
    session_id: str = Field(..., description="Session ID for follow-up queries")
    tenant_id: str = Field(..., description="Tenant ID")


class DecideRequest(BaseModel):
    """Request model for /men/decide endpoint."""
    query: str = Field(..., description="User's query to classify", min_length=1, max_length=4096)


class DecideResponse(BaseModel):
    """Response model for /men/decide endpoint."""
    domain: str = Field(..., description="Classified domain")
    confidence: float = Field(..., description="Classification confidence (0-1)")
    requires_expert: bool = Field(..., description="Whether query needs expert knowledge")


# ============================================================
# Session Endpoints
# ============================================================

class SessionMessage(BaseModel):
    """Single message in conversation history."""
    role: str = Field(..., description="Message role (user or assistant)")
    content: str = Field(..., description="Message content")


class SessionHistoryResponse(BaseModel):
    """Response model for session history endpoint."""
    session_id: str
    tenant_id: str
    history: List[SessionMessage]
    message_count: int


class ClearSessionResponse(BaseModel):
    """Response model for clear session endpoint."""
    message: str
    session_id: str
    cleared: bool


# ============================================================
# Tenant Expert Endpoints
# ============================================================

class ExpertInfo(BaseModel):
    """Information about an expert."""
    domain: str
    tenant_id: str
    path: str
    is_generic: bool
    document_types: List[str]


class TenantExpertsResponse(BaseModel):
    """Response model for tenant experts listing."""
    tenant_id: str
    experts: List[ExpertInfo]
    generic_experts: List[ExpertInfo]


class RegisterExpertRequest(BaseModel):
    """Request model for registering a new expert."""
    domain: str = Field(..., description="Expert domain (e.g., 'legal', 'contract')")
    path: str = Field(..., description="Path to LoRA weights")
    document_types: Optional[List[str]] = Field(
        default=None,
        description="Document types this expert handles"
    )


class RegisterExpertResponse(BaseModel):
    """Response model for expert registration."""
    message: str
    expert: ExpertInfo


# ============================================================
# Training Endpoints
# ============================================================

class TrainingRequest(BaseModel):
    """Request model for expert training."""
    tenant_id: str = Field(..., description="Tenant to train expert for")
    domain: str = Field(..., description="Domain specialization")
    training_data: Optional[List[Dict[str, str]]] = Field(
        default=None,
        description="Custom training examples [{input, output}, ...]"
    )
    use_synthetic: bool = Field(
        default=True,
        description="Generate synthetic examples if no training_data"
    )
    num_epochs: int = Field(default=3, ge=1, le=10, description="Training epochs")


class TrainingResponse(BaseModel):
    """Response model for training status."""
    status: str
    tenant_id: str
    domain: str
    expert_path: Optional[str]
    message: str


class TrainingStatusResponse(BaseModel):
    """Response model for training status check."""
    task_id: str
    status: str  # pending, running, completed, failed
    progress: float
    message: Optional[str]


# ============================================================
# Health & Status Endpoints
# ============================================================

class HealthResponse(BaseModel):
    """Response model for health check."""
    status: str
    service: str
    version: str
    loaded: bool
    orchestrator_loaded: bool
    modeler_loaded: bool
    modeler_enabled: bool
    experts_enabled: bool


class StatusResponse(BaseModel):
    """Detailed status response."""
    status: str
    service: str
    version: str
    loaded: bool
    orchestrator_loaded: bool
    modeler_loaded: bool
    modeler_enabled: bool
    experts_enabled: bool
    loaded_experts: List[str]
    active_sessions: int
    available_domains: List[str]
    vram_estimate: Dict[str, float]
