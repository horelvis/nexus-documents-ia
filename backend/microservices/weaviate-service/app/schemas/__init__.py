"""Pydantic schemas for Weaviate service"""

from .verified_generation import (
    VerificationStatus,
    VerificationEventType,
    CandidateClaim,
    EvidenceMatch,
    VerificationResult,
    VerifiedClaim,
    VerificationEvent,
    VerifiedDocumentRequest,
    VerifiedDocumentResponse,
    VerifiedClaimSummary,
    VerificationSessionStatus,
    SessionClaimsResponse,
)

__all__ = [
    # Verified Generation
    "VerificationStatus",
    "VerificationEventType",
    "CandidateClaim",
    "EvidenceMatch",
    "VerificationResult",
    "VerifiedClaim",
    "VerificationEvent",
    "VerifiedDocumentRequest",
    "VerifiedDocumentResponse",
    "VerifiedClaimSummary",
    "VerificationSessionStatus",
    "SessionClaimsResponse",
]