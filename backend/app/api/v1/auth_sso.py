"""
SSO Authentication Endpoints.

Provides endpoints for OIDC/SAML/LDAP authentication flows
in on-premise deployment mode.

These endpoints are only active when:
- DEPLOYMENT_MODE=on_premise
- SSO_MULTI_PROTOCOL feature flag is enabled
"""

import logging
from typing import Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status, Request, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from app.db.async_database import get_async_db
from app.core.auth.factory import AuthProviderFactory
from app.core.auth.base import AuthProviderError
from app.core.auth.exceptions import TokenExpiredError, TokenInvalidError
from app.db.models import User
from app.core.config import settings
from app.core.features import Feature, FeatureFlags

logger = logging.getLogger(__name__)


class SSOLoginRequest(BaseModel):
    """Request for SSO login with JIT provisioning."""
    access_token: str
    id_token: Optional[str] = None


class SSOUserResponse(BaseModel):
    """User data response from SSO login."""
    id: str
    email: str
    full_name: Optional[str]
    is_active: bool
    onboarding_completed: bool
    is_new_user: bool = False
    sso_provider: Optional[str] = None
    sso_groups: list = []


router = APIRouter(prefix="/sso", tags=["sso-auth"])


class LoginURLResponse(BaseModel):
    """Response for login URL request."""
    login_url: str
    provider: str


class LogoutURLResponse(BaseModel):
    """Response for logout URL request."""
    logout_url: Optional[str]
    provider: str


class TokenCallbackRequest(BaseModel):
    """Request for OAuth callback."""
    code: str
    state: Optional[str] = None
    redirect_uri: str


class TokenCallbackResponse(BaseModel):
    """Response from token exchange."""
    access_token: str
    refresh_token: Optional[str] = None
    id_token: Optional[str] = None
    token_type: str = "Bearer"
    expires_in: int = 3600


class TokenRefreshRequest(BaseModel):
    """Request for token refresh."""
    refresh_token: str


class TokenRefreshResponse(BaseModel):
    """Response from token refresh."""
    access_token: str
    refresh_token: Optional[str] = None
    expires_in: int = 3600


@router.get("/login-url", response_model=LoginURLResponse)
async def get_login_url(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """
    Get SSO login URL for the configured provider.

    Returns the authorization URL to redirect the user for SSO login.
    Uses the tenant's configured auth provider or the default provider.
    """
    try:
        # Get the auth provider for the tenant (or default)
        provider = await AuthProviderFactory.get_default()

        # Build redirect URI from request
        origin = request.headers.get("origin") or str(request.base_url).rstrip("/")
        redirect_uri = f"{origin}/auth/callback"

        # Generate state for CSRF protection
        import secrets
        state = secrets.token_urlsafe(16)

        # Get login URL from provider
        login_url = provider.get_login_url(redirect_uri, state)

        return LoginURLResponse(
            login_url=login_url,
            provider=provider.provider_type.value,
        )

    except AuthProviderError as e:
        logger.error(f"SSO login URL error: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"SSO provider not configured: {e}",
        )
    except Exception as e:
        logger.error(f"Unexpected error getting login URL: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate login URL",
        )


@router.post("/callback", response_model=TokenCallbackResponse)
async def handle_callback(
    callback: TokenCallbackRequest,
    db: AsyncSession = Depends(get_async_db),
):
    """
    Handle OAuth callback and exchange code for tokens.

    This endpoint receives the authorization code from the SSO provider
    and exchanges it for access/refresh/id tokens.
    """
    try:
        # Get the auth provider
        provider = await AuthProviderFactory.get_default()

        # Check if provider supports code exchange
        if not hasattr(provider, "exchange_code"):
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail="Provider does not support code exchange",
            )

        # Exchange code for tokens
        token_response = await provider.exchange_code(
            code=callback.code,
            redirect_uri=callback.redirect_uri,
        )

        # Calculate expires_in if not provided
        expires_in = token_response.get("expires_in", 3600)

        return TokenCallbackResponse(
            access_token=token_response["access_token"],
            refresh_token=token_response.get("refresh_token"),
            id_token=token_response.get("id_token"),
            token_type=token_response.get("token_type", "Bearer"),
            expires_in=expires_in,
        )

    except AuthProviderError as e:
        logger.error(f"SSO callback error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token exchange failed: {e}",
        )
    except Exception as e:
        logger.error(f"Unexpected error in callback: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process authentication callback",
        )


@router.post("/refresh", response_model=TokenRefreshResponse)
async def refresh_tokens(
    refresh_req: TokenRefreshRequest,
    db: AsyncSession = Depends(get_async_db),
):
    """
    Refresh access token using refresh token.

    Returns a new access token (and optionally a new refresh token).
    """
    try:
        # Get the auth provider
        provider = await AuthProviderFactory.get_default()

        # Check if provider supports token refresh
        if not provider.supports_token_refresh:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail="Provider does not support token refresh",
            )

        if not hasattr(provider, "refresh_token"):
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail="Provider does not implement token refresh",
            )

        # Refresh the tokens
        token_response = await provider.refresh_token(refresh_req.refresh_token)

        return TokenRefreshResponse(
            access_token=token_response["access_token"],
            refresh_token=token_response.get("refresh_token"),
            expires_in=token_response.get("expires_in", 3600),
        )

    except TokenExpiredError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has expired",
        )
    except TokenInvalidError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid refresh token: {e}",
        )
    except AuthProviderError as e:
        logger.error(f"SSO refresh error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token refresh failed: {e}",
        )
    except Exception as e:
        logger.error(f"Unexpected error in token refresh: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to refresh token",
        )


@router.get("/logout-url", response_model=LogoutURLResponse)
async def get_logout_url(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """
    Get SSO logout URL.

    Returns the end session URL if the provider supports it,
    or null if logout should be handled locally only.
    """
    try:
        # Get the auth provider
        provider = await AuthProviderFactory.get_default()

        # Build redirect URI for post-logout redirect
        origin = request.headers.get("origin") or str(request.base_url).rstrip("/")
        redirect_uri = f"{origin}/auth/sign-in"

        # Get logout URL from provider
        logout_url = provider.get_logout_url(redirect_uri)

        return LogoutURLResponse(
            logout_url=logout_url,
            provider=provider.provider_type.value,
        )

    except AuthProviderError as e:
        logger.error(f"SSO logout URL error: {e}")
        # Return null logout URL, client will handle locally
        return LogoutURLResponse(logout_url=None, provider="unknown")
    except Exception as e:
        logger.error(f"Unexpected error getting logout URL: {e}")
        return LogoutURLResponse(logout_url=None, provider="unknown")


@router.get("/provider-info")
async def get_provider_info(
    db: AsyncSession = Depends(get_async_db),
):
    """
    Get information about the configured SSO provider.

    Returns provider type and capabilities.
    """
    try:
        provider = await AuthProviderFactory.get_default()

        return {
            "provider_type": provider.provider_type.value,
            "supports_token_refresh": provider.supports_token_refresh,
            "is_initialized": provider._initialized,
        }

    except AuthProviderError as e:
        return {
            "provider_type": "none",
            "supports_token_refresh": False,
            "is_initialized": False,
            "error": str(e),
        }


# =============================================================================
# JIT Provisioning Login Endpoint
# =============================================================================

@router.post("/login", response_model=SSOUserResponse)
async def sso_login(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    authorization: Optional[str] = Header(None, alias="Authorization"),
):
    """
    SSO Login with JIT (Just-In-Time) Provisioning.

    This endpoint:
    1. Validates the SSO access/id token
    2. Extracts user info from token claims
    3. Finds or creates user in database (JIT provisioning)
    4. Returns user data

    For on-premise deployments with enterprise SSO.
    """
    # 1. Validate Authorization header
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
            headers={"WWW-Authenticate": "Bearer"}
        )

    access_token = authorization.split(" ")[1]

    # 2. Get auth provider and validate token
    try:
        provider = await AuthProviderFactory.get_default()

        # Validate the access token and get user info
        # Check for verify_token first (OIDC provider uses this)
        if hasattr(provider, "verify_token"):
            identity = await provider.verify_token(access_token)
            # Convert AuthenticatedIdentity to dict for uniform handling
            # Prefer constructing from parts — handles KeyCloak sending only surname as name claim
            if identity.given_name and identity.family_name:
                _name = f"{identity.given_name} {identity.family_name}"
            elif identity.given_name:
                _name = identity.given_name
            else:
                _name = identity.name or identity.family_name or ""
            user_info = {
                "sub": identity.external_id,
                "email": identity.email,
                "name": _name.strip(),
                "groups": identity.groups or [],
            }
        elif hasattr(provider, "validate_token"):
            user_info = await provider.validate_token(access_token)
        elif hasattr(provider, "get_userinfo"):
            user_info = await provider.get_userinfo(access_token)
        else:
            # Fallback: decode JWT to get claims (no signature verification)
            import jwt
            try:
                decoded = jwt.decode(access_token, options={"verify_signature": False})
                given = decoded.get("given_name", "")
                family = decoded.get("family_name", "")
                if given and family:
                    _decoded_name = f"{given} {family}"
                elif given:
                    _decoded_name = given
                else:
                    _decoded_name = decoded.get("name") or family or ""
                user_info = {
                    "sub": decoded.get("sub"),
                    "email": decoded.get("email") or decoded.get("preferred_username"),
                    "name": _decoded_name.strip(),
                    "groups": decoded.get("groups", []),
                }
            except jwt.InvalidTokenError as e:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=f"Invalid token: {e}"
                )

    except TokenExpiredError:
        logger.debug("SSO token expired")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        )
    except TokenInvalidError as e:
        logger.debug(f"SSO token invalid: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {e}",
        )
    except AuthProviderError as e:
        logger.error(f"SSO token validation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token validation failed: {e}",
        )

    # 3. Extract user information
    sso_external_id = user_info.get("sub")
    email = user_info.get("email")
    full_name = user_info.get("name", "").strip()
    groups = user_info.get("groups", [])

    if not sso_external_id or not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing required claims (sub, email)",
        )

    # 4. Find or create user (JIT Provisioning)
    is_new_user = False

    # Try to find by sso_external_id first
    result = await db.execute(
        select(User).where(User.sso_external_id == sso_external_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        # Try to find by email (might be pre-provisioned)
        result = await db.execute(
            select(User).where(User.email == email)
        )
        user = result.scalar_one_or_none()

    if user:
        # Update SSO fields if not set
        if not user.sso_external_id:
            user.sso_external_id = sso_external_id
        if not user.sso_provider:
            user.sso_provider = provider.provider_type.value
        # JIT-update full_name on each login (handles KeyCloak name fixes)
        if full_name and full_name != user.full_name:
            user.full_name = full_name
        user.sso_groups = groups
        user.last_login_at = datetime.utcnow()
        await db.commit()
        await db.refresh(user)
    else:
        # JIT Provisioning - Create new user
        is_new_user = True

        # Create new user
        from uuid import uuid4
        import secrets
        from passlib.context import CryptContext

        # Generate a random password hash for SSO users (they won't use it)
        pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        random_password_hash = pwd_context.hash(secrets.token_urlsafe(32))

        user = User(
            id=uuid4(),
            email=email,
            hashed_password=random_password_hash,  # Required by DB, but unused for SSO
            full_name=full_name if full_name else email.split("@")[0],
            sso_external_id=sso_external_id,
            sso_provider=provider.provider_type.value,
            sso_groups=groups,
            is_active=True,
            onboarding_completed=False,
            created_at=datetime.now(timezone.utc),
        )

        db.add(user)
        await db.commit()
        await db.refresh(user)

        logger.info(f"✅ JIT Provisioned new user: {user.id} ({email}) from SSO")

    # 5. Check if user is active
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )

    logger.info(f"✅ SSO Login successful for user {user.id} - New: {is_new_user}")

    return SSOUserResponse(
        id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        onboarding_completed=user.onboarding_completed,
        is_new_user=is_new_user,
        sso_provider=user.sso_provider,
        sso_groups=user.sso_groups or [],
    )
