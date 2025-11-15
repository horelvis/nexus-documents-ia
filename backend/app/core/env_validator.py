"""
Environment validation utilities.
Ensures critical secrets are provided before the application starts.
"""
import logging
import os
from typing import Iterable, List

logger = logging.getLogger(__name__)

# Default set of required environment variables for secure operation
REQUIRED_ENV_VARS: List[str] = [
    "MICROSERVICES_API_KEY",
    "POSTGRES_PASSWORD",
    "CLERK_SECRET_KEY",
    "STRIPE_SECRET_KEY",
    "SIGNATURE_ENCRYPTION_KEY",
]


def _resolve_required_vars(extra_required: Iterable[str] | None = None) -> List[str]:
    """Merge default required variables with any additional ones provided."""
    required = list(REQUIRED_ENV_VARS)
    if extra_required:
        for var in extra_required:
            if var not in required:
                required.append(var)
    return required


def validate_environment(extra_required: Iterable[str] | None = None) -> None:
    """
    Validate that all required environment variables are present.

    Raises:
        EnvironmentError: If any required environment variable is missing.
    """
    required_vars = _resolve_required_vars(extra_required)
    missing = [var for var in required_vars if not os.getenv(var)]

    if missing:
        logger.error("❌ Missing required environment variables: %s", ", ".join(missing))
        raise EnvironmentError(
            "Missing required environment variables: "
            + ", ".join(sorted(missing))
        )

    logger.info("✅ Environment validation passed for %s variables", len(required_vars))
