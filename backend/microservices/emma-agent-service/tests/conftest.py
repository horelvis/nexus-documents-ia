"""
Shared pytest configuration for emma-agent-service tests.

Sets required environment variables and mocks missing system-level
modules BEFORE any app module imports.

The import chain `app.agents.__init__ → Emma → emma_persistence_service → asyncpg`
pulls in heavy dependencies that are only installed inside Docker.
We mock them here so unit tests can run on the host.
"""

import os
import sys
from unittest.mock import MagicMock

# ── Environment Variables ─────────────────────────────────────────────────────
# Required by app.core.config.Settings (only field without a default)
os.environ.setdefault("MICROSERVICES_API_KEY", "test-api-key-for-unit-tests")

# Disable web search in tests to avoid real HTTP calls
os.environ.setdefault("WEB_SEARCH_ENABLED", "false")

# Use vllm provider (doesn't matter since we mock LLM calls)
os.environ.setdefault("LLM_PROVIDER", "vllm")


# ── Mock Missing System-Level Modules ─────────────────────────────────────────
# These are only installed inside Docker. Mocking them allows unit tests
# that import from `app.agents.*` to work on the host without installing
# the full service dependency graph.
_mock_modules = [
    "asyncpg",
    "asyncpg.pool",
    "asyncpg.exceptions",
]

for mod_name in _mock_modules:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = MagicMock()


# ── Sector-Parametrized Fixtures ─────────────────────────────────────────────
import pytest
from tests.sector_helpers import ALL_SECTORS, reset_sector_singleton, reset_tool_registry


@pytest.fixture(params=ALL_SECTORS)
def sector(request):
    """Parametrized fixture: runs the test 3x (legal, medical, documental).

    Yields (sector_name, SectorConfig) tuple.
    Resets the sector singleton before and after each test to prevent leaks.
    """
    sector_name = request.param
    reset_sector_singleton(sector_name)
    from app.agents.langgraph.sectors.registry import SECTOR_CONFIGS
    config = SECTOR_CONFIGS[sector_name]
    yield sector_name, config
    reset_sector_singleton("")


@pytest.fixture
def reset_singletons():
    """Reset all global singletons after the test."""
    yield
    reset_sector_singleton("")
    reset_tool_registry()
