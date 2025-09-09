#!/usr/bin/env python3
"""
Performance testing script for NexusDocs360 optimizations
"""
import asyncio
import time
import logging
from concurrent.futures import ThreadPoolExecutor
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.config import settings
from app.core.logging import setup_logging
from app.core.cache import cache, log_cache_performance
from app.core.metrics import get_performance_report
from app.core.async_optimizer import AsyncOptimizer
from app.db.database import get_db_context

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)


async def test_cache_performance():
    """Test cache performance with various operations"""
    print("🔄 Testing Cache Performance...")

    # Test basic cache operations
    start_time = time.time()

    # Set some test data
    for i in range(100):
        await cache.set(f"test_key_{i}", f"test_value_{i}", ttl=300)

    set_time = time.time() - start_time

    # Test cache retrieval
    start_time = time.time()
    hits = 0
    misses = 0

    for i in range(100):
        result = await cache.get(f"test_key_{i}")
        if result:
            hits += 1
        else:
            misses += 1

    get_time = time.time() - start_time

    print(".3f"    print(f"  Cache Hits: {hits}, Misses: {misses}")
    print(".1f"
    return {"set_time": set_time, "get_time": get_time, "hits": hits, "misses": misses}


async def test_async_operations():
    """Test async operation optimizations"""
    print("🔄 Testing Async Operations...")

    async with AsyncOptimizer() as optimizer:
        # Test parallel HTTP requests (simulated)
        urls = [f"http://httpbin.org/delay/0.{i}" for i in range(1, 6)]

        start_time = time.time()
        results = await optimizer.parallel_http_requests(urls[:3])  # Test with 3 URLs
        parallel_time = time.time() - start_time

        # Test sequential for comparison
        start_time = time.time()
        sequential_results = []
        for url in urls[:3]:
            try:
                result = await optimizer.http_get(url.replace("delay", "get"))
                sequential_results.append(result)
            except:
                sequential_results.append({"error": "failed"})
        sequential_time = time.time() - start_time

        print(".3f"        print(".3f"        print(".2f"
        return {
            "parallel_time": parallel_time,
            "sequential_time": sequential_time,
            "speedup": sequential_time / parallel_time if parallel_time > 0 else 0
        }


async def test_database_performance():
    """Test database query performance"""
    print("🔄 Testing Database Performance...")

    with get_db_context() as db:
        from app.services.query_optimizer import QueryOptimizer
        from app.core.metrics import performance_monitor

        optimizer = QueryOptimizer(db)

        # Test tenant stats query
        start_time = time.time()
        stats = optimizer.get_tenant_stats_optimized(settings.DEFAULT_TENANT)
        query_time = time.time() - start_time

        print(".3f"        print(f"  Documents: {stats.get('document_count', 0)}")
        print(f"  Users: {stats.get('user_count', 0)}")

        return {"query_time": query_time, "stats": stats}


async def test_compression_performance():
    """Test response compression performance"""
    print("🔄 Testing Compression Performance...")

    from app.core.compression import compress_response_data, estimate_compression_ratio

    # Test with different types of content
    test_data = {
        "json": '{"users": [' + ','.join([f'{{"id": {i}, "name": "User {i}"}}' for i in range(1000)]) + ']}',
        "html": "<html>" + "<div>Content</div>" * 1000 + "</html>",
        "text": "This is a test document. " * 1000
    }

    results = {}

    for content_type, content in test_data.items():
        original_size = len(content.encode('utf-8'))

        start_time = time.time()
        compressed = compress_response_data(content.encode('utf-8'))
        compression_time = time.time() - start_time

        compressed_size = len(compressed)
        ratio = (original_size - compressed_size) / original_size * 100

        print(f"  {content_type.upper()}:")
        print(f"    Original: {original_size} bytes")
        print(f"    Compressed: {compressed_size} bytes")
        print(".1f"        print(".4f"
        results[content_type] = {
            "original_size": original_size,
            "compressed_size": compressed_size,
            "ratio": ratio,
            "time": compression_time
        }

    return results


async def run_performance_tests():
    """Run all performance tests"""
    print("🚀 NexusDocs360 Performance Test Suite")
    print("=" * 50)

    results = {}

    try:
        # Test cache performance
        results["cache"] = await test_cache_performance()

        # Test async operations
        results["async"] = await test_async_operations()

        # Test database performance
        results["database"] = await test_database_performance()

        # Test compression
        results["compression"] = await test_compression_performance()

        # Get overall metrics
        print("
📊 Overall Performance Report:"        performance_report = get_performance_report()
        print(f"  Cache Hit Rate: {performance_report.get('summary', {}).get('histograms', {}).get('cache_operation_duration', {}).get('avg', 0):.1f}%")

        # Log cache performance
        print("
🔍 Cache Performance Details:"        log_cache_performance()

        print("
✅ All performance tests completed successfully!"        return results

    except Exception as e:
        logger.error(f"Performance test failed: {str(e)}")
        print(f"\n❌ Performance test failed: {str(e)}")
        return None


def generate_report(results):
    """Generate a performance report"""
    if not results:
        return

    report = f"""
# NexusDocs360 Performance Test Report

## Summary

### Cache Performance
- Set Time: {results['cache']['set_time']:.3f}s for 100 operations
- Get Time: {results['cache']['get_time']:.3f}s for 100 operations
- Hit Rate: {(results['cache']['hits'] / (results['cache']['hits'] + results['cache']['misses']) * 100):.1f}%

### Async Operations
- Parallel Time: {results['async']['parallel_time']:.3f}s
- Sequential Time: {results['async']['sequential_time']:.3f}s
- Speedup: {results['async']['speedup']:.2f}x

### Database Performance
- Query Time: {results['database']['query_time']:.3f}s
- Documents: {results['database']['stats'].get('document_count', 0)}
- Users: {results['database']['stats'].get('user_count', 0)}

### Compression Performance
"""

    for content_type, data in results['compression'].items():
        report += f"""
#### {content_type.upper()}
- Original Size: {data['original_size']} bytes
- Compressed Size: {data['compressed_size']} bytes
- Compression Ratio: {data['ratio']:.1f}%
- Compression Time: {data['time']:.4f}s
"""

    # Save report
    with open("performance_test_report.md", "w") as f:
        f.write(report)

    print("📄 Performance report saved to: performance_test_report.md")


if __name__ == "__main__":
    # Run performance tests
    results = asyncio.run(run_performance_tests())

    if results:
        generate_report(results)