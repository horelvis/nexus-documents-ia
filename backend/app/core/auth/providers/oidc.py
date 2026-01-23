"""
OpenID Connect (OIDC) Authentication Provider.

Supports any OIDC-compliant identity provider:
- KeyCloak
- Azure AD / Entra ID
- Okta
- Auth0
- Google Workspace
- Any OAuth2/OIDC provider

Configuration:
    OIDC_ISSUER=https://your-keycloak.com/realms/your-realm
    OIDC_CLIENT_ID=your-client-id
    OIDC_CLIENT_SECRET=your-client-secret
    OIDC_SCOPES=openid profile email groups

Usage:
    config = {
        "issuer": "https://keycloak.example.com/realms/myrealm",
        "client_id": "my-app",
        "client_secret": "secret",
        "scopes": ["openid", "profile", "email"],
    }
    provider = OIDCAuthProvider(config)
    await provider.initialize()
    identity = await provider.verify_token(access_token)
"""

import logging
import time
from typing import Dict, Any, Optional, List
from urllib.parse import urlencode
import httpx
import jwt
from jwt import PyJWKClient

from app.core.auth.base import (
    AuthProvider,
    AuthProviderType,
    AuthenticatedIdentity,
    AuthProviderError,
    ProviderInitializationError,
)
from app.core.auth.exceptions import (
    TokenExpiredError,
    TokenInvalidError,
)

logger = logging.getLogger(__name__)


class OIDCAuthProvider(AuthProvider):
    """
    OpenID Connect authentication provider.

    Verifies JWT access tokens using the issuer's JWKS endpoint.
    Supports discovery via .well-known/openid-configuration.
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)

        self.issuer = config.get("issuer", "").rstrip("/")
        # Internal issuer for fetching discovery/JWKS (Docker internal DNS)
        # Falls back to issuer if not specified
        self.internal_issuer = config.get("internal_issuer", "").rstrip("/") or self.issuer
        self.client_id = config.get("client_id", "")
        self.client_secret = config.get("client_secret", "")
        self.scopes = config.get("scopes", ["openid", "profile", "email"])

        # Will be populated during initialization
        self._jwks_client: Optional[PyJWKClient] = None
        self._discovery: Dict[str, Any] = {}
        self._jwks_url: Optional[str] = None
        self._token_endpoint: Optional[str] = None
        self._authorization_endpoint: Optional[str] = None
        self._userinfo_endpoint: Optional[str] = None
        self._end_session_endpoint: Optional[str] = None

    @property
    def provider_type(self) -> AuthProviderType:
        return AuthProviderType.OIDC

    @property
    def supports_token_refresh(self) -> bool:
        return True

    async def initialize(self) -> None:
        """
        Initialize the provider by fetching OIDC discovery document.
        """
        if self._initialized:
            return

        if not self.issuer:
            raise ProviderInitializationError("OIDC issuer URL is required")

        try:
            # Fetch discovery document using internal issuer (Docker DNS)
            # This allows token validation to use public issuer while
            # fetching JWKS from internal Docker network
            discovery_url = f"{self.internal_issuer}/.well-known/openid-configuration"
            logger.info(f"Fetching OIDC discovery from {discovery_url} (token issuer: {self.issuer})")

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(discovery_url)
                response.raise_for_status()
                self._discovery = response.json()

            # Extract endpoints - replace public issuer with internal for Docker DNS
            def to_internal_url(url: str) -> str:
                """Replace public issuer hostname with internal issuer for Docker networking."""
                if url and self.issuer and self.internal_issuer and self.issuer != self.internal_issuer:
                    return url.replace(self.issuer, self.internal_issuer)
                return url

            self._jwks_url = to_internal_url(self._discovery.get("jwks_uri", ""))
            self._token_endpoint = to_internal_url(self._discovery.get("token_endpoint", ""))
            # Keep authorization and end_session with public URLs (browser redirects)
            self._authorization_endpoint = self._discovery.get("authorization_endpoint")
            self._userinfo_endpoint = to_internal_url(self._discovery.get("userinfo_endpoint", ""))
            self._end_session_endpoint = self._discovery.get("end_session_endpoint")

            if not self._jwks_url:
                raise ProviderInitializationError("JWKS URI not found in discovery")

            logger.info(f"JWKS URL (internal): {self._jwks_url}")
            logger.info(f"Token endpoint (internal): {self._token_endpoint}")

            # Initialize JWKS client with internal URL
            self._jwks_client = PyJWKClient(self._jwks_url)

            self._initialized = True
            logger.info(f"OIDC provider initialized for issuer: {self.issuer}")

        except httpx.HTTPError as e:
            raise ProviderInitializationError(f"Failed to fetch OIDC discovery: {e}")
        except Exception as e:
            raise ProviderInitializationError(f"OIDC initialization failed: {e}")

    async def verify_token(self, token: str) -> AuthenticatedIdentity:
        """
        Verify a JWT access token and return the authenticated identity.

        Args:
            token: JWT access token

        Returns:
            AuthenticatedIdentity with user information

        Raises:
            TokenExpiredError: Token has expired
            TokenInvalidError: Token is invalid
        """
        if not self._initialized:
            await self.initialize()

        try:
            # Get the signing key from JWKS
            signing_key = self._jwks_client.get_signing_key_from_jwt(token)

            # First, try to verify with audience check
            # KeyCloak and some other IdPs put client_id in 'azp' (authorized party)
            # instead of 'aud' (audience), so we need to handle both cases
            try:
                payload = jwt.decode(
                    token,
                    signing_key.key,
                    algorithms=["RS256", "RS384", "RS512", "ES256", "ES384", "ES512"],
                    audience=self.client_id,
                    issuer=self.issuer,
                    options={
                        "verify_aud": bool(self.client_id),
                        "verify_iss": True,
                        "verify_exp": True,
                    }
                )
            except jwt.InvalidAudienceError:
                # KeyCloak uses 'azp' (authorized party) for client_id
                # Verify without audience, then check azp manually
                logger.debug("Audience check failed, checking azp claim (KeyCloak mode)")
                payload = jwt.decode(
                    token,
                    signing_key.key,
                    algorithms=["RS256", "RS384", "RS512", "ES256", "ES384", "ES512"],
                    issuer=self.issuer,
                    options={
                        "verify_aud": False,  # Skip aud, check azp instead
                        "verify_iss": True,
                        "verify_exp": True,
                    }
                )
                # Verify the authorized party (azp) matches our client_id
                azp = payload.get("azp")
                if self.client_id and azp != self.client_id:
                    logger.debug(f"Token azp '{azp}' doesn't match client_id '{self.client_id}'")
                    raise TokenInvalidError("Invalid authorized party")
                logger.debug(f"Token validated via azp claim: {azp}")

            # Extract identity from claims
            return self._extract_identity(payload)

        except jwt.ExpiredSignatureError:
            logger.debug("OIDC token expired")
            raise TokenExpiredError("Token has expired")

        except jwt.InvalidIssuerError:
            logger.debug("OIDC token has invalid issuer")
            raise TokenInvalidError("Invalid issuer")

        except jwt.InvalidTokenError as e:
            logger.debug(f"OIDC token validation failed: {type(e).__name__}")
            raise TokenInvalidError(f"Invalid token: {type(e).__name__}")

        except TokenInvalidError:
            raise  # Re-raise our own exceptions

        except Exception as e:
            logger.error(f"OIDC token verification error: {e}")
            raise TokenInvalidError(f"Token verification failed: {e}")

    def _extract_identity(self, payload: Dict[str, Any]) -> AuthenticatedIdentity:
        """
        Extract AuthenticatedIdentity from JWT claims.

        Handles various claim names used by different providers.
        """
        # Subject (required)
        subject = payload.get("sub")
        if not subject:
            raise TokenInvalidError("Token missing subject claim")

        # Email (try multiple claim names)
        email = (
            payload.get("email") or
            payload.get("preferred_username") or
            payload.get("upn") or  # Azure AD
            ""
        )

        # Name
        name = payload.get("name")
        given_name = payload.get("given_name")
        family_name = payload.get("family_name")

        # Picture
        picture = payload.get("picture")

        # Groups (try multiple claim names)
        groups = (
            payload.get("groups") or
            payload.get("cognito:groups") or  # AWS Cognito
            payload.get("roles") or  # Some providers use roles
            []
        )
        if isinstance(groups, str):
            groups = [groups]

        # Roles from IdP
        roles = payload.get("roles", [])
        if isinstance(roles, str):
            roles = [roles]

        # Map groups to application roles
        mapped_roles = self.map_groups_to_roles(groups)
        all_roles = list(set(roles + mapped_roles))

        # Session ID
        session_id = payload.get("sid") or payload.get("session_state")

        # Token expiry
        exp = payload.get("exp")
        from datetime import datetime
        token_expiry = datetime.fromtimestamp(exp) if exp else None

        # Tenant hint (custom claim, if present)
        tenant_hint = payload.get("tenant_id") or payload.get("tid")  # Azure AD uses tid

        return AuthenticatedIdentity(
            external_id=subject,
            email=email,
            name=name,
            given_name=given_name,
            family_name=family_name,
            picture_url=picture,
            provider=AuthProviderType.OIDC,
            provider_metadata={
                "issuer": self.issuer,
                "audience": payload.get("aud"),
                "azp": payload.get("azp"),  # Authorized party
            },
            groups=groups,
            roles=all_roles,
            session_id=session_id,
            token_expiry=token_expiry,
            tenant_hint=tenant_hint,
        )

    async def get_user_info(self, identity: AuthenticatedIdentity) -> Dict[str, Any]:
        """
        Get additional user information from the userinfo endpoint.

        Note: This requires the access token, not the identity.
        For most cases, the token claims are sufficient.
        """
        # The identity already contains the essential info from the token
        return identity.to_dict()

    def get_login_url(self, redirect_uri: str, state: Optional[str] = None) -> str:
        """
        Get the authorization URL to initiate OIDC login.

        Args:
            redirect_uri: Where to redirect after login
            state: Optional state parameter for CSRF

        Returns:
            URL to redirect user for login
        """
        if not self._authorization_endpoint:
            raise AuthProviderError("Authorization endpoint not configured")

        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "scope": " ".join(self.scopes),
            "redirect_uri": redirect_uri,
        }

        if state:
            params["state"] = state

        # Add nonce for security
        import secrets
        params["nonce"] = secrets.token_urlsafe(16)

        return f"{self._authorization_endpoint}?{urlencode(params)}"

    def get_logout_url(self, redirect_uri: Optional[str] = None) -> Optional[str]:
        """
        Get the end session URL for logout.

        Args:
            redirect_uri: Where to redirect after logout

        Returns:
            Logout URL or None if not supported
        """
        if not self._end_session_endpoint:
            return None

        params = {}
        if redirect_uri:
            params["post_logout_redirect_uri"] = redirect_uri
        if self.client_id:
            params["client_id"] = self.client_id

        if params:
            return f"{self._end_session_endpoint}?{urlencode(params)}"
        return self._end_session_endpoint

    async def refresh_token(self, refresh_token: str) -> Dict[str, str]:
        """
        Refresh an access token using the refresh token.

        Args:
            refresh_token: The refresh token

        Returns:
            Dictionary with access_token and optionally refresh_token
        """
        if not self._token_endpoint:
            raise AuthProviderError("Token endpoint not configured")

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    self._token_endpoint,
                    data={
                        "grant_type": "refresh_token",
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                        "refresh_token": refresh_token,
                    },
                )
                response.raise_for_status()
                data = response.json()

                return {
                    "access_token": data["access_token"],
                    "refresh_token": data.get("refresh_token", refresh_token),
                    "expires_in": data.get("expires_in"),
                }

        except httpx.HTTPError as e:
            raise AuthProviderError(f"Token refresh failed: {e}")

    async def exchange_code(self, code: str, redirect_uri: str) -> Dict[str, Any]:
        """
        Exchange authorization code for tokens.

        Args:
            code: Authorization code from callback
            redirect_uri: Must match the one used in login URL

        Returns:
            Token response with access_token, refresh_token, id_token
        """
        if not self._token_endpoint:
            raise AuthProviderError("Token endpoint not configured")

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    self._token_endpoint,
                    data={
                        "grant_type": "authorization_code",
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                        "code": code,
                        "redirect_uri": redirect_uri,
                    },
                )
                response.raise_for_status()
                return response.json()

        except httpx.HTTPError as e:
            raise AuthProviderError(f"Code exchange failed: {e}")
