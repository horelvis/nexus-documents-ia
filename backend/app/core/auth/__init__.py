"""
Authentication module for NexusDocs360.

This module provides unified authentication functionality:
- Pluggable auth providers (Clerk, OIDC, SAML, LDAP)
- Provider factory for tenant-specific configuration
- Typed authentication exceptions

Usage (new - provider pattern):
    from app.core.auth import AuthProviderFactory

    provider = await AuthProviderFactory.get_for_tenant(tenant_id, db)
    identity = await provider.verify_token(token)

Usage (legacy - Clerk direct):
    from app.core.auth import verify_clerk_token, AuthError

    payload = verify_clerk_token(token)
    user_id = payload['sub']
"""

# Legacy Clerk verification (still works)
from app.core.auth.clerk import (
    verify_clerk_token,
    get_jwks_manager,
    invalidate_jwks_cache,
)

# Exceptions
from app.core.auth.exceptions import (
    AuthError,
    TokenMissingError,
    TokenExpiredError,
    TokenInvalidError,
    UserNotFoundError,
    UserInactiveError,
    InsufficientPermissionsError,
    ClerkConfigError,
)

# New provider pattern
from app.core.auth.base import (
    AuthProvider,
    AuthProviderType,
    AuthenticatedIdentity,
    AuthProviderError,
)
from app.core.auth.factory import AuthProviderFactory

__all__ = [
    # Provider pattern (new)
    "AuthProvider",
    "AuthProviderType",
    "AuthenticatedIdentity",
    "AuthProviderFactory",
    "AuthProviderError",
    # Legacy Clerk verification
    "verify_clerk_token",
    "get_jwks_manager",
    "invalidate_jwks_cache",
    # Exceptions
    "AuthError",
    "TokenMissingError",
    "TokenExpiredError",
    "TokenInvalidError",
    "UserNotFoundError",
    "UserInactiveError",
    "InsufficientPermissionsError",
    "ClerkConfigError",
]
