"""
Orchestration Patterns for Emma Multi-Agent System

This module provides semantic routing for knowledge source classification
and domain detection.

ROUTERS:
- SemanticPatternRouter: Classifies orchestration patterns (HANDOFF, SEQUENTIAL, CONCURRENT)
- SemanticDomainRouter: Classifies legal/business domains (contract, labor, fiscal, etc.)
- SemanticKnowledgeRouter: Classifies knowledge sources (tenant_documents, public_knowledge, hybrid)
- HybridKnowledgeRouter: 2-stage routing (semantic + ML fallback)

Note: QwenAgent orchestration (sequential, concurrent) has been removed.
      Use LangGraph for multi-agent workflows instead.
"""

# Semantic Routers (optional - graceful fallback if not installed)
try:
    from .router import (
        # Pattern Router - classifies orchestration patterns (HANDOFF, SEQUENTIAL, CONCURRENT)
        SemanticPatternRouter,
        get_semantic_router,
        classify_pattern,
        # Domain Router - classifies legal/business domains (contract, labor, fiscal, etc.)
        SemanticDomainRouter,
        get_domain_router,
        classify_domain,
        # Preload function for startup
        preload_semantic_routers,
    )
    from .knowledge_source_router import (
        # Knowledge Source Router - classifies knowledge sources (tenant_documents, public_knowledge, hybrid)
        KnowledgeSource,
        KnowledgeSourceResult,
        SemanticKnowledgeRouter,
        get_knowledge_source_router,
        classify_knowledge_source,
        preload_knowledge_source_router,
    )
    from .hybrid_knowledge_router import (
        # Hybrid Knowledge Router - 2-stage routing (semantic + ML fallback)
        HybridClassificationResult,
        HybridKnowledgeRouter,
        get_hybrid_knowledge_router,
        classify_knowledge_source_hybrid,
        preload_hybrid_knowledge_router,
    )
    _SEMANTIC_ROUTER_AVAILABLE = True
except ImportError:
    _SEMANTIC_ROUTER_AVAILABLE = False
    # Pattern Router
    SemanticPatternRouter = None
    get_semantic_router = None
    classify_pattern = None
    # Domain Router
    SemanticDomainRouter = None
    get_domain_router = None
    classify_domain = None
    # Knowledge Source Router
    KnowledgeSource = None
    KnowledgeSourceResult = None
    SemanticKnowledgeRouter = None
    get_knowledge_source_router = None
    classify_knowledge_source = None
    preload_knowledge_source_router = None
    # Hybrid Knowledge Router
    HybridClassificationResult = None
    HybridKnowledgeRouter = None
    get_hybrid_knowledge_router = None
    classify_knowledge_source_hybrid = None
    preload_hybrid_knowledge_router = None
    # Preload function
    preload_semantic_routers = None

__all__ = [
    # Semantic Pattern Router (classifies HANDOFF/SEQUENTIAL/CONCURRENT)
    "SemanticPatternRouter",
    "get_semantic_router",
    "classify_pattern",
    # Semantic Domain Router (classifies legal/business domains)
    "SemanticDomainRouter",
    "get_domain_router",
    "classify_domain",
    # Knowledge Source Router (classifies tenant_documents/public_knowledge/hybrid)
    "KnowledgeSource",
    "KnowledgeSourceResult",
    "SemanticKnowledgeRouter",
    "get_knowledge_source_router",
    "classify_knowledge_source",
    "preload_knowledge_source_router",
    # Hybrid Knowledge Router (2-stage: semantic + ML fallback)
    "HybridClassificationResult",
    "HybridKnowledgeRouter",
    "get_hybrid_knowledge_router",
    "classify_knowledge_source_hybrid",
    "preload_hybrid_knowledge_router",
    # Preload function
    "preload_semantic_routers",
    # Availability flag
    "_SEMANTIC_ROUTER_AVAILABLE",
]
