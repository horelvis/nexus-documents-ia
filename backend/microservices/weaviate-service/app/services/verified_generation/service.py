"""
Verified Document Service - Stop-and-Go Orchestration

This service implements the "Agent Self-Verifies" pattern:
1. Writer generates ONE claim
2. Celery task verifies the claim against Weaviate
3. If verified, claim is cached in Redis
4. Repeat until document is complete

The loop is SERIAL by design - each new claim builds on verified context only.

Architecture:
    ┌─────────────────────────────────────────────────────────────────┐
    │                    STOP-AND-GO LOOP                              │
    ├─────────────────────────────────────────────────────────────────┤
    │                                                                  │
    │   ┌────────────┐    ┌────────────────┐    ┌────────────────┐   │
    │   │ 1. Writer  │───▶│ 2. Verifier    │───▶│ 3. Cache       │   │
    │   │ Generate   │    │ (Celery Task)  │    │ (Redis)        │   │
    │   │ ONE Claim  │    │ Search+Eval    │    │ Store Verified │   │
    │   └────────────┘    └────────────────┘    └────────────────┘   │
    │        │                                         │              │
    │        │◀────────────────────────────────────────┘              │
    │        │     (Context for next claim)                           │
    │                                                                  │
    └─────────────────────────────────────────────────────────────────┘

Usage:
    service = get_verified_document_service()

    # Streaming (SSE)
    async for event in service.generate_verified_document(request):
        yield event.to_sse()

    # Sync (wait for complete document)
    response = await service.generate_verified_document_sync(request)
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from typing import AsyncGenerator, List, Optional

import httpx

from app.core.config import settings
from app.schemas.verified_generation import (
    CandidateClaim,
    VerificationEvent,
    VerificationEventType,
    VerificationResult,
    VerificationStatus,
    VerifiedClaim,
    VerifiedClaimSummary,
    VerifiedDocumentRequest,
    VerifiedDocumentResponse,
)

from .verified_cache import get_verified_cache, VerifiedContextCache
from .writer_agent import get_writer_agent, WriterAgent

logger = logging.getLogger(__name__)

# Service URLs configuration (use Docker service names for inter-container communication)
WEAVIATE_SERVICE_URL = os.getenv("WEAVIATE_SERVICE_URL", "http://weaviate-service:8000")
BACKGROUND_WORKER_URL = os.getenv("BACKGROUND_WORKER_URL", "http://background-worker:8100")
MICROSERVICES_API_KEY = os.getenv("MICROSERVICES_API_KEY", "")


class VerifiedDocumentService:
    """
    Orchestrates verified document generation.

    Implements the stop-and-go pattern where each claim is verified
    before the next one is generated.
    """

    def __init__(
        self,
        writer: Optional[WriterAgent] = None,
        cache: Optional[VerifiedContextCache] = None,
    ):
        """
        Initialize the service.

        Args:
            writer: WriterAgent instance (uses singleton if None)
            cache: VerifiedContextCache instance (uses singleton if None)
        """
        self._writer = writer
        self._cache = cache
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize service components."""
        if self._initialized:
            return

        if self._writer is None:
            self._writer = get_writer_agent()

        if self._cache is None:
            self._cache = get_verified_cache()
            await self._cache.connect()

        self._initialized = True
        logger.info("✅ VerifiedDocumentService initialized")

    async def generate_verified_document(
        self,
        request: VerifiedDocumentRequest,
    ) -> AsyncGenerator[VerificationEvent, None]:
        """
        Generate a verified document with streaming progress events.

        This is the main entry point for SSE streaming. Events are yielded
        as the document is generated claim by claim.

        Args:
            request: Generation request with parameters

        Yields:
            VerificationEvent for each step in the process
        """
        await self.initialize()

        start_time = time.time()
        session_id = request.session_id or str(uuid.uuid4())

        # Clear any existing session data
        await self._cache.clear_session(request.tenant_id, session_id)

        # Get source context from Weaviate
        source_context = await self._get_source_context(
            query=request.query,
            tenant_id=request.tenant_id,
            document_ids=request.context_document_ids,
            collections=request.collections,
        )

        yield VerificationEvent(
            event_type=VerificationEventType.PROGRESS,
            data={
                "message": "Context retrieved, starting generation...",
                "session_id": session_id,
                "source_documents": len(request.context_document_ids) if request.context_document_ids else 0,
            },
            progress_percent=10,
        )

        # Statistics tracking
        claims_generated = 0
        claims_verified = 0
        claims_corrected = 0
        claims_rejected = 0
        correction_attempts = {}  # Track correction attempts per claim position
        total_verification_time = 0

        # Stop-and-go loop
        while claims_generated < request.max_claims:
            # Get verified claims so far
            verified_claims = await self._cache.get_verified_claims(
                request.tenant_id, session_id
            )

            # Check if document is complete
            if len(verified_claims) >= 3:
                is_complete = await self._writer.check_completion(
                    query=request.query,
                    verified_claims=verified_claims,
                    source_context=source_context,
                )
                if is_complete:
                    logger.info(f"🏁 Document generation complete at {len(verified_claims)} claims")
                    break

            # Generate next claim
            claims_generated += 1
            claim_position = len(verified_claims) + 1

            try:
                candidate = await self._writer.generate_next_claim(
                    query=request.query,
                    verified_claims=verified_claims,
                    source_context=source_context,
                    claim_number=claim_position,
                )
                candidate.context_document_ids = request.context_document_ids or []

            except Exception as e:
                logger.error(f"❌ Failed to generate claim: {e}")
                yield VerificationEvent(
                    event_type=VerificationEventType.ERROR,
                    data={"error": f"Claim generation failed: {str(e)}"},
                )
                break

            yield VerificationEvent(
                event_type=VerificationEventType.CLAIM_GENERATED,
                claim_id=candidate.id,
                data={
                    "claim_text": candidate.text,
                    "claim_number": claim_position,
                },
                progress_percent=min(90, 10 + (claims_generated * 80 // request.max_claims)),
            )

            # Send to Celery for verification
            yield VerificationEvent(
                event_type=VerificationEventType.VERIFICATION_STARTED,
                claim_id=candidate.id,
                data={"message": "Verifying claim against documents..."},
            )

            try:
                verification_result = await self._verify_claim(
                    candidate=candidate,
                    tenant_id=request.tenant_id,
                    session_id=session_id,
                    context_document_ids=request.context_document_ids,
                    collections=request.collections,
                    confidence_threshold=request.confidence_threshold,
                    timeout=request.verification_timeout_seconds,
                )
                total_verification_time += verification_result.get("verification_time_ms", 0)

            except asyncio.TimeoutError:
                logger.warning(f"⏱️ Verification timeout for claim {candidate.id}")
                yield VerificationEvent(
                    event_type=VerificationEventType.VERIFICATION_TIMEOUT,
                    claim_id=candidate.id,
                    data={"message": "Verification timed out, skipping claim"},
                )
                continue

            except Exception as e:
                logger.error(f"❌ Verification failed: {e}")
                yield VerificationEvent(
                    event_type=VerificationEventType.ERROR,
                    claim_id=candidate.id,
                    data={"error": f"Verification failed: {str(e)}"},
                )
                continue

            # Process verification result
            status = verification_result.get("status", "error")

            if status == "verified":
                # Claim verified - add to cache
                verified_claim = VerifiedClaim(
                    id=candidate.id,
                    text=candidate.text,
                    status=VerificationStatus.VERIFIED,
                    confidence=verification_result.get("confidence", 0.0),
                    evidence_document_ids=[
                        e["document_id"]
                        for e in verification_result.get("evidence", [])
                    ],
                    generation_order=claim_position,
                )
                await self._cache.add_verified_claim(
                    request.tenant_id, session_id, verified_claim
                )
                claims_verified += 1

                yield VerificationEvent(
                    event_type=VerificationEventType.CLAIM_VERIFIED,
                    claim_id=candidate.id,
                    data={
                        "claim_text": candidate.text,
                        "confidence": verification_result.get("confidence", 0.0),
                        "evidence_count": len(verification_result.get("evidence", [])),
                    },
                )

            elif status == "corrected" and request.auto_correct:
                # Claim corrected - check if we should accept correction
                current_attempts = correction_attempts.get(claim_position, 0)

                if current_attempts < request.max_correction_attempts:
                    correction = verification_result.get("correction", "")
                    if correction:
                        # Accept the correction
                        corrected_claim = VerifiedClaim(
                            id=candidate.id,
                            text=correction,
                            original_text=candidate.text,
                            status=VerificationStatus.CORRECTED,
                            confidence=verification_result.get("confidence", 0.0),
                            evidence_document_ids=[
                                e["document_id"]
                                for e in verification_result.get("evidence", [])
                            ],
                            generation_order=claim_position,
                        )
                        await self._cache.add_verified_claim(
                            request.tenant_id, session_id, corrected_claim
                        )
                        claims_corrected += 1
                        correction_attempts[claim_position] = current_attempts + 1

                        yield VerificationEvent(
                            event_type=VerificationEventType.CLAIM_CORRECTED,
                            claim_id=candidate.id,
                            data={
                                "original_text": candidate.text,
                                "corrected_text": correction,
                                "confidence": verification_result.get("confidence", 0.0),
                            },
                        )
                    else:
                        claims_rejected += 1
                        yield VerificationEvent(
                            event_type=VerificationEventType.CLAIM_REJECTED,
                            claim_id=candidate.id,
                            data={
                                "claim_text": candidate.text,
                                "reason": verification_result.get("rejection_reason", "No correction available"),
                            },
                        )
                else:
                    claims_rejected += 1
                    yield VerificationEvent(
                        event_type=VerificationEventType.CLAIM_REJECTED,
                        claim_id=candidate.id,
                        data={
                            "claim_text": candidate.text,
                            "reason": "Max correction attempts exceeded",
                        },
                    )

            else:
                # Claim rejected
                claims_rejected += 1
                yield VerificationEvent(
                    event_type=VerificationEventType.CLAIM_REJECTED,
                    claim_id=candidate.id,
                    data={
                        "claim_text": candidate.text,
                        "reason": verification_result.get("rejection_reason", "Unknown"),
                    },
                )

            # Extend cache TTL
            await self._cache.extend_ttl(request.tenant_id, session_id)

        # Assemble final document
        final_claims = await self._cache.get_verified_claims(request.tenant_id, session_id)
        document_text = self._assemble_document(request.query, final_claims)

        execution_time_ms = int((time.time() - start_time) * 1000)

        # Calculate average confidence
        avg_confidence = (
            sum(c.confidence for c in final_claims) / len(final_claims)
            if final_claims else 0.0
        )

        # Collect evidence document IDs
        all_evidence_ids = set()
        for claim in final_claims:
            all_evidence_ids.update(claim.evidence_document_ids)

        yield VerificationEvent(
            event_type=VerificationEventType.DOCUMENT_COMPLETE,
            data={
                "session_id": session_id,
                "document_text": document_text,
                "total_claims_generated": claims_generated,
                "claims_verified": claims_verified,
                "claims_corrected": claims_corrected,
                "claims_rejected": claims_rejected,
                "average_confidence": round(avg_confidence, 3),
                "execution_time_ms": execution_time_ms,
                "verification_time_ms": total_verification_time,
                "evidence_document_ids": list(all_evidence_ids),
            },
            progress_percent=100,
        )

    async def generate_verified_document_sync(
        self,
        request: VerifiedDocumentRequest,
    ) -> VerifiedDocumentResponse:
        """
        Generate a verified document synchronously.

        Waits for the complete document before returning.

        Args:
            request: Generation request

        Returns:
            Complete VerifiedDocumentResponse
        """
        final_event = None
        claims_data = []

        async for event in self.generate_verified_document(request):
            if event.event_type == VerificationEventType.DOCUMENT_COMPLETE:
                final_event = event
            elif event.event_type in (
                VerificationEventType.CLAIM_VERIFIED,
                VerificationEventType.CLAIM_CORRECTED,
            ):
                claims_data.append(event.data)

        if not final_event:
            raise Exception("Document generation did not complete")

        data = final_event.data
        session_id = data.get("session_id", "")

        # Build claim summaries
        claim_summaries = [
            VerifiedClaimSummary(
                text=c.get("claim_text", c.get("corrected_text", "")),
                confidence=c.get("confidence", 0.0),
                status=VerificationStatus.VERIFIED if "corrected_text" not in c else VerificationStatus.CORRECTED,
                evidence_count=c.get("evidence_count", 0),
            )
            for c in claims_data
        ]

        return VerifiedDocumentResponse(
            session_id=session_id,
            query=request.query,
            document_text=data.get("document_text", ""),
            claims=claim_summaries,
            total_claims_generated=data.get("total_claims_generated", 0),
            claims_verified=data.get("claims_verified", 0),
            claims_corrected=data.get("claims_corrected", 0),
            claims_rejected=data.get("claims_rejected", 0),
            average_confidence=data.get("average_confidence", 0.0),
            execution_time_ms=data.get("execution_time_ms", 0),
            verification_time_ms=data.get("verification_time_ms", 0),
            evidence_document_ids=data.get("evidence_document_ids", []),
        )

    async def _get_source_context(
        self,
        query: str,
        tenant_id: str,
        document_ids: Optional[List[str]] = None,
        collections: Optional[List[str]] = None,
    ) -> str:
        """
        Get source context from Weaviate.

        Uses hybrid search to find relevant documents.
        Collection name follows pattern: Nouxcube_{tenant_id}_documents
        """
        # Build collection name from tenant_id (format: Nouxcube_{tenant_id}_documents)
        sanitized_tenant = tenant_id.replace("-", "_")
        collection_name = collections[0] if collections else f"Nouxcube_{sanitized_tenant}_documents"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{WEAVIATE_SERVICE_URL}/weaviate/collections/{collection_name}/search",
                    headers={
                        "Content-Type": "application/json",
                        "X-API-Key": MICROSERVICES_API_KEY,
                    },
                    json={
                        "query": query,
                        "tenant_id": tenant_id,
                        "limit": 10,
                        "search_type": "hybrid",
                        "is_admin": True,  # For verified generation, bypass ACL
                    },
                )

                if response.status_code == 200:
                    data = response.json()
                    results = data.get("results", [])

                    # Combine content from results
                    context_parts = []
                    for result in results[:5]:  # Top 5 documents
                        title = result.get("title", "Document")
                        content = result.get("content", "")[:2000]
                        context_parts.append(f"[{title}]\n{content}")

                    return "\n\n---\n\n".join(context_parts)

                else:
                    logger.warning(f"⚠️ Failed to get source context: {response.status_code}")
                    return ""

        except Exception as e:
            logger.error(f"❌ Failed to get source context: {e}")
            return ""

    async def _verify_claim(
        self,
        candidate: CandidateClaim,
        tenant_id: str,
        session_id: str,
        context_document_ids: Optional[List[str]] = None,
        collections: Optional[List[str]] = None,
        confidence_threshold: float = 0.7,
        timeout: int = 45,
    ) -> dict:
        """
        Send claim to Celery for verification and wait for result.

        Args:
            candidate: The claim to verify
            tenant_id: Tenant identifier
            session_id: Session identifier
            context_document_ids: Document IDs to search
            collections: Collections to search
            confidence_threshold: Min confidence
            timeout: Verification timeout in seconds

        Returns:
            Verification result dict
        """
        try:
            async with httpx.AsyncClient(timeout=float(timeout + 5)) as client:
                # Enqueue verification task
                enqueue_response = await client.post(
                    f"{BACKGROUND_WORKER_URL}/tasks/verification/verify-claim",
                    headers={
                        "Content-Type": "application/json",
                        "X-API-Key": MICROSERVICES_API_KEY,
                    },
                    json={
                        "claim_id": candidate.id,
                        "claim_text": candidate.text,
                        "tenant_id": tenant_id,
                        "context_document_ids": context_document_ids,
                        "collections": collections,
                        "confidence_threshold": confidence_threshold,
                        "session_id": session_id,
                    },
                )

                if enqueue_response.status_code != 200:
                    raise Exception(f"Failed to enqueue verification: {enqueue_response.status_code}")

                job_data = enqueue_response.json()
                job_id = job_data.get("job_id")

                if not job_id:
                    raise Exception("No job_id returned from verification task")

                # Poll for result
                poll_interval = 1.0
                elapsed = 0

                while elapsed < timeout:
                    status_response = await client.get(
                        f"{BACKGROUND_WORKER_URL}/tasks/status/{job_id}",
                        headers={"X-API-Key": MICROSERVICES_API_KEY},
                    )

                    if status_response.status_code == 200:
                        status_data = status_response.json()
                        status = status_data.get("status", "")

                        if status == "SUCCESS":
                            return status_data.get("result", {})
                        elif status in ("FAILURE", "REVOKED"):
                            raise Exception(f"Verification task failed: {status}")
                        # Still pending/running
                    else:
                        logger.warning(f"⚠️ Status check failed: {status_response.status_code}")

                    await asyncio.sleep(poll_interval)
                    elapsed += poll_interval

                # Timeout
                raise asyncio.TimeoutError(f"Verification timed out after {timeout}s")

        except asyncio.TimeoutError:
            raise
        except Exception as e:
            logger.error(f"❌ Verification failed: {e}")
            raise

    def _assemble_document(
        self,
        query: str,
        claims: List[VerifiedClaim],
    ) -> str:
        """
        Assemble the final document from verified claims.

        Args:
            query: Original query (used for title)
            claims: List of verified claims

        Returns:
            Formatted document text
        """
        if not claims:
            return "No se pudieron generar claims verificados."

        # Create document with header
        lines = [
            f"## {query}",
            "",
            f"*Documento generado con {len(claims)} claims verificados.*",
            "",
        ]

        # Add claims
        for i, claim in enumerate(claims, 1):
            confidence_str = f" (confianza: {claim.confidence:.0%})" if claim.confidence > 0 else ""
            correction_note = ""
            if claim.status == VerificationStatus.CORRECTED and claim.original_text:
                correction_note = f"\n   *(corregido de: {claim.original_text[:50]}...)*"

            lines.append(f"{i}. {claim.text}{confidence_str}{correction_note}")
            lines.append("")

        return "\n".join(lines)


# =============================================================================
# Singleton Instance
# =============================================================================

_verified_service: Optional[VerifiedDocumentService] = None


def get_verified_document_service() -> VerifiedDocumentService:
    """Get the global VerifiedDocumentService singleton."""
    global _verified_service
    if _verified_service is None:
        _verified_service = VerifiedDocumentService()
    return _verified_service


async def initialize_verified_document_service() -> VerifiedDocumentService:
    """Initialize and return the VerifiedDocumentService singleton."""
    service = get_verified_document_service()
    await service.initialize()
    return service
