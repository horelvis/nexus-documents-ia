"""Shared DB enum types.

Lives in its own module to avoid circular imports between feature
model files (e.g. ``agent_models.py`` needs ``ModelRole`` and
``models.py`` re-exports it for backwards compatibility).
"""
from __future__ import annotations

import enum


class ModelRole(str, enum.Enum):
    """LLM role for the dual-model router (planner vs chat).

    Mirrored at runtime by ``app.agents.llm_types.ModelRole`` in the
    emma-agent-service so the wire format ('PLANNER' / 'CHAT') stays
    consistent across the service boundary.
    """
    PLANNER = "PLANNER"
    CHAT = "CHAT"
