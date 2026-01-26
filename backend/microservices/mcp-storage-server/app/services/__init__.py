"""Storage services."""

from app.core.config import settings

from .gcs_service import GCSService, get_gcs_service
from .local_service import LocalStorageService, get_local_service


def get_storage_service():
    """
    Get the appropriate storage service based on configuration.

    Returns:
        GCSService or LocalStorageService depending on STORAGE_PROVIDER env var
    """
    if settings.storage_provider.lower() == "local":
        return get_local_service()
    else:
        return get_gcs_service()


__all__ = [
    "GCSService",
    "get_gcs_service",
    "LocalStorageService",
    "get_local_service",
    "get_storage_service",
]
