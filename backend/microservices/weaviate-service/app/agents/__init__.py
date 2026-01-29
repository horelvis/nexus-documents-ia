"""
Weaviate Service - Minimal Agent Module

Agent orchestration (EmmaV2, LangGraph, domain routing) has been moved to
emma-agent-service for independent scaling.

This module is kept minimal. For full agent functionality, see:
- emma-agent-service (port 8009)

Note: SIL (Structural Intelligence Layer) and SLM Router have been removed.
Query understanding is now handled by LLM-based reasoning in emma-agent-service.
"""

__all__ = []
