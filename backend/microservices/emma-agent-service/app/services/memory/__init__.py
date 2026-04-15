"""Memory module for Emma.

Provides cross-session persistent user facts (name, department, preferences)
injected into LangGraph prompts for personalization.

Usage:
    from app.services.memory import get_user_facts_service

    facts_service = get_user_facts_service()
    facts = await facts_service.get_user_facts(user_id)
"""

from .user_facts import UserFactsService, get_user_facts_service
from .fact_extractor import extract_and_save_facts
from .memory_generator import generate_and_store_memory

__all__ = [
    "UserFactsService",
    "get_user_facts_service",
    "extract_and_save_facts",
    "generate_and_store_memory",
]
