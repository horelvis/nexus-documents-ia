"""
Shared helpers for sector-parametrized functional tests.

This is a regular module (not conftest.py) to avoid pytest auto-discovery
issues with singleton resets. Import explicitly in test files.

Usage:
    from tests.sector_helpers import (
        ALL_SECTORS, reset_sector_singleton, reset_tool_registry,
        MockLLMResponse, make_mock_router, SECTOR_QUERIES,
    )
"""

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock


# ── Constants ──────────────────────────────────────────────────────────

ALL_SECTORS = ["legal", "medical", "documental"]

TENANT_ID = "00000000-0000-0000-0000-000000000001"
USER_ID = "test-user-sector"
THREAD_ID = "test-thread-sector"


# ── Singleton Reset Helpers ────────────────────────────────────────────

def reset_sector_singleton(sector_name: str = ""):
    """Reset sector registry singleton and set ACTIVE_SECTOR env var.

    Must be called between tests that use different sectors to prevent
    the read-once singleton from returning stale config.
    """
    import app.agents.langgraph.sectors.registry as reg
    reg._active_sector_config = None
    reg._initialized = False
    os.environ["ACTIVE_SECTOR"] = sector_name


def reset_tool_registry():
    """Reset tool registry singleton.

    Must be called between tests that test different tool contexts,
    since the registry caches tool instances.
    """
    import app.agents.langgraph.tools.registry as treg
    treg._tool_registry = None


# ── Mock LLM Response ─────────────────────────────────────────────────

@dataclass
class MockToolCall:
    """Simulates an LLMResponse.tool_calls entry."""
    id: str = "tc-001"
    name: str = "terminate"
    arguments: Dict[str, Any] = field(default_factory=lambda: {"answer": "Mock answer"})


@dataclass
class MockLLMResponse:
    """Simulates LLMResponse from the LLM Router.

    Matches the interface used by react_loop_node:
    - .content: text response
    - .tool_calls: list of MockToolCall
    - .has_tool_calls: bool
    - .thinking: optional thinking text
    """
    content: str = ""
    tool_calls: List[MockToolCall] = field(default_factory=list)
    thinking: Optional[str] = None

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0


def make_mock_router(responses: Optional[List[MockLLMResponse]] = None):
    """Create a mock LLM router that returns responses in sequence.

    Args:
        responses: List of MockLLMResponse to return on successive .chat() calls.
                   If None, returns a single empty response.

    Returns:
        AsyncMock with .chat() configured as a coroutine.
    """
    if responses is None:
        responses = [MockLLMResponse(content="Mock response")]

    call_count = {"n": 0}

    async def mock_chat(*args, **kwargs):
        idx = min(call_count["n"], len(responses) - 1)
        call_count["n"] += 1
        return responses[idx]

    router = MagicMock()
    router.chat = mock_chat
    return router


# ── Sample Queries per Sector ──────────────────────────────────────────

SECTOR_QUERIES: Dict[str, List[str]] = {
    "legal": [
        "¿Qué dice el Art. 1902 del Código Civil?",
        "Analiza el Real Decreto 2/2015 sobre contratos laborales",
        "Busca la Sentencia STS 123/2020",
        "¿Qué establece la Ley Orgánica 3/2018 de protección de datos?",
        "Expediente núm. EXP-2024/001",
    ],
    "medical": [
        "Paciente con código CIE-10 J45.0 asma bronquial",
        "Dosis de 500 mg de amoxicilina cada 8 horas",
        "Historia Clínica núm. HC-2024-001 del paciente",
        "Procedimiento CIE-9-MC 99.84 realizado ayer",
        "NHC PAC-12345 diagnóstico pendiente",
    ],
    "documental": [
        "Facturas de María García López pendientes de pago",
        "Documentos con NIF B12345678 de la empresa ACME",
        "Expedientes con importe superior a 10.000,00 €",
        "Ref. PO-2024-001 del 15 de enero de 2024",
        "Contratos firmados por Javier Martínez en 2024",
    ],
}


# ── State Builder ──────────────────────────────────────────────────────

def make_react_state(
    query: str = "test query",
    sector_name: Optional[str] = None,
    user_memory: Optional[str] = None,
    fast_path_used: bool = False,
    is_complete: bool = False,
    use_swarm: bool = False,
    **overrides,
) -> Dict[str, Any]:
    """Build a minimal ReActState dict for testing.

    This avoids calling the async create_initial_react_state() which
    needs singleton setup. Instead, builds the dict directly.
    """
    from langchain_core.messages import HumanMessage

    sector_config = None
    if sector_name:
        from app.agents.langgraph.sectors.registry import SECTOR_CONFIGS
        sc = SECTOR_CONFIGS.get(sector_name)
        if sc:
            sector_config = {
                "name": sc.name,
                "sector": sc.sector.value,
                "agents": sc.agents,
                "default_agent": sc.default_agent,
                "hybrid_alpha": sc.hybrid_alpha,
                "top_k": sc.top_k,
                "rerank_enabled": sc.rerank_enabled,
                "chunk_strategy": sc.chunk_strategy,
                "system_prompt_key": sc.system_prompt_key,
            }

    state = {
        "messages": [HumanMessage(content=query)],
        "query": query,
        "thread_id": THREAD_ID,
        "tenant_id": TENANT_ID,
        "user_id": USER_ID,
        "user_role_ids": [],
        "is_admin": False,
        "sector": sector_name,
        "sector_config": sector_config,
        "current_step": 0,
        "max_steps": 10,
        "tool_calls_history": [],
        "is_complete": is_complete,
        "fast_path_used": fast_path_used,
        "fast_path_answer": None,
        "final_answer": None,
        "sources": [],
        "success": False,
        "reasoning_steps": [],
        "metadata": {"user_name": "Test User"},
        "features": {
            "web_search_enabled": False,
            "connectors_enabled": False,
            "social_channel_mode": False,
        },
        "user_memory": user_memory,
        "use_swarm": use_swarm,
        "swarm_sub_tasks": [],
        "swarm_current_task": None,
        "swarm_worker_id": None,
        "swarm_worker_results": [],
        "swarm_pending_events": [],
    }
    state.update(overrides)
    return state
