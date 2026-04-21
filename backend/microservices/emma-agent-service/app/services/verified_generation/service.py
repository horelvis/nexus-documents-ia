"""
DEPRECATED: Verified Document Service - Stop-and-Go Orchestration

This service is no longer called by any API endpoint. Verified generation
is now handled by the VerifiedGenerationTool sub-graph invoked from the
ReAct agent via /emma/query. This file is kept temporarily because:
- _rlm_filter_evidence() is imported by subgraphs/evidence.py
- _assemble_document() is imported by stop_and_go/strategies/verified.py
These will be extracted when stop_and_go is fully inlined into subgraphs.

Original description:
Thin service layer that delegates to the Stop-and-Go LangGraph for the
generate → verify → decide loop. The graph handles claim generation,
evidence search, LLM evaluation, and document assembly.

Usage:
    service = get_verified_document_service()

    # Streaming (SSE)
    async for event in service.generate_verified_document(request):
        yield event.to_sse()

    # Sync (wait for complete document)
    response = await service.generate_verified_document_sync(request)
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import AsyncGenerator, List, Optional

from app.schemas.verified_generation import (
    VerificationEvent,
    VerificationEventType,
    VerificationStatus,
    VerifiedClaim,
    VerifiedClaimSummary,
    VerifiedDocumentRequest,
    VerifiedDocumentResponse,
)

from app.core.config import settings
from app.services.shared.deduplication import is_duplicate_text
from .verified_cache import get_verified_cache, VerifiedContextCache
from .writer_agent import get_writer_agent, WriterAgent

logger = logging.getLogger(__name__)


def _is_duplicate_claim(
    new_text: str,
    existing_claims: list[VerifiedClaim],
    threshold: float = settings.verified_duplicate_threshold,
) -> bool:
    """Check if a claim is too similar to any existing verified claim using word overlap."""
    existing_texts = [c.text for c in existing_claims]
    return is_duplicate_text(new_text, existing_texts, threshold=threshold)


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
            "text_excerpt": chunk_text[:settings.verified_evidence_excerpt_limit],
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
        DEPRECATED: Use VerifiedGenerationTool via /emma/query instead.

        This method is no longer called by any API endpoint.
        Kept only for the helper functions imported by strategies.

        Args:
            request: Generation request with parameters

        Yields:
            VerificationEvent for each step in the process
        """
        await self.initialize()

        start_time = time.time()
        session_id = request.session_id or str(uuid.uuid4())

        # Langfuse trace for the entire verified generation pipeline
        trace = None
        try:
            from app.core.langfuse_config import create_trace, langfuse_context as _lf_ctx
            trace = create_trace(
                "verified.generate_document",
                session_id=session_id,
                metadata={"user_id": str(request.user_id) if request.user_id else ""},
                input={"query": request.query[:500]},
                tags=["verified-generation"],
            )
            if trace:
                _lf_ctx.push_observation(trace)
        except Exception:
            pass  # Non-fatal: observability should never break generation

        # Hydrate uploaded document texts
        uploaded_texts: list[dict] = []
        if request.uploaded_file_ids:
            try:
                from app.services.upload_context_service import upload_context_service
                uploaded_texts = upload_context_service.get_texts(request.uploaded_file_ids)
                if uploaded_texts:
                    logger.info(f"📎 Hydrated {len(uploaded_texts)} uploaded document(s) for verified generation")
            except Exception as e:
                logger.warning(f"⚠️ Failed to hydrate uploads: {e}")

            # If user explicitly uploaded files but none could be extracted, fail early
            if not uploaded_texts:
                logger.error(
                    f"❌ Upload hydration failed: {len(request.uploaded_file_ids)} file(s) "
                    f"requested but 0 extracted. Aborting verified generation."
                )
                yield VerificationEvent(
                    event_type=VerificationEventType.ERROR,
                    data={
                        "error": "No se pudo extraer el texto de los documentos subidos. "
                                 "Verifica que el servicio de extracción esté disponible e inténtalo de nuevo.",
                        "session_id": session_id,
                    },
                )
                return

        # Build initial state for the stop-and-go graph
        from app.agents.langgraph.stop_and_go import (
            get_stop_and_go_graph,
            get_stop_and_go_graph_hitl,
            stream_stop_and_go,
            create_initial_state,
        )

        # HITL from settings (unified config — no sector override)
        hitl_enabled = settings.verified_hitl_enabled

        initial_state = create_initial_state(
            session_id=session_id,
            user_id=request.user_id,
            query=request.query,
            mode="verified",
            max_items=request.max_claims,
            confidence_threshold=request.confidence_threshold,
            uploaded_texts=uploaded_texts,
            collections=request.collections,
            context_document_ids=request.context_document_ids,
            mode_config={
                "auto_correct": request.auto_correct,
                "max_correction_attempts": request.max_correction_attempts,
                "verification_timeout_seconds": request.verification_timeout_seconds,
                "document_type": request.document_type,
                "fidelity_confidence_cap": 0.80,
                "max_evidence": 5,
            },
            hitl_enabled=hitl_enabled,
        )

        # Select graph: HITL-enabled (with checkpointer) or simple
        if hitl_enabled:
            graph = await get_stop_and_go_graph_hitl()
        else:
            graph = get_stop_and_go_graph()

        # Map graph events → VerificationEvent SSE types
        EVENT_TYPE_MAP = {
            "progress": VerificationEventType.PROGRESS,
            "verified_item_extracted": VerificationEventType.CLAIM_GENERATED,
            "verified_verification_started": VerificationEventType.VERIFICATION_STARTED,
            "claim_verified": VerificationEventType.CLAIM_VERIFIED,
            "claim_corrected": VerificationEventType.CLAIM_CORRECTED,
            "claim_rejected": VerificationEventType.CLAIM_REJECTED,
            "verified_verification_timeout": VerificationEventType.VERIFICATION_TIMEOUT,
            "verified_complete": VerificationEventType.DOCUMENT_COMPLETE,
            "section_advanced": VerificationEventType.PROGRESS,
            "error": VerificationEventType.ERROR,
            # HITL events
            "review_requested": VerificationEventType.REVIEW_REQUESTED,
            "review_submitted": VerificationEventType.REVIEW_SUBMITTED,
            "review_skipped": VerificationEventType.REVIEW_SKIPPED,
        }

        # Pass thread_id when HITL is enabled (needed for checkpointer)
        stream_kwargs = {}
        if hitl_enabled:
            stream_kwargs["thread_id"] = session_id

        async for event in stream_stop_and_go(graph, initial_state, **stream_kwargs):
            event_type_str = event.get("event_type", "progress")

            # __interrupt__ is a runner-internal signal — close SSE cleanly
            if event_type_str == "__interrupt__":
                logger.info(
                    f"[verified] Graph interrupted for HITL review "
                    f"(session={session_id[:16]})"
                )
                return

            mapped_type = EVENT_TYPE_MAP.get(event_type_str)

            if mapped_type is None:
                continue

            # Compute execution_time_ms for the final event
            if mapped_type == VerificationEventType.DOCUMENT_COMPLETE:
                execution_time_ms = int((time.time() - start_time) * 1000)
                data = event.get("data", {})
                data["execution_time_ms"] = execution_time_ms
                yield VerificationEvent(
                    event_type=mapped_type,
                    data=data,
                    progress_percent=100,
                )
            else:
                yield VerificationEvent(
                    event_type=mapped_type,
                    claim_id=event.get("claim_id") or event.get("item_id"),
                    data=event.get("data", {}),
                    progress_percent=event.get("progress_percent"),
                )

        # Cleanup Langfuse trace
        try:
            if trace:
                trace.update(output={"completed": True})
                _lf_ctx.pop_observation()
                from app.core.langfuse_config import get_langfuse
                lf_client = get_langfuse()
                if lf_client:
                    lf_client.flush()
        except Exception:
            pass

    async def resume_after_review(
        self,
        session_id: str,
        review_decisions: list[dict],
    ) -> AsyncGenerator[VerificationEvent, None]:
        """Resume verified generation after HITL review.

        Args:
            session_id: Session ID (also used as thread_id)
            review_decisions: List of {claim_id, action, edited_text}

        Yields:
            VerificationEvent for synthesis steps
        """
        await self.initialize()

        start_time = time.time()

        from app.agents.langgraph.stop_and_go import (
            get_stop_and_go_graph_hitl,
            stream_stop_and_go,
        )

        graph = await get_stop_and_go_graph_hitl()

        resume_value = {"decisions": review_decisions}

        EVENT_TYPE_MAP = {
            "review_submitted": VerificationEventType.REVIEW_SUBMITTED,
            "verified_complete": VerificationEventType.DOCUMENT_COMPLETE,
            "error": VerificationEventType.ERROR,
            "progress": VerificationEventType.PROGRESS,
        }

        async for event in stream_stop_and_go(
            graph,
            {},  # initial_state ignored on resume
            thread_id=session_id,
            resume_value=resume_value,
        ):
            event_type_str = event.get("event_type", "progress")
            mapped_type = EVENT_TYPE_MAP.get(event_type_str)

            if mapped_type is None:
                continue

            if mapped_type == VerificationEventType.DOCUMENT_COMPLETE:
                execution_time_ms = int((time.time() - start_time) * 1000)
                data = event.get("data", {})
                data["execution_time_ms"] = execution_time_ms
                yield VerificationEvent(
                    event_type=mapped_type,
                    data=data,
                    progress_percent=100,
                )
            else:
                yield VerificationEvent(
                    event_type=mapped_type,
                    data=event.get("data", {}),
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
                evidence_sources=c.get("evidence_sources", []),
                verification_type=c.get("verification_type"),
                verification_reason=c.get("verification_reason"),
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
            sources=data.get("sources", []),
            doi_validations=data.get("doi_validations", []),
            source_filenames=data.get("source_filenames", []),
            source_summary=data.get("source_summary", ""),
        )

    def _assemble_document(
        self,
        query: str,
        claims: List[VerifiedClaim],
        sources: Optional[list] = None,
        doi_validations: Optional[list] = None,
        source_filenames: Optional[List[str]] = None,
        source_summary: Optional[str] = None,
    ) -> str:
        """
        Assemble the final document from verified claims using a Jinja2 template.

        Args:
            query: Original query (used for title)
            claims: List of verified claims
            sources: Optional global sources list from sources_map
            doi_validations: Optional DOI validation results from source document
            source_filenames: Original filenames of uploaded source documents
            source_summary: LLM-generated brief summary of the source document

        Returns:
            Formatted document text (markdown)
        """
        if not claims:
            return "No se pudieron generar claims verificados."

        from pathlib import Path
        from jinja2 import Environment, FileSystemLoader

        # In Docker: /app/services/verified_generation/service.py -> /app/config/templates
        # On host: emma-agent-service/app/services/... -> emma-agent-service/config/templates
        service_root = Path(__file__).parent.parent.parent  # -> /app or emma-agent-service/app
        template_dir = service_root.parent / "config" / "templates"

        # Fallback: if running from /app directly, templates are at /app/config/templates
        if not template_dir.exists():
            template_dir = service_root / "config" / "templates"
        if not template_dir.exists():
            # Last resort: look relative to __file__
            template_dir = Path(__file__).resolve().parent.parent.parent.parent / "config" / "templates"

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
                    "evidence_sources": c.evidence_sources,
                    "verification_type": c.verification_type,
                    "verification_reason": c.verification_reason,
                }
                for c in claims
            ],
            sources=sources or [],
            doi_validations=doi_validations or [],
            source_filenames=source_filenames or [],
            source_summary=source_summary or "",
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
