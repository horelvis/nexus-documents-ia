"""
Feature Flags API endpoints.

Exposes feature flag state to the frontend for conditional UI rendering.
"""

from fastapi import APIRouter, Depends
from typing import Dict, Optional
from pydantic import BaseModel

from app.core.features import Feature, FeatureFlags
from app.api.async_dependencies import get_current_tenant_id_async

router = APIRouter(prefix="/features", tags=["features"])


class FeatureFlagsResponse(BaseModel):
    """Response model for feature flags."""

    deployment_mode: str
    features: Dict[str, bool]
    enabled: list[str]
    disabled: list[str]


class FeatureCheckResponse(BaseModel):
    """Response model for single feature check."""

    feature: str
    enabled: bool


@router.get("", response_model=FeatureFlagsResponse)
async def get_features(
    tenant_id: Optional[str] = Depends(get_current_tenant_id_async),
) -> FeatureFlagsResponse:
    """
    Get all feature flags for the current tenant.

    Returns the deployment mode and state of all features.
    Used by frontend to conditionally render UI components.
    """
    return FeatureFlagsResponse(
        deployment_mode=FeatureFlags.get_deployment_mode(),
        features=FeatureFlags.get_all(tenant_id),
        enabled=FeatureFlags.get_enabled_features(tenant_id),
        disabled=FeatureFlags.get_disabled_features(tenant_id),
    )


@router.get("/{feature_name}", response_model=FeatureCheckResponse)
async def check_feature(
    feature_name: str,
    tenant_id: Optional[str] = Depends(get_current_tenant_id_async),
) -> FeatureCheckResponse:
    """
    Check if a specific feature is enabled.

    Args:
        feature_name: The feature name (e.g., "digital_signatures")

    Returns:
        The feature name and whether it's enabled.
    """
    try:
        feature = Feature(feature_name)
        enabled = FeatureFlags.is_enabled(feature, tenant_id)
    except ValueError:
        # Unknown feature, return as disabled
        enabled = False

    return FeatureCheckResponse(
        feature=feature_name,
        enabled=enabled,
    )


@router.get("/mode/info")
async def get_deployment_info() -> Dict[str, str]:
    """
    Get deployment mode information.

    Returns basic deployment information without requiring authentication.
    Useful for login page customization.
    """
    mode = FeatureFlags.get_deployment_mode()

    return {
        "deployment_mode": mode,
        "auth_provider": "sso" if mode == "on_premise" else "clerk",
        "emma_mode": "fullscreen" if FeatureFlags.is_enabled(Feature.EMMA_FULLSCREEN_MODE) else "sidebar",
    }
