"""
Verified Document Service - Stop-and-Go Orchestration

This service implements the "Agent Self-Verifies" pattern:
1. Writer generates ONE claim
2. Inline verifier searches Weaviate + web for evidence, evaluates with LLM
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
    │   │ Generate   │    │ (Inline: Weav  │    │ (Redis)        │   │
    │   │ ONE Claim  │    │  + Web + LLM)  │    │ Store Verified │   │
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


def _is_duplicate_claim(
    new_text: str,
    existing_claims: list[VerifiedClaim],
    threshold: float = 0.65,
) -> bool:
    """Check if a claim is too similar to any existing verified claim using word overlap."""
    if not existing_claims:
        return False

    new_words = set(new_text.lower().split())
    if len(new_words) < 3:
        return False

    for claim in existing_claims:
        existing_words = set(claim.text.lower().split())
        if not existing_words:
            continue
        intersection = new_words & existing_words
        union = new_words | existing_words
        similarity = len(intersection) / len(union) if union else 0
        if similarity >= threshold:
            return True

    return False


# =============================================================================
# RLM-Powered Evidence Filtering
# =============================================================================

async def _rlm_filter_evidence(
    claim_text: str,
    uploaded_texts: list[dict],
    max_evidence: int = 5,
) -> list[dict]:
    """
    Use RLM utilities to chunk uploaded documents and filter by relevance.

    Instead of naive fixed-size chunking, this:
    1. Uses RLM's paragraph-boundary-aware chunking
    2. Scores each chunk against the claim using word overlap + position
    3. Returns only the top-N most relevant chunks

    Args:
        claim_text: The claim to find evidence for
        uploaded_texts: List of {"id", "filename", "text"} dicts
        max_evidence: Maximum evidence items to return

    Returns:
        List of evidence dicts ready for verification
    """
    from app.agents.langgraph.nodes.rlm_processor import _chunk_documents, _estimate_tokens

    # Convert uploaded texts to the format RLM expects
    docs_for_rlm = []
    doc_meta = {}  # chunk_index -> (doc_id, doc_title)
    for t in uploaded_texts:
        text = t.get("text", "")
        if not text:
            continue
        doc_id = t.get("id", "uploaded")
        doc_title = t.get("filename", "Uploaded document")
        docs_for_rlm.append({"content": text, "title": doc_title})
        doc_meta[doc_id] = doc_title

    if not docs_for_rlm:
        return []

    # Use RLM chunking (paragraph-boundary aware, overlap for context)
    # Smaller chunks than normal RLM since we only need evidence snippets
    rlm_chunks = _chunk_documents(
        docs=docs_for_rlm,
        chunk_size=1500,   # ~6000 chars — smaller than RLM default for evidence
        overlap=100,       # ~400 chars overlap
        max_chunks=30,     # Cap total chunks
    )

    if not rlm_chunks:
        return []

    # Score chunks by relevance to claim
    claim_words = set(claim_text.lower().split())
    # Remove stopwords for better matching
    stopwords = {
        "el", "la", "los", "las", "de", "del", "en", "un", "una", "que", "es",
        "y", "a", "por", "con", "se", "para", "no", "al", "lo", "como", "su",
        "the", "is", "a", "an", "of", "in", "to", "and", "for", "on", "with",
    }
    claim_words -= stopwords

    scored_chunks = []
    for i, chunk in enumerate(rlm_chunks):
        if len(chunk.strip()) < 30:
            continue
        chunk_words = set(chunk.lower().split()) - stopwords
        # Word overlap score
        overlap_count = len(claim_words & chunk_words)
        # Normalize by claim size for fair comparison
        score = overlap_count / max(len(claim_words), 1)
        scored_chunks.append((score, i, chunk))

    # Sort by relevance score (highest first)
    scored_chunks.sort(key=lambda x: x[0], reverse=True)

    # Take top-N
    top_chunks = scored_chunks[:max_evidence]

    # Resolve doc metadata (use first doc as default since RLM merges docs)
    first_doc_id = list(doc_meta.keys())[0] if doc_meta else "uploaded"
    first_doc_title = list(doc_meta.values())[0] if doc_meta else "Uploaded document"

    evidence = []
    for score, chunk_idx, chunk_text in top_chunks:
        evidence.append({
            "document_id": first_doc_id,
            "document_title": first_doc_title,
            "chunk_id": f"rlm_chunk_{chunk_idx}",
            "text_excerpt": chunk_text[:2000],  # Cap excerpt size
            "similarity_score": round(min(score, 1.0), 3),
            "source": "uploaded",
        })

    if evidence:
        logger.info(
            f"📎 RLM evidence: {len(evidence)}/{len(rlm_chunks)} chunks "
            f"(scores: {', '.join(str(round(e.get('similarity_score', 0), 2)) for e in evidence)})"
        )

    return evidence


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

        # Store session metadata for later PDF export
        from datetime import datetime, timezone
        await self._cache.store_session_metadata(
            request.tenant_id,
            session_id,
            {
                "query": request.query,
                "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
                "session_id": session_id,
            },
        )

        # Hydrate uploaded document texts (same pattern as normal Emma flow)
        uploaded_texts: list[dict] = []
        if request.uploaded_file_ids:
            try:
                from app.services.upload_context_service import upload_context_service
                uploaded_texts = upload_context_service.get_texts(request.uploaded_file_ids)
                if uploaded_texts:
                    logger.info(f"📎 Hydrated {len(uploaded_texts)} uploaded document(s) for verified generation")
            except Exception as e:
                logger.warning(f"⚠️ Failed to hydrate uploads: {e}")

        # Get source context from Weaviate and/or uploads
        source_context = await self._get_source_context(
            query=request.query,
            tenant_id=request.tenant_id,
            document_ids=request.context_document_ids,
            collections=request.collections,
            uploaded_texts=uploaded_texts,
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
        duplicate_streak = 0
        sources_map: dict[str, dict] = {}  # id -> {title, source, url}
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

            # Deduplicate: skip if too similar to an existing verified claim
            if _is_duplicate_claim(candidate.text, verified_claims):
                logger.info(
                    f"⏭️ Skipping duplicate claim #{claim_position}: {candidate.text[:60]}..."
                )
                duplicate_streak += 1
                if duplicate_streak >= 2:
                    logger.info("🏁 Stopping generation: consecutive duplicates detected")
                    break
                continue
            duplicate_streak = 0

            yield VerificationEvent(
                event_type=VerificationEventType.CLAIM_GENERATED,
                claim_id=candidate.id,
                data={
                    "claim_text": candidate.text,
                    "claim_number": claim_position,
                },
                progress_percent=min(90, 10 + (claims_generated * 80 // request.max_claims)),
            )

            # Verify claim inline (Weaviate + web + LLM)
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
                    uploaded_texts=uploaded_texts,
                )
                total_verification_time += verification_result.get("verification_time_ms", 0)

                # Collect source details for PDF export
                for ev in verification_result.get("evidence", []):
                    src_id = ev.get("document_id", "")
                    if src_id not in sources_map:
                        sources_map[src_id] = {
                            "id": src_id,
                            "title": ev.get("document_title", ""),
                            "source": ev.get("source", "internal"),
                            "url": ev.get("url", ""),
                        }

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

        # Update session metadata with execution stats and sources
        existing_meta = await self._cache.get_session_metadata(request.tenant_id, session_id)
        existing_meta["execution_time_ms"] = execution_time_ms
        existing_meta["sources"] = list(sources_map.values())
        await self._cache.store_session_metadata(request.tenant_id, session_id, existing_meta)

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
                "sources": list(sources_map.values()),
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
        uploaded_texts: Optional[list[dict]] = None,
    ) -> str:
        """
        Get source context from uploaded documents and/or Weaviate.

        Uses uploaded document text first (already hydrated), then supplements
        with Weaviate search results if available.
        """
        context_parts: list[str] = []

        # --- Priority 1: Uploaded document text (already extracted) ---
        if uploaded_texts:
            for t in uploaded_texts:
                filename = t.get("filename", "Uploaded document")
                text = t.get("text", "")[:3000]
                if text:
                    context_parts.append(f"[{filename}]\n{text}")
                    logger.info(f"📎 Source context from upload: {filename} ({len(text)} chars)")

        # --- Priority 2: Weaviate search ---
        if not context_parts:
            sanitized_tenant = tenant_id.replace("-", "_")
            collection_name = collections[0] if collections else f"Nouxcube_{sanitized_tenant}_documents"

            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        f"{settings.weaviate_service_url}/weaviate/collections/{collection_name}/search",
                        headers={
                            "Content-Type": "application/json",
                            "X-API-Key": settings.MICROSERVICES_API_KEY,
                        },
                        json={
                            "query": query,
                            "tenant_id": tenant_id,
                            "limit": 10,
                            "search_type": "hybrid",
                            "is_admin": True,
                        },
                    )

                    if response.status_code == 200:
                        data = response.json()
                        results = data.get("results", [])
                        for result in results[:5]:
                            title = result.get("title", "Document")
                            content = result.get("content", "")[:2000]
                            context_parts.append(f"[{title}]\n{content}")
                    else:
                        logger.warning(f"⚠️ Weaviate source context returned {response.status_code}")

            except Exception as e:
                logger.error(f"❌ Weaviate source context failed: {e}")

        return "\n\n---\n\n".join(context_parts)

    async def _verify_claim(
        self,
        candidate: CandidateClaim,
        tenant_id: str,
        session_id: str,
        context_document_ids: Optional[List[str]] = None,
        collections: Optional[List[str]] = None,
        confidence_threshold: float = 0.7,
        timeout: int = 45,
        uploaded_texts: Optional[list[dict]] = None,
    ) -> dict:
        """
        Verify a claim inline using emma-agent-service's own clients.

        Searches Weaviate + web for evidence, then evaluates with vLLM.

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
        import json
        import re
        from datetime import datetime, timezone

        start_time = time.time()
        SIMILARITY_THRESHOLD = 0.65

        try:
            # --- Step 1a: Search Weaviate for evidence ---
            sanitized_tenant = tenant_id.replace("-", "_")
            safe_tenant = ''.join(c for c in tenant_id if c.isalnum())[:32]
            # Try collections in priority order: explicit > documents > knowledge
            candidate_collections = (
                [collections[0]] if collections
                else [
                    f"Nouxcube_{sanitized_tenant}_documents",
                    f"Nouxcube_{safe_tenant}_knowledge",
                ]
            )
            evidence: list = []

            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                  for collection_name in candidate_collections:
                    response = await client.post(
                        f"{settings.weaviate_service_url}/weaviate/collections/{collection_name}/search",
                        headers={
                            "Content-Type": "application/json",
                            "X-API-Key": settings.MICROSERVICES_API_KEY,
                        },
                        json={
                            "query": candidate.text,
                            "tenant_id": tenant_id,
                            "limit": 5,
                            "search_type": "hybrid",
                            "is_admin": True,
                        },
                    )
                    if response.status_code == 200:
                        results = response.json().get("results", [])
                        for r in results:
                            distance = r.get("distance", 1.0)
                            similarity = 1.0 - min(distance, 1.0)
                            if similarity >= SIMILARITY_THRESHOLD:
                                evidence.append({
                                    "document_id": r.get("document_id", ""),
                                    "document_title": r.get("title", ""),
                                    "chunk_id": r.get("chunk_id"),
                                    "text_excerpt": r.get("content", "")[:500],
                                    "similarity_score": round(similarity, 3),
                                    "source": "internal",
                                })
                        logger.info(f"✅ Weaviate evidence from '{collection_name}': {len(evidence)} items")
                        break  # Found results, stop trying other collections
                    else:
                        logger.debug(f"⚠️ Collection '{collection_name}' returned {response.status_code}, trying next...")
            except Exception as e:
                logger.error(f"❌ Weaviate evidence search failed: {e}")

            # --- Step 1a-bis: Use uploaded document text as evidence (RLM-powered) ---
            # Uses RLM chunking (paragraph-boundary aware) + LLM relevance filtering
            MAX_UPLOAD_EVIDENCE = 5
            if not evidence and uploaded_texts:
                evidence = await _rlm_filter_evidence(
                    candidate.text, uploaded_texts, max_evidence=MAX_UPLOAD_EVIDENCE
                )

            # --- Step 1b: Search web for supplementary evidence (with timeout) ---
            MAX_WEB_EVIDENCE = 3
            if settings.web_search_enabled and len(evidence) < MAX_UPLOAD_EVIDENCE:
                try:
                    from app.services.web_search import get_web_search_client
                    import hashlib

                    web_client = get_web_search_client()
                    web_results = await asyncio.wait_for(
                        web_client.search(candidate.text, max_results=3),
                        timeout=10.0,  # 10s max for web search per claim
                    )
                    for wr in web_results:
                        url_hash = hashlib.md5(wr.url.encode()).hexdigest()[:12]
                        evidence.append({
                            "document_id": f"web:{url_hash}",
                            "document_title": wr.title,
                            "chunk_id": None,
                            "text_excerpt": wr.snippet[:500],
                            "similarity_score": 0.70,
                            "source": "web",
                            "url": wr.url,
                        })
                    if web_results:
                        logger.info(f"🌐 Added {len(web_results)} web evidence items")
                except asyncio.TimeoutError:
                    logger.warning("⏱️ Web evidence search timed out (10s), skipping")
                except Exception as e:
                    logger.warning(f"Web evidence search failed (non-fatal): {e}")

            # --- Step 2: Evaluate claim with LLM ---
            if not evidence:
                evaluation = {
                    "supported": False,
                    "confidence": 0.0,
                    "reason": "No evidence found to support the claim",
                    "correction": None,
                }
            else:
                # Build evidence context with source labels (cap at ~8000 chars for LLM context)
                MAX_EVIDENCE_CHARS = 8000
                evidence_parts = []
                total_chars = 0
                for e in evidence:
                    source = e.get("source", "internal")
                    if source == "web":
                        label = f"[Web Source: {e.get('document_title', 'Unknown')} - {e.get('url', '')}]"
                    elif source == "uploaded":
                        label = f"[Uploaded Document: {e.get('document_title', 'Unknown')}]"
                    else:
                        label = f"[Internal Document: {e.get('document_title', 'Unknown')}]"
                    part = f"{label}\n{e['text_excerpt']}"
                    if total_chars + len(part) > MAX_EVIDENCE_CHARS:
                        # Include truncated remainder if we have room
                        remaining = MAX_EVIDENCE_CHARS - total_chars
                        if remaining > 100:
                            evidence_parts.append(part[:remaining] + "...")
                        break
                    evidence_parts.append(part)
                    total_chars += len(part)
                evidence_text = "\n\n".join(evidence_parts)

                system_prompt = (
                    "You are a fact-checking assistant. Evaluate if a claim is supported by evidence.\n\n"
                    "Respond ONLY with a JSON object (no markdown, no explanation):\n"
                    '{"supported": true/false, "confidence": 0.0-1.0, "reason": "brief reason", '
                    '"correction": "rewritten claim text or null"}\n\n'
                    "Rules:\n"
                    "- supported=true if the evidence reasonably supports or is consistent with the claim\n"
                    "- For uploaded documents: the claim was generated FROM this document, so verify it reflects the content accurately\n"
                    "- Prioritize evidence from internal/uploaded documents. Web evidence is supplementary.\n"
                    "- If the claim paraphrases or summarizes the evidence correctly, mark as supported with high confidence\n"
                    "- When web evidence supports the general idea of the claim, mark as supported\n"
                    "- IMPORTANT: 'correction' must be the REWRITTEN CLAIM TEXT in the SAME LANGUAGE as the original claim, NOT a meta-comment about what to change\n"
                    "- If the claim is mostly correct but needs minor fixes, set correction to the improved claim text\n"
                    "- If the claim cannot be fixed, set correction to null\n"
                    "- NEVER use <think> tags. Output JSON directly."
                )
                user_prompt = (
                    f"CLAIM TO VERIFY:\n{candidate.text}\n\n"
                    f"EVIDENCE:\n{evidence_text}\n\n"
                    "Evaluate if the claim is supported by the evidence. Respond with JSON only."
                )

                evaluation = {"supported": False, "confidence": 0.0, "reason": "LLM evaluation failed", "correction": None}

                try:
                    from app.agents.llm_client import get_llm_client

                    llm_client = await get_llm_client()
                    llm_response = await llm_client.chat(
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        temperature=0.1,
                        max_tokens=500,
                        enable_thinking=False,
                    )

                    if llm_response and llm_response.content:
                        content = llm_response.content.strip()
                        logger.debug(f"🔍 Raw LLM response ({len(content)} chars): {content[:300]}")
                        # Clean thinking tags
                        content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL)
                        if '<think>' in content:
                            content = content[:content.find('<think>')]
                        content = content.strip()
                        # Clean markdown code blocks
                        if content.startswith("```"):
                            content = content.split("```")[1]
                            if content.startswith("json"):
                                content = content[4:]
                            content = content.strip()

                        # Try to extract JSON object from response
                        parsed = False
                        try:
                            result = json.loads(content)
                            parsed = True
                        except json.JSONDecodeError:
                            # Try to find JSON object within the text
                            json_match = re.search(r'\{[^{}]*"supported"[^{}]*\}', content, re.DOTALL)
                            if json_match:
                                try:
                                    result = json.loads(json_match.group())
                                    parsed = True
                                except json.JSONDecodeError:
                                    pass

                        if parsed:
                            evaluation = {
                                "supported": result.get("supported", False),
                                "confidence": float(result.get("confidence", 0.0)),
                                "reason": result.get("reason", ""),
                                "correction": result.get("correction"),
                            }
                        else:
                            logger.warning(f"⚠️ Failed to parse LLM JSON: {content[:300]}")
                            # Fallback: if response contains "true" or "supported", assume positive
                            lower = content.lower()
                            if '"supported": true' in lower or '"supported":true' in lower:
                                evaluation = {"supported": True, "confidence": 0.7, "reason": "Parsed from non-JSON response", "correction": None}
                            else:
                                evaluation["reason"] = "Could not parse LLM response"

                except Exception as e:
                    logger.error(f"❌ LLM claim evaluation failed: {e}")

            # --- Step 3: Build result ---
            if evaluation["supported"] and evaluation["confidence"] >= confidence_threshold:
                status = "verified"
            elif evaluation["correction"]:
                status = "corrected"
            else:
                status = "rejected"

            verification_time_ms = int((time.time() - start_time) * 1000)

            evidence_matches = [
                {
                    "document_id": e["document_id"],
                    "document_title": e.get("document_title"),
                    "chunk_id": e.get("chunk_id"),
                    "text_excerpt": e["text_excerpt"],
                    "similarity_score": e["similarity_score"],
                    "supports_claim": evaluation["supported"],
                }
                for e in evidence
            ]

            result = {
                "claim_id": candidate.id,
                "status": status,
                "confidence": evaluation["confidence"],
                "evidence": evidence_matches,
                "correction": evaluation.get("correction"),
                "rejection_reason": evaluation.get("reason") if status == "rejected" else None,
                "verification_time_ms": verification_time_ms,
                "verified_at": datetime.now(timezone.utc).isoformat(),
            }

            logger.info(
                f"✅ Claim verification complete: status={status}, "
                f"confidence={evaluation['confidence']:.2f}, time={verification_time_ms}ms"
            )
            return result

        except Exception as e:
            verification_time_ms = int((time.time() - start_time) * 1000)
            logger.error(f"❌ Claim verification failed: {e}")
            return {
                "claim_id": candidate.id,
                "status": "error",
                "confidence": 0.0,
                "evidence": [],
                "correction": None,
                "rejection_reason": f"Verification error: {str(e)}",
                "verification_time_ms": verification_time_ms,
                "verified_at": datetime.now(timezone.utc).isoformat(),
            }

    def _assemble_document(
        self,
        query: str,
        claims: List[VerifiedClaim],
    ) -> str:
        """
        Assemble the final document from verified claims using a Jinja2 template.

        Args:
            query: Original query (used for title)
            claims: List of verified claims

        Returns:
            Formatted document text (markdown)
        """
        if not claims:
            return "No se pudieron generar claims verificados."

        from pathlib import Path
        from jinja2 import Environment, FileSystemLoader

        template_dir = Path(__file__).parent.parent.parent.parent / "config" / "templates"
        env = Environment(loader=FileSystemLoader(str(template_dir)))
        template = env.get_template("verified_document.md")

        return template.render(
            query=query,
            claims=[
                {
                    "text": c.text,
                    "confidence": c.confidence,
                    "status": c.status.value,
                    "original_text": c.original_text,
                }
                for c in claims
            ],
        ).strip()


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
