#!/usr/bin/env python3
"""
Standalone RLM Environment Tests

Run with: python3 run_rlm_tests.py
No pytest required - uses asyncio directly.
"""

import asyncio
import sys
import time
from pathlib import Path
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.agents.rlm_environment import (
    RLMEnvironment,
    StoredContext,
    MemoryEntry,
)


# Test sample content
SAMPLE_CONTENT = """
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

## Conclusion

The RLM Environment provides efficient context storage for long document processing.
"""


class TestResult:
    """Simple test result container."""
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []

    def add_pass(self, name: str):
        self.passed += 1
        print(f"  ✅ {name}")

    def add_fail(self, name: str, error: str):
        self.failed += 1
        self.errors.append((name, error))
        print(f"  ❌ {name}: {error}")

    def summary(self):
        total = self.passed + self.failed
        print(f"\n{'='*60}")
        print(f"Results: {self.passed}/{total} passed, {self.failed} failed")
        if self.errors:
            print("\nFailures:")
            for name, error in self.errors:
                print(f"  - {name}: {error}")
        return self.failed == 0


result = TestResult()


async def test_initialization():
    """Test RLMEnvironment initialization."""
    print("\n🧪 Testing Initialization...")

    env = RLMEnvironment()
    await env.initialize()

    try:
        assert env._initialized is True, "Should be initialized"
        result.add_pass("initializes correctly")

        assert env._use_redis_fallback is False, "Should not use Redis by default"
        result.add_pass("uses RAM by default (not Redis)")

        assert env._redis is None, "Redis should be None"
        result.add_pass("no Redis connection")

        assert len(env._memory_store) == 0, "Memory store should start empty"
        result.add_pass("memory store starts empty")

        assert env._cleanup_task is not None, "Cleanup task should exist"
        result.add_pass("cleanup task started")

    except AssertionError as e:
        result.add_fail("initialization", str(e))
    finally:
        await env.shutdown()


async def test_store_and_retrieve():
    """Test storing and retrieving context."""
    print("\n🧪 Testing Store and Retrieve...")

    env = RLMEnvironment()
    await env.initialize()

    try:
        # Store context
        context_id = await env.store_context(
            content=SAMPLE_CONTENT,
            tenant_id="test-tenant",
            document_id="doc-123",
            metadata={"source": "test"}
        )

        assert context_id is not None, "Should return context_id"
        assert len(context_id) == 16, f"Context ID should be 16 chars, got {len(context_id)}"
        result.add_pass("stores context and returns ID")

        # Retrieve context
        context = await env.get_context(context_id)

        assert context is not None, "Should retrieve context"
        assert context.content == SAMPLE_CONTENT, "Content should match"
        assert context.tenant_id == "test-tenant", "Tenant should match"
        assert context.document_id == "doc-123", "Document ID should match"
        assert context.metadata == {"source": "test"}, "Metadata should match"
        result.add_pass("retrieves context correctly")

        # Token estimation
        expected_tokens = len(SAMPLE_CONTENT) // 4
        assert context.total_tokens == expected_tokens, f"Tokens should be ~{expected_tokens}"
        result.add_pass("estimates tokens correctly")

        # Non-existent context
        none_context = await env.get_context("nonexistent-id")
        assert none_context is None, "Should return None for non-existent"
        result.add_pass("returns None for non-existent context")

    except AssertionError as e:
        result.add_fail("store_and_retrieve", str(e))
    finally:
        await env.shutdown()


async def test_ram_storage_no_serialization():
    """Test that RAM mode stores objects directly without serialization."""
    print("\n🧪 Testing RAM Storage (No Serialization)...")

    env = RLMEnvironment()
    await env.initialize()

    try:
        context_id = await env.store_context(
            content=SAMPLE_CONTENT,
            tenant_id="test-tenant",
        )

        # Access internal memory store
        key = f"rlm:context:{context_id}"
        entry = env._memory_store.get(key)

        assert entry is not None, "Entry should exist in memory"
        assert isinstance(entry, MemoryEntry), "Should be MemoryEntry"
        assert isinstance(entry.value, StoredContext), "Value should be StoredContext object"
        assert not isinstance(entry.value, str), "Should NOT be serialized to string"
        result.add_pass("stores Python objects directly (no JSON serialization)")

    except AssertionError as e:
        result.add_fail("ram_storage", str(e))
    finally:
        await env.shutdown()


async def test_section_access():
    """Test random access to sections."""
    print("\n🧪 Testing Section Access (Random Access)...")

    env = RLMEnvironment()
    await env.initialize()

    try:
        context_id = await env.store_context(
            content=SAMPLE_CONTENT,
            tenant_id="test-tenant",
        )

        # Get first 100 characters
        section = await env.get_section(
            context_id=context_id,
            start_offset=0,
            end_offset=100,
        )

        assert section is not None, "Should retrieve section"
        assert section.content == SAMPLE_CONTENT[0:100], "Content should match slice"
        assert section.start_offset == 0, "Start offset should be 0"
        assert section.end_offset == 100, "End offset should be 100"
        result.add_pass("retrieves section by offset")

        # Get middle section
        section2 = await env.get_section(
            context_id=context_id,
            start_offset=200,
            end_offset=400,
        )
        assert section2.content == SAMPLE_CONTENT[200:400], "Middle section should match"
        result.add_pass("retrieves middle section correctly")

        # Invalid context
        invalid_section = await env.get_section("invalid-id", 0, 100)
        assert invalid_section is None, "Should return None for invalid context"
        result.add_pass("returns None for invalid context section")

    except AssertionError as e:
        result.add_fail("section_access", str(e))
    finally:
        await env.shutdown()


async def test_result_caching():
    """Test caching intermediate results."""
    print("\n🧪 Testing Result Caching...")

    env = RLMEnvironment()
    await env.initialize()

    try:
        context_id = await env.store_context(
            content=SAMPLE_CONTENT,
            tenant_id="test-tenant",
        )

        # Cache a result
        await env.cache_result(
            context_id=context_id,
            task_id="summarize-section-1",
            result="This is the summary of section 1.",
        )

        # Retrieve cached result
        cached = await env.get_cached_result(context_id, "summarize-section-1")
        assert cached == "This is the summary of section 1.", "Cached result should match"
        result.add_pass("caches and retrieves results")

        # Non-existent cache
        none_cache = await env.get_cached_result(context_id, "unknown-task")
        assert none_cache is None, "Should return None for unknown task"
        result.add_pass("returns None for uncached results")

    except AssertionError as e:
        result.add_fail("result_caching", str(e))
    finally:
        await env.shutdown()


async def test_section_index():
    """Test section indexing for navigation."""
    print("\n🧪 Testing Section Index...")

    env = RLMEnvironment()
    await env.initialize()

    try:
        context_id = await env.store_context(
            content=SAMPLE_CONTENT,
            tenant_id="test-tenant",
        )

        index = await env.get_section_index(context_id)

        assert len(index) > 0, "Should detect section headers"
        result.add_pass("creates section index")

        # Validate index structure
        for start, end, section_type in index:
            assert isinstance(start, int), "Start should be int"
            assert isinstance(end, int), "End should be int"
            assert section_type in ["header", "legal", "numbered"], f"Invalid type: {section_type}"
        result.add_pass("index has valid structure")

    except AssertionError as e:
        result.add_fail("section_index", str(e))
    finally:
        await env.shutdown()


async def test_delete_context():
    """Test context deletion."""
    print("\n🧪 Testing Delete Context...")

    env = RLMEnvironment()
    await env.initialize()

    try:
        context_id = await env.store_context(
            content=SAMPLE_CONTENT,
            tenant_id="test-tenant",
        )

        # Verify exists
        context = await env.get_context(context_id)
        assert context is not None, "Context should exist before delete"

        # Delete
        deleted = await env.delete_context(context_id)
        assert deleted is True, "Delete should return True"
        result.add_pass("deletes context successfully")

        # Verify gone
        context = await env.get_context(context_id)
        assert context is None, "Context should be None after delete"
        result.add_pass("context no longer retrievable after delete")

    except AssertionError as e:
        result.add_fail("delete_context", str(e))
    finally:
        await env.shutdown()


async def test_statistics():
    """Test environment statistics."""
    print("\n🧪 Testing Statistics...")

    env = RLMEnvironment()
    await env.initialize()

    try:
        # Store some content
        await env.store_context(content=SAMPLE_CONTENT, tenant_id="test-tenant")
        await env.store_context(content="Another document", tenant_id="test-tenant")

        stats = await env.get_stats()

        assert stats["storage_mode"] == "ram", "Should be RAM mode"
        assert stats["context_count"] == 2, f"Should have 2 contexts, got {stats['context_count']}"
        assert stats["memory_entries"] > 0, "Should have memory entries"
        assert stats["estimated_memory_mb"] > 0, "Should estimate memory usage"
        result.add_pass("returns accurate statistics")

    except AssertionError as e:
        result.add_fail("statistics", str(e))
    finally:
        await env.shutdown()


async def test_performance():
    """Test RAM performance characteristics."""
    print("\n🧪 Testing Performance...")

    env = RLMEnvironment()
    await env.initialize()

    try:
        start = time.perf_counter()

        # Perform 100 store + retrieve operations
        for i in range(100):
            context_id = await env.store_context(
                content=f"Test content {i}" * 100,
                tenant_id="test-tenant",
            )
            await env.get_context(context_id)

        elapsed = time.perf_counter() - start

        assert elapsed < 1.0, f"100 operations took {elapsed:.2f}s, expected < 1s"
        result.add_pass(f"100 store+retrieve operations in {elapsed*1000:.1f}ms")

        # Average time per operation
        avg_ms = (elapsed / 200) * 1000
        result.add_pass(f"average {avg_ms:.3f}ms per operation")

    except AssertionError as e:
        result.add_fail("performance", str(e))
    finally:
        await env.shutdown()


async def test_concurrent_operations():
    """Test concurrent read/write operations."""
    print("\n🧪 Testing Concurrent Operations...")

    env = RLMEnvironment()
    await env.initialize()

    try:
        async def write_context(i):
            return await env.store_context(
                content=f"Content for context {i}",
                tenant_id="test-tenant",
            )

        # Create 50 concurrent writes
        tasks = [write_context(i) for i in range(50)]
        context_ids = await asyncio.gather(*tasks)

        assert len(context_ids) == 50, "Should create 50 contexts"
        assert len(set(context_ids)) == 50, "All context IDs should be unique"
        result.add_pass("handles 50 concurrent writes")

        stats = await env.get_stats()
        assert stats["context_count"] == 50, f"Should have 50 contexts, got {stats['context_count']}"
        result.add_pass("all contexts stored correctly")

    except AssertionError as e:
        result.add_fail("concurrent_operations", str(e))
    finally:
        await env.shutdown()


async def test_ttl_expiration():
    """Test TTL expiration."""
    print("\n🧪 Testing TTL Expiration...")

    env = RLMEnvironment()
    await env.initialize()

    try:
        # Store with 1 second TTL
        context_id = await env.store_context(
            content=SAMPLE_CONTENT,
            tenant_id="test-tenant",
            ttl=1,
        )

        # Should exist immediately
        context = await env.get_context(context_id)
        assert context is not None, "Should exist before TTL"
        result.add_pass("context exists before TTL expires")

        # Wait for expiration
        await asyncio.sleep(1.5)

        # Should be expired
        context = await env.get_context(context_id)
        assert context is None, "Should be None after TTL expires"
        result.add_pass("context expires after TTL")

    except AssertionError as e:
        result.add_fail("ttl_expiration", str(e))
    finally:
        await env.shutdown()


async def main():
    """Run all tests."""
    print("=" * 60)
    print("RLM Environment Tests")
    print("=" * 60)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    try:
        await test_initialization()
        await test_store_and_retrieve()
        await test_ram_storage_no_serialization()
        await test_section_access()
        await test_result_caching()
        await test_section_index()
        await test_delete_context()
        await test_statistics()
        await test_performance()
        await test_concurrent_operations()
        await test_ttl_expiration()

    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        result.add_fail("unexpected", str(e))

    success = result.summary()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
