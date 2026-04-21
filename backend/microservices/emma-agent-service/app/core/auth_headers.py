"""
Shared auth header helpers for microservices.

The microservices do NOT validate JWTs themselves — the main API and the
TLS proxy already do that. Each microservice receives the authenticated
user context as trusted headers from the API gateway:

    X-User-Id       : str    — the authenticated user's sub (UUID-as-str)
    X-User-Roles    : str    — comma-separated KeyCloak roles, e.g. "LEGAL,SALES"

These helpers centralise parsing and the EVERYONE wildcard logic.

(Replicated per-microservice because there is no shared Python package
across backend/microservices/. Keep the copies in sync.)
"""
from typing import List, Optional

from fastapi import Header


EVERYONE_ROLE = "EVERYONE"


async def extract_user_roles(
    x_user_roles: Optional[str] = Header(default=None, alias="X-User-Roles"),
) -> List[str]:
    """FastAPI dependency: parse the X-User-Roles header into a list.

    The header is comma-separated. Whitespace is stripped around each
    entry. If the header is missing or empty the returned list is empty
    (which is NOT the same as "everyone" — empty means "no roles"; use
    `allowed_roles()` to fold in the EVERYONE wildcard before querying).
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


def allowed_roles(user_roles: List[str]) -> List[str]:
    """Return the caller's roles plus the EVERYONE wildcard.

    Used in ACL filters and graph queries. Documents tagged with the
    EVERYONE sentinel are visible to every authenticated user regardless
    of their role list.
    """
    return list({*user_roles, EVERYONE_ROLE})
