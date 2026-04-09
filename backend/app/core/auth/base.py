"""
Base classes for authentication providers.

This module defines the abstract interface for authentication providers,
allowing pluggable authentication backends (Clerk, OIDC, SAML, LDAP).

Usage:
    from app.core.auth.base import AuthProvider, AuthenticatedIdentity

    class MyProvider(AuthProvider):
        async def verify_token(self, token: str) -> AuthenticatedIdentity:
            ...
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from datetime import datetime
from enum import Enum


class AuthProviderType(Enum):
    """Supported authentication provider types."""
    CLERK = "clerk"
    OIDC = "oidc"
    SAML = "saml"
    LDAP = "ldap"


@dataclass
class AuthenticatedIdentity:
    """
    Normalized identity from any authentication provider.

    This is the common format that all auth providers must return,
    regardless of the underlying authentication mechanism.
    """

    # Core identity
    external_id: str  # ID in the external auth system
    email: str

    # Profile info (may be empty depending on provider)
    name: Optional[str] = None
    given_name: Optional[str] = None
    family_name: Optional[str] = None
    picture_url: Optional[str] = None

    # Provider info
    provider: AuthProviderType = AuthProviderType.CLERK
    provider_metadata: Dict[str, Any] = field(default_factory=dict)

    # Groups/roles from IdP (for role mapping)
    groups: List[str] = field(default_factory=list)
    roles: List[str] = field(default_factory=list)

    # Token info
    session_id: Optional[str] = None
    token_expiry: Optional[datetime] = None

    def get_full_name(self) -> str:
        """Get full name, constructing from parts if needed."""
        if self.name:
            return self.name
        parts = []
        if self.given_name:
            parts.append(self.given_name)
        if self.family_name:
            parts.append(self.family_name)
        return " ".join(parts) if parts else self.email.split("@")[0]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "external_id": self.external_id,
            "email": self.email,
            "name": self.get_full_name(),
            "given_name": self.given_name,
            "family_name": self.family_name,
            "picture_url": self.picture_url,
            "provider": self.provider.value,
            "groups": self.groups,
            "roles": self.roles,
            "session_id": self.session_id,
        }


class AuthProvider(ABC):
    """
    Abstract base class for authentication providers.

    All authentication providers (Clerk, OIDC, SAML, LDAP) must implement
    this interface to be usable with the auth factory.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize provider with configuration.

        Args:
            config: Provider-specific configuration dictionary
        """
        self.config = config
        self._initialized = False

    @property
    @abstractmethod
    def provider_type(self) -> AuthProviderType:
        """Return the provider type."""
        pass

    @property
    @abstractmethod
    def supports_token_refresh(self) -> bool:
        """Whether this provider supports token refresh."""
        pass

    @abstractmethod
    async def initialize(self) -> None:
        """
        Initialize the provider (load keys, connect to servers, etc).

        Called once when the provider is first used.
        """
        pass

    @abstractmethod
    async def verify_token(self, token: str) -> AuthenticatedIdentity:
        """
        Verify a token and return the authenticated identity.

        Args:
            token: The authentication token (JWT, SAML assertion, etc)

        Returns:
            AuthenticatedIdentity with user information

        Raises:
            TokenExpiredError: Token has expired
            TokenInvalidError: Token is invalid or malformed
            AuthProviderError: Other provider-specific errors
        """
        pass

    @abstractmethod
    async def get_user_info(self, identity: AuthenticatedIdentity) -> Dict[str, Any]:
        """
        Get additional user information from the provider.

        Args:
            identity: The authenticated identity

        Returns:
            Dictionary with additional user attributes
        """
        pass

    @abstractmethod
    def get_login_url(self, redirect_uri: str, state: Optional[str] = None) -> str:
        """
        Get the URL to initiate login flow.

        Args:
            redirect_uri: Where to redirect after login
            state: Optional state parameter for CSRF protection

        Returns:
            URL to redirect the user for login
        """
        pass

    @abstractmethod
    def get_logout_url(self, redirect_uri: Optional[str] = None) -> Optional[str]:
        """
        Get the URL to initiate logout flow (if supported).

        Args:
            redirect_uri: Where to redirect after logout

        Returns:
            URL for logout, or None if not supported
        """
        pass

    async def refresh_token(self, refresh_token: str) -> Dict[str, str]:
        """
        Refresh an access token using a refresh token.

        Args:
            refresh_token: The refresh token

        Returns:
            Dictionary with new access_token and optionally new refresh_token

        Raises:
            NotImplementedError: If provider doesn't support refresh
        """
        raise NotImplementedError(
            f"{self.provider_type.value} does not support token refresh"
        )

    async def validate_session(self, session_id: str) -> bool:
        """
        Validate that a session is still active.

        Args:
            session_id: The session identifier

        Returns:
            True if session is valid, False otherwise
        """
        # Default implementation - override in providers that track sessions
        return True

    def map_groups_to_roles(self, groups: List[str]) -> List[str]:
        """
        Map IdP groups to application roles.

        Uses the group_role_mapping configuration if available.

        Args:
            groups: List of group names from IdP

        Returns:
            List of application role names
        """
        mapping = self.config.get("group_role_mapping", {})
        roles = []

        for group in groups:
            if group in mapping:
                mapped = mapping[group]
                if isinstance(mapped, list):
                    roles.extend(mapped)
                else:
                    roles.append(mapped)

        return list(set(roles))  # Remove duplicates


class AuthProviderError(Exception):
    """Base exception for auth provider errors."""
    pass


class ProviderNotConfiguredError(AuthProviderError):
    """Provider is not properly configured."""
    pass


class ProviderInitializationError(AuthProviderError):
    """Failed to initialize provider."""
    pass


@dataclass(frozen=True)
class UserProfile:
    """Request-scoped immutable view of an authenticated user.

    Built once per request from the JWT (in Plan 2 of the multi-tenancy
    removal refactor — currently dormant). Carries the canonical role
    identifiers from `map_groups_to_roles()`, not raw KeyCloak group names.

    The `roles` field is a list of strings (e.g. ['LEGAL', 'SALES']).
    The reserved value 'EVERYONE' is NEVER present here — it is a wildcard
    used only on the document side. See `app.core.auth.acl` for usage.
    """

    sub: str
    email: str
    name: Optional[str] = None
    roles: List[str] = field(default_factory=list)
