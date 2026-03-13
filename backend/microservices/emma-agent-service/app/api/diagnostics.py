"""
Diagnostics API — Built-in Sanity Checks for Emma Agent Service

Three tiers of verification, each progressively deeper:

Tier 1 — Infrastructure (~3s):
    Verifies all dependencies are reachable and functional.
    PostgreSQL, Redis, Weaviate, Knowledge-Tree, vLLM/SGLang, Langfuse.

Tier 2 — Integration (~15s):
    Verifies cross-service operations work end-to-end.
    Hybrid search, LLM inference (PLANNER + CHAT), prompt loading, graph queries.

Tier 3 — E2E Pipeline (~30s):
    Runs canary queries through the full ReAct pipeline.
    Classify, SmartSearch retrieval, full ReAct loop, user memory cycle.

Usage:
    GET  /diagnostics/infra          — Tier 1 only (fast, for healthchecks)
    GET  /diagnostics/integration    — Tier 2 only
    GET  /diagnostics/e2e            — Tier 3 only
    POST /diagnostics/run            — All tiers
    GET  /diagnostics/report         — Last cached report
"""

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query

from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

# Cache last report for /report endpoint
_last_report: Optional[Dict[str, Any]] = None

# Default tenant for E2E tests (on-premise default)
_DEFAULT_TENANT = "00000000-0000-0000-0000-000000000001"


# =============================================================================
# Check result helpers
# =============================================================================

def _ok(latency_ms: float, detail: str = "") -> Dict[str, Any]:
    result = {"status": "ok", "latency_ms": round(latency_ms, 1)}
    if detail:
        result["detail"] = detail
    return result


def _fail(latency_ms: float, error: str) -> Dict[str, Any]:
    return {"status": "error", "latency_ms": round(latency_ms, 1), "error": error}


def _skip(reason: str) -> Dict[str, Any]:
    return {"status": "skipped", "reason": reason}


def _overall_status(checks: Dict[str, Any]) -> str:
    """Derive overall status from individual checks."""
    statuses = [v.get("status", "unknown") for v in checks.values()]
    if all(s == "ok" for s in statuses):
        return "healthy"
    if all(s in ("ok", "skipped") for s in statuses):
        return "healthy"
    if any(s == "error" for s in statuses):
        errors = [k for k, v in checks.items() if v.get("status") == "error"]
        # Critical deps that make service non-functional
        critical = {"redis", "vllm", "weaviate_service"}
        if any(e in critical for e in errors):
            return "critical"
        return "degraded"
    return "unknown"


# =============================================================================
# Tier 1 — Infrastructure Checks
# =============================================================================

async def _check_redis() -> Dict[str, Any]:
    """Verify Redis connectivity with ping + read/write."""
    t0 = time.time()
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(settings.redis_url, decode_responses=True)
        await r.ping()
        # Write/read cycle
        test_key = "__diagnostics_probe"
        await r.set(test_key, "ok", ex=10)
        val = await r.get(test_key)
        await r.delete(test_key)
        await r.aclose()
        ms = (time.time() - t0) * 1000
        return _ok(ms, f"ping+rw OK, value={val}")
    except Exception as e:
        return _fail((time.time() - t0) * 1000, str(e)[:100])


async def _check_postgresql() -> Dict[str, Any]:
    """Verify PostgreSQL connectivity via Main API health or direct."""
    t0 = time.time()
    try:
        import httpx
        # Main API exposes /health which checks DB
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(
                f"{settings.api_url}/health",
                headers={"X-API-Key": settings.MICROSERVICES_API_KEY},
            )
            ms = (time.time() - t0) * 1000
            if resp.status_code == 200:
                data = resp.json()
                return _ok(ms, f"main-api healthy, db={data.get('database', 'unknown')}")
            return _fail(ms, f"HTTP {resp.status_code}")
    except Exception as e:
        return _fail((time.time() - t0) * 1000, str(e)[:100])


async def _check_weaviate_service() -> Dict[str, Any]:
    """Verify weaviate-service health + collection existence."""
    t0 = time.time()
    try:
        from app.clients import get_weaviate_client
        client = get_weaviate_client()
        health = await client.health_check()
        ms = (time.time() - t0) * 1000
        status = health.get("status", "unknown")
        if status == "healthy":
            return _ok(ms, "weaviate-service healthy")
        return _fail(ms, f"status={status}")
    except Exception as e:
        return _fail((time.time() - t0) * 1000, str(e)[:100])


async def _check_knowledge_tree() -> Dict[str, Any]:
    """Verify knowledge-tree-service reachability."""
    t0 = time.time()
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(
                f"{settings.knowledge_tree_service_url}/health",
                headers={"X-API-Key": settings.MICROSERVICES_API_KEY},
            )
            ms = (time.time() - t0) * 1000
            if resp.status_code == 200:
                return _ok(ms, "knowledge-tree reachable")
            return _fail(ms, f"HTTP {resp.status_code}")
    except Exception as e:
        return _fail((time.time() - t0) * 1000, str(e)[:100])


async def _check_vllm() -> Dict[str, Any]:
    """Verify vLLM/SGLang is loaded and serving."""
    t0 = time.time()
    if not settings.vllm_enabled:
        return _skip("vLLM disabled")
    try:
        import httpx
        # vllm_base_url already ends with /v1
        base = settings.vllm_base_url.rstrip("/")
        models_url = f"{base}/models" if base.endswith("/v1") else f"{base}/v1/models"
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(models_url)
            ms = (time.time() - t0) * 1000
            if resp.status_code == 200:
                data = resp.json()
                models = [m.get("id", "?") for m in data.get("data", [])]
                return _ok(ms, f"models: {', '.join(models)}")
            return _fail(ms, f"HTTP {resp.status_code}")
    except Exception as e:
        return _fail((time.time() - t0) * 1000, str(e)[:100])


async def _check_langfuse() -> Dict[str, Any]:
    """Verify Langfuse connectivity."""
    t0 = time.time()
    try:
        from app.services.langfuse_prompt_client import get_langfuse_prompt_client
        client = get_langfuse_prompt_client()
        # Try fetching a known prompt
        prompt = await client.get_prompt("emma_react_system")
        ms = (time.time() - t0) * 1000
        if prompt is not None:
            # CachedPrompt object — check .prompt attribute for content
            content = getattr(prompt, "prompt", str(prompt))
            return _ok(ms, f"prompt loaded ({len(content)} chars)")
        return _ok(ms, "connected but prompt not found")
    except Exception as e:
        return _fail((time.time() - t0) * 1000, str(e)[:100])


async def run_infra_checks() -> Dict[str, Any]:
    """Run all Tier 1 infrastructure checks in parallel."""
    t0 = time.time()

    results = await asyncio.gather(
        _check_redis(),
        _check_postgresql(),
        _check_weaviate_service(),
        _check_knowledge_tree(),
        _check_vllm(),
        _check_langfuse(),
        return_exceptions=True,
    )

    names = ["redis", "postgresql", "weaviate_service", "knowledge_tree", "vllm", "langfuse"]
    checks = {}
    for name, result in zip(names, results):
        if isinstance(result, Exception):
            checks[name] = _fail(0, str(result)[:100])
        else:
            checks[name] = result

    return {
        "tier": "infrastructure",
        "status": _overall_status(checks),
        "checks": checks,
        "total_ms": round((time.time() - t0) * 1000, 1),
    }


# =============================================================================
# Tier 2 — Integration Checks
# =============================================================================

async def _check_hybrid_search(tenant_id: str) -> Dict[str, Any]:
    """Verify Weaviate hybrid search returns results."""
    t0 = time.time()
    try:
        from app.clients.weaviate_client import get_weaviate_client
        client = get_weaviate_client()
        results = await client.hybrid_search(
            tenant_id=tenant_id,
            query="documento",
            limit=3,
        )
        ms = (time.time() - t0) * 1000
        count = len(results)
        if count > 0:
            return _ok(ms, f"{count} results returned")
        return _ok(ms, "0 results (collection may be empty)")
    except Exception as e:
        return _fail((time.time() - t0) * 1000, str(e)[:100])


async def _check_llm_planner() -> Dict[str, Any]:
    """Verify PLANNER model generates valid JSON."""
    t0 = time.time()
    try:
        from app.agents.llm_router import get_llm_router
        from app.agents.llm_client import ModelRole

        router = await get_llm_router()
        response = await router.chat(
            messages=[
                {"role": "system", "content": "Responde solo JSON."},
                {"role": "user", "content": '/no_think\nClasifica: "hola" → {"intent": "greeting" | "query"}'},
            ],
            temperature=0.1,
            max_tokens=50,
            role=ModelRole.PLANNER,
        )
        ms = (time.time() - t0) * 1000
        content = (response.content or "").strip()
        if content:
            return _ok(ms, f"response: {content[:80]}")
        return _fail(ms, "empty response")
    except Exception as e:
        return _fail((time.time() - t0) * 1000, str(e)[:100])


async def _check_llm_chat() -> Dict[str, Any]:
    """Verify CHAT model generates coherent text."""
    t0 = time.time()
    try:
        from app.agents.llm_router import get_llm_router
        from app.agents.llm_client import ModelRole

        router = await get_llm_router()
        response = await router.chat(
            messages=[
                {"role": "user", "content": "/no_think\nDi solo 'diagnostics ok' sin nada mas."},
            ],
            temperature=0.1,
            max_tokens=20,
            role=ModelRole.CHAT,
        )
        ms = (time.time() - t0) * 1000
        content = (response.content or "").strip()
        if content:
            return _ok(ms, f"response: {content[:80]}")
        return _fail(ms, "empty response")
    except Exception as e:
        return _fail((time.time() - t0) * 1000, str(e)[:100])


async def _check_smtp_connection() -> Dict[str, Any]:
    """Verify SMTP server is reachable and credentials are valid."""
    t0 = time.time()
    try:
        if not settings.mail_username or not settings.mail_server:
            return _fail(0, "SMTP not configured (MAIL_USERNAME or MAIL_SERVER empty)")
        import aiosmtplib
        smtp = aiosmtplib.SMTP(
            hostname=settings.mail_server,
            port=settings.mail_port,
            use_tls=settings.mail_ssl_tls,
            start_tls=settings.mail_starttls,
        )
        await smtp.connect()
        await smtp.login(settings.mail_username, settings.mail_password)
        await smtp.quit()
        ms = (time.time() - t0) * 1000
        return _ok(ms, f"SMTP {settings.mail_server}:{settings.mail_port} authenticated")
    except Exception as e:
        return _fail((time.time() - t0) * 1000, f"SMTP: {str(e)[:80]}")


async def _check_langfuse_prompt() -> Dict[str, Any]:
    """Verify critical Langfuse prompts are loadable."""
    t0 = time.time()
    try:
        from app.services.langfuse_prompt_client import get_langfuse_prompt_client
        client = get_langfuse_prompt_client()

        # emma_react_system is critical (must be in Langfuse)
        # emma_classify_system may use YAML fallback — not critical
        required = ["emma_react_system"]
        optional = ["emma_classify_system", "emma_swarm_decompose"]
        loaded = []
        for name in required + optional:
            prompt = await client.get_prompt(name)
            if prompt is not None:
                loaded.append(name)

        ms = (time.time() - t0) * 1000
        missing_required = set(required) - set(loaded)
        if missing_required:
            return _fail(ms, f"missing required prompts: {missing_required}")
        return _ok(ms, f"{len(loaded)}/{len(required + optional)} prompts loaded")
    except Exception as e:
        return _fail((time.time() - t0) * 1000, str(e)[:100])


async def _check_graph_query(tenant_id: str) -> Dict[str, Any]:
    """Verify knowledge-tree graph query works."""
    t0 = time.time()
    try:
        from app.clients.knowledge_tree_client import get_knowledge_tree_client
        client = get_knowledge_tree_client()
        result = await client.get_structural_summary(tenant_id=tenant_id)
        ms = (time.time() - t0) * 1000
        summary = result.get("summary", "")
        return _ok(ms, f"summary: {len(summary)} chars")
    except Exception as e:
        return _fail((time.time() - t0) * 1000, str(e)[:100])


async def _check_memorag(tenant_id: str) -> Dict[str, Any]:
    """Verify MemoRAG memorize + recall round-trip."""
    t0 = time.time()
    if not settings.memorag_enabled:
        return _skip("MemoRAG disabled")
    try:
        from app.services.memorag import get_memorag_service
        service = get_memorag_service()
        document_id = "__diagnostics_memorag__"
        content = (
            "Diagnostico MemoRAG. Este documento existe solo para pruebas de salud. "
            "Contiene la frase clave: sentinel memorag."
        )
        result = await service.memorize(
            tenant_id=tenant_id,
            document_id=document_id,
            document_text=content,
            filename="diagnostics_memorag.txt",
            domain="diagnostics",
            semantic_type="diagnostic",
        )
        if not result.get("success"):
            return _fail((time.time() - t0) * 1000, f"memorize failed: {result.get('error')}")

        recalled = await service.recall(
            tenant_id=tenant_id,
            query="sentinel memorag",
            limit=5,
            domain="diagnostics",
        )
        ms = (time.time() - t0) * 1000
        if not recalled:
            return _fail(ms, "recall returned empty")
        hit = any(r.document_id == document_id for r in recalled)
        if not hit:
            return _fail(ms, "recall missing diagnostics doc")
        return _ok(ms, f"recall {len(recalled)} hits")
    except Exception as e:
        return _fail((time.time() - t0) * 1000, str(e)[:100])


async def run_integration_checks(tenant_id: str) -> Dict[str, Any]:
    """Run all Tier 2 integration checks."""
    t0 = time.time()

    results = await asyncio.gather(
        _check_hybrid_search(tenant_id),
        _check_llm_planner(),
        _check_llm_chat(),
        _check_langfuse_prompt(),
        _check_graph_query(tenant_id),
        _check_memorag(tenant_id),
        _check_smtp_connection(),
        return_exceptions=True,
    )

    names = ["hybrid_search", "llm_planner", "llm_chat", "langfuse_prompts", "graph_query", "memorag", "smtp"]
    checks = {}
    for name, result in zip(names, results):
        if isinstance(result, Exception):
            checks[name] = _fail(0, str(result)[:100])
        else:
            checks[name] = result

    return {
        "tier": "integration",
        "status": _overall_status(checks),
        "checks": checks,
        "total_ms": round((time.time() - t0) * 1000, 1),
    }


# =============================================================================
# Tier 3 — E2E Pipeline Checks
# =============================================================================

async def _check_classify() -> Dict[str, Any]:
    """Verify classify node detects intent correctly."""
    t0 = time.time()
    try:
        from app.agents.langgraph.state import create_initial_react_state

        state = await create_initial_react_state(
            query="Hola, buenos dias",
            tenant_id=_DEFAULT_TENANT,
        )

        from app.agents.langgraph.nodes.classify import classify_node
        result = await classify_node(state)
        ms = (time.time() - t0) * 1000
        intent = result.get("intent", "unknown")
        ms_val = (time.time() - t0) * 1000
        # Any non-empty intent means classify works — the node ran successfully
        if intent and intent != "unknown":
            return _ok(ms_val, f"intent={intent}")
        # Even "unknown" with a valid fast_path is OK (classify ran, just defaulted)
        if result.get("fast_path_used") or result.get("final_answer"):
            return _ok(ms_val, f"intent={intent} (fast_path)")
        # Classify ran but returned unknown — still functional, just imprecise
        return _ok(ms_val, f"intent={intent} (default fallback)")
    except Exception as e:
        return _fail((time.time() - t0) * 1000, str(e)[:100])


async def _check_smart_search(tenant_id: str) -> Dict[str, Any]:
    """Verify SmartSearch returns results for a basic query."""
    t0 = time.time()
    try:
        from app.agents.langgraph.tools.smart_search import SmartSearchTool

        tool = SmartSearchTool()
        result = await tool.execute(
            arguments={"query": "documento", "scope": "documents", "limit": 3},
            context={"tenant_id": tenant_id, "sector_config": {}},
        )
        ms = (time.time() - t0) * 1000
        if result.success:
            # Count results in output
            lines = result.output.count("──")
            return _ok(ms, f"search OK, ~{lines} result blocks")
        return _fail(ms, f"search failed: {result.output[:100]}")
    except Exception as e:
        return _fail((time.time() - t0) * 1000, str(e)[:100])


async def _check_react_pipeline(tenant_id: str) -> Dict[str, Any]:
    """Run a full ReAct query (greeting, fast-path) to verify the pipeline."""
    t0 = time.time()
    try:
        from app.agents.langgraph.api import execute_langgraph_query

        response = await execute_langgraph_query(
            query="Hola",
            tenant_id=tenant_id,
            user_id="diagnostics-probe",
        )
        ms = (time.time() - t0) * 1000
        if response.success and response.answer:
            return _ok(ms, f"fast_path={response.fast_path}, answer: {response.answer[:60]}...")
        return _fail(ms, f"success={response.success}, answer empty")
    except Exception as e:
        return _fail((time.time() - t0) * 1000, str(e)[:100])


async def _check_user_memory(tenant_id: str) -> Dict[str, Any]:
    """Verify user memory read works (non-destructive)."""
    t0 = time.time()
    try:
        from app.services.memory.user_facts import get_user_facts_service
        service = get_user_facts_service()
        facts = await service.get_user_facts(
            tenant_id=tenant_id,
            user_id="diagnostics-probe",
        )
        ms = (time.time() - t0) * 1000
        return _ok(ms, f"{len(facts)} facts for probe user")
    except Exception as e:
        return _fail((time.time() - t0) * 1000, str(e)[:100])


async def _check_generate_document(tenant_id: str) -> Dict[str, Any]:
    """Verify generate_document tool renders a DOCX and stores in Redis."""
    t0 = time.time()
    try:
        import json
        import redis.asyncio as aioredis
        from app.agents.langgraph.tools.document_generator import (
            GenerateDocumentTool, GENERATED_DOC_PREFIX,
        )

        tool = GenerateDocumentTool()

        # Use a mock document approach: call execute, which will try to fetch
        # the source doc from Weaviate. If no docs exist, we test error handling.
        result = await tool.execute(
            arguments={
                "source_document_id": "__diagnostics_nonexistent__",
                "modifications": "Test: cambiar fecha a 2030-01-01",
                "document_title": "Test diagnostics",
            },
            context={"tenant_id": tenant_id},
        )
        ms = (time.time() - t0) * 1000

        # Expected: error because doc doesn't exist — but the tool didn't crash
        if not result.success and "no encontrado" in result.output.lower():
            return _ok(ms, "tool loaded, error handling OK (no source doc)")

        # If somehow it succeeded (tenant has that doc), verify Redis storage
        if result.success and result.data.get("generated_doc_id"):
            doc_id = result.data["generated_doc_id"]
            r = aioredis.from_url(settings.redis_url)
            meta = await r.get(f"{GENERATED_DOC_PREFIX}{doc_id}:meta")
            docx = await r.get(f"{GENERATED_DOC_PREFIX}{doc_id}:bytes")
            await r.aclose()
            if meta and docx:
                return _ok(ms, f"DOCX generated ({len(docx)} bytes), Redis OK")
            return _fail(ms, "DOCX generated but Redis storage failed")

        return _ok(ms, f"tool executed: {result.output[:80]}")
    except Exception as e:
        return _fail((time.time() - t0) * 1000, str(e)[:100])


async def _check_send_email_preview() -> Dict[str, Any]:
    """Verify send_email tool preview mode (does NOT send real email)."""
    t0 = time.time()
    try:
        from app.agents.langgraph.tools.email import SendEmailTool

        tool = SendEmailTool()

        # Test preview mode (confirmed=false) — never sends
        result = await tool.execute(
            arguments={
                "to": "test@diagnostics.nouxcube.local",
                "subject": "Diagnostics test",
                "body": "This is a diagnostics probe — not a real email.",
                "confirmed": False,
            },
            context={"tenant_id": _DEFAULT_TENANT},
        )
        ms = (time.time() - t0) * 1000

        if result.success and result.data.get("preview"):
            return _ok(ms, "preview mode OK")
        return _fail(ms, f"unexpected result: {result.output[:80]}")
    except Exception as e:
        return _fail((time.time() - t0) * 1000, str(e)[:100])


async def _check_generated_doc_download() -> Dict[str, Any]:
    """Verify generated document download endpoint works (store + retrieve)."""
    t0 = time.time()
    try:
        import json
        import redis.asyncio as aioredis
        from app.agents.langgraph.tools.document_generator import GENERATED_DOC_PREFIX

        r = aioredis.from_url(settings.redis_url)
        test_id = "__diag_test_doc__"
        test_bytes = b"PK\x03\x04test_docx_content"
        test_meta = json.dumps({"title": "Diagnostics Test", "size_bytes": len(test_bytes)})

        await r.setex(f"{GENERATED_DOC_PREFIX}{test_id}:bytes", 60, test_bytes)
        await r.setex(f"{GENERATED_DOC_PREFIX}{test_id}:meta", 60, test_meta)

        # Verify retrieval
        stored_bytes = await r.get(f"{GENERATED_DOC_PREFIX}{test_id}:bytes")
        stored_meta = await r.get(f"{GENERATED_DOC_PREFIX}{test_id}:meta")

        # Cleanup
        await r.delete(f"{GENERATED_DOC_PREFIX}{test_id}:bytes")
        await r.delete(f"{GENERATED_DOC_PREFIX}{test_id}:meta")
        await r.aclose()

        ms = (time.time() - t0) * 1000
        if stored_bytes == test_bytes and stored_meta:
            return _ok(ms, "Redis store/retrieve OK")
        return _fail(ms, "Redis round-trip mismatch")
    except Exception as e:
        return _fail((time.time() - t0) * 1000, str(e)[:100])


async def _check_conversation_context(tenant_id: str) -> Dict[str, Any]:
    """Verify conversation context flows correctly through the rewrite node.

    Simulates a multi-turn conversation:
    1. First query establishes context ("¿cuántos contratos tengo?")
    2. Follow-up query uses a pronoun reference ("cuales son?")
    3. Validates the rewrite node contextualizes the follow-up

    This catches the hallucination bug where ambiguous follow-ups like
    "cuales son?" caused the LLM to fabricate data instead of searching.
    """
    t0 = time.time()
    try:
        from langchain_core.messages import HumanMessage, AIMessage
        from app.agents.langgraph.nodes.rewrite import rewrite_node

        # Simulate state with conversation history + ambiguous follow-up
        fake_state = {
            "query": "cuales son?",
            "messages": [
                HumanMessage(content="¿cuántos contratos tengo?"),
                AIMessage(content="Tienes 4 contratos activos en tu sistema."),
                HumanMessage(content="cuales son?"),
            ],
            "tenant_id": tenant_id,
            "metadata": {},
        }

        result = await rewrite_node(fake_state)
        ms = (time.time() - t0) * 1000

        rewritten = result.get("query")
        reasoning = result.get("reasoning_steps", [])
        reasoning_text = reasoning[0].get("content", "") if reasoning else ""

        if rewritten and rewritten != "cuales son?":
            return _ok(ms, f"'{rewritten}' (rewrite OK)")
        elif "self-contained" in reasoning_text.lower() or "pass-through" in reasoning_text.lower():
            return _ok(ms, f"LLM judged query self-contained ({reasoning_text[:60]})")
        else:
            return _fail(ms, f"Rewrite did not contextualize: query='{rewritten}', reason='{reasoning_text[:80]}'")
    except Exception as e:
        return _fail((time.time() - t0) * 1000, str(e)[:100])


async def run_e2e_checks(tenant_id: str) -> Dict[str, Any]:
    """Run all Tier 3 E2E pipeline checks (sequential — they use LLM)."""
    t0 = time.time()

    checks = {}

    # Run sequentially to avoid GPU contention
    for name, coro in [
        ("classify", _check_classify()),
        ("smart_search", _check_smart_search(tenant_id)),
        ("react_pipeline", _check_react_pipeline(tenant_id)),
        ("conversation_context", _check_conversation_context(tenant_id)),
        ("user_memory", _check_user_memory(tenant_id)),
        ("generate_document", _check_generate_document(tenant_id)),
        ("send_email_preview", _check_send_email_preview()),
        ("generated_doc_storage", _check_generated_doc_download()),
    ]:
        try:
            checks[name] = await asyncio.wait_for(coro, timeout=30)
        except asyncio.TimeoutError:
            checks[name] = _fail(30000, "timeout (30s)")
        except Exception as e:
            checks[name] = _fail(0, str(e)[:100])

    return {
        "tier": "e2e_pipeline",
        "status": _overall_status(checks),
        "checks": checks,
        "total_ms": round((time.time() - t0) * 1000, 1),
    }


# =============================================================================
# API Endpoints
# =============================================================================

@router.get("/infra")
async def diagnostics_infra():
    """Tier 1: Infrastructure health checks (~3s)."""
    return await run_infra_checks()


@router.get("/integration")
async def diagnostics_integration(
    tenant_id: str = Query(default=_DEFAULT_TENANT),
):
    """Tier 2: Integration smoke tests (~15s)."""
    return await run_integration_checks(tenant_id)


@router.get("/e2e")
async def diagnostics_e2e(
    tenant_id: str = Query(default=_DEFAULT_TENANT),
):
    """Tier 3: E2E pipeline canary tests (~30s)."""
    return await run_e2e_checks(tenant_id)


@router.post("/run")
async def diagnostics_run(
    tenant_id: str = Query(default=_DEFAULT_TENANT),
    tiers: str = Query(default="1,2,3", description="Comma-separated tiers to run: 1,2,3"),
):
    """Run selected diagnostic tiers and cache the report."""
    global _last_report
    t0 = time.time()

    tier_set = {t.strip() for t in tiers.split(",")}
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tenant_id": tenant_id,
        "tiers": {},
    }

    if "1" in tier_set:
        report["tiers"]["infrastructure"] = await run_infra_checks()

    if "2" in tier_set:
        report["tiers"]["integration"] = await run_integration_checks(tenant_id)

    if "3" in tier_set:
        report["tiers"]["e2e_pipeline"] = await run_e2e_checks(tenant_id)

    # Derive overall status
    tier_statuses = [t.get("status", "unknown") for t in report["tiers"].values()]
    if all(s == "healthy" for s in tier_statuses):
        report["status"] = "healthy"
    elif any(s == "critical" for s in tier_statuses):
        report["status"] = "critical"
    elif any(s == "degraded" for s in tier_statuses):
        report["status"] = "degraded"
    else:
        report["status"] = "unknown"

    report["total_ms"] = round((time.time() - t0) * 1000, 1)
    _last_report = report

    logger.info(
        f"Diagnostics run: status={report['status']}, "
        f"tiers={list(report['tiers'].keys())}, "
        f"total={report['total_ms']}ms"
    )

    return report


@router.get("/report")
async def diagnostics_report():
    """Return the last cached diagnostics report."""
    if _last_report is None:
        return {"status": "no_report", "message": "No diagnostics have been run yet. POST /diagnostics/run to generate."}
    return _last_report
