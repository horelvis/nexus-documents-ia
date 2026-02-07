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
