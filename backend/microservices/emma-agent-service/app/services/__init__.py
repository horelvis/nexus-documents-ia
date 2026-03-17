"""Services for Emma Agent Service"""

# Note: Imports are done lazily to avoid circular dependencies


def get_persistence_service():
    """Get the persistence service (lazy import)."""
    from .emma_persistence_service import EmmaPersistenceService
    return EmmaPersistenceService()


__all__ = [
    "get_persistence_service",
]
