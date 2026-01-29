"""Services for Emma Agent Service"""

# Note: Imports are done lazily to avoid circular dependencies
# Use: from app.services.emma_service import EmmaService, emma_service


def get_emma_service():
    """Get the Emma service singleton (lazy import)."""
    from .emma_service import emma_service
    return emma_service


def get_persistence_service():
    """Get the persistence service (lazy import)."""
    from .emma_persistence_service import EmmaPersistenceService
    return EmmaPersistenceService()


__all__ = [
    "get_emma_service",
    "get_persistence_service",
]
