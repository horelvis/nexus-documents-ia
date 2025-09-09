"""
Security configuration validator
"""
import logging
import os
from typing import List, Dict, Any

from app.core.config import settings
from app.core.security_config import ENCRYPTION_KEY, JWT_SECRET_KEY

logger = logging.getLogger(__name__)


class SecurityValidator:
    """Validates security configuration on startup"""

    def __init__(self):
        self.warnings: List[str] = []
        self.errors: List[str] = []
        self.security_score: int = 0

    def validate_all(self) -> Dict[str, Any]:
        """Run all security validations"""
        logger.info("🔒 Starting security configuration validation...")

        self._validate_environment()
        self._validate_secrets()
        self._validate_cors()
        self._validate_database()
        self._validate_file_upload()
        self._validate_rate_limiting()

        self._calculate_security_score()

        result = {
            "valid": len(self.errors) == 0,
            "warnings": self.warnings,
            "errors": self.errors,
            "security_score": self.security_score,
            "recommendations": self._get_recommendations()
        }

        if self.errors:
            logger.error(f"❌ Security validation failed with {len(self.errors)} errors")
            for error in self.errors:
                logger.error(f"  - {error}")
        else:
            logger.info(f"✅ Security validation passed (Score: {self.security_score}/100)")

        if self.warnings:
            logger.warning(f"⚠️ {len(self.warnings)} security warnings:")
            for warning in self.warnings:
                logger.warning(f"  - {warning}")

        return result

    def _validate_environment(self) -> None:
        """Validate environment settings"""
        if settings.DEBUG:
            self.warnings.append("DEBUG mode is enabled - disable in production")
            self.security_score -= 10

        if os.getenv("PYTHONPATH"):
            self.warnings.append("PYTHONPATH is set - potential security risk")

    def _validate_secrets(self) -> None:
        """Validate secret keys and passwords"""
        # Check JWT secret
        if not JWT_SECRET_KEY or JWT_SECRET_KEY == "your-jwt-secret-key-here":
            self.errors.append("JWT_SECRET_KEY not properly configured")
            self.security_score -= 30

        if len(JWT_SECRET_KEY) < 32:
            self.warnings.append("JWT_SECRET_KEY should be at least 32 characters")
            self.security_score -= 5

        # Check encryption key
        if not settings.DEBUG and (not ENCRYPTION_KEY or ENCRYPTION_KEY == "your-32-byte-encryption-key-here"):
            self.errors.append("ENCRYPTION_KEY required in production")
            self.security_score -= 25

        # Check database password
        if settings.POSTGRES_PASSWORD in ["password", "postgres", "admin"]:
            self.errors.append("Weak database password detected")
            self.security_score -= 20

    def _validate_cors(self) -> None:
        """Validate CORS configuration"""
        cors_origins = [str(origin) for origin in settings.BACKEND_CORS_ORIGINS]

        if "*" in cors_origins:
            self.errors.append("Wildcard (*) CORS origin not allowed")
            self.security_score -= 30

        if not cors_origins and not settings.DEBUG:
            self.errors.append("No CORS origins configured for production")
            self.security_score -= 20

        if len(cors_origins) > 10:
            self.warnings.append("Too many CORS origins configured")
            self.security_score -= 5

    def _validate_database(self) -> None:
        """Validate database configuration"""
        if "localhost" in settings.POSTGRES_SERVER and not settings.DEBUG:
            self.warnings.append("Database running on localhost in production")
            self.security_score -= 10

        if not settings.POSTGRES_PASSWORD:
            self.errors.append("Database password not configured")
            self.security_score -= 25

    def _validate_file_upload(self) -> None:
        """Validate file upload security"""
        from app.core.security_config import MAX_FILE_SIZE, ALLOWED_EXTENSIONS

        if MAX_FILE_SIZE > 100 * 1024 * 1024:  # 100MB
            self.warnings.append("File size limit too high")
            self.security_score -= 5

        dangerous_extensions = ['exe', 'bat', 'cmd', 'scr', 'pif', 'com']
        if any(ext in ALLOWED_EXTENSIONS for ext in dangerous_extensions):
            self.errors.append("Dangerous file extensions allowed")
            self.security_score -= 20

    def _validate_rate_limiting(self) -> None:
        """Validate rate limiting configuration"""
        from app.core.security_config import RATE_LIMIT_REQUESTS

        if RATE_LIMIT_REQUESTS > 1000:
            self.warnings.append("Rate limit too permissive")
            self.security_score -= 10

        if RATE_LIMIT_REQUESTS < 10:
            self.warnings.append("Rate limit too restrictive")
            self.security_score -= 5

    def _calculate_security_score(self) -> None:
        """Calculate overall security score"""
        self.security_score = max(0, min(100, self.security_score + 100))

    def _get_recommendations(self) -> List[str]:
        """Get security recommendations based on findings"""
        recommendations = []

        if self.errors:
            recommendations.append("Fix all security errors before deploying to production")

        if settings.DEBUG:
            recommendations.append("Disable DEBUG mode in production")

        if not ENCRYPTION_KEY or ENCRYPTION_KEY == "your-32-byte-encryption-key-here":
            recommendations.append("Generate and set a strong ENCRYPTION_KEY")

        if len(JWT_SECRET_KEY) < 32:
            recommendations.append("Use a JWT secret key of at least 32 characters")

        recommendations.append("Regularly rotate all secret keys and passwords")
        recommendations.append("Enable HTTPS/TLS in production")
        recommendations.append("Implement proper logging and monitoring")
        recommendations.append("Regular security audits and penetration testing")

        return recommendations


def validate_security_on_startup() -> None:
    """Validate security configuration on application startup"""
    validator = SecurityValidator()
    result = validator.validate_all()

    if not result["valid"]:
        logger.error("🚨 SECURITY VALIDATION FAILED - Application may not be secure!")
        if not settings.DEBUG:
            raise RuntimeError("Security validation failed in production environment")

    return result