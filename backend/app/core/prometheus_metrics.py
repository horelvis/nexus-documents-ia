"""
Prometheus metrics integration for NexusDocs360
"""
import time
from typing import Dict, Any, Optional
try:
    from prometheus_client import (
        Counter, Histogram, Gauge, Summary,
        generate_latest, CONTENT_TYPE_LATEST
    )
    from prometheus_client.core import CollectorRegistry
    PROMETHEUS_AVAILABLE = True
except ImportError:
    # Fallback when prometheus_client is not available
    PROMETHEUS_AVAILABLE = False

    class Counter:
        def __init__(self, *args, **kwargs):
            pass
        def inc(self, *args, **kwargs):
            pass
        def labels(self, *args, **kwargs):
            return self

    class Histogram:
        def __init__(self, *args, **kwargs):
            pass
        def observe(self, *args, **kwargs):
            pass
        def labels(self, *args, **kwargs):
            return self

    class Gauge:
        def __init__(self, *args, **kwargs):
            pass
        def set(self, *args, **kwargs):
            pass
        def inc(self, *args, **kwargs):
            pass
        def dec(self, *args, **kwargs):
            pass

    class Summary:
        def __init__(self, *args, **kwargs):
            pass
        def observe(self, *args, **kwargs):
            pass

    def generate_latest(*args, **kwargs):
        return b""

    CONTENT_TYPE_LATEST = "text/plain; version=0.0.4; charset=utf-8"

    class CollectorRegistry:
        pass
from fastapi import Response
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)

# Create custom registry for our metrics
registry = CollectorRegistry()

# ===========================================
# HTTP REQUEST METRICS
# ===========================================

# HTTP request counter
http_requests_total = Counter(
    'nexus_http_requests_total',
    'Total number of HTTP requests',
    ['method', 'endpoint', 'status_code', 'tenant_id'],
    registry=registry
)

# HTTP request duration histogram
http_request_duration_seconds = Histogram(
    'nexus_http_request_duration_seconds',
    'HTTP request duration in seconds',
    ['method', 'endpoint', 'status_code'],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
    registry=registry
)

# HTTP response size histogram
http_response_size_bytes = Histogram(
    'nexus_http_response_size_bytes',
    'HTTP response size in bytes',
    ['method', 'endpoint', 'status_code'],
    buckets=[100, 1000, 10000, 100000, 1000000],
    registry=registry
)

# ===========================================
# DATABASE METRICS
# ===========================================

# Database connection pool metrics
db_connections_active = Gauge(
    'nexus_db_connections_active',
    'Number of active database connections',
    registry=registry
)

db_connections_idle = Gauge(
    'nexus_db_connections_idle',
    'Number of idle database connections',
    registry=registry
)

# Database query metrics
db_query_duration_seconds = Histogram(
    'nexus_db_query_duration_seconds',
    'Database query duration in seconds',
    ['query_type', 'table'],
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 5.0],
    registry=registry
)

db_query_errors_total = Counter(
    'nexus_db_query_errors_total',
    'Total number of database query errors',
    ['query_type', 'error_type'],
    registry=registry
)

# ===========================================
# CACHE METRICS
# ===========================================

# Cache hit/miss counters
cache_operations_total = Counter(
    'nexus_cache_operations_total',
    'Total number of cache operations',
    ['operation', 'result', 'cache_type'],
    registry=registry
)

# Cache size gauge
cache_size_items = Gauge(
    'nexus_cache_size_items',
    'Number of items in cache',
    ['cache_type'],
    registry=registry
)

# Cache hit rate gauge
cache_hit_rate = Gauge(
    'nexus_cache_hit_rate',
    'Cache hit rate percentage',
    ['cache_type'],
    registry=registry
)

# ===========================================
# BUSINESS METRICS
# ===========================================

# Document operations
document_operations_total = Counter(
    'nexus_document_operations_total',
    'Total number of document operations',
    ['operation', 'tenant_id', 'file_type'],
    registry=registry
)

# User activity
user_sessions_active = Gauge(
    'nexus_user_sessions_active',
    'Number of active user sessions',
    registry=registry
)

# Search operations
search_operations_total = Counter(
    'nexus_search_operations_total',
    'Total number of search operations',
    ['search_type', 'result_count'],
    registry=registry
)

# ===========================================
# SYSTEM METRICS
# ===========================================

# Memory usage
memory_usage_bytes = Gauge(
    'nexus_memory_usage_bytes',
    'Memory usage in bytes',
    ['type'],  # heap, rss, etc.
    registry=registry
)

# CPU usage
cpu_usage_percent = Gauge(
    'nexus_cpu_usage_percent',
    'CPU usage percentage',
    registry=registry
)

# Disk usage
disk_usage_bytes = Gauge(
    'nexus_disk_usage_bytes',
    'Disk usage in bytes',
    ['mount_point'],
    registry=registry
)

# ===========================================
# BUSINESS KPIs
# ===========================================

# Tenant metrics
tenant_count = Gauge(
    'nexus_tenant_count',
    'Total number of tenants',
    registry=registry
)

# Document metrics
document_count_total = Gauge(
    'nexus_document_count_total',
    'Total number of documents',
    ['tenant_id', 'status'],
    registry=registry
)

# User metrics
user_count_total = Gauge(
    'nexus_user_count_total',
    'Total number of users',
    ['tenant_id', 'status'],
    registry=registry
)

# ===========================================
# ERROR METRICS
# ===========================================

# Application errors
application_errors_total = Counter(
    'nexus_application_errors_total',
    'Total number of application errors',
    ['error_type', 'endpoint', 'severity'],
    registry=registry
)

# External service errors
external_service_errors_total = Counter(
    'nexus_external_service_errors_total',
    'Total number of external service errors',
    ['service_name', 'error_type'],
    registry=registry
)

# ===========================================
# PERFORMANCE ALERTS
# ===========================================

# Slow request alerts
slow_requests_total = Counter(
    'nexus_slow_requests_total',
    'Total number of slow requests (>5s)',
    ['method', 'endpoint'],
    registry=registry
)

# High memory usage alerts
high_memory_usage = Gauge(
    'nexus_high_memory_usage',
    'High memory usage indicator (1 if high, 0 if normal)',
    registry=registry
)

# Database connection issues
db_connection_errors_total = Counter(
    'nexus_db_connection_errors_total',
    'Total number of database connection errors',
    registry=registry
)


class MetricsMiddleware:
    """Middleware to collect HTTP metrics"""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Extract request info
        method = scope.get("method", "UNKNOWN")
        path = scope.get("path", "/")

        # Skip metrics endpoint to avoid recursion
        if path == "/metrics":
            await self.app(scope, receive, send)
            return

        start_time = time.time()

        # Track response
        response_status = [200]  # Use list to modify in nested function
        response_size = [0]

        async def metrics_send(message):
            if message["type"] == "http.response.start":
                response_status[0] = message.get("status", 200)

            elif message["type"] == "http.response.body":
                body = message.get("body", b"")
                response_size[0] = len(body)

            await send(message)

        # Process request
        try:
            await self.app(scope, receive, metrics_send)
        except Exception as e:
            # Track error
            application_errors_total.labels(
                error_type=type(e).__name__,
                endpoint=path,
                severity="error"
            ).inc()
            raise
        finally:
            # Record metrics
            duration = time.time() - start_time

            # HTTP metrics
            http_requests_total.labels(
                method=method,
                endpoint=path,
                status_code=str(response_status[0]),
                tenant_id="unknown"  # TODO: Extract from request headers
            ).inc()

            http_request_duration_seconds.labels(
                method=method,
                endpoint=path,
                status_code=str(response_status[0])
            ).observe(duration)

            http_response_size_bytes.labels(
                method=method,
                endpoint=path,
                status_code=str(response_status[0])
            ).observe(response_size[0])

            # Slow request alert
            if duration > 5.0:
                slow_requests_total.labels(
                    method=method,
                    endpoint=path
                ).inc()


def get_metrics_response() -> Response:
    """Get Prometheus metrics as HTTP response"""
    try:
        metrics_data = generate_latest(registry)
        return Response(
            content=metrics_data,
            media_type=CONTENT_TYPE_LATEST
        )
    except Exception as e:
        logger.error(f"Error generating metrics: {str(e)}")
        return Response(
            content="# Error generating metrics\n",
            media_type=CONTENT_TYPE_LATEST,
            status_code=500
        )


def update_system_metrics():
    """Update system-level metrics"""
    try:
        import psutil
        import os

        # Memory metrics
        process = psutil.Process(os.getpid())
        memory_info = process.memory_info()

        memory_usage_bytes.labels(type="rss").set(memory_info.rss)
        memory_usage_bytes.labels(type="vms").set(memory_info.vms)

        # CPU metrics
        cpu_percent = process.cpu_percent(interval=1.0)
        cpu_usage_percent.set(cpu_percent)

        # Disk metrics
        disk_usage = psutil.disk_usage('/')
        disk_usage_bytes.labels(mount_point="/").set(disk_usage.used)

        # High memory alert
        memory_mb = memory_info.rss / (1024 * 1024)
        high_memory_usage.set(1 if memory_mb > 500 else 0)  # Alert if > 500MB

    except ImportError:
        logger.warning("psutil not available, skipping system metrics")
    except Exception as e:
        logger.error(f"Error updating system metrics: {str(e)}")


def update_business_metrics():
    """Update business-level metrics"""
    try:
        from app.db.database import engine
        from sqlalchemy import text

        with engine.connect() as conn:
            # Tenant count
            result = conn.execute(text("SELECT COUNT(*) FROM tenants"))
            tenant_count_val = result.fetchone()[0]
            tenant_count.set(tenant_count_val)

            # User count by status
            result = conn.execute(text("SELECT COUNT(*) FROM users WHERE is_active = true"))
            users_active = result.fetchone()[0]

            result = conn.execute(text("SELECT COUNT(*) FROM users WHERE is_active = false"))
            users_inactive = result.fetchone()[0]

            user_count_total.labels(tenant_id="all", status="active").set(users_active)
            user_count_total.labels(tenant_id="all", status="inactive").set(users_inactive)

            # Document count by status
            result = conn.execute(text("SELECT COUNT(*) FROM documents WHERE indexed = 1"))
            docs_indexed = result.fetchone()[0]

            result = conn.execute(text("SELECT COUNT(*) FROM documents WHERE indexed = 0"))
            docs_not_indexed = result.fetchone()[0]

            document_count_total.labels(tenant_id="all", status="indexed").set(docs_indexed)
            document_count_total.labels(tenant_id="all", status="not_indexed").set(docs_not_indexed)

    except Exception as e:
        logger.error(f"Error updating business metrics: {str(e)}")


def update_cache_metrics():
    """Update cache-related metrics"""
    try:
        from app.core.cache import cache

        stats = cache.get_stats()

        # Redis cache metrics
        redis_stats = stats.get('redis', {})
        if redis_stats:
            cache_operations_total.labels(
                operation="get",
                result="hit",
                cache_type="redis"
            )._value = redis_stats.get('hits', 0)

            cache_operations_total.labels(
                operation="get",
                result="miss",
                cache_type="redis"
            )._value = redis_stats.get('misses', 0)

            # Cache size
            cache_size_items.labels(cache_type="redis").set(
                redis_stats.get('cache_size', 0)
            )

        # Memory cache metrics
        memory_stats = stats.get('memory', {})
        if memory_stats:
            cache_size_items.labels(cache_type="memory").set(
                memory_stats.get('cache_size', 0)
            )

        # Combined hit rate
        combined_hit_rate = stats.get('combined_hit_rate', 0)
        cache_hit_rate.labels(cache_type="combined").set(combined_hit_rate)

    except Exception as e:
        logger.error(f"Error updating cache metrics: {str(e)}")


def update_database_metrics():
    """Update database-related metrics"""
    try:
        from app.db.database import get_connection_stats

        stats = get_connection_stats()

        db_connections_active.set(stats.get('checkedout', 0))
        db_connections_idle.set(stats.get('checkedin', 0))

    except Exception as e:
        logger.error(f"Error updating database metrics: {str(e)}")


def collect_all_metrics():
    """Collect all metrics"""
    update_system_metrics()
    update_business_metrics()
    update_cache_metrics()
    update_database_metrics()


# Initialize metrics collection
def start_metrics_collection():
    """Start background metrics collection"""
    import threading

    def metrics_collector():
        while True:
            try:
                collect_all_metrics()
            except Exception as e:
                logger.error(f"Error in metrics collection: {str(e)}")
            time.sleep(60)  # Collect every 60 seconds to reduce database load

    thread = threading.Thread(target=metrics_collector, daemon=True)
    thread.start()
    logger.info("Started background metrics collection (60s interval)")