"""
Emma Meta Agent — ADAS-inspired agent design automation.

Generates, evaluates, and selects Python `forward()` functions that orchestrate
Emma's primitives (LLM calls + tools) in novel ways discovered through search.

Architecture:
    OFFLINE:  Generator → Sandbox → Evaluator → Archive
    ONLINE:   classify_node → OnlineSelector → Sandbox.execute(forward, query)
    FEEDBACK: Production signals → Archive score updates

All flags default to off — enable via META_AGENT_ENABLED, META_AGENT_ONLINE_SELECTION.
"""
