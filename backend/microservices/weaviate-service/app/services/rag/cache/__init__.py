"""
RAG Caching Layer - Multi-tier caching for production RAG pipelines

This module implements a hybrid RAG+CAG caching strategy with 3 distinct layers:

1. Retrieval Cache: Caches vector search results (doc IDs + scores)
   - Key: hash(query_embedding + tenant_id + user_id + filters)
   - TTL: 5-15 minutes
   - Benefit: Avoids expensive vector search operations

2. Context Assembly Cache: Caches assembled context ready for LLM
   - Key: hash(doc_ids + chunk_version + index_version)
   - TTL: 30-60 minutes
   - Benefit: Avoids context assembly and token counting

3. Semantic Cache (existing): Caches final LLM responses
   - Key: semantic similarity of query
   - TTL: 1-4 hours
   - Benefit: Avoids LLM inference entirely

Together, these layers achieve 30-40% cost reduction and 50-70% latency improvement.

Version Management ensures cache invalidation when:
- Documents are added/updated/deleted
- Embeddings are re-computed
- Chunking strategy changes
- Index is rebuilt

Reference: "RAG + CAG Hybrid Caching Patterns for Production"
"""

from .retrieval_cache import RetrievalCache, retrieval_cache
from .context_cache import ContextAssemblyCache, context_cache
from .version_manager import CacheVersionManager, cache_version_manager

__all__ = [
    "RetrievalCache",
    "retrieval_cache",
    "ContextAssemblyCache",
    "context_cache",
    "CacheVersionManager",
    "cache_version_manager",
]
