"""
Verified Generation Service - Agent Self-Verifies Pattern

This package implements verified document generation where each claim
is validated against Weaviate before being accepted into the final document.

Components:
- VerifiedContextCache: Redis-backed storage for verified claims
- WriterAgent: Generates claims using SGLang
- VerifiedDocumentService: Orchestrates the stop-and-go verification loop

Usage:
    from app.services.verified_generation import (
        get_verified_document_service,
        VerifiedDocumentService,
    )

    service = get_verified_document_service()
    async for event in service.generate_verified_document(request):
        # Handle streaming events
        pass
"""

from .verified_cache import (
    VerifiedContextCache,
    get_verified_cache,
    initialize_verified_cache,
)
from .writer_agent import (
    WriterAgent,
    get_writer_agent,
)
from .service import (
    VerifiedDocumentService,
    get_verified_document_service,
    initialize_verified_document_service,
)

__all__ = [
    # Cache
    "VerifiedContextCache",
    "get_verified_cache",
    "initialize_verified_cache",
    # Writer
    "WriterAgent",
    "get_writer_agent",
    # Service
    "VerifiedDocumentService",
    "get_verified_document_service",
    "initialize_verified_document_service",
]
