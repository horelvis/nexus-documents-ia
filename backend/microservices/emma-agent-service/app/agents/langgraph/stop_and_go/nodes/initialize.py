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
from typing import Any, Dict, List, Optional

import httpx

import redis.asyncio as aioredis

from app.core.config import settings
from app.agents.langgraph.stop_and_go.strategy import get_strategy

logger = logging.getLogger(__name__)

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

    source_context = await _get_source_context(
        query=state["query"],
        tenant_id=state["tenant_id"],
        document_ids=state.get("context_document_ids"),
        collections=state.get("collections"),
        uploaded_texts=state.get("uploaded_texts"),
    )

    updates: Dict[str, Any] = {
        "source_context": source_context,
        "pending_events": [{
            "event_type": "progress",
            "data": {
                "message": "Context retrieved, starting extraction...",
                "session_id": state["session_id"],
            },
            "progress_percent": 10,
        }],
    }

    # For legal sector: search CENDOJ for jurisprudence evidence (ephemeral)
    verification_sources = state.get("mode_config", {}).get("verification_sources", [])
    if "jurisprudence" in verification_sources or "public_knowledge" in verification_sources:
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
) -> str:
    """
    Get source context from uploaded documents and/or Weaviate.

    Shared between predictive and verified modes. This was previously
    duplicated identically in both service classes.

    Priority:
        1. Uploaded documents (already extracted text)
        2. Weaviate hybrid search (if no uploads)
    """
    context_parts: list[str] = []

    # Priority 1: Uploaded document text
    if uploaded_texts:
        for t in uploaded_texts:
            filename = t.get("filename", "Uploaded document")
            text = t.get("text", "")[:3000]
            if text:
                context_parts.append(f"[{filename}]\n{text}")

    # Priority 2: Weaviate search
    if not context_parts:
        sanitized_tenant = tenant_id.replace("-", "_")
        collection_name = (
            collections[0] if collections
            else f"Nouxcube_{sanitized_tenant}_documents"
        )
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
                    results = response.json().get("results", [])
                    for r in results[:5]:
                        title = r.get("title", "Document")
                        content = r.get("content", "")[:2000]
                        context_parts.append(f"[{title}]\n{content}")
        except Exception as e:
            logger.error(f"Weaviate source context failed: {e}")

    return "\n\n---\n\n".join(context_parts)


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
