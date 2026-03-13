"""
Initialize node — loads source context and clears Redis session.

This is the entry point of the stop-and-go graph. It:
1. Resolves the strategy and initializes lazy resources
2. Loads source context from uploads and/or Weaviate
3. For legal sector: searches CENDOJ for jurisprudence (ephemeral)
4. Clears any prior session data in Redis
5. Emits a PROGRESS event

The _get_source_context() function is extracted from the identical
code previously duplicated in both PredictiveAnalysisService and
VerifiedDocumentService.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

import redis.asyncio as aioredis

from app.core.config import settings
from app.agents.langgraph.stop_and_go.strategy import get_strategy

logger = logging.getLogger(__name__)

# If a document fits within ~50% of Qwen3-14B's 32K-token context (~64K chars),
# skip sectioning entirely so the WriterAgent sees the full source at once.
# This eliminates hallucinations caused by the LLM "filling in" missing context
# when it only sees a 3500-char window of a 50K-char document.
NO_CHUNK_THRESHOLD = int(os.getenv("VERIFIED_NO_CHUNK_THRESHOLD", "64000"))

CENDOJ_DOCKER_IMAGE = "nouxcube-cendoj-agent"
CENDOJ_REDIS_KEY = "emma:cendoj:enabled"

_redis = None


async def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.Redis(
            host=settings.redis_host, port=settings.redis_port, decode_responses=True
        )
    return _redis


async def _is_cendoj_enabled() -> bool:
    """Check if CENDOJ is enabled: Redis → env var → sector default."""
    try:
        r = await _get_redis()
        val = await r.get(CENDOJ_REDIS_KEY)
        if val is not None:
            return val.lower() == "true"
    except Exception as e:
        logger.warning(f"Redis read failed for CENDOJ toggle, using settings: {e}")
    return settings.cendoj_enabled


async def initialize_node(state: dict) -> dict:
    """Load source context, clear session, emit progress event."""
    strategy = get_strategy(state["mode"])
    await strategy.initialize(state)

    source_context, source_document_ids = await _get_source_context(
        query=state["query"],
        tenant_id=state["tenant_id"],
        document_ids=state.get("context_document_ids"),
        collections=state.get("collections"),
        uploaded_texts=state.get("uploaded_texts"),
    )

    # Abort if no source document — generating claims without source = hallucinations
    if not source_context.strip():
        logger.error("No source context available — aborting verified generation")
        return {
            "source_context": "",
            "source_sections": [""],
            "current_section_index": 0,
            "section_claims_count": [0],
            "is_complete": True,
            "pending_events": [{
                "event_type": "error",
                "data": {
                    "message": "No se pudo obtener el contenido del documento. "
                               "Asegúrese de subir un archivo antes de generar.",
                    "session_id": state["session_id"],
                },
            }],
        }

    # Extract source document name(s) for the report header
    source_filenames = [
        t.get("filename", "Documento") for t in (state.get("uploaded_texts") or [])
        if t.get("text")
    ]

    # Split source into sections for windowed claim generation
    sections = _chunk_source_into_sections(source_context)
    logger.info(
        f"Source context loaded: {len(source_context)} chars, "
        f"{len(sections)} section(s), {len(source_document_ids)} source doc(s), "
        f"files={source_filenames}"
    )

    updates: Dict[str, Any] = {
        "source_context": source_context,
        "source_document_ids": source_document_ids,
        "source_filenames": source_filenames,
        "source_sections": sections,
        "current_section_index": 0,
        "section_claims_count": [0] * len(sections),
        "pending_events": [{
            "event_type": "progress",
            "data": {
                "message": "Context retrieved, starting extraction...",
                "session_id": state["session_id"],
                "total_sections": len(sections),
            },
            "progress_percent": 10,
        }],
    }

    # Validate DOIs from uploaded documents (catch invalid references early)
    if state.get("uploaded_texts"):
        doi_validations = await _validate_source_dois(state["uploaded_texts"])
        if doi_validations:
            updates["source_doi_validations"] = doi_validations
            valid = sum(1 for d in doi_validations if d.get("valid"))
            invalid = len(doi_validations) - valid
            logger.info(
                f"DOI pre-validation: {len(doi_validations)} DOIs found in source "
                f"({valid} valid, {invalid} invalid)"
            )

    # For legal sector: search CENDOJ for jurisprudence evidence (ephemeral)
    # CENDOJ is legal-only — the Docker container may not exist for other sectors
    verification_sources = state.get("mode_config", {}).get("verification_sources", [])
    sector = state.get("sector", "")
    if sector == "legal" and ("jurisprudence" in verification_sources or "public_knowledge" in verification_sources):
        cendoj_enabled = await _is_cendoj_enabled()
        if cendoj_enabled:
            jurisprudence = await _search_cendoj_jurisprudence(
                query=state["query"],
                with_content=settings.cendoj_max_content,
            )
            if jurisprudence:
                updates["jurisprudence_evidence"] = jurisprudence
                logger.info(f"CENDOJ: cached {len(jurisprudence)} evidence items for session")
        else:
            logger.info("CENDOJ disabled via admin toggle, skipping jurisprudence search")

    return updates


async def _get_source_context(
    query: str,
    tenant_id: str,
    document_ids: Optional[List[str]] = None,
    collections: Optional[List[str]] = None,
    uploaded_texts: Optional[List[Dict]] = None,
) -> Tuple[str, List[str]]:
    """Build source context from uploaded documents.

    Verified generation requires an explicit source document — there is no
    Weaviate fallback.  Without a source, claims cannot be faithfulness-checked
    and the WriterAgent would hallucinate from unrelated tenant documents.

    Returns:
        Tuple of (context_text, source_document_ids).
    """
    context_parts: list[str] = []
    source_doc_ids: list[str] = []

    if not uploaded_texts:
        logger.warning("No uploaded texts provided — verified generation requires a source document")
        return "", []

    for t in uploaded_texts:
        filename = t.get("filename", "Uploaded document")
        text = t.get("text", "")
        if text:
            context_parts.append(f"[{filename}]\n{text}")
            doc_id = t.get("id", "")
            if doc_id:
                source_doc_ids.append(doc_id)

    return "\n\n---\n\n".join(context_parts), source_doc_ids


def _chunk_source_into_sections(
    source_context: str,
    section_size: int | None = None,
    overlap: int | None = None,
) -> list[str]:
    """Split source context into overlapping sections for windowed claim generation.

    Respects paragraph boundaries (``\\n\\n``) so sections don't cut mid-sentence.
    Short documents (≤ section_size) return a single-element list, preserving
    identical behaviour to the previous non-sectioned pipeline.

    Args:
        source_context: Full concatenated source text.
        section_size: Target chars per section (default from settings).
        overlap: Chars of overlap between consecutive sections.

    Returns:
        List of section strings (always ≥ 1 element).
    """
    if section_size is None:
        section_size = settings.verified_section_size
    if overlap is None:
        overlap = settings.verified_section_overlap

    if not source_context or len(source_context) <= max(section_size, NO_CHUNK_THRESHOLD):
        return [source_context] if source_context else [""]

    sections: list[str] = []
    start = 0
    text_len = len(source_context)

    while start < text_len:
        end = start + section_size

        if end >= text_len:
            # Last section — take everything remaining
            sections.append(source_context[start:])
            break

        # Try to break at a paragraph boundary within the last 20% of the section
        search_start = end - section_size // 5
        boundary = source_context.rfind("\n\n", search_start, end)
        if boundary > start:
            end = boundary + 2  # include the \n\n in this section

        sections.append(source_context[start:end])

        # Advance with overlap
        start = end - overlap
        if start <= (end - section_size):
            # Safety: ensure we always advance
            start = end

    logger.info(
        f"Section chunking: {text_len} chars → {len(sections)} sections "
        f"(size={section_size}, overlap={overlap})"
    )
    return sections


async def _validate_source_dois(
    uploaded_texts: List[Dict],
) -> List[Dict[str, Any]]:
    """Extract DOIs from uploaded documents and validate each via doi.org.

    This runs ONCE at initialization (not per claim) so the results can be
    reused for every claim in the session.  Invalid DOIs are a strong signal
    that the source document contains reference errors.

    Returns a list of dicts:
        [{"doi": "10.xxx", "valid": bool, "metadata": {...}, "context": "surrounding text"}, ...]
    """
    from app.agents.langgraph.stop_and_go.nodes.search_and_evaluate import DOI_PATTERN

    # Collect unique DOIs from all uploaded texts
    all_dois: Dict[str, str] = {}  # doi -> surrounding context
    for t in uploaded_texts:
        text = t.get("text", "")
        if not text:
            continue
        for match in DOI_PATTERN.finditer(text):
            doi = match.group().rstrip(".")
            if doi not in all_dois:
                # Keep ~100 chars of context around the DOI for citation matching
                start = max(0, match.start() - 80)
                end = min(len(text), match.end() + 80)
                all_dois[doi] = text[start:end].replace("\n", " ").strip()

    if not all_dois:
        return []

    logger.info(f"DOI pre-validation: extracting {len(all_dois)} unique DOIs from uploaded docs")

    # Validate in parallel (reuse the same validator from search_and_evaluate)
    from app.agents.langgraph.stop_and_go.nodes.search_and_evaluate import (
        _validate_single_doi,
    )

    results = await asyncio.gather(
        *[_validate_single_doi(doi) for doi in all_dois],
        return_exceptions=True,
    )

    validated: List[Dict[str, Any]] = []
    for doi, result in zip(all_dois, results):
        if isinstance(result, Exception):
            logger.warning(f"DOI validation exception for {doi}: {result}")
            validated.append({"doi": doi, "valid": False, "metadata": {}, "context": all_dois[doi]})
        else:
            result["context"] = all_dois[doi]
            validated.append(result)

    return validated


async def _search_cendoj_jurisprudence(
    query: str,
    court: str = "TS",
    max_results: int = 10,
    with_content: int = 3,
) -> List[Dict[str, Any]]:
    """Launch ephemeral CENDOJ Docker container to search for jurisprudence.

    Downloads PDFs for top N results and extracts text in memory.
    The container is destroyed after the search — nothing persists.
    Returns a list of evidence dicts compatible with _search_evidence().
    """
    cmd = [
        "docker", "run", "--rm",
        "--network=bridge",
        "--memory=512m",
        "--cpus=1",
        CENDOJ_DOCKER_IMAGE,
        "--query", query,
        "--court", court,
        "--max-results", str(max_results),
    ]
    if with_content > 0:
        cmd.extend(["--with-content", str(with_content)])

    logger.info(
        f"CENDOJ init: query='{query[:60]}' court={court} "
        f"max={max_results} with_content={with_content}"
    )

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=settings.cendoj_timeout
        )

        if stderr:
            for line in stderr.decode().strip().split("\n")[-5:]:
                logger.debug(f"[cendoj-init] {line}")

        if proc.returncode != 0:
            error_msg = stderr.decode().strip().split("\n")[-1] if stderr else "unknown"
            logger.warning(f"CENDOJ init failed (exit {proc.returncode}): {error_msg}")
            return []

        references = json.loads(stdout.decode())

    except asyncio.TimeoutError:
        logger.warning(f"CENDOJ init timed out after {settings.cendoj_timeout}s")
        return []
    except (json.JSONDecodeError, FileNotFoundError) as e:
        logger.warning(f"CENDOJ init error: {e}")
        return []
    except Exception as e:
        logger.warning(f"CENDOJ init unexpected error: {e}")
        return []

    # Convert CENDOJ references to evidence format for search_and_evaluate
    evidence: List[Dict[str, Any]] = []
    for ref in references:
        roj = ref.get("roj", "")
        ecli = ref.get("ecli", "")
        content = ref.get("content")

        # Build text excerpt from content sections or summary
        text_excerpt = ""
        if content:
            legal_grounds = content.get("legal_grounds", "")
            ruling = content.get("ruling", "")
            if legal_grounds:
                text_excerpt = legal_grounds[:2000]
            elif ruling:
                text_excerpt = ruling[:1000]
        if not text_excerpt:
            text_excerpt = ref.get("summary", "")[:500]

        if not text_excerpt:
            continue

        evidence.append({
            "document_id": f"cendoj:{ecli or roj}",
            "document_title": f"{roj} — {ref.get('court', '')}",
            "chunk_id": None,
            "text_excerpt": text_excerpt,
            "similarity_score": 0.80,  # High base score for jurisprudence
            "source": "jurisprudence",
            "url": ref.get("cendoj_url", ""),
            "roj": roj,
            "ecli": ecli,
            "date": ref.get("date", ""),
            "resolution_type": ref.get("resolution_type", ""),
            "ponente": ref.get("ponente", ""),
            # Full content sections (for factor evaluation)
            "_content": content,
        })

    logger.info(f"CENDOJ init: {len(evidence)} evidence items with content")
    return evidence
