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
    "CLERK_SECRET_KEY",
    "STRIPE_SECRET_KEY",
    "SIGNATURE_ENCRYPTION_KEY",
]

TEST_REQUIRED_ENV_VARS: List[str] = [
    "MICROSERVICES_API_KEY",
    "SIGNATURE_ENCRYPTION_KEY",
]

DB_REQUIRED_GROUPS: List[List[str]] = [
    ["DATABASE_URL"],
    ["POSTGRES_SERVER", "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB"],
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
    is_testing = os.getenv("TESTING", "false").lower() == "true"
    base_required = TEST_REQUIRED_ENV_VARS if is_testing else REQUIRED_ENV_VARS

    required_vars = _resolve_required_vars(extra_required)
    required_vars = list(dict.fromkeys(base_required + required_vars))

    missing = [var for var in required_vars if not os.getenv(var)]

    db_ok = any(all(os.getenv(v) for v in group) for group in DB_REQUIRED_GROUPS)
    if not db_ok:
        missing.append("DATABASE_URL (or POSTGRES_SERVER/POSTGRES_USER/POSTGRES_PASSWORD/POSTGRES_DB)")

    if missing:
        logger.error("❌ Missing required environment variables: %s", ", ".join(missing))
        raise EnvironmentError(
            "Missing required environment variables: "
            + ", ".join(sorted(missing))
        )

    logger.info("✅ Environment validation passed for %s variables", len(required_vars))
