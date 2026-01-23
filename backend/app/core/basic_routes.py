"""
Basic application routes (health, cors test, etc.)
"""
from typing import Dict, Any

from fastapi import APIRouter, Request

from app.core.config import settings
from app.core.metrics import get_performance_report, get_metrics_summary
from app.core.prometheus_metrics import get_metrics_response
from app.core.health_checks import get_health_status, run_health_checks
from app.core.alerting import get_active_alerts, get_alert_history, acknowledge_alert

# Create router for basic endpoints
basic_router = APIRouter()


@basic_router.get("/health", tags=["health"])
async def health_check() -> Dict[str, Any]:
    """Basic health check endpoint"""
    return {"status": "healthy", "version": "1.0.0"}


@basic_router.get("/health/detailed", tags=["health"])
async def detailed_health_check() -> Dict[str, Any]:
    """Detailed health check with all components"""
    return get_health_status()


@basic_router.get("/health/live", tags=["health"])
async def liveness_check() -> Dict[str, Any]:
    """Kubernetes liveness probe - checks if app is running"""
    return {
        "status": "alive",
        "timestamp": "2024-01-01T00:00:00Z",  # Would be dynamic
        "service": "nouxcubeia"
    }


@basic_router.get("/health/ready", tags=["health"])
async def readiness_check() -> Dict[str, Any]:
    """Kubernetes readiness probe - checks if app is ready to serve traffic"""
    health_status = get_health_status()

    # App is ready if overall status is healthy or degraded (but not unhealthy)
    is_ready = health_status['status'] in ['healthy', 'degraded']

    return {
        "status": "ready" if is_ready else "not_ready",
        "overall_health": health_status['status'],
        "timestamp": health_status['timestamp'],
        "checks_summary": health_status['summary']
    }


@basic_router.post("/health/run-checks", tags=["health"])
async def trigger_health_checks() -> Dict[str, Any]:
    """Manually trigger all health checks"""
    results = await run_health_checks()
    return {
        "message": "Health checks completed",
        "results": {name: result.to_dict() for name, result in results.items()}
    }


@basic_router.get("/alerts/active", tags=["monitoring"])
async def get_active_alerts_endpoint() -> Dict[str, Any]:
    """Get all active alerts"""
    alerts = get_active_alerts()
    return {
        "alerts": [alert.to_dict() for alert in alerts],
        "count": len(alerts)
    }


@basic_router.get("/alerts/history", tags=["monitoring"])
async def get_alert_history_endpoint(hours: int = 24) -> Dict[str, Any]:
    """Get alert history for the last N hours"""
    alerts = get_alert_history(hours)
    return {
        "alerts": [alert.to_dict() for alert in alerts],
        "count": len(alerts),
        "hours": hours
    }


@basic_router.post("/alerts/{alert_name}/acknowledge", tags=["monitoring"])
async def acknowledge_alert_endpoint(alert_name: str, user_id: str = "system") -> Dict[str, Any]:
    """Acknowledge an alert"""
    success = acknowledge_alert(alert_name, user_id)
    return {
        "success": success,
        "message": f"Alert '{alert_name}' acknowledged" if success else f"Alert '{alert_name}' not found or not active"
    }


@basic_router.get("/cors-test", tags=["health"])
async def cors_test(request: Request) -> Dict[str, Any]:
    """Test CORS configuration"""
    return {
        "status": "ok",
        "origin": request.headers.get("origin"),
        "method": request.method,
        "cors_configured": len(settings.BACKEND_CORS_ORIGINS) > 0,
        "allowed_origins": [str(origin) for origin in settings.BACKEND_CORS_ORIGINS]
    }


@basic_router.get("/direct-auth-test", tags=["debug"])
async def direct_auth_test() -> Dict[str, str]:
    """Direct auth test endpoint"""
    return {"status": "direct_endpoint_working", "message": "This endpoint works without router"}


@basic_router.get("/test-connection", tags=["health"])
async def test_connection(request: Request) -> Dict[str, Any]:
    """Test connection and headers"""
    client_ip = request.client.host if request.client else "unknown"
    headers = dict(request.headers)

    return {
        "status": "connected",
        "client_ip": client_ip,
        "headers": headers,
        "cors_origins": [str(origin) for origin in settings.BACKEND_CORS_ORIGINS],
        "api_prefix": settings.API_PREFIX,
        "server_host": str(settings.SERVER_HOST)
    }


@basic_router.get("/metrics", tags=["monitoring"])
async def get_metrics() -> Dict[str, Any]:
    """Get application performance metrics"""
    return get_metrics_summary()


@basic_router.get("/performance-report", tags=["monitoring"])
async def get_performance() -> Dict[str, Any]:
    """Get detailed performance report"""
    return get_performance_report()


@basic_router.get("/metrics", tags=["monitoring"])
async def prometheus_metrics():
    """Get Prometheus metrics"""
    return get_metrics_response()