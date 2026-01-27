# Multi-Tier RAG Caching Architecture

## Overview

NouxCubeIA implements a sophisticated multi-tier caching system that combines **RAG (Retrieval-Augmented Generation)** with **CAG (Cache-Augmented Generation)** patterns. This architecture significantly reduces latency, compute costs, and GPU utilization for production deployments.

## The Problem

Traditional RAG pipelines execute the same expensive operations for every query:

```
Query → Embed → Vector Search → Fetch Docs → Assemble Context → LLM → Response
         │           │               │               │            │
       ~50ms      ~200ms          ~100ms          ~50ms       ~3-10s
```

For repetitive workloads (common in enterprise), this wastes resources on identical computations.

## The Solution: Multi-Tier Caching

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    MULTI-TIER CACHING ARCHITECTURE                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  User Query                                                                  │
│       │                                                                      │
│       ▼                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  TIER 1: Retrieval Cache                                            │    │
│  │  ────────────────────────────────────────────────────────────────   │    │
│  │  • What: Document IDs + relevance scores from vector search         │    │
│  │  • Key: hash(query_embedding + tenant_id + user_id + filters)       │    │
│  │  • TTL: 5 minutes (short for data freshness)                        │    │
│  │  • User-isolated: Respects ACL (different users = different cache)  │    │
│  │  • Saves: ~200-500ms (skip embedding + vector search)               │    │
│  └────────────────────────────────┬────────────────────────────────────┘    │
│                                   │ cache miss                              │
│                                   ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  TIER 2: Context Assembly Cache                                     │    │
│  │  ────────────────────────────────────────────────────────────────   │    │
│  │  • What: Assembled context string ready for LLM injection           │    │
│  │  • Key: hash(sorted_doc_ids + chunk_version + index_version)        │    │
│  │  • TTL: 30 minutes                                                  │    │
│  │  • Insight: Different queries → same docs → SAME context            │    │
│  │  • Saves: ~50-200ms (skip doc fetching + token counting)            │    │
│  │  • Reverse index: doc_id → cache_keys for O(1) invalidation         │    │
│  └────────────────────────────────┬────────────────────────────────────┘    │
│                                   │ cache miss                              │
│                                   ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  TIER 3: Semantic Cache (Existing)                                  │    │
│  │  ────────────────────────────────────────────────────────────────   │    │
│  │  • What: Final LLM responses                                        │    │
│  │  • Key: Semantic similarity of query (cosine > 0.92)                │    │
│  │  • TTL: 1 hour                                                      │    │
│  │  • Saves: ~3-10 seconds (skip entire RAG + LLM inference)           │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  Version Manager                                                    │    │
│  │  ────────────────────────────────────────────────────────────────   │    │
│  │  • Tracks: embedding_model, chunk_strategy, index_version           │    │
│  │  • On change: Cascading invalidation via registered callbacks       │    │
│  │  • History: Last 10 version changes for debugging                   │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Components

### 1. Retrieval Cache (`retrieval_cache.py`)

Caches the results of vector search operations.

```python
from app.services.rag.cache import retrieval_cache

# Automatic usage in rag_pipeline.py
cached = await retrieval_cache.get(
    query_embedding=embedding,
    tenant_id="tenant-123",
    user_id="user-456",  # ACL isolation
    filters={"document_type": "contract"},
    top_k=20
)

if cached:
    # Use cached doc_ids and scores
    doc_ids = cached.doc_ids
    scores = cached.scores
else:
    # Perform vector search, then cache
    results = await vector_search(...)
    await retrieval_cache.set(
        query_embedding=embedding,
        tenant_id="tenant-123",
        user_id="user-456",
        filters=filters,
        doc_ids=results.doc_ids,
        scores=results.scores,
        top_k=20
    )
```

**Key design decisions:**
- **User isolation**: Cache key includes `user_id` to respect ACL
- **Short TTL**: 5 minutes balances freshness vs. hit rate
- **Embedding-based key**: Similar queries naturally hit same cache

### 2. Context Assembly Cache (`context_cache.py`)

Caches the assembled context string that gets injected into the LLM prompt.

```python
from app.services.rag.cache import context_cache

# Key insight: Same documents = same context, regardless of original query
# Query A: "What are payment terms?" → docs [1,2,3] → context_hash_abc
# Query B: "When do I pay?" → docs [1,2,3] → context_hash_abc (SAME!)

cached = await context_cache.get(
    doc_ids=["doc-1", "doc-2", "doc-3"],
    tenant_id="tenant-123",
    chunk_version="semantic-v1",
    index_version="42"
)

if cached:
    context_string = cached.context_string
    total_tokens = cached.total_tokens
```

**Reverse index for invalidation:**
```
doc_id → Set[cache_keys]

Example:
  doc-123 → {context:tenant:abc123, context:tenant:def456}
  doc-456 → {context:tenant:abc123}

When doc-123 is updated:
  1. Look up doc-123 → {abc123, def456}
  2. Delete both cache entries
  3. O(1) lookup instead of full scan
```

### 3. Version Manager (`version_manager.py`)

Coordinates cache invalidation across all tiers when system components change.

```python
from app.services.rag.cache import cache_version_manager

# Get current versions
versions = await cache_version_manager.get_versions("tenant-123")
# VersionInfo(embedding_model="bge-m3", chunk_strategy="semantic-v1",
#             index_version="42", last_reindex="2024-01-15T10:30:00")

# Bump version on reindex (triggers invalidation)
new_version = await cache_version_manager.bump_index_version(
    "tenant-123",
    reason="full_reindex"
)

# Mark specific documents as updated
invalidated = await cache_version_manager.mark_documents_updated(
    "tenant-123",
    doc_ids=["doc-123", "doc-456"],
    reason="document_content_changed"
)
print(f"Invalidated {invalidated} cache entries")
```

**Version tracking:**
| Component | Tracked In | Changes When |
|-----------|------------|--------------|
| `embedding_model` | Redis | Admin upgrades embedding model |
| `chunk_strategy` | Redis | Admin changes chunking config |
| `index_version` | Redis (atomic INCR) | Full reindex completes |
| `document_version` | Redis per doc | Individual doc updated |

## Cache Invalidation Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         INVALIDATION SCENARIOS                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  SCENARIO 1: Document Updated                                               │
│  ─────────────────────────────                                               │
│  document_service.update(doc_id="doc-123")                                  │
│       │                                                                      │
│       ▼                                                                      │
│  version_manager.mark_documents_updated(["doc-123"])                        │
│       │                                                                      │
│       ├──▶ retrieval_cache.invalidate_by_query_results(doc-123)            │
│       │         (invalidates queries that returned this doc)                │
│       │                                                                      │
│       ├──▶ context_cache.invalidate_by_documents(doc-123)                  │
│       │         (uses reverse index for O(1) lookup)                        │
│       │                                                                      │
│       └──▶ semantic_cache.invalidate_by_document(doc-123)                  │
│                 (existing cache)                                             │
│                                                                              │
│  SCENARIO 2: Full Reindex                                                   │
│  ─────────────────────────                                                   │
│  admin_api.trigger_reindex(tenant_id="tenant-123")                          │
│       │                                                                      │
│       ▼                                                                      │
│  version_manager.bump_index_version("tenant-123")                           │
│       │                                                                      │
│       └──▶ ALL CACHES INVALIDATED for tenant                               │
│            (version mismatch on next read = cache miss)                     │
│                                                                              │
│  SCENARIO 3: Embedding Model Upgrade                                        │
│  ────────────────────────────────────                                        │
│  admin_api.set_embedding_model("bge-m3-v2")                                 │
│       │                                                                      │
│       ▼                                                                      │
│  version_manager.set_embedding_model("tenant-123", "bge-m3-v2")             │
│       │                                                                      │
│       └──▶ ALL CACHES INVALIDATED                                           │
│            (WARNING logged: REINDEX REQUIRED!)                              │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Configuration

```bash
# backend/docker/.env

# =============================================================================
# TIER 1: Retrieval Cache
# =============================================================================
# Caches vector search results (doc_ids + scores)
RETRIEVAL_CACHE_ENABLED=true
RETRIEVAL_CACHE_TTL_SECONDS=300        # 5 minutes
RETRIEVAL_CACHE_MAX_ENTRIES=500        # Max cached queries per tenant

# =============================================================================
# TIER 2: Context Assembly Cache
# =============================================================================
# Caches assembled context strings ready for LLM
CONTEXT_CACHE_ENABLED=true
CONTEXT_CACHE_TTL_SECONDS=1800         # 30 minutes
CONTEXT_CACHE_MAX_SIZE_MB=100          # Max total cache size

# =============================================================================
# TIER 3: Semantic Cache (existing)
# =============================================================================
# Caches final LLM responses
RAG_CACHE_ENABLED=true
RAG_CACHE_TTL_SECONDS=3600             # 1 hour
RAG_SEMANTIC_CACHE_SIMILARITY=0.92     # Similarity threshold for cache hit

# =============================================================================
# Redis Configuration
# =============================================================================
REDIS_HOST=redis
REDIS_PORT=6379
```

## Performance Metrics

### Expected Hit Rates

| Cache Tier | Typical Hit Rate | Best Case | Notes |
|------------|------------------|-----------|-------|
| Retrieval | 40-60% | 80%+ | Higher for repetitive queries |
| Context Assembly | 50-70% | 85%+ | Different queries often retrieve same docs |
| Semantic | 30-50% | 70%+ | Similar questions get cached answers |

### Latency Savings

| Scenario | Without Cache | With Cache Hit | Savings |
|----------|---------------|----------------|---------|
| Full query | 3-10s | 50-100ms | 95%+ |
| Tier 1 hit | 3s | 2.5s | ~500ms |
| Tier 2 hit | 2.5s | 2.3s | ~200ms |
| Tier 3 hit | 3s | 50ms | 95%+ |

### GPU Utilization Impact

With caching enabled, vLLM GPU utilization typically drops 30-50% for production workloads because:
1. Tier 3 semantic cache eliminates LLM calls for similar queries
2. Reduced query volume allows better batching for remaining queries

## Redis Memory Planning

| Deployment Size | Users | Expected Cache Size | Redis Memory |
|-----------------|-------|---------------------|--------------|
| Development | 1-5 | ~50MB | 256MB |
| Small | 5-20 | ~200MB | 512MB |
| Medium | 20-100 | ~500MB | 1GB |
| Large | 100-500 | ~2GB | 4GB |
| Enterprise | 500+ | ~5GB+ | 8GB+ / Cluster |

## Monitoring

### Health Check Endpoint

```bash
curl http://localhost:8007/api/v1/cache/health \
  -H "X-Tenant-ID: tenant-123" | jq
```

Response:
```json
{
  "tenant_id": "tenant-123",
  "retrieval_cache": {
    "enabled": true,
    "hits": 1234,
    "misses": 567,
    "hit_rate": 0.68,
    "avg_hit_latency_ms": 2.3
  },
  "context_cache": {
    "enabled": true,
    "hits": 890,
    "misses": 234,
    "hit_rate": 0.79,
    "avg_cached_tokens": 4500,
    "invalidations": 45
  },
  "semantic_cache": {
    "enabled": true,
    "hits": 456,
    "misses": 123,
    "hit_rate": 0.78
  },
  "version_info": {
    "embedding_model": "bge-m3",
    "chunk_strategy": "semantic-v1",
    "index_version": "42",
    "last_reindex": "2024-01-15T10:30:00Z"
  },
  "recent_version_changes": [
    {
      "component": "index",
      "old": "41",
      "new": "42",
      "reason": "full_reindex",
      "timestamp": "2024-01-15T10:30:00Z"
    }
  ]
}
```

### Redis Monitoring

```bash
# Check memory usage
docker compose exec redis redis-cli INFO memory | grep used_memory_human

# Count cache keys by type
docker compose exec redis redis-cli KEYS "retrieval:*" | wc -l
docker compose exec redis redis-cli KEYS "context:*" | wc -l
docker compose exec redis redis-cli KEYS "version:*" | wc -l

# Monitor cache operations in real-time
docker compose exec redis redis-cli MONITOR | grep -E "(retrieval|context|version)"
```

## Troubleshooting

### Low Hit Rates

**Symptom**: Hit rate < 20% despite repetitive workloads

**Possible causes**:
1. **TTL too short**: Increase TTL if data doesn't change frequently
2. **High query diversity**: Normal for exploratory usage patterns
3. **Frequent invalidations**: Check version history for unexpected changes

```bash
# Check version change history
curl http://localhost:8007/api/v1/cache/health | jq '.recent_version_changes'
```

### High Memory Usage

**Symptom**: Redis using more memory than expected

**Solutions**:
1. Reduce TTL values
2. Reduce `RETRIEVAL_CACHE_MAX_ENTRIES`
3. Reduce `CONTEXT_CACHE_MAX_SIZE_MB`
4. Increase Redis memory limit

```bash
# Check which cache tier uses most memory
docker compose exec redis redis-cli DEBUG OBJECT "retrieval:tenant-123:*"
```

### Stale Data Returned

**Symptom**: User sees outdated information after document update

**Cause**: Invalidation not triggered

**Solution**: Verify invalidation flow:
```bash
# Check if document update triggers invalidation
docker compose logs weaviate-service | grep "mark_documents_updated"

# Manual invalidation
curl -X POST http://localhost:8007/api/v1/cache/invalidate \
  -H "X-Tenant-ID: tenant-123" \
  -H "Content-Type: application/json" \
  -d '{"document_ids": ["doc-123"]}'
```

## File Locations

| File | Description |
|------|-------------|
| `weaviate-service/app/services/rag/cache/__init__.py` | Cache module exports |
| `weaviate-service/app/services/rag/cache/retrieval_cache.py` | Tier 1 implementation |
| `weaviate-service/app/services/rag/cache/context_cache.py` | Tier 2 implementation |
| `weaviate-service/app/services/rag/cache/version_manager.py` | Version tracking |
| `weaviate-service/app/services/rag/rag_pipeline.py` | Integration point |
| `weaviate-service/app/core/config.py` | Configuration variables |

## Related Documentation

- [RAG Pipeline Architecture](./RAG_PIPELINE.md)
- [SLM Router](./SLM_ROUTER.md)
- [On-Premise Deployment](../../README-ONPREMISE.md)
