"""
MEN Service - Mixture of Experts Network for Document Intelligence.

Architecture:
- Orchestrator (1.5B): Domain classification
- Experts (0.5B + LoRA): Tenant-specific knowledge
- LLM Modeler (3B): Response synthesis with conversational memory
"""

__version__ = "1.0.0"
