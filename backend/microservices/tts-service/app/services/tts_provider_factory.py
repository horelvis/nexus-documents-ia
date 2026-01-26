"""
TTS Provider Factory

Factory pattern for selecting and managing TTS providers.
Supports VibeVoice (primary) and Google Cloud TTS (fallback).
"""

import logging
from abc import ABC, abstractmethod
from typing import AsyncGenerator, List, Optional, Protocol, runtime_checkable

from app.core.config import settings
from app.schemas.tts import VoiceInfo

logger = logging.getLogger(__name__)


@runtime_checkable
class TTSProvider(Protocol):
    """Protocol defining the TTS provider interface."""

    async def initialize(self) -> bool:
        """Initialize the provider."""
        ...

    @property
    def is_initialized(self) -> bool:
        """Check if provider is ready."""
        ...

    def get_available_voices(self) -> List[VoiceInfo]:
        """Get available voices."""
        ...

    async def synthesize(
        self,
        text: str,
        voice_id: str,
        language: str,
        speed: float
    ) -> tuple[bytes, int]:
        """Synthesize text to speech."""
        ...

    async def stream_synthesize(
        self,
        text: str,
        voice_id: str,
        language: str
    ) -> AsyncGenerator[bytes, None]:
        """Stream synthesize text to speech."""
        ...

    def check_gpu_available(self) -> bool:
        """Check GPU availability."""
        ...


class TTSProviderFactory:
    """
    Factory for creating and managing TTS providers.

    Handles provider selection and initialization based on configuration.
    """

    _instance: Optional["TTSProviderFactory"] = None
    _provider: Optional[TTSProvider] = None
    _provider_name: str = ""

    def __new__(cls):
        """Singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    async def get_provider(cls) -> TTSProvider:
        """
        Get the configured TTS provider.

        Returns initialized provider based on settings.

        Returns:
            TTSProvider instance
        """
        factory = cls()

        if factory._provider is not None and factory._provider.is_initialized:
            return factory._provider

        provider_name = settings.tts_provider.lower()
        logger.info(f"Initializing TTS provider: {provider_name}")

        if provider_name == "vibevoice":
            provider = await factory._create_vibevoice_provider()
        elif provider_name == "google":
            provider = await factory._create_google_provider()
        elif provider_name == "edge":
            provider = await factory._create_edge_provider()
        else:
            raise ValueError(f"Unknown TTS provider: {provider_name}")

        if provider is None:
            raise RuntimeError(f"Failed to initialize TTS provider: {provider_name}")

        factory._provider = provider
        factory._provider_name = provider_name

        return provider

    @classmethod
    def get_provider_name(cls) -> str:
        """Get current provider name."""
        return cls()._provider_name or settings.tts_provider

    @classmethod
    async def _create_vibevoice_provider(cls) -> Optional[TTSProvider]:
        """Create and initialize VibeVoice provider."""
        try:
            from app.services.vibevoice_service import get_vibevoice_service

            service = get_vibevoice_service()
            if await service.initialize():
                logger.info("VibeVoice provider initialized successfully")
                return service
            else:
                logger.warning("VibeVoice initialization failed, trying fallback")
                # Try Google TTS as fallback if enabled
                if settings.google_tts_enabled:
                    return await cls._create_google_provider()
                return None

        except Exception as e:
            logger.error(f"Failed to create VibeVoice provider: {e}")
            if settings.google_tts_enabled:
                logger.info("Falling back to Google TTS")
                return await cls._create_google_provider()
            return None

    @classmethod
    async def _create_google_provider(cls) -> Optional[TTSProvider]:
        """Create and initialize Google TTS provider."""
        try:
            from app.services.google_tts_service import get_google_tts_service

            service = get_google_tts_service()
            if await service.initialize():
                logger.info("Google TTS provider initialized successfully")
                return service
            return None

        except Exception as e:
            logger.error(f"Failed to create Google TTS provider: {e}")
            return None

    @classmethod
    async def _create_edge_provider(cls) -> Optional[TTSProvider]:
        """Create and initialize Edge TTS provider."""
        try:
            from app.services.edge_tts_service import get_edge_tts_service

            service = get_edge_tts_service()
            if await service.initialize():
                logger.info("Edge TTS provider initialized successfully")
                return service
            return None

        except Exception as e:
            logger.error(f"Failed to create Edge TTS provider: {e}")
            return None

    @classmethod
    async def health_check(cls) -> dict:
        """
        Perform health check on TTS provider.

        Returns:
            Health status dictionary
        """
        factory = cls()

        try:
            provider = await cls.get_provider()
            return {
                "status": "healthy",
                "provider": factory._provider_name,
                "model_loaded": provider.is_initialized,
                "gpu_available": provider.check_gpu_available()
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "provider": factory._provider_name or "none",
                "model_loaded": False,
                "gpu_available": False,
                "error": str(e)
            }

    @classmethod
    async def cleanup(cls) -> None:
        """
        Cleanup provider and release resources.

        Should be called during application shutdown to properly
        free GPU memory and other resources.
        """
        factory = cls()

        if factory._provider is not None:
            logger.info(f"Cleaning up TTS provider: {factory._provider_name}")

            # Check if provider has unload_model method (VibeVoice)
            if hasattr(factory._provider, 'unload_model'):
                try:
                    await factory._provider.unload_model()
                except Exception as e:
                    logger.error(f"Error unloading model: {e}")

            factory._provider = None
            factory._provider_name = ""
            logger.info("TTS provider cleanup complete")

    @classmethod
    def reset(cls):
        """Reset factory state (for testing)."""
        factory = cls()
        factory._provider = None
        factory._provider_name = ""
