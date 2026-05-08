"""
Shared auth header helpers for microservices.

The microservices do NOT validate JWTs themselves — the main API and the
TLS proxy already do that. Each microservice receives the authenticated
user context as trusted headers from the API gateway:

    X-User-Id       : str    — the authenticated user's sub (UUID-as-str)
    X-User-Roles    : str    — comma-separated KeyCloak roles (informational only)

Role-based ACL has been removed. These helpers retain only the informational
`extract_user_roles` dependency for logging/audit metadata flow.

(Replicated per-microservice because there is no shared Python package
across backend/microservices/. Keep the copies in sync.)
"""
from typing import List, Optional

from fastapi import Header


async def extract_user_roles(
    x_user_roles: Optional[str] = Header(default=None, alias="X-User-Roles"),
) -> List[str]:
    """FastAPI dependency: parse the X-User-Roles header into a list.

    The header is comma-separated. Whitespace is stripped around each
    entry. Kept for informational/audit metadata flow after ACL removal.
    """
    if not x_user_roles:
        return []
    return [r.strip() for r in x_user_roles.split(",") if r.strip()]


async def extract_user_id(
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
) -> Optional[str]:
    """FastAPI dependency: read the X-User-Id header.

    Returns None if missing. Endpoints that require a user id should
    validate the return value and raise 401 when None.
    """
    return x_user_id
