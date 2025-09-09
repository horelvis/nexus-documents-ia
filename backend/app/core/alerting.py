"""
Alerting system for performance and system monitoring
"""
import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass
from enum import Enum

from app.core.config import settings
from app.core.structured_logging import structured_logger


class AlertSeverity(Enum):
    """Alert severity levels"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertStatus(Enum):
    """Alert status"""
    ACTIVE = "active"
    RESOLVED = "resolved"
    ACKNOWLEDGED = "acknowledged"


@dataclass
class Alert:
    """Alert data structure"""
    id: str
    name: str
    description: str
    severity: AlertSeverity
    status: AlertStatus
    value: float
    threshold: float
    labels: Dict[str, str]
    created_at: datetime
    updated_at: datetime
    resolved_at: Optional[datetime] = None
    acknowledged_at: Optional[datetime] = None
    acknowledged_by: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert alert to dictionary"""
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'severity': self.severity.value,
            'status': self.status.value,
            'value': self.value,
            'threshold': self.threshold,
            'labels': self.labels,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'resolved_at': self.resolved_at.isoformat() if self.resolved_at else None,
            'acknowledged_at': self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            'acknowledged_by': self.acknowledged_by
        }


class AlertRule:
    """Alert rule definition"""

    def __init__(self, name: str, description: str, severity: AlertSeverity,
                 condition: Callable, threshold: float, labels: Optional[Dict[str, str]] = None):
        self.name = name
        self.description = description
        self.severity = severity
        self.condition = condition
        self.threshold = threshold
        self.labels = labels or {}

    def evaluate(self, metrics: Dict[str, Any]) -> Optional[Alert]:
        """Evaluate rule against metrics"""
        try:
            result = self.condition(metrics)
            if result is not None:
                return Alert(
                    id=f"{self.name}_{datetime.utcnow().timestamp()}",
                    name=self.name,
                    description=self.description,
                    severity=self.severity,
                    status=AlertStatus.ACTIVE,
                    value=result,
                    threshold=self.threshold,
                    labels=self.labels.copy(),
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
        except Exception as e:
            structured_logger.error(f"Error evaluating alert rule {self.name}: {str(e)}")
        return None


class AlertManager:
    """Alert manager for handling alerts"""

    def __init__(self):
        self.alerts: Dict[str, Alert] = {}
        self.rules: List[AlertRule] = []
        self.notifiers: List[Callable] = []
        self.resolution_window = timedelta(minutes=5)  # Auto-resolve after 5 minutes

    def add_rule(self, rule: AlertRule) -> None:
        """Add alert rule"""
        self.rules.append(rule)
        structured_logger.info(f"Added alert rule: {rule.name}")

    def add_notifier(self, notifier: Callable) -> None:
        """Add alert notifier"""
        self.notifiers.append(notifier)

    def evaluate_rules(self, metrics: Dict[str, Any]) -> None:
        """Evaluate all alert rules"""
        for rule in self.rules:
            alert = rule.evaluate(metrics)
            if alert:
                self._handle_alert(alert)

        # Check for resolved alerts
        self._check_resolved_alerts()

    def _handle_alert(self, alert: Alert) -> None:
        """Handle new alert"""
        existing_alert = self.alerts.get(alert.name)

        if existing_alert and existing_alert.status == AlertStatus.ACTIVE:
            # Update existing alert
            existing_alert.value = alert.value
            existing_alert.updated_at = datetime.utcnow()
        else:
            # New alert
            self.alerts[alert.name] = alert
            self._notify_alert(alert)

        structured_logger.warning(f"Alert triggered: {alert.name}", {
            'event_type': 'alert_triggered',
            'alert_name': alert.name,
            'severity': alert.severity.value,
            'value': alert.value,
            'threshold': alert.threshold
        })

    def _check_resolved_alerts(self) -> None:
        """Check for alerts that should be resolved"""
        now = datetime.utcnow()
        to_resolve = []

        for alert_name, alert in self.alerts.items():
            if alert.status == AlertStatus.ACTIVE:
                if now - alert.updated_at > self.resolution_window:
                    alert.status = AlertStatus.RESOLVED
                    alert.resolved_at = now
                    alert.updated_at = now
                    to_resolve.append(alert)

        for alert in to_resolve:
            self._notify_alert_resolution(alert)

    def _notify_alert(self, alert: Alert) -> None:
        """Notify about new alert"""
        for notifier in self.notifiers:
            try:
                asyncio.create_task(notifier(alert))
            except Exception as e:
                structured_logger.error(f"Error notifying alert: {str(e)}")

    def _notify_alert_resolution(self, alert: Alert) -> None:
        """Notify about resolved alert"""
        for notifier in self.notifiers:
            try:
                asyncio.create_task(notifier(alert, resolved=True))
            except Exception as e:
                structured_logger.error(f"Error notifying alert resolution: {str(e)}")

    def acknowledge_alert(self, alert_name: str, user_id: str) -> bool:
        """Acknowledge an alert"""
        alert = self.alerts.get(alert_name)
        if alert and alert.status == AlertStatus.ACTIVE:
            alert.status = AlertStatus.ACKNOWLEDGED
            alert.acknowledged_at = datetime.utcnow()
            alert.acknowledged_by = user_id
            alert.updated_at = datetime.utcnow()
            return True
        return False

    def get_active_alerts(self) -> List[Alert]:
        """Get all active alerts"""
        return [alert for alert in self.alerts.values()
                if alert.status in [AlertStatus.ACTIVE, AlertStatus.ACKNOWLEDGED]]

    def get_alert_history(self, hours: int = 24) -> List[Alert]:
        """Get alert history for the last N hours"""
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        return [alert for alert in self.alerts.values()
                if alert.created_at > cutoff]


class ConsoleNotifier:
    """Console alert notifier for development"""

    async def __call__(self, alert: Alert, resolved: bool = False) -> None:
        """Send alert notification to console"""
        status = "RESOLVED" if resolved else "TRIGGERED"
        severity_emoji = {
            AlertSeverity.INFO: "ℹ️",
            AlertSeverity.WARNING: "⚠️",
            AlertSeverity.ERROR: "❌",
            AlertSeverity.CRITICAL: "🚨"
        }

        message = f"{severity_emoji[alert.severity]} ALERT {status}: {alert.name}"
        if not resolved:
            message += f" (Value: {alert.value:.2f}, Threshold: {alert.threshold:.2f})"

        print(f"[{datetime.utcnow().isoformat()}] {message}")
        structured_logger.info(message, {
            'event_type': 'alert_notification',
            'alert_name': alert.name,
            'resolved': resolved,
            'severity': alert.severity.value
        })


class SlackNotifier:
    """Slack alert notifier"""

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    async def __call__(self, alert: Alert, resolved: bool = False) -> None:
        """Send alert notification to Slack"""
        import aiohttp

        status = "resolved" if resolved else "triggered"
        color = {
            AlertSeverity.INFO: "good",
            AlertSeverity.WARNING: "warning",
            AlertSeverity.ERROR: "danger",
            AlertSeverity.CRITICAL: "#FF0000"
        }[alert.severity]

        payload = {
            "attachments": [{
                "color": color,
                "title": f"🚨 Alert {status.upper()}: {alert.name}",
                "text": alert.description,
                "fields": [
                    {"title": "Severity", "value": alert.severity.value, "short": True},
                    {"title": "Value", "value": f"{alert.value:.2f}", "short": True},
                    {"title": "Threshold", "value": f"{alert.threshold:.2f}", "short": True}
                ],
                "footer": "NexusDocs360 Monitoring",
                "ts": alert.created_at.timestamp()
            }]
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.webhook_url, json=payload) as response:
                    if response.status != 200:
                        structured_logger.error(f"Slack notification failed: {response.status}")
        except Exception as e:
            structured_logger.error(f"Error sending Slack notification: {str(e)}")


class EmailNotifier:
    """Email alert notifier"""

    def __init__(self, smtp_config: Dict[str, Any]):
        self.smtp_config = smtp_config

    async def __call__(self, alert: Alert, resolved: bool = False) -> None:
        """Send alert notification via email"""
        import aiosmtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        status = "RESOLVED" if resolved else "TRIGGERED"
        subject = f"NexusDocs360 Alert {status}: {alert.name}"

        body = f"""
        Alert Details:
        Name: {alert.name}
        Description: {alert.description}
        Severity: {alert.severity.value}
        Value: {alert.value:.2f}
        Threshold: {alert.threshold:.2f}
        Time: {alert.created_at.isoformat()}

        Labels: {json.dumps(alert.labels, indent=2)}
        """

        msg = MIMEMultipart()
        msg['Subject'] = subject
        msg['From'] = self.smtp_config['from']
        msg['To'] = ','.join(self.smtp_config['to'])
        msg.attach(MIMEText(body, 'plain'))

        try:
            await aiosmtplib.send(
                msg,
                hostname=self.smtp_config['host'],
                port=self.smtp_config['port'],
                username=self.smtp_config['username'],
                password=self.smtp_config['password'],
                use_tls=self.smtp_config.get('use_tls', True)
            )
        except Exception as e:
            structured_logger.error(f"Error sending email notification: {str(e)}")


# Global alert manager instance
alert_manager = AlertManager()

# Default alert rules
def create_default_alert_rules():
    """Create default alert rules"""

    # High response time alert
    def check_response_time(metrics):
        http_metrics = metrics.get('histograms', {}).get('http_request_duration_seconds', {})
        avg_duration = http_metrics.get('avg', 0)
        return avg_duration if avg_duration > 5.0 else None

    alert_manager.add_rule(AlertRule(
        name="high_response_time",
        description="Average HTTP response time is too high",
        severity=AlertSeverity.WARNING,
        condition=check_response_time,
        threshold=5.0,
        labels={"component": "http"}
    ))

    # High error rate alert
    def check_error_rate(metrics):
        counters = metrics.get('counters', {})
        total_requests = sum([
            counters.get(f'http_requests_total{{status_class={code}xx}}', 0)
            for code in ['2', '3', '4', '5']
        ])
        error_requests = counters.get('http_requests_total{status_class=5xx}', 0)

        if total_requests > 0:
            error_rate = error_requests / total_requests
            return error_rate if error_rate > 0.05 else None
        return None

    alert_manager.add_rule(AlertRule(
        name="high_error_rate",
        description="HTTP error rate is above 5%",
        severity=AlertSeverity.ERROR,
        condition=check_error_rate,
        threshold=0.05,
        labels={"component": "http"}
    ))

    # Low cache hit rate alert
    def check_cache_hit_rate(metrics):
        gauges = metrics.get('gauges', {})
        hit_rate = gauges.get('cache_hit_rate{combined}', 0)
        return hit_rate if hit_rate < 0.8 else None

    alert_manager.add_rule(AlertRule(
        name="low_cache_hit_rate",
        description="Cache hit rate is below 80%",
        severity=AlertSeverity.WARNING,
        condition=check_cache_hit_rate,
        threshold=0.8,
        labels={"component": "cache"}
    ))

    # High memory usage alert
    def check_memory_usage(metrics):
        gauges = metrics.get('gauges', {})
        memory_mb = gauges.get('memory_usage_mb', 0)
        return memory_mb if memory_mb > 500 else None

    alert_manager.add_rule(AlertRule(
        name="high_memory_usage",
        description="Memory usage is above 500MB",
        severity=AlertSeverity.WARNING,
        condition=check_memory_usage,
        threshold=500,
        labels={"component": "system"}
    ))

    # Database connection issues
    def check_db_connections(metrics):
        gauges = metrics.get('gauges', {})
        active_connections = gauges.get('db_connections_active', 0)
        return active_connections if active_connections > 20 else None

    alert_manager.add_rule(AlertRule(
        name="high_db_connections",
        description="Too many active database connections",
        severity=AlertSeverity.WARNING,
        condition=check_db_connections,
        threshold=20,
        labels={"component": "database"}
    ))


# Setup default notifiers
def setup_default_notifiers():
    """Setup default alert notifiers"""
    # Console notifier for development
    alert_manager.add_notifier(ConsoleNotifier())

    # Slack notifier if configured
    slack_webhook = settings.__dict__.get('SLACK_WEBHOOK_URL')
    if slack_webhook:
        alert_manager.add_notifier(SlackNotifier(slack_webhook))

    # Email notifier if configured
    email_config = {
        'host': settings.MAIL_SERVER,
        'port': settings.MAIL_PORT,
        'username': settings.MAIL_USERNAME,
        'password': settings.MAIL_PASSWORD,
        'from': settings.MAIL_FROM,
        'to': [settings.MAIL_FROM],  # Send to admin
        'use_tls': settings.MAIL_STARTTLS
    }

    if all(email_config.values()):
        alert_manager.add_notifier(EmailNotifier(email_config))


# Initialize alerting system
def initialize_alerting():
    """Initialize the alerting system"""
    create_default_alert_rules()
    setup_default_notifiers()

    structured_logger.info("Alerting system initialized", {
        'event_type': 'system_init',
        'component': 'alerting',
        'rules_count': len(alert_manager.rules),
        'notifiers_count': len(alert_manager.notifiers)
    })


# Background alert evaluation
async def start_alert_evaluation():
    """Start background alert evaluation"""
    while True:
        try:
            from app.core.metrics import get_metrics_summary
            metrics = get_metrics_summary()
            alert_manager.evaluate_rules(metrics)
        except Exception as e:
            structured_logger.error(f"Error evaluating alerts: {str(e)}")

        await asyncio.sleep(60)  # Evaluate every minute


# Convenience functions
def get_active_alerts() -> List[Alert]:
    """Get all active alerts"""
    return alert_manager.get_active_alerts()

def get_alert_history(hours: int = 24) -> List[Alert]:
    """Get alert history"""
    return alert_manager.get_alert_history(hours)

def acknowledge_alert(alert_name: str, user_id: str) -> bool:
    """Acknowledge an alert"""
    return alert_manager.acknowledge_alert(alert_name, user_id)