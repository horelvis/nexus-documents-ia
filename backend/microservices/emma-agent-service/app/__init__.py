"""
Emma Agent Service - Intelligent Query Orchestration

This microservice handles:
- Emma v2 AI agent with SIL fast path
- LangGraph multi-agent orchestration
- SLM Router for TOON-based query planning
- Session and conversation management
- LLM client with multi-provider support

Separated from weaviate-service to enable:
- Independent scaling (agents vs retrieval)
- Fault isolation (LLM errors don't affect vector search)
- Faster iteration on agent logic
"""

__version__ = "1.0.0"
