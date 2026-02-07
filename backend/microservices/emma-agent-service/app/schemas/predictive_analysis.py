"""
Pydantic schemas for Predictive Analysis.

Sector-agnostic predictive analysis that adapts to ACTIVE_SECTOR:
- Legal → predicts judicial outcome based on jurisprudence
- Medical → analyzes clinical report against protocols
- Documental → verifies technical report against standards
- Generic → risk/compliance analysis

Architecture mirrors Verified Generation's stop-and-go pattern:
    FactorAgent → OutcomeExtractor → PredictionSynthesizer → Redis Cache
    (Extract)      (Evaluate)          (Aggregate)             (Store)
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
import uuid


# =============================================================================
# Enums
# =============================================================================


class PredictiveEventType(str, Enum):
    """Types of events emitted during predictive analysis."""
    FACTOR_EXTRACTED = "factor_extracted"
    FACTOR_VERIFICATION_STARTED = "factor_verification_started"
    FACTOR_WEIGHTED = "factor_weighted"
    FACTOR_REJECTED = "factor_rejected"
    SYNTHESIS_STARTED = "synthesis_started"
    PREDICTION_COMPLETE = "prediction_complete"
    ERROR = "error"
    PROGRESS = "progress"


class OutcomeLabel(str, Enum):
    """Generic outcome labels — sector configs map to display strings."""
    POSITIVE = "positive"
    NEGATIVE = "negative"
    MIXED = "mixed"


# =============================================================================
# Factor & Evidence Models
# =============================================================================


class PredictionFactor(BaseModel):
    """
    A factor extracted by the FactorAgent for analysis.
    Adapts CandidateClaim from Verified Generation.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    factor_type: str = Field(..., description="Type of factor (from sector config factor_types)")
    description: str = Field(..., description="Natural language description of the factor")
    legal_basis: Optional[str] = Field(None, description="Legal article, protocol, or standard reference")
    source_query: str = Field(..., description="Original case description that prompted this factor")
    extraction_order: int = Field(..., description="Order in which this factor was extracted (1-indexed)")
    context_document_ids: List[str] = Field(default_factory=list)
    extracted_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class VerificationMatch(BaseModel):
    """
    A document match found during factor verification.
    Adapts EvidenceMatch from Verified Generation.
    """
    document_id: str = Field(..., description="ID of the source document")
    document_title: Optional[str] = Field(None, description="Title of the source document")
    chunk_id: Optional[str] = Field(None, description="Specific chunk ID if applicable")
    text_excerpt: str = Field(..., description="Relevant text excerpt")
    similarity_score: float = Field(..., ge=0.0, le=1.0)
    outcome: str = Field(..., description="Outcome label for this match (sector-specific)")
    supports_factor: bool = Field(..., description="Whether this match supports the factor")
    source: str = Field(default="internal", description="Source: internal, web, uploaded, public_knowledge, jurisprudence")
    url: Optional[str] = Field(None, description="URL if web source")
    # CENDOJ jurisprudence fields (optional, only populated for jurisprudence sources)
    roj: Optional[str] = Field(None, description="ROJ identifier (e.g., STS 1234/2024)")
    ecli: Optional[str] = Field(None, description="ECLI identifier")
    date: Optional[str] = Field(None, description="Resolution date")
    resolution_type: Optional[str] = Field(None, description="Type of resolution (Sentencia, Auto, etc.)")
    ponente: Optional[str] = Field(None, description="Reporting judge")


class WeightedFactor(BaseModel):
    """
    A factor that has been extracted, verified, and weighted.
    Adapts VerifiedClaim from Verified Generation.
    """
    id: str = Field(..., description="Unique factor identifier")
    factor_type: str = Field(..., description="Type of factor")
    description: str = Field(..., description="Factor description")
    legal_basis: Optional[str] = Field(None, description="Legal/protocol reference")
    weight: float = Field(..., ge=0.0, le=1.0, description="Impact weight (0=negligible, 1=decisive)")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in the assessment")
    outcome: str = Field(..., description="Predicted outcome for this factor (sector-specific label key)")
    outcome_ratio: Dict[str, float] = Field(
        default_factory=dict,
        description="Ratio of outcomes from matching documents {label_key: ratio}"
    )
    supporting_matches: List[VerificationMatch] = Field(default_factory=list)
    extraction_order: int = Field(..., description="Order in final analysis")
    weighted_at: datetime = Field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for Redis storage."""
        return {
            "id": self.id,
            "factor_type": self.factor_type,
            "description": self.description,
            "legal_basis": self.legal_basis,
            "weight": self.weight,
            "confidence": self.confidence,
            "outcome": self.outcome,
            "outcome_ratio": self.outcome_ratio,
            "supporting_matches": [m.model_dump() for m in self.supporting_matches],
            "extraction_order": self.extraction_order,
            "weighted_at": self.weighted_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WeightedFactor":
        """Create from dictionary (Redis deserialization)."""
        matches = [
            VerificationMatch(**m) for m in data.get("supporting_matches", [])
        ]
        return cls(
            id=data["id"],
            factor_type=data["factor_type"],
            description=data["description"],
            legal_basis=data.get("legal_basis"),
            weight=data["weight"],
            confidence=data["confidence"],
            outcome=data["outcome"],
            outcome_ratio=data.get("outcome_ratio", {}),
            supporting_matches=matches,
            extraction_order=data["extraction_order"],
            weighted_at=(
                datetime.fromisoformat(data["weighted_at"])
                if isinstance(data["weighted_at"], str)
                else data["weighted_at"]
            ),
        )


# =============================================================================
# Prediction Result
# =============================================================================


class PredictionResult(BaseModel):
    """Final prediction result with probability, factors, and recommendation."""
    session_id: str
    probability: float = Field(..., ge=0.0, le=1.0, description="Overall predicted probability for primary outcome")
    confidence_interval: List[float] = Field(
        ..., min_length=2, max_length=2,
        description="[lower_bound, upper_bound] confidence interval"
    )
    primary_outcome: str = Field(..., description="Most likely outcome label key")
    outcome_probabilities: Dict[str, float] = Field(
        ..., description="Probability for each outcome {label_key: probability}"
    )
    factors: List[WeightedFactor] = Field(default_factory=list)
    recommendation: str = Field(..., description="Natural language recommendation")
    disclaimer: str = Field(..., description="Sector-specific legal disclaimer")
    sector: Optional[str] = Field(None, description="Active sector used for analysis")
    execution_time_ms: int = Field(default=0)
    created_at: datetime = Field(default_factory=datetime.utcnow)


# =============================================================================
# SSE Event
# =============================================================================


class PredictiveEvent(BaseModel):
    """Event emitted during predictive analysis for SSE streaming."""
    event_type: PredictiveEventType
    factor_id: Optional[str] = None
    data: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    progress_percent: Optional[int] = Field(None, ge=0, le=100)

    def to_sse(self) -> str:
        """Format as Server-Sent Event."""
        import json
        payload = {
            "event_type": self.event_type.value,
            "factor_id": self.factor_id,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
            "progress_percent": self.progress_percent,
        }
        return f"data: {json.dumps(payload)}\n\n"


# =============================================================================
# API Request/Response Schemas
# =============================================================================


class PredictionRequest(BaseModel):
    """Request to perform predictive analysis."""
    case_description: str = Field(..., description="Description of the case/report to analyze")
    tenant_id: str = Field(..., description="Tenant identifier")
    session_id: Optional[str] = Field(None, description="Session ID (auto-generated if not provided)")
    user_id: Optional[str] = Field(None, description="User ID for audit")

    # Analysis parameters
    max_factors: int = Field(default=10, ge=1, le=20, description="Maximum factors to extract")
    confidence_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    sector_override: Optional[str] = Field(
        None, description="Override ACTIVE_SECTOR for this request (legal, medical, documental)"
    )

    # Context parameters
    context_document_ids: List[str] = Field(default_factory=list)
    uploaded_file_ids: List[str] = Field(default_factory=list)
    collections: List[str] = Field(default_factory=list)

    class Config:
        json_schema_extra = {
            "example": {
                "case_description": "Analiza las probabilidades de éxito en una reclamación por incumplimiento contractual...",
                "tenant_id": "tenant-123",
                "max_factors": 8,
                "confidence_threshold": 0.7,
            }
        }


class PredictionResponse(BaseModel):
    """Synchronous prediction response."""
    session_id: str
    case_description: str
    result: PredictionResult
    factors_extracted: int
    factors_weighted: int
    factors_rejected: int
    execution_time_ms: int
    created_at: datetime = Field(default_factory=datetime.utcnow)


class PredictionSessionResponse(BaseModel):
    """Response for cached prediction session."""
    session_id: str
    tenant_id: str
    result: Optional[PredictionResult] = None
    factors: List[WeightedFactor] = Field(default_factory=list)
    total_factors: int = 0
    cache_ttl_remaining_seconds: Optional[int] = None
