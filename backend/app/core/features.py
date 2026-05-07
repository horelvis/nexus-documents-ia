"""
Feature Flags System for NouxCubeIA.

This module provides centralized control over which features are enabled/disabled.
On-premise single-tenant: flags are deployment-wide.

Features can be controlled via:
1. Environment variables (FEATURE_<NAME>=true/false)
2. On-premise defaults defined here

Usage:
    from app.core.features import Feature, FeatureFlags

    if FeatureFlags.is_enabled(Feature.DIGITAL_SIGNATURES):
        # Include signatures router
        pass

    # Get all feature states
    features = FeatureFlags.get_all()
"""

import os
import logging
from enum import Enum
from typing import Optional, Dict

logger = logging.getLogger(__name__)


class Feature(Enum):
    """
    Available features that can be toggled.

    Naming convention: FEATURE_NAME matches environment variable FEATURE_<FEATURE_NAME>
    """

    # === Modules to DISABLE for on-premise Emma-centric deployment ===

    # Digital signatures workflow (DocuSign, Adobe Sign, etc.)
    DIGITAL_SIGNATURES = "digital_signatures"

    # External site portal for guest access
    SITE_PORTAL = "site_portal"

    # Dashboard with analytics and statistics
    DASHBOARD_ANALYTICS = "dashboard_analytics"

    # Elasticsearch service for full-text search
    ELASTICSEARCH_SEARCH = "elasticsearch_search"

    # Document editing (template editor)
    DOCUMENT_EDITING = "document_editing"

    # Document library UI (list view, folders, etc.)
    DOCUMENT_LIBRARY_UI = "document_library_ui"

    # === Modules to ENABLE for on-premise Emma-centric deployment ===

    # Emma fullscreen mode (main UI)
    EMMA_FULLSCREEN_MODE = "emma_fullscreen_mode"

    # Multi-protocol SSO (SAML, OIDC, LDAP)
    SSO_MULTI_PROTOCOL = "sso_multi_protocol"

    # SharePoint connector
    SHAREPOINT_CONNECTOR = "sharepoint_connector"

    # OneDrive connector
    ONEDRIVE_CONNECTOR = "onedrive_connector"

    # Google Workspace connector
    GOOGLE_WORKSPACE_CONNECTOR = "google_workspace_connector"

    # Weaviate hybrid search (BM25 + vector)
    WEAVIATE_HYBRID_SEARCH = "weaviate_hybrid_search"


class DeploymentMode(Enum):
    """Supported deployment mode."""

    ON_PREMISE = "on_premise"


# Default feature states for the only supported runtime mode.
_ON_PREMISE_DEFAULTS: Dict[Feature, bool] = {
    Feature.DIGITAL_SIGNATURES: False,
    Feature.SITE_PORTAL: False,
    Feature.DASHBOARD_ANALYTICS: False,
    Feature.ELASTICSEARCH_SEARCH: False,
    Feature.DOCUMENT_EDITING: False,
    Feature.DOCUMENT_LIBRARY_UI: False,
    Feature.EMMA_FULLSCREEN_MODE: True,
    Feature.SSO_MULTI_PROTOCOL: True,
    Feature.SHAREPOINT_CONNECTOR: True,
    Feature.ONEDRIVE_CONNECTOR: True,
    Feature.GOOGLE_WORKSPACE_CONNECTOR: True,
    Feature.WEAVIATE_HYBRID_SEARCH: True,
}


class FeatureFlags:
    """
    Centralized feature flag management.

    Priority order (highest to lowest):
    1. Environment variable override
    2. On-premise defaults
    """

    @classmethod
    def _get_deployment_mode(cls) -> DeploymentMode:
        """Return the supported deployment mode.

        Unsupported historical values are treated as on-premise to avoid
        reactivating removed code paths through configuration drift.
        """
        mode_str = os.getenv("DEPLOYMENT_MODE", "on_premise").lower()
        if mode_str != DeploymentMode.ON_PREMISE.value:
            logger.warning(
                "Unsupported DEPLOYMENT_MODE=%r ignored; using on_premise",
                mode_str,
            )
        return DeploymentMode.ON_PREMISE

    @classmethod
    def _get_mode_default(cls, feature: Feature) -> bool:
        """Get the on-premise default value for a feature."""
        return _ON_PREMISE_DEFAULTS.get(feature, False)

    @classmethod
    def _get_env_override(cls, feature: Feature) -> Optional[bool]:
        """Check for environment variable override."""
        env_key = f"FEATURE_{feature.value.upper()}"
        env_value = os.getenv(env_key)

        if env_value is None:
            return None

        return env_value.lower() in ("true", "1", "yes", "on")

    @classmethod
    def is_enabled(cls, feature: Feature) -> bool:
        """
        Check if a feature is enabled.

        Args:
            feature: The feature to check

        Returns:
            True if the feature is enabled, False otherwise

        Example:
            if FeatureFlags.is_enabled(Feature.DIGITAL_SIGNATURES):
                api_router.include_router(signatures.router)
        """
        # Priority 1: Environment variable
        env_override = cls._get_env_override(feature)
        if env_override is not None:
            return env_override

        # Priority 2: Deployment mode default
        return cls._get_mode_default(feature)

    @classmethod
    def get_all(cls) -> Dict[str, bool]:
        """
        Get state of all features.

        Returns:
            Dictionary mapping feature names to their enabled state

        Example:
            features = FeatureFlags.get_all()
            # {"digital_signatures": False, "emma_fullscreen_mode": True, ...}
        """
        return {
            feature.value: cls.is_enabled(feature)
            for feature in Feature
        }

    @classmethod
    def get_deployment_mode(cls) -> str:
        """Get current deployment mode as string."""
        return cls._get_deployment_mode().value

    @classmethod
    def get_disabled_features(cls) -> list[str]:
        """Get list of disabled feature names."""
        all_features = cls.get_all()
        return [name for name, enabled in all_features.items() if not enabled]

    @classmethod
    def get_enabled_features(cls) -> list[str]:
        """Get list of enabled feature names."""
        all_features = cls.get_all()
        return [name for name, enabled in all_features.items() if enabled]


# Convenience functions for common checks
def is_on_premise_mode() -> bool:
    """Check if running in on-premise mode."""
    return FeatureFlags.get_deployment_mode() == DeploymentMode.ON_PREMISE.value


def signatures_enabled() -> bool:
    """Check if digital signatures are enabled."""
    return FeatureFlags.is_enabled(Feature.DIGITAL_SIGNATURES)


def elasticsearch_enabled() -> bool:
    """Check if Elasticsearch is enabled."""
    return FeatureFlags.is_enabled(Feature.ELASTICSEARCH_SEARCH)


def emma_fullscreen_enabled() -> bool:
    """Check if Emma fullscreen mode is enabled."""
    return FeatureFlags.is_enabled(Feature.EMMA_FULLSCREEN_MODE)


def sso_enabled() -> bool:
    """Check if multi-protocol SSO is enabled."""
    return FeatureFlags.is_enabled(Feature.SSO_MULTI_PROTOCOL)
