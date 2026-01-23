"""
Pydantic schemas for identity document extraction.

Supports:
- DNI (Spanish National ID)
- NIE (Foreign Resident ID in Spain)
- Passport
- Driver's License

GDPR Compliance:
- Explicit consent required for processing
- Automatic retention policies
- Audit logging of all access
"""

from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class IdentityDocumentType(str, Enum):
    """Types of identity documents supported"""
    DNI = "dni"
    NIE = "nie"
    PASSPORT = "passport"
    DRIVER_LICENSE = "driver_license"
    RESIDENCE_CARD = "residence_card"
    UNKNOWN = "unknown"


class Gender(str, Enum):
    """Gender values for identity documents"""
    MALE = "M"
    FEMALE = "F"
    OTHER = "X"


class ExtractionConfidence(str, Enum):
    """Confidence levels for extracted fields"""
    HIGH = "high"      # > 90%
    MEDIUM = "medium"  # 60-90%
    LOW = "low"        # < 60%


class ExtractedField(BaseModel):
    """A single extracted field with confidence"""
    value: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0)
    confidence_level: ExtractionConfidence = ExtractionConfidence.MEDIUM
    source: str = "ocr"  # ocr, mrz, pattern_match

    @field_validator("confidence_level", mode="before")
    @classmethod
    def calculate_confidence_level(cls, v, info):
        if "confidence" in info.data:
            conf = info.data["confidence"]
            if conf >= 0.9:
                return ExtractionConfidence.HIGH
            elif conf >= 0.6:
                return ExtractionConfidence.MEDIUM
            else:
                return ExtractionConfidence.LOW
        return v


class MRZData(BaseModel):
    """Machine Readable Zone data from ID documents"""
    line1: Optional[str] = None
    line2: Optional[str] = None
    line3: Optional[str] = None  # For some passport formats
    checksum_valid: bool = False
    document_type: Optional[str] = None  # P (passport), ID, etc.


class IdentityDocumentExtraction(BaseModel):
    """
    Extracted data from an identity document.

    Contains all extracted fields with confidence scores.
    Sensitive data should be encrypted at rest.
    """
    # Document classification
    document_type: IdentityDocumentType
    issuing_country: Optional[str] = Field(
        None,
        description="ISO 3166-1 alpha-3 country code (e.g., ESP, GBR)"
    )

    # Personal information
    full_name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    second_last_name: Optional[str] = None  # Spanish patronymic
    document_number: Optional[str] = None
    date_of_birth: Optional[date] = None
    expiration_date: Optional[date] = None
    issue_date: Optional[date] = None
    nationality: Optional[str] = None
    gender: Optional[Gender] = None
    place_of_birth: Optional[str] = None
    address: Optional[str] = None

    # MRZ data (if present)
    mrz_data: Optional[MRZData] = None

    # For driver's license
    license_categories: Optional[List[str]] = None  # ["B", "A1", etc.]

    # Extraction metadata
    confidence_score: float = Field(
        ge=0.0, le=1.0,
        description="Overall confidence score (0.0 - 1.0)"
    )
    ocr_engine: Optional[str] = None
    processing_time_ms: float = 0.0

    # Field-level confidence
    field_confidences: Dict[str, float] = Field(
        default_factory=dict,
        description="Confidence score for each extracted field"
    )

    # Validation results
    is_valid: bool = False
    validation_errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)

    class Config:
        json_schema_extra = {
            "example": {
                "document_type": "dni",
                "issuing_country": "ESP",
                "full_name": "GARCIA MARTINEZ JUAN",
                "first_name": "JUAN",
                "last_name": "GARCIA",
                "second_last_name": "MARTINEZ",
                "document_number": "12345678A",
                "date_of_birth": "1990-01-15",
                "expiration_date": "2030-01-15",
                "nationality": "ESP",
                "gender": "M",
                "confidence_score": 0.92,
                "is_valid": True,
            }
        }


class IdentityDocumentRequest(BaseModel):
    """Request to process an identity document"""
    document_type: Optional[IdentityDocumentType] = Field(
        None,
        description="Expected document type (auto-detected if not provided)"
    )
    consent_given: bool = Field(
        ...,
        description="User explicitly consented to PII processing (required)"
    )
    purpose: str = Field(
        ...,
        description="Purpose for processing (e.g., 'identity_verification', 'kyc')"
    )
    retention_days: int = Field(
        default=90,
        ge=1,
        le=365,
        description="Days to retain extracted data (GDPR compliance)"
    )


class IdentityDocumentResponse(BaseModel):
    """Response from identity document processing"""
    success: bool
    extraction: Optional[IdentityDocumentExtraction] = None
    error: Optional[str] = None

    # GDPR metadata
    retention_until: Optional[datetime] = None
    audit_id: Optional[UUID] = None

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "extraction": {
                    "document_type": "dni",
                    "full_name": "GARCIA MARTINEZ JUAN",
                    "document_number": "12345678A",
                    "confidence_score": 0.92,
                },
                "retention_until": "2024-06-15T00:00:00Z",
                "audit_id": "550e8400-e29b-41d4-a716-446655440000",
            }
        }


class IdentityExtractionAuditLog(BaseModel):
    """Audit log entry for identity document access (GDPR compliance)"""
    id: UUID
    document_id: UUID
    tenant_id: UUID
    user_id: UUID
    action: str  # extract, view, export, delete
    timestamp: datetime
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    purpose: str
    fields_accessed: List[str] = Field(default_factory=list)


class IdentityDocumentDBCreate(BaseModel):
    """Schema for creating identity document extraction in database"""
    document_id: UUID
    tenant_id: UUID
    document_type: IdentityDocumentType
    issuing_country: Optional[str] = None
    extracted_data: Dict[str, Any]  # Encrypted JSON
    confidence_score: float
    ocr_engine: Optional[str] = None
    retention_until: datetime
    consent_purpose: str
    created_by: UUID


class IdentityDocumentDB(IdentityDocumentDBCreate):
    """Schema for identity document extraction from database"""
    id: UUID
    created_at: datetime
    access_log: List[Dict[str, Any]] = Field(default_factory=list)

    class Config:
        from_attributes = True
