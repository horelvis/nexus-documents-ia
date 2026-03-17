"""
RLM (Recursive Language Models) Processor — 3-Node Pipeline

Splits the original monolithic rlm_process_node into three LangGraph nodes
for granular streaming:

    rlm_plan_node  → Detects large content, chunks, checks cache
    rlm_map_node   → Processes chunks in parallel with LLM
    rlm_reduce_node → Aggregates results and caches

Flow:
    graph_expand → rlm_plan → rlm_map → rlm_reduce → synthesize
                           ↘ plan (small doc, passthrough)
                           ↘ synthesize (cache hit)

Design Decisions:
1. Token estimation via len/4 — sufficient for PoC, avoids tokenizer dependency
2. Parallel chunk processing via asyncio.gather — vLLM continuous batching handles concurrency
3. Result stored in agent_results["rlm_agent"] — reuses synthesize_node as-is
4. Feature-flagged off by default — zero impact on existing flows
"""

import asyncio
import hashlib
import json
import logging
import time
from typing import Any, Dict, List, Optional

from ..state import RAGState
from ..reasoning_tracker import ReasoningTracker, StepType

logger = logging.getLogger(__name__)


# ─── RLM Prompt Loader (from Langfuse) ────────────────────────────────────────

async def _get_rlm_prompt(key: str, **kwargs: Any) -> str:
    """Get an RLM prompt by key from Langfuse, formatted with kwargs.

    Maps short keys (chunk_system, aggregate_user) to Langfuse prompt names
    (emma_rlm_chunk_system, emma_rlm_aggregate_user).
    """
    from app.services.langfuse_prompt_client import get_langfuse_prompt_client
    client = get_langfuse_prompt_client()
    prompt_name = f"emma_rlm_{key}"
    prompt = await client.get_prompt(prompt_name)
    template = prompt.content
    if template and kwargs:
        try:
            return template.format(**kwargs)
        except KeyError as e:
            logger.warning(f"RLM prompt '{prompt_name}' missing placeholder: {e}")
            return template
    return template


# ─── RLM Result Cache (Redis) ───────────────────────────────────────────────

async def _get_cached_result(cache_key: str) -> Optional[str]:
    """Try to get cached RLM result from Redis."""
    try:
        import redis.asyncio as aioredis
        from app.core.config import settings
        client = aioredis.from_url(f"redis://{settings.redis_host}:{settings.redis_port}")
        result = await client.get(f"rlm:result:{cache_key}")
        await client.aclose()
        if result:
            logger.info(f"🔄 RLM Cache HIT: {cache_key[:16]}...")
            return result.decode("utf-8")
    except Exception as e:
        logger.debug(f"RLM cache get failed: {e}")
    return None


async def _set_cached_result(cache_key: str, result: str, ttl: int = 3600) -> None:
    """Cache RLM result in Redis."""
    try:
        import redis.asyncio as aioredis
        from app.core.config import settings
        client = aioredis.from_url(f"redis://{settings.redis_host}:{settings.redis_port}")
        await client.setex(f"rlm:result:{cache_key}", ttl, result)
        await client.aclose()
        logger.info(f"🔄 RLM Cache SET: {cache_key[:16]}... (TTL={ttl}s)")
    except Exception as e:
        logger.debug(f"RLM cache set failed: {e}")


def _compute_cache_key(query: str, content_hash: str) -> str:
    """Compute cache key from query + content hash."""
    raw = f"{query}|{content_hash}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _estimate_tokens(text: str) -> int:
    """Estimate token count using chars/4 heuristic."""
    return len(text) // 4


def _chunk_documents(
    docs: List[Dict[str, Any]],
    chunk_size: int,
    overlap: int,
    max_chunks: int,
) -> List[str]:
    """
    Split retrieved document contents into chunks respecting document boundaries.

    Concatenates all document content, then splits into overlapping windows.
    Each chunk stays within chunk_size tokens (estimated).

    Args:
        docs: Retrieved documents with 'content' field
        chunk_size: Target tokens per chunk
        overlap: Token overlap between chunks
        max_chunks: Maximum number of chunks to produce

    Returns:
        List of text chunks
    """
    # Concatenate all document content with separators
    parts = []
    for doc in docs:
        content = doc.get("content", "")
        title = doc.get("title", "")
        if content:
            header = f"[Documento: {title}]\n" if title else ""
            parts.append(f"{header}{content}")

    full_text = "\n\n---\n\n".join(parts)
    if not full_text:
        return []

    # Convert token sizes to char sizes (x4 heuristic)
    char_chunk_size = chunk_size * 4
    char_overlap = overlap * 4

    chunks = []
    start = 0
    text_len = len(full_text)

    while start < text_len and len(chunks) < max_chunks:
        end = start + char_chunk_size

        # Try to break at paragraph boundary
        if end < text_len:
            # Look for paragraph break near the end
            break_point = full_text.rfind("\n\n", start + char_chunk_size // 2, end)
            if break_point > start:
                end = break_point

        chunks.append(full_text[start:end].strip())
        start = end - char_overlap
        if start < 0:
            start = 0

    logger.info(f"🔄 RLM: Split {_estimate_tokens(full_text)} tokens into {len(chunks)} chunks")
    return chunks


async def _process_chunk(
    llm_client: Any,
    query: str,
    chunk: str,
    idx: int,
    total: int,
    task: str = "analyze",
) -> str:
    """
    Process a single chunk with the LLM.

    Args:
        llm_client: LLM client instance
        query: Original user query
        chunk: Text chunk to process
        idx: Chunk index (0-based)
        total: Total number of chunks
        task: Processing task description

    Returns:
        LLM response text for this chunk
    """
    system_prompt = await _get_rlm_prompt(
        "chunk_system", chunk_idx=idx + 1, chunk_total=total
    )
    user_message = await _get_rlm_prompt(
        "chunk_user", query=query, chunk_idx=idx + 1, chunk_total=total, chunk=chunk
    )

    try:
        from langchain_core.messages import SystemMessage, HumanMessage

        model = llm_client.bind(temperature=0.3, max_tokens=1024)
        response = await model.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_message),
        ])
        if response and response.content:
            return response.content
        return f"[Sin resultado para sección {idx + 1}]"
    except Exception as e:
        logger.warning(f"RLM chunk {idx + 1}/{total} failed: {e}")
        return f"[Error procesando sección {idx + 1}: {str(e)}]"


async def _aggregate_results(
    llm_client: Any,
    query: str,
    sub_results: List[str],
    chunk_size: int,
    max_depth: int,
    depth: int = 0,
) -> str:
    """
    Recursively aggregate sub-results into a final answer.

    If the combined sub-results still exceed chunk_size tokens,
    re-chunk and recurse (up to max_depth).

    Args:
        llm_client: LLM client instance
        query: Original user query
        sub_results: List of sub-result texts
        chunk_size: Token limit per chunk
        max_depth: Maximum recursion depth
        depth: Current recursion depth

    Returns:
        Aggregated result text
    """
    combined = "\n\n---\n\n".join(
        f"**Resultado parcial {i + 1}**:\n{r}" for i, r in enumerate(sub_results) if r
    )

    combined_tokens = _estimate_tokens(combined)
    logger.info(
        f"🔄 RLM Aggregate: depth={depth}, sub_results={len(sub_results)}, "
        f"combined_tokens={combined_tokens}"
    )

    # If fits in context or max depth reached, do final synthesis
    if combined_tokens <= chunk_size or depth >= max_depth:
        system_prompt = await _get_rlm_prompt("aggregate_system")
        user_message = await _get_rlm_prompt(
            "aggregate_user", query=query, combined=combined
        )

        try:
            from langchain_core.messages import SystemMessage, HumanMessage

            model = llm_client.bind(temperature=0.3, max_tokens=2048)
            response = await model.ainvoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_message),
            ])
            if response and response.content:
                return response.content
        except Exception as e:
            logger.warning(f"RLM aggregation failed at depth {depth}: {e}")

        # Fallback: return concatenated
        return combined

    # Still too large — re-chunk and recurse
    logger.info(f"🔄 RLM: Re-chunking at depth {depth + 1} ({combined_tokens} > {chunk_size})")
    char_chunk_size = chunk_size * 4
    char_overlap = 500 * 4  # Fixed overlap for re-chunking

    re_chunks = []
    start = 0
    while start < len(combined):
        end = start + char_chunk_size
        if end < len(combined):
            break_point = combined.rfind("\n\n", start + char_chunk_size // 2, end)
            if break_point > start:
                end = break_point
        re_chunks.append(combined[start:end].strip())
        start = end - char_overlap

    # Process re-chunks in parallel
    re_tasks = [
        _process_chunk(llm_client, query, chunk, i, len(re_chunks), task="re-aggregate")
        for i, chunk in enumerate(re_chunks)
    ]
    new_sub_results = await asyncio.gather(*re_tasks)

    return await _aggregate_results(
        llm_client, query, new_sub_results, chunk_size, max_depth, depth + 1
    )


# =============================================================================
# Node 1: rlm_plan_node — Detect, chunk, check cache
# =============================================================================

async def rlm_plan_node(state: RAGState) -> Dict[str, Any]:
    """
    LangGraph node: RLM planning phase.

    Detects if content exceeds token threshold, creates chunks,
    and checks Redis cache. Sets rlm_activated flag for routing.

    Returns:
        State updates: rlm_activated, rlm_chunks, rlm_cache_key, reasoning_steps
    """
    from app.core.config import settings

    start_time = time.time()
    tracker = ReasoningTracker()
    tracker.set_source("rlm_plan")

    # Check feature flag
    if not settings.rlm_enabled:
        logger.debug("RLM: Disabled via config")
        return {"rlm_activated": False}

    # Gather content from tenant docs AND uploaded texts.
    # Exclude public knowledge docs (BOE, legislation) — those are short
    # retrieval chunks meant for domain agents, not large documents
    # requiring recursive processing.
    retrieved_docs = state.get("retrieved_docs", [])
    metadata = state.get("metadata", {})
    uploaded_texts = metadata.get("uploaded_texts") or []

    # Only consider tenant docs (not public knowledge) for RLM activation
    tenant_docs = [
        doc for doc in retrieved_docs
        if doc.get("metadata", {}).get("source") != "public_knowledge"
    ]

    all_docs = list(tenant_docs)
    for item in uploaded_texts:
        text = item.get("text", "")
        if text:
            all_docs.append({
                "id": f"upload-{item.get('filename', 'unknown')}",
                "title": item.get("filename", "Uploaded Document"),
                "content": text,
                "score": 1.0,
            })

    if not all_docs:
        logger.debug("RLM: No retrieved docs or uploaded texts")
        return {"rlm_activated": False}

    total_content = " ".join(
        doc.get("content", "") for doc in all_docs
    )
    total_tokens = _estimate_tokens(total_content)

    public_count = len(retrieved_docs) - len(tenant_docs)
    source_desc = f"{len(tenant_docs)} tenant + {len(uploaded_texts)} uploaded"
    if public_count:
        source_desc += f" (excluded {public_count} public knowledge)"
    logger.info(f"🔄 RLM Plan: Estimated {total_tokens} tokens from {source_desc}")

    tracker.add_step(
        StepType.QUERY_ANALYSIS,
        f"Documento grande detectado: {total_tokens:,} tokens ({source_desc})",
        confidence=1.0,
    )

    # Below threshold — passthrough
    if total_tokens < settings.rlm_token_threshold:
        logger.info(
            f"🔄 RLM Plan: Below threshold ({total_tokens} < {settings.rlm_token_threshold}), passing through"
        )
        return {
            "rlm_activated": False,
            "rlm_total_tokens": total_tokens,
        }

    # Above threshold — activate RLM
    logger.info(
        f"🔄 RLM Plan: Activated! {total_tokens} tokens > {settings.rlm_token_threshold} threshold"
    )

    tracker.add_thinking_step(
        f"RLM activado: {total_tokens:,} tokens excede umbral de {settings.rlm_token_threshold:,}. "
        f"Procesamiento recursivo por chunks necesario.",
        confidence=0.95,
    )

    query = state.get("query", "")

    # Check cache first
    content_hash = hashlib.md5(total_content[:10000].encode()).hexdigest()
    cache_key = _compute_cache_key(query, content_hash)
    cached = await _get_cached_result(cache_key)
    if cached:
        latency_ms = (time.time() - start_time) * 1000
        logger.info(f"✅ RLM Plan: Cache hit! ({latency_ms:.1f}ms)")
        tracker.add_step(
            StepType.OBSERVATION,
            f"Resultado encontrado en caché ({latency_ms:.0f}ms)",
            confidence=1.0,
        )
        existing_results = dict(state.get("agent_results", {}))
        existing_results["rlm_agent"] = {
            "agent": "rlm_agent",
            "output": cached,
            "tools_used": ["rlm_cached"],
            "sources": [doc.get("title", "Unknown") for doc in all_docs[:10]],
            "error": None,
            "latency_ms": latency_ms,
            "reasoning_steps": tracker.get_steps(),
        }
        return {
            "rlm_activated": True,
            "rlm_total_tokens": total_tokens,
            "rlm_chunks": [],
            "rlm_cache_key": cache_key,
            "rlm_sub_results": [],
            "rlm_depth": 0,
            "agent_results": existing_results,
            "reasoning_steps": tracker.get_steps(),
            "metadata": {**metadata, "rlm_cache_hit": True},
        }

    # Chunk documents
    chunks = _chunk_documents(
        all_docs,
        chunk_size=settings.rlm_chunk_size,
        overlap=settings.rlm_chunk_overlap,
        max_chunks=settings.rlm_max_chunks,
    )

    if not chunks:
        logger.warning("RLM Plan: No chunks produced")
        return {"rlm_activated": False}

    tracker.add_step(
        StepType.TRANSFORMATION,
        f"Documento dividido en {len(chunks)} secciones para análisis paralelo",
        confidence=1.0,
        metadata={"chunks": len(chunks), "total_tokens": total_tokens},
    )

    return {
        "rlm_activated": True,
        "rlm_total_tokens": total_tokens,
        "rlm_chunks": chunks,
        "rlm_cache_key": cache_key,
        "reasoning_steps": tracker.get_steps(),
    }


# =============================================================================
# Node 2: rlm_map_node — Process chunks in parallel
# =============================================================================

async def rlm_map_node(state: RAGState) -> Dict[str, Any]:
    """
    LangGraph node: RLM map phase.

    Processes each chunk with the LLM in parallel, filters irrelevant results.

    Returns:
        State updates: rlm_sub_results, rlm_relevant_count, reasoning_steps
    """
    from app.core.config import settings

    tracker = ReasoningTracker()
    tracker.set_source("rlm_map")

    chunks = state.get("rlm_chunks", [])
    query = state.get("query", "")

    if not chunks:
        logger.warning("RLM Map: No chunks to process")
        return {"rlm_sub_results": [], "rlm_relevant_count": 0}

    try:
        from app.agents.llm_models import get_chat_model
        llm_client = get_chat_model()
    except Exception as e:
        logger.error(f"RLM Map: Failed to get LLM model: {e}")
        tracker.add_error_step(f"No se pudo conectar al LLM: {e}")
        return {
            "rlm_sub_results": [],
            "rlm_relevant_count": 0,
            "reasoning_steps": tracker.get_steps(),
        }

    tracker.add_step(
        StepType.TOOL_EXECUTION,
        f"Analizando {len(chunks)} secciones del documento con LLM...",
        confidence=0.9,
    )

    # Process chunks in parallel with semaphore
    max_concurrent = settings.llm_max_concurrent
    semaphore = asyncio.Semaphore(max_concurrent)

    async def _process_with_semaphore(idx: int, chunk: str) -> str:
        async with semaphore:
            logger.info(f"🔄 RLM Map: Processing chunk {idx + 1}/{len(chunks)}")
            return await _process_chunk(llm_client, query, chunk, idx, len(chunks))

    tasks = [_process_with_semaphore(i, chunk) for i, chunk in enumerate(chunks)]
    sub_results_raw = await asyncio.gather(*tasks)

    # Filter out non-relevant chunks
    no_relevant_marker = _get_rlm_prompt("no_relevant_marker") or "[NO_RELEVANTE]"
    relevant_results = [r for r in sub_results_raw if no_relevant_marker not in r]
    logger.info(
        f"🔄 RLM Map: {len(relevant_results)}/{len(sub_results_raw)} chunks had relevant content"
    )

    tracker.add_observation_step(
        tool_name="rlm_chunk_processor",
        observation=f"{len(sub_results_raw)} secciones analizadas completamente",
        success=True,
    )

    tracker.add_reflection_step(
        reflection=f"{len(relevant_results)} de {len(sub_results_raw)} secciones contienen información relevante",
        decision="agregar resultados" if relevant_results else "sin información relevante",
        confidence=len(relevant_results) / max(len(sub_results_raw), 1),
    )

    # Store sub_results as list of dicts for state serialization
    rlm_sub_results = [
        {"chunk": i, "text": r, "preview": r[:200]}
        for i, r in enumerate(relevant_results)
    ]

    return {
        "rlm_sub_results": rlm_sub_results,
        "rlm_relevant_count": len(relevant_results),
        "reasoning_steps": tracker.get_steps(),
    }


# =============================================================================
# Node 3: rlm_reduce_node — Aggregate and cache
# =============================================================================

async def rlm_reduce_node(state: RAGState) -> Dict[str, Any]:
    """
    LangGraph node: RLM reduce phase.

    Aggregates relevant sub-results into a final answer and caches it.

    Returns:
        State updates: agent_results["rlm_agent"], reasoning_steps
    """
    from app.core.config import settings

    start_time = time.time()
    tracker = ReasoningTracker()
    tracker.set_source("rlm_reduce")

    sub_results = state.get("rlm_sub_results", [])
    query = state.get("query", "")
    cache_key = state.get("rlm_cache_key", "")
    total_tokens = state.get("rlm_total_tokens", 0)
    metadata = state.get("metadata", {})

    # Collect source titles
    retrieved_docs = state.get("retrieved_docs", [])
    uploaded_texts = metadata.get("uploaded_texts") or []
    all_doc_titles = [doc.get("title", "Unknown") for doc in retrieved_docs[:10]]
    all_doc_titles += [item.get("filename", "Unknown") for item in uploaded_texts[:5]]

    # Extract text from sub_results
    relevant_texts = [r.get("text", "") for r in sub_results if r.get("text")]

    if not relevant_texts:
        latency_ms = (time.time() - start_time) * 1000
        no_result_msg = _get_rlm_prompt("no_relevant_message") or "No se encontró información relevante sobre esta consulta en el documento analizado."
        logger.info(f"✅ RLM Reduce: No relevant chunks found ({latency_ms:.1f}ms)")
        tracker.add_step(
            StepType.RESPONSE,
            f"No se encontró información relevante en el documento ({latency_ms:.0f}ms)",
            confidence=1.0,
        )
        existing_results = dict(state.get("agent_results", {}))
        existing_results["rlm_agent"] = {
            "agent": "rlm_agent",
            "output": no_result_msg,
            "tools_used": ["rlm_recursive_processing"],
            "sources": [],
            "error": None,
            "latency_ms": latency_ms,
            "reasoning_steps": tracker.get_steps(),
        }
        return {
            "agent_results": existing_results,
            "reasoning_steps": tracker.get_steps(),
            "metadata": {
                **metadata,
                "rlm_latency_ms": latency_ms,
                "rlm_relevant_chunks": 0,
                "rlm_total_tokens": total_tokens,
            },
        }

    tracker.add_step(
        StepType.TRANSFORMATION,
        f"Sintetizando {len(relevant_texts)} resultados parciales en respuesta final...",
        confidence=0.9,
    )

    try:
        from app.agents.llm_models import get_chat_model
        llm_client = get_chat_model()
    except Exception as e:
        logger.error(f"RLM Reduce: Failed to get LLM model: {e}")
        # Fallback to concatenation
        final_result = "\n\n".join(relevant_texts)
        tracker.add_error_step(f"LLM no disponible, concatenando resultados: {e}")
        existing_results = dict(state.get("agent_results", {}))
        existing_results["rlm_agent"] = {
            "agent": "rlm_agent",
            "output": final_result,
            "tools_used": ["rlm_recursive_processing"],
            "sources": all_doc_titles,
            "error": str(e),
            "latency_ms": (time.time() - start_time) * 1000,
        }
        return {
            "agent_results": existing_results,
            "reasoning_steps": tracker.get_steps(),
        }

    logger.info(f"🔄 RLM Reduce: Aggregating {len(relevant_texts)} sub-results")
    final_result = await _aggregate_results(
        llm_client,
        query,
        relevant_texts,
        chunk_size=settings.rlm_chunk_size,
        max_depth=settings.rlm_max_depth,
    )

    # Cache the result
    if cache_key:
        await _set_cached_result(cache_key, final_result)

    latency_ms = (time.time() - start_time) * 1000
    logger.info(f"✅ RLM Reduce: Completed in {latency_ms:.1f}ms")

    chunks_total = len(state.get("rlm_chunks", []))
    tracker.add_step(
        StepType.RESPONSE,
        f"Análisis RLM completado en {latency_ms:.0f}ms "
        f"({len(relevant_texts)}/{chunks_total} secciones relevantes)",
        confidence=1.0,
        metadata={
            "latency_ms": latency_ms,
            "relevant_chunks": len(relevant_texts),
            "total_chunks": chunks_total,
        },
    )

    existing_results = dict(state.get("agent_results", {}))
    existing_results["rlm_agent"] = {
        "agent": "rlm_agent",
        "output": final_result,
        "tools_used": ["rlm_recursive_processing"],
        "sources": all_doc_titles,
        "error": None,
        "latency_ms": latency_ms,
        "reasoning_steps": tracker.get_steps(),
    }

    return {
        "agent_results": existing_results,
        "reasoning_steps": tracker.get_steps(),
        "metadata": {
            **metadata,
            "rlm_latency_ms": latency_ms,
            "rlm_chunks": chunks_total,
            "rlm_relevant_chunks": len(relevant_texts),
            "rlm_total_tokens": total_tokens,
        },
    }
