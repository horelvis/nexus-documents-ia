"""
Application metrics and monitoring service
"""
import logging
import time
from collections import defaultdict, deque
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class MetricsCollector:
    """Collect and manage application performance metrics"""

    def __init__(self, max_history: int = 1000):
        self.max_history = max_history
        self.metrics = defaultdict(lambda: defaultdict(list))
        self.counters = defaultdict(int)
        self.timers = {}
        self.gauges = {}

    def increment_counter(self, name: str, value: int = 1, tags: Optional[Dict[str, str]] = None) -> None:
        """Increment a counter metric"""
        key = self._make_key(name, tags)
        self.counters[key] += value

    def set_gauge(self, name: str, value: float, tags: Optional[Dict[str, str]] = None) -> None:
        """Set a gauge metric"""
        key = self._make_key(name, tags)
        self.gauges[key] = value

    def start_timer(self, name: str, tags: Optional[Dict[str, str]] = None) -> str:
        """Start a timer and return timer ID"""
        timer_id = f"{name}_{time.time()}"
        key = self._make_key(name, tags)
        self.timers[timer_id] = {
            'start_time': time.time(),
            'key': key
        }
        return timer_id

    def stop_timer(self, timer_id: str) -> float:
        """Stop a timer and record the duration"""
        if timer_id not in self.timers:
            logger.warning(f"Timer {timer_id} not found")
            return 0.0

        timer_data = self.timers.pop(timer_id)
        duration = time.time() - timer_data['start_time']

        # Record the duration
        self._record_metric(timer_data['key'], duration)

        return duration

    def record_histogram(self, name: str, value: float, tags: Optional[Dict[str, str]] = None) -> None:
        """Record a histogram value"""
        key = self._make_key(name, tags)
        self._record_metric(key, value)

    def time_function(self, name: str, tags: Optional[Dict[str, str]] = None):
        """Decorator to time function execution"""
        def decorator(func):
            def wrapper(*args, **kwargs):
                timer_id = self.start_timer(name, tags)
                try:
                    result = func(*args, **kwargs)
                    return result
                finally:
                    self.stop_timer(timer_id)
            return wrapper
        return decorator

    def async_time_function(self, name: str, tags: Optional[Dict[str, str]] = None):
        """Decorator to time async function execution"""
        def decorator(func):
            async def wrapper(*args, **kwargs):
                timer_id = self.start_timer(name, tags)
                try:
                    result = await func(*args, **kwargs)
                    return result
                finally:
                    self.stop_timer(timer_id)
            return wrapper
        return decorator

    def _make_key(self, name: str, tags: Optional[Dict[str, str]] = None) -> str:
        """Create a metric key with tags"""
        if not tags:
            return name

        tag_str = ",".join([f"{k}={v}" for k, v in sorted(tags.items())])
        return f"{name}{{{tag_str}}}"

    def _record_metric(self, key: str, value: float) -> None:
        """Record a metric value"""
        metric_list = self.metrics[key]['values']
        metric_list.append({
            'value': value,
            'timestamp': datetime.now()
        })

        # Keep only recent values
        if len(metric_list) > self.max_history:
            metric_list.pop(0)

    def get_metrics_summary(self) -> Dict[str, Any]:
        """Get a summary of all metrics"""
        summary = {
            'counters': dict(self.counters),
            'gauges': dict(self.gauges),
            'histograms': {}
        }

        # Calculate histogram statistics
        for key, data in self.metrics.items():
            values = [item['value'] for item in data['values']]
            if values:
                summary['histograms'][key] = {
                    'count': len(values),
                    'min': min(values),
                    'max': max(values),
                    'avg': sum(values) / len(values),
                    'latest': values[-1] if values else None
                }

        return summary

    def get_recent_metrics(self, minutes: int = 5) -> Dict[str, Any]:
        """Get metrics from the last N minutes"""
        cutoff_time = datetime.now() - timedelta(minutes=minutes)
        recent_metrics = defaultdict(list)

        for key, data in self.metrics.items():
            recent_values = [
                item['value'] for item in data['values']
                if item['timestamp'] > cutoff_time
            ]
            if recent_values:
                recent_metrics[key] = recent_values

        return dict(recent_metrics)

    def reset_metrics(self) -> None:
        """Reset all metrics"""
        self.metrics.clear()
        self.counters.clear()
        self.timers.clear()
        self.gauges.clear()
        logger.info("All metrics have been reset")


class PerformanceMonitor:
    """Monitor application performance and detect bottlenecks"""

    def __init__(self, metrics_collector: MetricsCollector):
        self.metrics = metrics_collector
        self.slow_query_threshold = 1.0  # seconds
        self.high_memory_threshold = 100 * 1024 * 1024  # 100MB

    def monitor_database_query(self, query_name: str, execution_time: float) -> None:
        """Monitor database query performance"""
        self.metrics.record_histogram(
            'db_query_duration',
            execution_time,
            {'query': query_name}
        )

        if execution_time > self.slow_query_threshold:
            logger.warning(f"Slow database query detected: {query_name} took {execution_time:.2f}s")

    def monitor_cache_operation(self, operation: str, hit: bool, duration: float) -> None:
        """Monitor cache operation performance"""
        self.metrics.increment_counter(
            'cache_operations_total',
            tags={'operation': operation, 'result': 'hit' if hit else 'miss'}
        )

        self.metrics.record_histogram(
            'cache_operation_duration',
            duration,
            {'operation': operation}
        )

    def monitor_http_request(self, method: str, path: str, status_code: int,
                           duration: float, response_size: int) -> None:
        """Monitor HTTP request performance"""
        self.metrics.increment_counter(
            'http_requests_total',
            tags={
                'method': method,
                'status': str(status_code),
                'status_class': str(status_code // 100) + 'xx'
            }
        )

        self.metrics.record_histogram(
            'http_request_duration',
            duration,
            {'method': method, 'status': str(status_code)}
        )

        self.metrics.record_histogram(
            'http_response_size',
            response_size,
            {'method': method}
        )

    def monitor_memory_usage(self, memory_mb: float) -> None:
        """Monitor memory usage"""
        self.metrics.set_gauge('memory_usage_mb', memory_mb)

        if memory_mb > self.high_memory_threshold / (1024 * 1024):
            logger.warning(f"High memory usage detected: {memory_mb:.1f}MB")

    def get_performance_report(self) -> Dict[str, Any]:
        """Generate a performance report"""
        metrics_summary = self.metrics.get_metrics_summary()
        recent_metrics = self.metrics.get_recent_metrics(5)

        report = {
            'timestamp': datetime.now().isoformat(),
            'summary': metrics_summary,
            'recent_activity': recent_metrics,
            'alerts': self._generate_alerts(metrics_summary)
        }

        return report

    def _generate_alerts(self, metrics_summary: Dict[str, Any]) -> List[str]:
        """Generate performance alerts based on metrics"""
        alerts = []

        # Check for slow queries
        db_metrics = metrics_summary.get('histograms', {}).get('db_query_duration', {})
        if db_metrics.get('avg', 0) > self.slow_query_threshold:
            alerts.append(".2f"
        # Check for high error rates
        error_count = metrics_summary.get('counters', {}).get('http_requests_total{status_class=5xx}', 0)
        total_requests = sum([
            metrics_summary.get('counters', {}).get(f'http_requests_total{{status_class={code}xx}}', 0)
            for code in ['2', '3', '4', '5']
        ])

        if total_requests > 0:
            error_rate = error_count / total_requests
            if error_rate > 0.05:  # 5% error rate
                alerts.append(".1%")

        # Check cache hit rate
        cache_hits = metrics_summary.get('counters', {}).get('cache_operations_total{operation=get,result=hit}', 0)
        cache_misses = metrics_summary.get('counters', {}).get('cache_operations_total{operation=get,result=miss}', 0)

        if cache_hits + cache_misses > 0:
            hit_rate = cache_hits / (cache_hits + cache_misses)
            if hit_rate < 0.8:  # Less than 80% hit rate
                alerts.append(".1%")

        return alerts


# Global instances
metrics_collector = MetricsCollector()
performance_monitor = PerformanceMonitor(metrics_collector)


# Convenience functions
def increment_counter(name: str, value: int = 1, tags: Optional[Dict[str, str]] = None) -> None:
    """Increment a counter"""
    metrics_collector.increment_counter(name, value, tags)


def set_gauge(name: str, value: float, tags: Optional[Dict[str, str]] = None) -> None:
    """Set a gauge value"""
    metrics_collector.set_gauge(name, value, tags)


def record_histogram(name: str, value: float, tags: Optional[Dict[str, str]] = None) -> None:
    """Record a histogram value"""
    metrics_collector.record_histogram(name, value, tags)


def time_function(name: str, tags: Optional[Dict[str, str]] = None):
    """Decorator to time function execution"""
    return metrics_collector.time_function(name, tags)


def async_time_function(name: str, tags: Optional[Dict[str, str]] = None):
    """Decorator to time async function execution"""
    return metrics_collector.async_time_function(name, tags)


def get_metrics_summary() -> Dict[str, Any]:
    """Get metrics summary"""
    return metrics_collector.get_metrics_summary()


def get_performance_report() -> Dict[str, Any]:
    """Get performance report"""
    return performance_monitor.get_performance_report()