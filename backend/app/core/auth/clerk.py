"""
Unified Clerk JWT verification module.

This module provides a single source of truth for Clerk token verification,
with JWKS caching, normalized logging, and typed exceptions.

Usage:
    from app.core.auth.clerk import verify_clerk_token

    payload = verify_clerk_token(token)
    clerk_user_id = payload['sub']
"""
import logging
import time
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
from threading import Lock

import jwt
from jwt import PyJWKClient

from app.core.config import settings
from app.core.auth.exceptions import (
    TokenMissingError,
    TokenExpiredError,
    TokenInvalidError,
    ClerkConfigError,
)

logger = logging.getLogger(__name__)


@dataclass
class JWKSCache:
    """Cache entry for JWKS client with TTL."""
    client: PyJWKClient
    created_at: float
    issuer: str


class ClerkJWKSManager:
    """
    Manages JWKS clients with caching per issuer.

    JWKS (JSON Web Key Set) contains the public keys used to verify JWT signatures.
    Caching prevents repeated network calls to fetch keys for each token verification.

    Thread-safe implementation with configurable TTL.
    """

    # Default TTL: 1 hour (Clerk rotates keys infrequently)
    DEFAULT_TTL_SECONDS = 3600

    def __init__(self, ttl_seconds: int = DEFAULT_TTL_SECONDS):
        self._cache: Dict[str, JWKSCache] = {}
        self._lock = Lock()
        self._ttl = ttl_seconds

    def get_client(self, issuer: str) -> PyJWKClient:
        """
        Get or create a JWKS client for the given issuer.

        Args:
            issuer: The JWT issuer URL (e.g., https://clerk.example.com)

        Returns:
            PyJWKClient configured for the issuer's JWKS endpoint
        """
        current_time = time.time()

        with self._lock:
            cached = self._cache.get(issuer)

            # Return cached client if valid
            if cached and (current_time - cached.created_at) < self._ttl:
                return cached.client

            # Create new client
            jwks_url = f"{issuer}/.well-known/jwks.json"
            client = PyJWKClient(jwks_url)

            self._cache[issuer] = JWKSCache(
                client=client,
                created_at=current_time,
                issuer=issuer
            )

            logger.debug(f"Created JWKS client for issuer (cached for {self._ttl}s)")
            return client

    def invalidate(self, issuer: Optional[str] = None):
        """
        Invalidate cached JWKS client(s).

        Args:
            issuer: Specific issuer to invalidate, or None to clear all
        """
        with self._lock:
            if issuer:
                self._cache.pop(issuer, None)
            else:
                self._cache.clear()


# Global JWKS manager instance
_jwks_manager = ClerkJWKSManager()


def verify_clerk_token(token: str) -> dict:
    """
    Verify a Clerk JWT token using JWKS.

    This is the single source of truth for Clerk token verification.
    Use this function from both sync and async contexts.

    Args:
        token: The JWT token from Authorization header (without 'Bearer ' prefix)

    Returns:
        dict with verified payload containing:
        - sub: Clerk user ID
        - iss: Token issuer
        - session_id: Clerk session ID (if present)

    Raises:
        TokenMissingError: No token provided
        TokenExpiredError: Token has expired
        TokenInvalidError: Token is malformed or signature invalid
        ClerkConfigError: Clerk not properly configured

    Example:
        >>> payload = verify_clerk_token("eyJ...")
        >>> user_id = payload['sub']
        >>> print(f"Authenticated user: {user_id}")
    """
    # Validate configuration
    if not settings.CLERK_SECRET_KEY:
        logger.error("Clerk verification failed: CLERK_SECRET_KEY not configured")
        raise ClerkConfigError()

    # Validate token presence
    if not token:
        raise TokenMissingError("No token provided")

    try:
        # Step 1: Decode without verification to extract issuer
        # This is safe because we verify the signature in step 3
        unverified = jwt.decode(token, options={"verify_signature": False})
        issuer = unverified.get('iss', '')

        if not issuer:
            raise TokenInvalidError("Token missing issuer claim")

        # Step 2: Get JWKS client (cached)
        jwks_client = _jwks_manager.get_client(issuer)

        # Step 3: Get signing key and verify signature
        signing_key = jwks_client.get_signing_key_from_jwt(token)

        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            # Clerk tokens may not have audience claim
            options={"verify_aud": False}
        )

        # Step 4: Validate required claims
        clerk_user_id = payload.get('sub')
        if not clerk_user_id:
            raise TokenInvalidError("Token missing subject claim (user ID)")

        # Log success without sensitive data
        # Only log partial user ID for debugging (first 8 chars)
        logger.debug(f"Token verified for user: {clerk_user_id[:8]}...")

        return {
            'sub': clerk_user_id,
            'iss': issuer,
            'session_id': payload.get('sid'),
        }

    except jwt.ExpiredSignatureError:
        logger.debug("Token verification failed: expired")
        raise TokenExpiredError()

    except jwt.InvalidTokenError as e:
        # Log error type without token content
        logger.debug(f"Token verification failed: {type(e).__name__}")
        raise TokenInvalidError(f"Invalid token: {type(e).__name__}")


def get_jwks_manager() -> ClerkJWKSManager:
    """
    Get the global JWKS manager instance.

    Useful for testing or manual cache invalidation.
    """
    return _jwks_manager


def invalidate_jwks_cache(issuer: Optional[str] = None):
    """
    Invalidate JWKS cache.

    Call this if you need to force a refresh of signing keys
    (e.g., after key rotation).

    Args:
        issuer: Specific issuer to invalidate, or None for all
    """
    _jwks_manager.invalidate(issuer)
    logger.info("JWKS cache invalidated")
