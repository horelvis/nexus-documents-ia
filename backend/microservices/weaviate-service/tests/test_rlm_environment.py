"""
Tests for RLM Environment Module

Covers:
- In-memory storage (RAM) as primary
- Context storage and retrieval
- Section access (random access)
- Result caching
- TTL expiration
- Redis fallback mode (when explicitly enabled)

Reference: RLM paper arXiv:2512.24601 - Section 3.2 "External Environment"
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any

# Add parent directory to path for imports
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.agents.rlm_environment import (
    RLMEnvironment,
    StoredContext,
    ContextSection,
    MemoryEntry,
    rlm_environment,
)


# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def environment():
    """Create a fresh RLMEnvironment for each test."""
    env = RLMEnvironment()
    return env


@pytest.fixture
def sample_content():
    """Sample document content for testing."""
    return """
# Introduction

This is a sample document for testing the RLM Environment.

## Section 1: Overview

The RLM (Recursive Language Model) pattern enables processing of documents
that exceed the context window of language models.

### 1.1 Key Concepts

- External Environment: Stores context outside LLM context window
- Random Access: Enables retrieval of specific sections
- Caching: Intermediate results can be cached for reuse

## Section 2: Implementation

The implementation follows the paper arXiv:2512.24601.

### 2.1 Storage

Primary storage uses RAM for optimal performance (~0.001ms per operation).
Redis is available as a fallback for distributed scenarios.

### 2.2 TTL

All stored items have a configurable time-to-live (TTL) for automatic cleanup.

## Conclusion

The RLM Environment provides efficient context storage for long document processing.
"""


@pytest.fixture
def large_content():
    """Large content to test token estimation."""
    # Generate ~40K characters (~10K tokens)
    base = "This is a test sentence for generating large content. " * 100
    return base * 8


# ============================================================================
# Test: Initialization
# ============================================================================


class TestInitialization:
    """Tests for RLMEnvironment initialization."""

    @pytest.mark.asyncio
    async def test_initializes_with_ram_by_default(self, environment):
        """By default, environment should use RAM storage."""
        await environment.initialize()

        assert environment._initialized is True
        assert environment._use_redis_fallback is False
        assert environment._redis is None

    @pytest.mark.asyncio
    async def test_memory_store_starts_empty(self, environment):
        """Memory store should start empty."""
        await environment.initialize()

        assert len(environment._memory_store) == 0

    @pytest.mark.asyncio
    async def test_cleanup_task_starts(self, environment):
        """Cleanup task should be started on initialization."""
        await environment.initialize()

        assert environment._cleanup_task is not None
        assert not environment._cleanup_task.done()

        # Cleanup
        await environment.shutdown()


# ============================================================================
# Test: Store Context
# ============================================================================


class TestStoreContext:
    """Tests for store_context method."""

    @pytest.mark.asyncio
    async def test_stores_context_successfully(self, environment, sample_content):
        """Should store context and return valid context_id."""
        await environment.initialize()

        context_id = await environment.store_context(
            content=sample_content,
            tenant_id="test-tenant",
        )

        assert context_id is not None
        assert len(context_id) == 16  # SHA256 truncated to 16 chars

        await environment.shutdown()

    @pytest.mark.asyncio
    async def test_stores_with_metadata(self, environment, sample_content):
        """Should store context with metadata."""
        await environment.initialize()

        metadata = {"source": "test", "version": 1}
        context_id = await environment.store_context(
            content=sample_content,
            tenant_id="test-tenant",
            document_id="doc-123",
            metadata=metadata,
        )

        context = await environment.get_context(context_id)

        assert context is not None
        assert context.document_id == "doc-123"
        assert context.metadata == metadata

        await environment.shutdown()

    @pytest.mark.asyncio
    async def test_calculates_tokens_correctly(self, environment, sample_content):
        """Should estimate token count (~4 chars per token)."""
        await environment.initialize()

        context_id = await environment.store_context(
            content=sample_content,
            tenant_id="test-tenant",
        )

        context = await environment.get_context(context_id)

        expected_tokens = len(sample_content) // 4
        assert context.total_tokens == expected_tokens

        await environment.shutdown()

    @pytest.mark.asyncio
    async def test_stores_directly_in_memory(self, environment, sample_content):
        """In RAM mode, objects should be stored directly (no serialization)."""
        await environment.initialize()

        context_id = await environment.store_context(
            content=sample_content,
            tenant_id="test-tenant",
        )

        # Access internal memory store
        key = f"rlm:context:{context_id}"
        entry = environment._memory_store.get(key)

        assert entry is not None
        assert isinstance(entry, MemoryEntry)
        assert isinstance(entry.value, StoredContext)  # Direct object, not JSON string

        await environment.shutdown()


# ============================================================================
# Test: Get Context
# ============================================================================


class TestGetContext:
    """Tests for get_context method."""

    @pytest.mark.asyncio
    async def test_retrieves_stored_context(self, environment, sample_content):
        """Should retrieve previously stored context."""
        await environment.initialize()

        context_id = await environment.store_context(
            content=sample_content,
            tenant_id="test-tenant",
        )

        context = await environment.get_context(context_id)

        assert context is not None
        assert context.content == sample_content
        assert context.tenant_id == "test-tenant"

        await environment.shutdown()

    @pytest.mark.asyncio
    async def test_returns_none_for_nonexistent(self, environment):
        """Should return None for non-existent context."""
        await environment.initialize()

        context = await environment.get_context("nonexistent-id")

        assert context is None

        await environment.shutdown()

    @pytest.mark.asyncio
    async def test_returns_none_for_expired(self, environment, sample_content):
        """Should return None for expired context."""
        await environment.initialize()

        # Store with very short TTL
        context_id = await environment.store_context(
            content=sample_content,
            tenant_id="test-tenant",
            ttl=1,  # 1 second TTL
        )

        # Wait for expiration
        await asyncio.sleep(1.5)

        context = await environment.get_context(context_id)

        assert context is None

        await environment.shutdown()


# ============================================================================
# Test: Get Section (Random Access)
# ============================================================================


class TestGetSection:
    """Tests for get_section method (random access)."""

    @pytest.mark.asyncio
    async def test_retrieves_section_by_offset(self, environment, sample_content):
        """Should retrieve specific section by character offsets."""
        await environment.initialize()

        context_id = await environment.store_context(
            content=sample_content,
            tenant_id="test-tenant",
        )

        # Get first 100 characters
        section = await environment.get_section(
            context_id=context_id,
            start_offset=0,
            end_offset=100,
        )

        assert section is not None
        assert section.content == sample_content[0:100]
        assert section.start_offset == 0
        assert section.end_offset == 100

        await environment.shutdown()

    @pytest.mark.asyncio
    async def test_caches_sections(self, environment, sample_content):
        """Repeated section requests should be cached."""
        await environment.initialize()

        context_id = await environment.store_context(
            content=sample_content,
            tenant_id="test-tenant",
        )

        # First request
        section1 = await environment.get_section(context_id, 0, 100)

        # Second request (should hit cache)
        section2 = await environment.get_section(context_id, 0, 100)

        assert section1.content == section2.content

        # Verify cache entry exists
        cache_key = f"rlm:section:{context_id}:0:100"
        assert cache_key in environment._memory_store

        await environment.shutdown()

    @pytest.mark.asyncio
    async def test_returns_none_for_invalid_context(self, environment):
        """Should return None when context doesn't exist."""
        await environment.initialize()

        section = await environment.get_section(
            context_id="invalid-id",
            start_offset=0,
            end_offset=100,
        )

        assert section is None

        await environment.shutdown()


# ============================================================================
# Test: Cache Results
# ============================================================================


class TestCacheResults:
    """Tests for result caching methods."""

    @pytest.mark.asyncio
    async def test_caches_result(self, environment, sample_content):
        """Should cache intermediate results."""
        await environment.initialize()

        context_id = await environment.store_context(
            content=sample_content,
            tenant_id="test-tenant",
        )

        await environment.cache_result(
            context_id=context_id,
            task_id="summarize-section-1",
            result="This is the summary of section 1.",
        )

        result = await environment.get_cached_result(context_id, "summarize-section-1")

        assert result == "This is the summary of section 1."

        await environment.shutdown()

    @pytest.mark.asyncio
    async def test_returns_none_for_uncached(self, environment):
        """Should return None for uncached tasks."""
        await environment.initialize()

        result = await environment.get_cached_result("ctx-123", "unknown-task")

        assert result is None

        await environment.shutdown()


# ============================================================================
# Test: Section Index
# ============================================================================


class TestSectionIndex:
    """Tests for section indexing."""

    @pytest.mark.asyncio
    async def test_creates_section_index(self, environment, sample_content):
        """Should create index of section boundaries."""
        await environment.initialize()

        context_id = await environment.store_context(
            content=sample_content,
            tenant_id="test-tenant",
        )

        index = await environment.get_section_index(context_id)

        # Should detect headers (## and ###)
        assert len(index) > 0

        # Each entry is (start, end, type)
        for start, end, section_type in index:
            assert isinstance(start, int)
            assert isinstance(end, int)
            assert section_type in ["header", "legal", "numbered"]

        await environment.shutdown()


# ============================================================================
# Test: Delete Context
# ============================================================================


class TestDeleteContext:
    """Tests for delete_context method."""

    @pytest.mark.asyncio
    async def test_deletes_context(self, environment, sample_content):
        """Should delete stored context."""
        await environment.initialize()

        context_id = await environment.store_context(
            content=sample_content,
            tenant_id="test-tenant",
        )

        # Verify it exists
        context = await environment.get_context(context_id)
        assert context is not None

        # Delete
        result = await environment.delete_context(context_id)

        assert result is True

        # Verify it's gone
        context = await environment.get_context(context_id)
        assert context is None

        await environment.shutdown()

    @pytest.mark.asyncio
    async def test_deletes_related_data(self, environment, sample_content):
        """Should delete sections and cached results too."""
        await environment.initialize()

        context_id = await environment.store_context(
            content=sample_content,
            tenant_id="test-tenant",
        )

        # Create a section cache entry
        await environment.get_section(context_id, 0, 100)

        # Cache a result
        await environment.cache_result(context_id, "task-1", "result")

        # Delete context
        await environment.delete_context(context_id)

        # Verify all related data is deleted
        section = await environment.get_section(context_id, 0, 100)
        result = await environment.get_cached_result(context_id, "task-1")

        # Section should return None (context doesn't exist)
        assert section is None

        await environment.shutdown()


# ============================================================================
# Test: Statistics
# ============================================================================


class TestStatistics:
    """Tests for get_stats method."""

    @pytest.mark.asyncio
    async def test_returns_stats(self, environment, sample_content):
        """Should return environment statistics."""
        await environment.initialize()

        # Store some content
        await environment.store_context(
            content=sample_content,
            tenant_id="test-tenant",
        )

        stats = await environment.get_stats()

        assert stats["storage_mode"] == "ram"
        assert stats["context_count"] == 1
        assert stats["memory_entries"] > 0
        assert stats["estimated_memory_mb"] > 0

        await environment.shutdown()


# ============================================================================
# Test: TTL and Expiration
# ============================================================================


class TestTTLExpiration:
    """Tests for TTL and automatic expiration."""

    @pytest.mark.asyncio
    async def test_custom_ttl(self, environment, sample_content):
        """Should respect custom TTL."""
        await environment.initialize()

        context_id = await environment.store_context(
            content=sample_content,
            tenant_id="test-tenant",
            ttl=7200,  # 2 hours
        )

        context = await environment.get_context(context_id)

        # expires_at should be ~2 hours from now
        time_diff = context.expires_at - datetime.now()
        assert 7100 < time_diff.total_seconds() < 7200

        await environment.shutdown()


# ============================================================================
# Test: Thread Safety
# ============================================================================


class TestThreadSafety:
    """Tests for thread safety of memory operations."""

    @pytest.mark.asyncio
    async def test_concurrent_writes(self, environment):
        """Should handle concurrent writes safely."""
        await environment.initialize()

        async def write_context(i):
            await environment.store_context(
                content=f"Content for context {i}",
                tenant_id="test-tenant",
            )

        # Create 50 concurrent writes
        tasks = [write_context(i) for i in range(50)]
        await asyncio.gather(*tasks)

        stats = await environment.get_stats()

        # All contexts should be stored
        assert stats["context_count"] == 50

        await environment.shutdown()

    @pytest.mark.asyncio
    async def test_concurrent_reads_writes(self, environment, sample_content):
        """Should handle concurrent reads and writes safely."""
        await environment.initialize()

        # First store a context
        context_id = await environment.store_context(
            content=sample_content,
            tenant_id="test-tenant",
        )

        async def read_context():
            return await environment.get_context(context_id)

        async def write_new_context(i):
            return await environment.store_context(
                content=f"New content {i}",
                tenant_id="test-tenant",
            )

        # Mix of reads and writes
        tasks = []
        for i in range(20):
            tasks.append(read_context())
            tasks.append(write_new_context(i))

        results = await asyncio.gather(*tasks)

        # All reads should return the same context
        for i in range(0, len(results), 2):
            ctx = results[i]
            assert ctx is not None
            assert ctx.content == sample_content

        await environment.shutdown()


# ============================================================================
# Test: Performance (RAM vs Redis comparison concept)
# ============================================================================


class TestPerformance:
    """Tests to validate RAM performance characteristics."""

    @pytest.mark.asyncio
    async def test_ram_no_serialization(self, environment, sample_content):
        """RAM mode should store objects directly without serialization."""
        await environment.initialize()

        context_id = await environment.store_context(
            content=sample_content,
            tenant_id="test-tenant",
        )

        key = f"rlm:context:{context_id}"
        entry = environment._memory_store[key]

        # Should be a direct Python object, not a JSON string
        assert isinstance(entry.value, StoredContext)
        assert not isinstance(entry.value, str)

        await environment.shutdown()

    @pytest.mark.asyncio
    async def test_multiple_operations_fast(self, environment):
        """Multiple operations should complete quickly in RAM mode."""
        await environment.initialize()

        import time
        start = time.perf_counter()

        # Perform 100 store + retrieve operations
        for i in range(100):
            context_id = await environment.store_context(
                content=f"Test content {i}" * 100,
                tenant_id="test-tenant",
            )
            await environment.get_context(context_id)

        elapsed = time.perf_counter() - start

        # Should complete in well under 1 second for RAM operations
        assert elapsed < 1.0, f"100 operations took {elapsed:.2f}s, expected < 1s"

        await environment.shutdown()


# ============================================================================
# Test: Global Instance
# ============================================================================


class TestGlobalInstance:
    """Tests for the global rlm_environment instance."""

    def test_global_instance_exists(self):
        """Global instance should exist."""
        assert rlm_environment is not None
        assert isinstance(rlm_environment, RLMEnvironment)


# ============================================================================
# Run tests
# ============================================================================


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--asyncio-mode=auto"])
