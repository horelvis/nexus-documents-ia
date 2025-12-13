"""
Authentication module for NexusDocs360.

This module provides unified authentication functionality:
- Clerk JWT verification with JWKS caching
- Typed authentication exceptions
- Thread-safe token validation

Usage:
    from app.core.auth import verify_clerk_token, AuthError

    try:
        payload = verify_clerk_token(token)
        user_id = payload['sub']
    except AuthError as e:
        # Handle authentication failure
        print(f"Auth failed: {e.message} ({e.error_code})")
"""

from app.core.auth.clerk import (
    verify_clerk_token,
    get_jwks_manager,
    invalidate_jwks_cache,
)

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

__all__ = [
    # Verification
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
