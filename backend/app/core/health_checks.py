"""
Comprehensive health check system for NouxCubeIA
"""
import asyncio
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum

from app.core.config import settings
from app.core.structured_logging import structured_logger


class HealthStatus(Enum):
    """Health check status"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class HealthCheckResult:
    """Health check result"""
    name: str
    status: HealthStatus
    response_time: float
    message: str
    details: Optional[Dict[str, Any]] = None
    timestamp: Optional[datetime] = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'name': self.name,
            'status': self.status.value,
            'response_time': round(self.response_time, 3),
            'message': self.message,
            'details': self.details or {},
            'timestamp': self.timestamp.isoformat()
        }


class HealthChecker:
    """Base class for health checks"""

    def __init__(self, name: str, timeout: float = 5.0):
        self.name = name
        self.timeout = timeout

    async def check(self) -> HealthCheckResult:
        """Perform health check"""
        start_time = time.time()

        try:
            result = await asyncio.wait_for(
                self._check_impl(),
                timeout=self.timeout
            )
            response_time = time.time() - start_time
            # Create new HealthCheckResult with updated response_time
            return HealthCheckResult(
                name=result.name,
                status=result.status,
                response_time=response_time,
                message=result.message,
                details=result.details,
                timestamp=result.timestamp
            )

        except asyncio.TimeoutError:
            response_time = time.time() - start_time
            return HealthCheckResult(
                name=self.name,
                status=HealthStatus.UNHEALTHY,
                response_time=response_time,
                message=f"Health check timed out after {self.timeout}s"
            )

        except Exception as e:
            response_time = time.time() - start_time
            return HealthCheckResult(
                name=self.name,
                status=HealthStatus.UNHEALTHY,
                response_time=response_time,
                message=f"Health check failed: {str(e)}"
            )

    async def _check_impl(self) -> HealthCheckResult:
        """Implementation of health check"""
        raise NotImplementedError("Subclasses must implement _check_impl")


class DatabaseHealthCheck(HealthChecker):
    """Database health check"""

    async def _check_impl(self) -> HealthCheckResult:
        from app.db.database import engine, get_connection_stats

        try:
            # Use engine directly to avoid creating new sessions
            with engine.connect() as conn:
                # Test basic connectivity
                from sqlalchemy import text
                result = conn.execute(text("SELECT 1 as test"))
                row = result.fetchone()

                if row and row[0] == 1:
                    # Get connection stats
                    stats = get_connection_stats()

                    return HealthCheckResult(
                        name="database",
                        status=HealthStatus.HEALTHY,
                        response_time=0,  # Will be set by parent
                        message="Database connection is healthy",
                        details={
                            'active_connections': stats.get('checkedout', 0),
                            'idle_connections': stats.get('checkedin', 0),
                            'connection_pool_size': stats.get('size', 0),
                            'overflow': stats.get('overflow', 0)
                        }
                    )
                else:
                    return HealthCheckResult(
                        name="database",
                        status=HealthStatus.UNHEALTHY,
                        response_time=0,
                        message="Database query returned unexpected result"
                    )

        except Exception as e:
            return HealthCheckResult(
                name="database",
                status=HealthStatus.UNHEALTHY,
                response_time=0,
                message=f"Database health check failed: {str(e)}"
            )


class RedisHealthCheck(HealthChecker):
    """Redis health check"""

    async def _check_impl(self) -> HealthCheckResult:
        try:
            from app.core.cache import cache

            if cache is None:
                return HealthCheckResult(
                    name="redis",
                    status=HealthStatus.UNHEALTHY,
                    response_time=0,
                    message="Redis cache not initialized"
                )

            # Test basic connectivity (cache is synchronous)
            result = cache.get("health_check_test")
            if result is None:
                # Set a test value
                cache.set("health_check_test", "ok", ttl=10)
                result = cache.get("health_check_test")

            if result == "ok":
                # Get cache stats
                stats = cache.get_stats()

                return HealthCheckResult(
                    name="redis",
                    status=HealthStatus.HEALTHY,
                    response_time=0,
                    message="Redis connection is healthy",
                    details={
                        'connected': stats.get('redis', {}).get('connected', False),
                        'cache_size': stats.get('memory', {}).get('cache_size', 0),
                        'hit_rate': stats.get('combined_hit_rate', 0)
                    }
                )
            else:
                return HealthCheckResult(
                    name="redis",
                    status=HealthStatus.UNHEALTHY,
                    response_time=0,
                    message="Redis health check returned unexpected result"
                )

        except Exception as e:
            return HealthCheckResult(
                name="redis",
                status=HealthStatus.UNHEALTHY,
                response_time=0,
                message=f"Redis health check failed: {str(e)}"
            )


class ExternalServiceHealthCheck(HealthChecker):
    """External service health check"""

    def __init__(self, name: str, url: str, expected_status: int = 200, timeout: float = 5.0):
        super().__init__(name, timeout)
        self.url = url
        self.expected_status = expected_status

    async def _check_impl(self) -> HealthCheckResult:
        import aiohttp

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.url, timeout=aiohttp.ClientTimeout(total=self.timeout)) as response:
                    if response.status == self.expected_status:
                        return HealthCheckResult(
                            name=self.name,
                            status=HealthStatus.HEALTHY,
                            response_time=0,
                            message=f"{self.name} is responding correctly",
                            details={
                                'status_code': response.status,
                                'response_time': response.headers.get('X-Response-Time'),
                                'url': self.url
                            }
                        )
                    else:
                        return HealthCheckResult(
                            name=self.name,
                            status=HealthStatus.UNHEALTHY,
                            response_time=0,
                            message=f"{self.name} returned status {response.status}, expected {self.expected_status}",
                            details={'status_code': response.status, 'url': self.url}
                        )

        except aiohttp.ClientError as e:
            return HealthCheckResult(
                name=self.name,
                status=HealthStatus.UNHEALTHY,
                response_time=0,
                message=f"{self.name} connection failed: {str(e)}",
                details={'url': self.url, 'error': str(e)}
            )


class SystemHealthCheck(HealthChecker):
    """System resources health check"""

    async def _check_impl(self) -> HealthCheckResult:
        try:
            import psutil

            # Get system metrics
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')

            # Check thresholds
            issues = []

            if cpu_percent > 90:
                issues.append(f"High CPU usage: {cpu_percent}%")
            if memory.percent > 90:
                issues.append(f"High memory usage: {memory.percent}%")
            if disk.percent > 95:
                issues.append(f"Low disk space: {disk.percent}% free")

            status = HealthStatus.HEALTHY if not issues else HealthStatus.DEGRADED
            if len(issues) > 2:
                status = HealthStatus.UNHEALTHY

            return HealthCheckResult(
                name="system",
                status=status,
                response_time=0,
                message="System resources check completed" if not issues else f"Issues found: {', '.join(issues)}",
                details={
                    'cpu_percent': cpu_percent,
                    'memory_percent': memory.percent,
                    'memory_used_mb': memory.used // (1024 * 1024),
                    'memory_total_mb': memory.total // (1024 * 1024),
                    'disk_percent': disk.percent,
                    'disk_free_gb': disk.free // (1024 * 1024 * 1024),
                    'issues': issues
                }
            )

        except ImportError:
            return HealthCheckResult(
                name="system",
                status=HealthStatus.DEGRADED,
                response_time=0,
                message="psutil not available for system monitoring",
                details={'warning': 'System monitoring limited without psutil'}
            )
        except Exception as e:
            return HealthCheckResult(
                name="system",
                status=HealthStatus.UNHEALTHY,
                response_time=0,
                message=f"System health check failed: {str(e)}"
            )


class StorageServiceHealthCheck(HealthChecker):
    """Storage Service health check"""

    async def _check_impl(self) -> HealthCheckResult:
        try:
            from app.services.async_storage_client import AsyncStorageClient

            # Create client with minimal context (health check doesn't need tenant)
            client = AsyncStorageClient(tenant_id="health-check")
            result = await client.health_check()

            if result.get("status") == "healthy":
                return HealthCheckResult(
                    name="storage",
                    status=HealthStatus.HEALTHY,
                    response_time=0,
                    message="Storage service is healthy",
                    details=result
                )
            else:
                return HealthCheckResult(
                    name="storage",
                    status=HealthStatus.UNHEALTHY,
                    response_time=0,
                    message=f"Storage service unhealthy: {result.get('error', 'Unknown')}",
                    details=result
                )

        except Exception as e:
            return HealthCheckResult(
                name="storage",
                status=HealthStatus.UNHEALTHY,
                response_time=0,
                message=f"Storage service health check failed: {str(e)}"
            )


class ApplicationHealthCheck(HealthChecker):
    """Application-specific health check"""

    async def _check_impl(self) -> HealthCheckResult:
        try:
            from app.core.metrics import get_metrics_summary
            from app.core.alerting import get_active_alerts

            metrics = get_metrics_summary()
            active_alerts = get_active_alerts()

            # Check for critical metrics
            issues = []

            # Check error rates
            counters = metrics.get('counters', {})
            total_requests = sum([
                counters.get(f'http_requests_total{{status_class={code}xx}}', 0)
                for code in ['2', '3', '4', '5']
            ])
            error_requests = counters.get('http_requests_total{status_class=5xx}', 0)

            if total_requests > 0:
                error_rate = error_requests / total_requests
                if error_rate > 0.1:  # 10% error rate
                    issues.append(f"High error rate: {error_rate:.1%}")

            # Check active alerts
            critical_alerts = [a for a in active_alerts if a.severity.name == 'CRITICAL']
            if critical_alerts:
                issues.append(f"{len(critical_alerts)} critical alerts active")

            # Determine status
            status = HealthStatus.HEALTHY
            if issues:
                status = HealthStatus.DEGRADED
            if len(issues) > 3 or critical_alerts:
                status = HealthStatus.UNHEALTHY

            return HealthCheckResult(
                name="application",
                status=status,
                response_time=0,
                message="Application health check completed" if not issues else f"Issues found: {', '.join(issues)}",
                details={
                    'total_requests': total_requests,
                    'error_requests': error_requests,
                    'error_rate': error_rate if total_requests > 0 else 0,
                    'active_alerts': len(active_alerts),
                    'critical_alerts': len(critical_alerts),
                    'issues': issues
                }
            )

        except Exception as e:
            return HealthCheckResult(
                name="application",
                status=HealthStatus.UNHEALTHY,
                response_time=0,
                message=f"Application health check failed: {str(e)}"
            )


class HealthCheckManager:
    """Manager for all health checks"""

    def __init__(self):
        self.checks: List[HealthChecker] = []
        self.last_results: Dict[str, HealthCheckResult] = {}
        self.check_interval = 30  # seconds

    def add_check(self, check: HealthChecker) -> None:
        """Add a health check"""
        self.checks.append(check)

    def add_default_checks(self) -> None:
        """Add default health checks"""
        # Database check
        self.add_check(DatabaseHealthCheck("database"))

        # Redis check
        self.add_check(RedisHealthCheck("redis"))

        # System check
        self.add_check(SystemHealthCheck("system"))

        # Application check
        self.add_check(ApplicationHealthCheck("application"))

        # Storage service check
        if hasattr(settings, 'STORAGE_SERVICE_URL') or hasattr(settings, 'STORAGE_SERVICE_INTERNAL_URL'):
            self.add_check(StorageServiceHealthCheck("storage"))

        # External service checks (if configured)
        if hasattr(settings, 'WEAVIATE_SERVICE_URL'):
            self.add_check(ExternalServiceHealthCheck(
                "weaviate",
                f"{settings.WEAVIATE_SERVICE_URL}/health"
            ))

        # Only check Elasticsearch if explicitly enabled (service was removed from architecture)
        if getattr(settings, 'ENABLE_ELASTICSEARCH', False):
            self.add_check(ExternalServiceHealthCheck(
                "elasticsearch",
                f"{settings.ELASTICSEARCH_URL}/_cluster/health"
            ))

    async def run_all_checks(self) -> Dict[str, HealthCheckResult]:
        """Run all health checks"""
        results = {}

        # Run checks concurrently
        tasks = [check.check() for check in self.checks]
        check_results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, result in enumerate(check_results):
            check_name = self.checks[i].name

            if isinstance(result, Exception):
                # Handle check failure
                results[check_name] = HealthCheckResult(
                    name=check_name,
                    status=HealthStatus.UNHEALTHY,
                    response_time=0,
                    message=f"Health check failed: {str(result)}"
                )
            else:
                results[check_name] = result

        # Update last results
        self.last_results.update(results)

        # Log results
        self._log_results(results)

        return results

    def _log_results(self, results: Dict[str, HealthCheckResult]) -> None:
        """Log health check results"""
        healthy = sum(1 for r in results.values() if r.status == HealthStatus.HEALTHY)
        degraded = sum(1 for r in results.values() if r.status == HealthStatus.DEGRADED)
        unhealthy = sum(1 for r in results.values() if r.status == HealthStatus.UNHEALTHY)

        structured_logger.info("Health check completed", {
            'event_type': 'health_check',
            'total_checks': len(results),
            'healthy': healthy,
            'degraded': degraded,
            'unhealthy': unhealthy,
            'results': {name: result.to_dict() for name, result in results.items()}
        })

        # Log individual unhealthy checks
        for name, result in results.items():
            if result.status == HealthStatus.UNHEALTHY:
                structured_logger.error(f"Health check failed: {name}", {
                    'event_type': 'health_check_failed',
                    'check_name': name,
                    'message': result.message,
                    'response_time': result.response_time
                })

    def get_overall_status(self, results: Optional[Dict[str, HealthCheckResult]] = None) -> HealthStatus:
        """Get overall health status"""
        if results is None:
            results = self.last_results

        if not results:
            return HealthStatus.UNHEALTHY

        # If any check is unhealthy, overall status is unhealthy
        if any(r.status == HealthStatus.UNHEALTHY for r in results.values()):
            return HealthStatus.UNHEALTHY

        # If any check is degraded, overall status is degraded
        if any(r.status == HealthStatus.DEGRADED for r in results.values()):
            return HealthStatus.DEGRADED

        # All checks are healthy
        return HealthStatus.HEALTHY

    def get_detailed_report(self) -> Dict[str, Any]:
        """Get detailed health report"""
        results = self.last_results
        overall_status = self.get_overall_status(results)

        return {
            'status': overall_status.value,
            'timestamp': datetime.utcnow().isoformat(),
            'checks': {name: result.to_dict() for name, result in results.items()},
            'summary': {
                'total': len(results),
                'healthy': sum(1 for r in results.values() if r.status == HealthStatus.HEALTHY),
                'degraded': sum(1 for r in results.values() if r.status == HealthStatus.DEGRADED),
                'unhealthy': sum(1 for r in results.values() if r.status == HealthStatus.UNHEALTHY)
            }
        }


# Global health check manager
health_manager = HealthCheckManager()

# Initialize default checks
def initialize_health_checks():
    """Initialize health check system"""
    health_manager.add_default_checks()
    # Increase check interval to reduce database load
    health_manager.check_interval = 60  # Check every 60 seconds instead of 30
    structured_logger.info("Health check system initialized", {
        'event_type': 'system_init',
        'component': 'health_checks',
        'checks_count': len(health_manager.checks),
        'check_interval_seconds': health_manager.check_interval
    })


# Background health check runner
async def start_health_check_monitoring():
    """Start background health check monitoring"""
    while True:
        try:
            await health_manager.run_all_checks()
        except Exception as e:
            structured_logger.error(f"Error running health checks: {str(e)}")

        await asyncio.sleep(health_manager.check_interval)


# Convenience functions
async def run_health_checks() -> Dict[str, HealthCheckResult]:
    """Run all health checks"""
    return await health_manager.run_all_checks()

def get_health_status() -> Dict[str, Any]:
    """Get current health status"""
    return health_manager.get_detailed_report()

def get_overall_health_status() -> str:
    """Get overall health status as string"""
    return health_manager.get_overall_status().value