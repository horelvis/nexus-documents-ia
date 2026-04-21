"""
Structured logging system for ELK stack integration
"""
import json
import logging
import os
import sys
import threading
from datetime import datetime
from typing import Dict, Any, Optional
import uuid

try:
    from pythonjsonlogger.jsonlogger import JsonFormatter
except ImportError:
    # Fallback for different package versions
    try:
        from pythonjsonlogger import jsonlogger
        JsonFormatter = jsonlogger.JsonFormatter
    except ImportError:
        # Simple fallback formatter
        class JsonFormatter:
            def __init__(self, **kwargs):
                pass
            def format(self, record):
                return f"{record.levelname}: {record.getMessage()}"

from app.core.config import settings


class StructuredLogger:
    """Structured logger for ELK stack compatibility"""

    def __init__(self, name: str, level: int = logging.INFO):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(level)

        # Remove existing handlers to avoid duplicates
        for handler in self.logger.handlers[:]:
            self.logger.removeHandler(handler)

        # Create JSON formatter
        formatter = JsonFormatter(
            fmt='%(asctime)s %(name)s %(levelname)s %(message)s',
            datefmt='%Y-%m-%dT%H:%M:%S%z'
        )

        # Console handler for development
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)

        # File handler for production
        if not settings.DEBUG:
            os.makedirs('logs', exist_ok=True)
            file_handler = logging.FileHandler('logs/nexus.log')
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)

        # Store context for structured logging
        self._context = threading.local()

    def _get_base_fields(self) -> Dict[str, Any]:
        """Get base fields for all log entries"""
        return {
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'service': 'nouxcubeia',
            'version': '1.0.0',
            'environment': 'development' if settings.DEBUG else 'production',
            'request_id': getattr(self._context, 'request_id', str(uuid.uuid4())),
            'user_id': getattr(self._context, 'user_id', None),
            'session_id': getattr(self._context, 'session_id', None),
            'ip_address': getattr(self._context, 'ip_address', None),
            'user_agent': getattr(self._context, 'user_agent', None),
        }

    def _log(self, level: int, message: str, extra: Optional[Dict[str, Any]] = None,
             exc_info=None) -> None:
        """Internal logging method"""
        fields = self._get_base_fields()

        if extra:
            fields.update(extra)

        # Add exception info if present
        if exc_info:
            fields['exception'] = {
                'type': type(exc_info).__name__,
                'message': str(exc_info),
                'traceback': self._format_exception(exc_info)
            }

        # Create log record with extra fields
        record = logging.LogRecord(
            name=self.logger.name,
            level=level,
            pathname='',
            lineno=0,
            msg=message,
            args=(),
            exc_info=None
        )

        # Add structured fields
        for key, value in fields.items():
            setattr(record, key, value)

        self.logger.handle(record)

    def _format_exception(self, exc) -> str:
        """Format exception traceback"""
        import traceback
        return ''.join(traceback.format_exception(type(exc), exc, exc.__traceback__))

    def set_context(self, **kwargs) -> None:
        """Set context for structured logging"""
        for key, value in kwargs.items():
            setattr(self._context, key, value)

    def clear_context(self) -> None:
        """Clear logging context"""
        self._context.__dict__.clear()

    def debug(self, message: str, extra: Optional[Dict[str, Any]] = None) -> None:
        """Log debug message"""
        self._log(logging.DEBUG, message, extra)

    def info(self, message: str, extra: Optional[Dict[str, Any]] = None) -> None:
        """Log info message"""
        self._log(logging.INFO, message, extra)

    def warning(self, message: str, extra: Optional[Dict[str, Any]] = None) -> None:
        """Log warning message"""
        self._log(logging.WARNING, message, extra)

    def error(self, message: str, extra: Optional[Dict[str, Any]] = None,
              exc_info=None) -> None:
        """Log error message"""
        self._log(logging.ERROR, message, extra, exc_info)

    def critical(self, message: str, extra: Optional[Dict[str, Any]] = None,
                 exc_info=None) -> None:
        """Log critical message"""
        self._log(logging.CRITICAL, message, extra, exc_info)

    # Business-specific logging methods
    def log_http_request(self, method: str, path: str, status_code: int,
                        duration: float, user_id: Optional[str] = None) -> None:
        """Log HTTP request"""
        self.info("HTTP Request", {
            'event_type': 'http_request',
            'http_method': method,
            'http_path': path,
            'http_status': status_code,
            'duration_ms': round(duration * 1000, 2),
            'user_id': user_id
        })

    def log_database_query(self, query: str, duration: float,
                          params: Optional[Dict[str, Any]] = None) -> None:
        """Log database query"""
        self.info("Database Query", {
            'event_type': 'db_query',
            'query': query[:500],  # Truncate long queries
            'duration_ms': round(duration * 1000, 2),
            'params': params
        })

    def log_business_event(self, event_name: str, event_data: Dict[str, Any]) -> None:
        """Log business event"""
        self.info(f"Business Event: {event_name}", {
            'event_type': 'business_event',
            'event_name': event_name,
            'event_data': event_data
        })

    def log_security_event(self, event_type: str, details: Dict[str, Any],
                          severity: str = 'info') -> None:
        """Log security event"""
        log_method = getattr(self, severity, self.info)
        log_method(f"Security Event: {event_type}", {
            'event_type': 'security_event',
            'security_event_type': event_type,
            'severity': severity,
            'details': details
        })

    def log_performance_metric(self, metric_name: str, value: float,
                              tags: Optional[Dict[str, str]] = None) -> None:
        """Log performance metric"""
        self.info("Performance Metric", {
            'event_type': 'performance_metric',
            'metric_name': metric_name,
            'metric_value': value,
            'tags': tags or {}
        })

    def log_error_with_context(self, error: Exception, context: Dict[str, Any]) -> None:
        """Log error with additional context"""
        self.error(f"Error: {str(error)}", {
            'event_type': 'error',
            'error_type': type(error).__name__,
            'context': context
        }, exc_info=error)


class RequestContextMiddleware:
    """Middleware to add request context to logging"""

    def __init__(self, app, logger: StructuredLogger):
        self.app = app
        self.logger = logger

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Extract request information
        headers = dict(scope.get("headers", []))
        query_string = scope.get("query_string", b"").decode()

        # Set logging context
        request_id = headers.get(b'x-request-id', str(uuid.uuid4()).encode()).decode()
        user_id = headers.get(b'x-user-id', b'').decode() or None

        self.logger.set_context(
            request_id=request_id,
            user_id=user_id,
            ip_address=self._get_client_ip(scope),
            user_agent=headers.get(b'user-agent', b'').decode(),
            http_method=scope.get("method"),
            http_path=scope.get("path"),
            query_string=query_string
        )

        # Log request start
        self.logger.info("Request started", {
            'event_type': 'request_start'
        })

        start_time = datetime.utcnow()

        try:
            await self.app(scope, receive, send)
        except Exception as e:
            # Log error
            self.logger.log_error_with_context(e, {
                'request_duration': (datetime.utcnow() - start_time).total_seconds()
            })
            raise
        finally:
            # Log request completion
            duration = (datetime.utcnow() - start_time).total_seconds()
            self.logger.info("Request completed", {
                'event_type': 'request_complete',
                'duration_ms': round(duration * 1000, 2)
            })

            # Clear context
            self.logger.clear_context()

    def _get_client_ip(self, scope) -> str:
        """Extract client IP from ASGI scope"""
        headers = dict(scope.get("headers", []))
        forwarded = headers.get(b'x-forwarded-for', b'').decode()

        if forwarded:
            return forwarded.split(',')[0].strip()

        client = scope.get("client")
        if client:
            return client[0]

        return "unknown"


# Global logger instance
structured_logger = StructuredLogger("nouxcubeia")

# Convenience functions
def get_logger(name: str) -> StructuredLogger:
    """Get a structured logger instance"""
    return StructuredLogger(name)

def log_http_request(method: str, path: str, status_code: int,
                    duration: float, user_id: Optional[str] = None) -> None:
    """Log HTTP request"""
    structured_logger.log_http_request(method, path, status_code, duration, user_id)

def log_database_query(query: str, duration: float,
                      params: Optional[Dict[str, Any]] = None) -> None:
    """Log database query"""
    structured_logger.log_database_query(query, duration, params)

def log_business_event(event_name: str, event_data: Dict[str, Any]) -> None:
    """Log business event"""
    structured_logger.log_business_event(event_name, event_data)

def log_security_event(event_type: str, details: Dict[str, Any],
                      severity: str = 'info') -> None:
    """Log security event"""
    structured_logger.log_security_event(event_type, details, severity)

def log_performance_metric(metric_name: str, value: float,
                           tags: Optional[Dict[str, str]] = None) -> None:
    """Log performance metric"""
    structured_logger.log_performance_metric(metric_name, value, tags)

def log_error_with_context(error: Exception, context: Dict[str, Any]) -> None:
    """Log error with context"""
    structured_logger.log_error_with_context(error, context)


# Initialize logging
def setup_structured_logging():
    """Setup structured logging for the application"""
    # Configure root logger to not duplicate messages
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.WARNING)  # Only log warnings and above from libraries

    # Start metrics collection in background
    try:
        from app.core.prometheus_metrics import start_metrics_collection
        start_metrics_collection()
    except Exception as e:
        structured_logger.error(f"Failed to start metrics collection: {str(e)}")

    structured_logger.info("Structured logging initialized", {
        'event_type': 'system_init',
        'component': 'logging'
    })