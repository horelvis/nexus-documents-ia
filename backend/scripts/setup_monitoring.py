#!/usr/bin/env python3
"""
Setup and test monitoring system for NouxCubeIA
"""
import asyncio
import json
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.config import settings
from app.core.logging import setup_logging
from app.core.health_checks import run_health_checks, get_health_status
from app.core.alerting import get_active_alerts, get_alert_history
from app.core.metrics import get_metrics_summary, get_performance_report
from app.core.structured_logging import structured_logger

# Setup logging
setup_logging()


async def test_monitoring_system():
    """Test all monitoring components"""
    print("🔍 Testing NouxCubeIA Monitoring System")
    print("=" * 50)

    results = {}

    try:
        # Test health checks
        print("🏥 Testing Health Checks...")
        health_results = await run_health_checks()
        health_status = get_health_status()

        results["health"] = {
            "results": {name: result.to_dict() for name, result in health_results.items()},
            "overall_status": health_status
        }

        print(f"  ✅ Health checks completed: {health_status['summary']['healthy']}/{health_status['summary']['total']} healthy")

        # Test metrics collection
        print("📊 Testing Metrics Collection...")
        metrics = get_metrics_summary()
        performance_report = get_performance_report()

        results["metrics"] = {
            "summary": metrics,
            "performance": performance_report
        }

        print(f"  ✅ Metrics collected: {len(metrics.get('counters', {}))} counters, {len(metrics.get('gauges', {}))} gauges")

        # Test alerting system
        print("🚨 Testing Alerting System...")
        active_alerts = get_active_alerts()
        alert_history = get_alert_history(hours=1)

        results["alerts"] = {
            "active": [alert.to_dict() for alert in active_alerts],
            "history": [alert.to_dict() for alert in alert_history]
        }

        print(f"  ✅ Alerting system: {len(active_alerts)} active alerts, {len(alert_history)} historical alerts")

        # Test structured logging
        print("📝 Testing Structured Logging...")
        structured_logger.info("Monitoring system test completed", {
            'event_type': 'monitoring_test',
            'component': 'setup_script',
            'test_results': {
                'health_checks': len(health_results),
                'metrics_collected': bool(metrics),
                'alerts_active': len(active_alerts)
            }
        })

        print("  ✅ Structured logging test completed")

        # Generate configuration summary
        print("
⚙️ Configuration Summary:"        config_summary = {
            "environment": "development" if settings.DEBUG else "production",
            "monitoring_enabled": True,
            "health_checks": len(health_results),
            "alert_rules": 5,  # Default rules
            "metrics_enabled": True,
            "structured_logging": True
        }

        results["configuration"] = config_summary

        print(f"  • Environment: {config_summary['environment']}")
        print(f"  • Health Checks: {config_summary['health_checks']}")
        print(f"  • Alert Rules: {config_summary['alert_rules']}")
        print(f"  • Metrics: {'Enabled' if config_summary['metrics_enabled'] else 'Disabled'}")
        print(f"  • Structured Logging: {'Enabled' if config_summary['structured_logging'] else 'Disabled'}")

        print("
✅ All monitoring systems tested successfully!"        return results

    except Exception as e:
        print(f"\n❌ Monitoring system test failed: {str(e)}")
        structured_logger.error("Monitoring system test failed", {
            'event_type': 'monitoring_test_failed',
            'error': str(e)
        })
        return None


def generate_monitoring_config():
    """Generate monitoring configuration files"""
    print("
📄 Generating Monitoring Configuration..."    # Prometheus configuration
    prometheus_config = f"""
# NouxCubeIA Prometheus Configuration
global:
  scrape_interval: 15s
  evaluation_interval: 15s

rule_files:
  # - "first_rules.yml"
  # - "second_rules.yml"

scrape_configs:
  - job_name: 'nouxcubeia'
    static_configs:
      - targets: ['localhost:{settings.SERVER_PORT or 8000}']
    metrics_path: '/metrics'
    scrape_interval: 30s

  - job_name: 'nouxcubeia-health'
    static_configs:
      - targets: ['localhost:{settings.SERVER_PORT or 8000}']
    metrics_path: '/health/detailed'
    scrape_interval: 60s
"""

    # Alert manager configuration
    alertmanager_config = """
# NouxCubeIA AlertManager Configuration
global:
  smtp_smarthost: 'localhost:587'
  smtp_from: 'alerts@nouxcubeia.com'

route:
  group_by: ['alertname']
  group_wait: 10s
  group_interval: 10s
  repeat_interval: 1h
  receiver: 'team'
  routes:
  - match:
      severity: critical
    receiver: 'team-critical'

receivers:
- name: 'team'
  email_configs:
  - to: 'team@nouxcubeia.com'
  slack_configs:
  - api_url: 'YOUR_SLACK_WEBHOOK_URL'
    channel: '#alerts'

- name: 'team-critical'
  email_configs:
  - to: 'team@nouxcubeia.com'
  slack_configs:
  - api_url: 'YOUR_SLACK_WEBHOOK_URL'
    channel: '#critical'
"""

    # Grafana dashboard configuration (JSON)
    grafana_dashboard = {
        "dashboard": {
            "title": "NouxCubeIA Monitoring",
            "tags": ["nouxcubeia", "monitoring"],
            "timezone": "browser",
            "panels": [
                {
                    "title": "HTTP Request Rate",
                    "type": "graph",
                    "targets": [{
                        "expr": "rate(nexus_http_requests_total[5m])",
                        "legendFormat": "{{method}} {{status_code}}"
                    }]
                },
                {
                    "title": "Response Time",
                    "type": "graph",
                    "targets": [{
                        "expr": "histogram_quantile(0.95, rate(nexus_http_request_duration_seconds_bucket[5m]))",
                        "legendFormat": "95th percentile"
                    }]
                },
                {
                    "title": "Error Rate",
                    "type": "graph",
                    "targets": [{
                        "expr": "rate(nexus_http_requests_total{status_code=~\"5..\"}[5m]) / rate(nexus_http_requests_total[5m]) * 100",
                        "legendFormat": "Error rate %"
                    }]
                }
            ]
        }
    }

    # Save configurations
    configs_dir = Path("monitoring-config")
    configs_dir.mkdir(exist_ok=True)

    with open(configs_dir / "prometheus.yml", "w") as f:
        f.write(prometheus_config)

    with open(configs_dir / "alertmanager.yml", "w") as f:
        f.write(alertmanager_config)

    with open(configs_dir / "grafana-dashboard.json", "w") as f:
        json.dump(grafana_dashboard, f, indent=2)

    print("  ✅ Configuration files generated in 'monitoring-config/' directory")
    print("     - prometheus.yml")
    print("     - alertmanager.yml")
    print("     - grafana-dashboard.json")


def print_monitoring_guide():
    """Print monitoring setup guide"""
    print("
📚 NouxCubeIA Monitoring Setup Guide"    print("=" * 50)

    print("
1. 📊 PROMETHEUS SETUP:"    print("   # Start Prometheus with generated config"    print("   ./prometheus --config.file=monitoring-config/prometheus.yml"    print("   # Access at: http://localhost:9090"

    print("
2. 🚨 ALERTMANAGER SETUP:"    print("   # Start AlertManager"    print("   ./alertmanager --config.file=monitoring-config/alertmanager.yml"    print("   # Access at: http://localhost:9093"

    print("
3. 📈 GRAFANA SETUP:"    print("   # Start Grafana"    print("   # Import dashboard from: monitoring-config/grafana-dashboard.json"    print("   # Access at: http://localhost:3000"

    print("
4. 🔍 AVAILABLE ENDPOINTS:"    print("   GET  /metrics              # Prometheus metrics"    print("   GET  /health/detailed     # Detailed health status"    print("   GET  /alerts/active       # Active alerts"    print("   GET  /alerts/history      # Alert history"    print("   GET  /performance-report  # Performance metrics"

    print("
5. 📧 ALERT CONFIGURATION:"    print("   # Configure Slack webhook in environment:"    print("   export SLACK_WEBHOOK_URL='your-webhook-url'"    print("   # Configure email settings in .env file"

    print("
6. 📋 MONITORING CHECKLIST:"    print("   □ Prometheus scraping metrics"    print("   □ AlertManager receiving alerts"    print("   □ Grafana dashboard imported"    print("   □ Slack/email notifications configured"    print("   □ Health checks running every 30s"    print("   □ Alert rules evaluating every 60s"


if __name__ == "__main__":
    # Run monitoring tests
    results = asyncio.run(test_monitoring_system())

    if results:
        # Generate configuration files
        generate_monitoring_config()

        # Print setup guide
        print_monitoring_guide()

        # Save test results
        with open("monitoring_test_results.json", "w") as f:
            json.dump(results, f, indent=2, default=str)

        print("
💾 Test results saved to: monitoring_test_results.json"        print("🎉 Monitoring system setup completed successfully!"
    else:
        print("❌ Monitoring system setup failed!")
        sys.exit(1)