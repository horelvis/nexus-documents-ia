"""
Shared fixtures for MEN service tests.

All heavy ML components (Orchestrator, LLMModeler, Expert) are mocked
so tests run without GPU or model downloads.
"""

import json
import os
from typing import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Read the real API key from the environment (set in docker-compose)
# Fall back to a test key if not set.
# ---------------------------------------------------------------------------

TEST_API_KEY = os.environ.get("MICROSERVICES_API_KEY", "test-api-key")


def auth_headers() -> dict:
    """Return default authentication headers."""
    return {"X-API-Key": TEST_API_KEY}


# ---------------------------------------------------------------------------
# Mock component builders
# ---------------------------------------------------------------------------

def _build_mock_orchestrator():
    """Build a mock Orchestrator that returns deterministic classifications."""
    mock = MagicMock()
    mock.is_loaded = True
    mock.load.return_value = None
    mock.unload.return_value = None
    mock.route.return_value = ["legal"]
    mock.route_with_confidence.return_value = ("legal", 0.85)
    return mock


def _build_mock_modeler():
    """Build a mock LLMModeler with in-memory history."""
    mock = MagicMock()
    mock.is_loaded = True
    mock.load.return_value = None
    mock.unload.return_value = None

    _history: dict = {}

    def _gen_response(user_input, session_id="default", expert_data=None, tenant_context=None):
        if session_id not in _history:
            _history[session_id] = []
        _history[session_id].append({"role": "user", "content": user_input})
        response = f"Respuesta mock para: {user_input[:50]}"
        _history[session_id].append({"role": "assistant", "content": response})
        return response

    mock.generate_response.side_effect = _gen_response

    def _get_history(session_id):
        return list(_history.get(session_id, []))

    mock.get_history.side_effect = _get_history

    def _clear_history(session_id):
        if session_id in _history:
            del _history[session_id]
            return True
        return False

    mock.clear_history.side_effect = _clear_history
    mock.get_all_sessions.side_effect = lambda: list(_history.keys())
    mock.get_session_count.side_effect = lambda: len(_history)

    return mock


def _build_mock_tenant_manager(experts_dir: str):
    """Build a real TenantExpertManager pointing at the test directory."""
    from app.services.tenant_expert_manager import TenantExpertManager

    manager = TenantExpertManager(experts_dir=experts_dir)
    manager.initialize()
    return manager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def experts_dir(tmp_path) -> str:
    """Create a temp experts directory with one generic and one tenant expert stub."""
    base = tmp_path / "trained_experts"
    generic = base / "_generic_" / "legal"
    generic.mkdir(parents=True)
    (generic / "adapter_config.json").write_text("{}")

    tenant_dir = base / "tenant-test" / "contract_expert"
    tenant_dir.mkdir(parents=True)
    (tenant_dir / "adapter_model.safetensors").write_bytes(b"\x00")
    metadata = {"document_types": ["contrato", "acuerdo"]}
    (tenant_dir / "expert_metadata.json").write_text(json.dumps(metadata))

    return str(base)


@pytest.fixture()
def men_config(experts_dir):
    """Build a MENConfig pointing at the temp experts dir."""
    from app.core.config import MENConfig

    return MENConfig(
        orchestrator_model="test-orch",
        llm_modeler_model="test-modeler",
        expert_base_model="test-expert",
        experts_dir=experts_dir,
    )


@pytest.fixture()
def mock_orchestrator():
    return _build_mock_orchestrator()


@pytest.fixture()
def mock_modeler():
    return _build_mock_modeler()


@pytest.fixture()
def mock_men_system(men_config, mock_orchestrator, mock_modeler, experts_dir):
    """
    Build a MENSystem with mocked ML components but a real TenantExpertManager.
    """
    from app.services.men_system import MENSystem

    system = MENSystem.__new__(MENSystem)
    system.config = men_config
    system.orchestrator = mock_orchestrator
    system.llm_modeler = mock_modeler
    system.tenant_manager = _build_mock_tenant_manager(experts_dir)
    system._experts = {}
    system._loaded_experts = set()
    system._loaded = True

    # Mock _get_or_load_expert so it never tries to load a real model
    mock_expert = MagicMock()
    mock_expert.query.return_value = "Datos técnicos del experto mock."
    mock_expert.is_loaded = True
    mock_expert.unload.return_value = None
    system._get_or_load_expert = MagicMock(return_value=mock_expert)

    return system


@pytest.fixture()
def client(mock_men_system) -> Generator:
    """
    FastAPI TestClient with the MEN system fully mocked.

    We patch the module-level singleton so all route handlers
    see the mock instead of the real (GPU-loaded) MENSystem.
    """
    import app.services.men_system as men_mod
    import app.api.routes as routes_mod
    import app.api.session_routes as session_mod
    import app.api.tenant_routes as tenant_mod

    # Save originals
    orig_global = men_mod._men_system

    # Patch the singleton and all get_men_system references
    men_mod._men_system = mock_men_system

    def _get_mock():
        return mock_men_system

    with patch.object(men_mod, "get_men_system", _get_mock), \
         patch.object(routes_mod, "get_men_system", _get_mock), \
         patch.object(session_mod, "get_men_system", _get_mock), \
         patch.object(tenant_mod, "get_men_system", _get_mock):

        from app.main import app
        with TestClient(app) as c:
            yield c

    # Restore
    men_mod._men_system = orig_global
