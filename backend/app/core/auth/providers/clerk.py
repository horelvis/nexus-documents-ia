"""
Clerk Authentication Provider.

Wrapper around the existing Clerk verification logic,
implementing the AuthProvider interface for compatibility.

This is used in SaaS mode when DEPLOYMENT_MODE=saas.

Usage:
    config = {
        "secret_key": "sk_live_...",
    }
    provider = ClerkAuthProvider(config)
    await provider.initialize()
    identity = await provider.verify_token(jwt_token)
"""

import logging
from typing import Dict, Any, Optional

from app.core.auth.base import (
    AuthProvider,
    AuthProviderType,
    AuthenticatedIdentity,
)
from app.core.auth.exceptions import (
    TokenMissingError,
    TokenExpiredError,
    TokenInvalidError,
    ClerkConfigError,
)

# Import the existing Clerk verification logic
from app.core.auth.clerk import verify_clerk_token, ClerkJWKSManager

logger = logging.getLogger(__name__)


class ClerkAuthProvider(AuthProvider):
    """
    Clerk authentication provider.

    Wraps the existing Clerk JWT verification to implement
    the AuthProvider interface.
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.secret_key = config.get("secret_key", "")
        self._jwks_manager: Optional[ClerkJWKSManager] = None

    @property
    def provider_type(self) -> AuthProviderType:
        return AuthProviderType.CLERK

    @property
    def supports_token_refresh(self) -> bool:
        # Clerk handles session management client-side
        return False

    async def initialize(self) -> None:
        """
        Initialize the Clerk provider.

        Clerk doesn't require explicit initialization beyond
        having the secret key configured.
        """
        if self._initialized:
            return

        from app.core.config import settings

        # Use settings if not provided in config
        if not self.secret_key:
            self.secret_key = settings.CLERK_SECRET_KEY

        if not self.secret_key:
            raise ClerkConfigError("Clerk secret key not configured")

        self._initialized = True
        logger.info("Clerk provider initialized")

    async def verify_token(self, token: str) -> AuthenticatedIdentity:
        """
        Verify a Clerk JWT token.

        Args:
            token: JWT token from Clerk

        Returns:
            AuthenticatedIdentity with user information

        Raises:
            TokenExpiredError: Token has expired
            TokenInvalidError: Token is invalid
        """
        if not self._initialized:
            await self.initialize()

        if not token:
            raise TokenMissingError("No token provided")

        # Use existing verification logic
        payload = verify_clerk_token(token)

        # Extract identity from Clerk payload
        return AuthenticatedIdentity(
            external_id=payload["sub"],
            email="",  # Clerk JWT doesn't include email, get from API if needed
            provider=AuthProviderType.CLERK,
            provider_metadata={
                "issuer": payload.get("iss"),
            },
            session_id=payload.get("session_id"),
        )

    async def get_user_info(self, identity: AuthenticatedIdentity) -> Dict[str, Any]:
        """
        Get user information from Clerk API.

        Note: This requires a backend API call to Clerk, which is
        typically handled by the webhook flow instead.
        """
        # In the current flow, user info comes from the database
        # after being synced via Clerk webhooks
        return identity.to_dict()

    def get_login_url(self, redirect_uri: str, state: Optional[str] = None) -> str:
        """
        Get Clerk login URL.

        Clerk uses its own hosted UI, so this returns
        the path to the Clerk sign-in page.
        """
        # Clerk handles login through its React components
        # Return the app's sign-in route
        return "/auth/sign-in"

    def get_logout_url(self, redirect_uri: Optional[str] = None) -> Optional[str]:
        """
        Get Clerk logout URL.

        Clerk handles logout through its React components.
        """
        return "/auth/sign-in"
