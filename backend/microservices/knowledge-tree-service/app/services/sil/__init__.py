"""
SIL (Structural Intelligence Layer) Stub for Emma Agent Service.

This module provides stubs that delegate to weaviate-service via HTTP.
The actual SIL implementation lives in weaviate-service.
"""

from .engine import pre_llm_engine, PreLLMEngine
from .schemas import ReasoningType, SILResult

__all__ = [
    "pre_llm_engine",
    "PreLLMEngine",
    "ReasoningType",
    "SILResult",
]
