"""
Type definitions preserved from the old LLM layer.

Used during and after migration. Consumers that only need ModelRole
should import from here instead of llm_client.py.
"""

from enum import Enum


class ModelRole(str, Enum):
    """Model role in dual-phase architecture.

    PLANNER: Fast, deterministic — routing, tool calling, classification.
    CHAT: Creative, longer output — synthesis, social, final responses.
    """
    PLANNER = "planner"
    CHAT = "chat"
