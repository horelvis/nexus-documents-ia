import logging
from typing import Generic, TypeVar

from app.providers.base import ExtractionProvider, EmbeddingProvider, EntityProvider

T = TypeVar("T", ExtractionProvider, EmbeddingProvider, EntityProvider)
logger = logging.getLogger(__name__)


class ProviderRegistry(Generic[T]):
    """Ordered registry of providers with automatic fallback."""

    def __init__(self):
        self._providers: list[T] = []

    def register(self, provider: T) -> None:
        self._providers.append(provider)

    def all(self) -> list[T]:
        return list(self._providers)

    async def get_available(self) -> T:
        """Return the first available provider, or raise RuntimeError."""
        for provider in self._providers:
            try:
                if await provider.is_available():
                    return provider
            except Exception as e:
                logger.warning(f"Provider {provider.name} availability check failed: {e}")
        names = [p.name for p in self._providers]
        raise RuntimeError(f"No provider available. Tried: {names}")

    async def status(self) -> list[dict]:
        """Return availability status of all providers."""
        result = []
        for provider in self._providers:
            try:
                available = await provider.is_available()
            except Exception:
                available = False
            result.append({"name": provider.name, "available": available})
        return result
