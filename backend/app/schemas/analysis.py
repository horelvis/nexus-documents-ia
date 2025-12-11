"""
Schemas for Document Analysis Queue (Emma AI)

Pydantic models for analysis queue operations, status tracking,
and result persistence.
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from uuid import UUID
from enum import Enum

from pydantic import BaseModel, Field


class AnalysisStatus(str, Enum):
    """Analysis job status"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class AnalysisType(str, Enum):
    """Type of analysis to perform"""
    LEGAL = "legal"
    CONTRACT = "contract"
    COMPLIANCE = "compliance"
    GENERAL = "general"


# =====================================
# Request Schemas
# =====================================

class AnalysisQueueRequest(BaseModel):
    """Request to queue a document for analysis"""
    document_id: UUID
    analysis_type: AnalysisType = AnalysisType.LEGAL
    priority: int = Field(default=0, ge=0, le=10, description="Priority 0-10, higher = more urgent")

    class Config:
        json_schema_extra = {
            "example": {
                "document_id": "550e8400-e29b-41d4-a716-446655440000",
                "analysis_type": "legal",
                "priority": 0
            }
        }


class AnalysisBatchRequest(BaseModel):
    """Request to queue multiple documents for analysis"""
    document_ids: List[UUID] = Field(..., min_length=1, max_length=50)
    analysis_type: AnalysisType = AnalysisType.LEGAL
    priority: int = Field(default=0, ge=0, le=10)


# =====================================
# Response Schemas - Progress & Steps
# =====================================

class AnalysisStepInfo(BaseModel):
    """Information about an analysis step"""
    index: int
    agent: str
    description: str
    status: str  # pending, in_progress, completed, failed
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result_summary: Optional[str] = None


class AnalysisFinding(BaseModel):
    """A finding from the analysis"""
    type: str  # risk, recommendation, observation, warning
    severity: Optional[str] = None  # critical, high, medium, low, info
    title: str
    description: str
    agent: Optional[str] = None
    location: Optional[Dict[str, Any]] = None  # Page, paragraph, etc.
    references: Optional[List[str]] = None


class AnalysisAnnotation(BaseModel):
    """PDF annotation for visualization"""
    page: int
    x: float
    y: float
    width: float
    height: float
    type: str  # highlight, underline, note, box
    color: Optional[str] = None
    text: Optional[str] = None
    finding_id: Optional[str] = None


# =====================================
# Response Schemas - Analysis Job
# =====================================

class AnalysisJobBase(BaseModel):
    """Base analysis job info"""
    id: UUID
    document_id: UUID
    status: AnalysisStatus
    progress: int = Field(ge=0, le=100)
    analysis_type: str
    current_step: Optional[str] = None


class AnalysisJobCreate(BaseModel):
    """Created analysis job response"""
    id: UUID
    document_id: UUID
    status: AnalysisStatus = AnalysisStatus.PENDING
    created_at: datetime

    class Config:
        from_attributes = True


class AnalysisJobProgress(AnalysisJobBase):
    """Analysis job with progress details"""
    plan_title: Optional[str] = None
    total_steps: int = 0
    steps_completed: int = 0
    detected_document_type: Optional[str] = None
    detected_document_type_display: Optional[str] = None
    detection_confidence: Optional[float] = None
    started_at: Optional[datetime] = None
    error_message: Optional[str] = None

    class Config:
        from_attributes = True


class AnalysisJobResult(AnalysisJobProgress):
    """Complete analysis job result"""
    summary: Optional[str] = None
    risks: List[AnalysisFinding] = []
    recommendations: List[AnalysisFinding] = []
    findings: List[AnalysisFinding] = []
    annotations: List[AnalysisAnnotation] = []
    annotated_pdf_url: Optional[str] = None
    confidence_score: Optional[float] = None
    execution_time_ms: Optional[int] = None
    completed_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class AnalysisJobListItem(BaseModel):
    """Analysis job list item (for queue display)"""
    id: UUID
    document_id: UUID
    document_filename: Optional[str] = None
    status: AnalysisStatus
    progress: int
    analysis_type: str
    current_step: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    error_message: Optional[str] = None

    class Config:
        from_attributes = True


# =====================================
# Response Schemas - Queue
# =====================================

class AnalysisQueueStats(BaseModel):
    """Statistics about the analysis queue"""
    pending_count: int = 0
    processing_count: int = 0
    completed_count: int = 0
    failed_count: int = 0
    total_count: int = 0
    avg_execution_time_ms: Optional[float] = None


class AnalysisQueueResponse(BaseModel):
    """Response with queue items and stats"""
    jobs: List[AnalysisJobListItem]
    stats: AnalysisQueueStats
    total: int
    page: int = 1
    page_size: int = 20


# =====================================
# SSE Stream Schemas
# =====================================

class AnalysisStreamEvent(BaseModel):
    """Event sent via SSE during analysis"""
    event_type: str  # progress, step_started, step_completed, finding, error, completed
    timestamp: datetime
    data: Dict[str, Any]


class AnalysisProgressEvent(BaseModel):
    """Progress update event"""
    progress: int
    current_step: Optional[str] = None
    steps_completed: int = 0
    total_steps: int = 0


class AnalysisStepEvent(BaseModel):
    """Step started/completed event"""
    step_index: int
    agent: str
    description: str
    status: str
    result: Optional[Dict[str, Any]] = None


class AnalysisFindingEvent(BaseModel):
    """New finding discovered event"""
    finding: AnalysisFinding
    step_index: int


class AnalysisCompletedEvent(BaseModel):
    """Analysis completed event"""
    success: bool
    summary: Optional[str] = None
    risk_count: int = 0
    recommendation_count: int = 0
    execution_time_ms: int
    annotated_pdf_url: Optional[str] = None
