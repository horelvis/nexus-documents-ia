"""
TTS Service Client

HTTP client for communicating with the TTS microservice.
Provides both batch and WebSocket streaming interfaces.
"""

import logging
from typing import AsyncGenerator, List, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class TTSClient:
    """
    Client for the TTS microservice.

    Handles authentication and provides methods for text-to-speech synthesis.
    """

    def __init__(self, tenant_id: Optional[str] = None, user_id: Optional[str] = None):
        """
        Initialize TTS client.

        Args:
            tenant_id: Tenant ID for multi-tenancy context
            user_id: User ID for tracking
        """
        self.base_url = settings.TTS_SERVICE_URL.rstrip("/")
        self.api_key = settings.MICROSERVICES_API_KEY
        self.tenant_id = tenant_id
        self.user_id = user_id

        self.headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
        }

        if tenant_id:
            self.headers["X-Tenant-ID"] = tenant_id
        if user_id:
            self.headers["X-User-ID"] = user_id

    async def synthesize(
        self,
        text: str,
        voice_id: Optional[str] = None,
        language: Optional[str] = None,
        speed: float = 1.0
    ) -> dict:
        """
        Synthesize text to speech (batch mode).

        Args:
            text: Text to synthesize
            voice_id: Voice identifier (default: provider default)
            language: Language code (e.g., "en-US", "es-ES")
            speed: Playback speed multiplier (0.5-2.0)

        Returns:
            Dictionary with audio_base64, format, duration_ms, sample_rate

        Raises:
            httpx.HTTPStatusError: If request fails
        """
        url = f"{self.base_url}/api/v1/tts/synthesize"

        payload = {
            "text": text,
            "speed": speed
        }
        if voice_id:
            payload["voice_id"] = voice_id
        if language:
            payload["language"] = language

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, json=payload, headers=self.headers)
            response.raise_for_status()
            return response.json()

    async def get_voices(self) -> dict:
        """
        Get list of available TTS voices.

        Returns:
            Dictionary with voices list and default_voice_id
        """
        url = f"{self.base_url}/api/v1/tts/voices"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=self.headers)
            response.raise_for_status()
            return response.json()

    async def health_check(self) -> dict:
        """
        Check TTS service health.

        Returns:
            Health status dictionary
        """
        url = f"{self.base_url}/api/v1/tts/health"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, headers=self.headers)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.warning(f"TTS health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e)
            }

    def get_websocket_url(self) -> str:
        """
        Get WebSocket URL for streaming TTS.

        Returns:
            WebSocket URL with authentication parameters
        """
        # Convert HTTP to WebSocket URL
        ws_url = self.base_url.replace("http://", "ws://").replace("https://", "wss://")

        # Add authentication as query parameters for WebSocket
        params = f"?api_key={self.api_key}"
        if self.tenant_id:
            params += f"&tenant_id={self.tenant_id}"
        if self.user_id:
            params += f"&user_id={self.user_id}"

        return f"{ws_url}/api/v1/tts/stream{params}"


def get_tts_client(tenant_id: Optional[str] = None, user_id: Optional[str] = None) -> TTSClient:
    """
    Factory function to create TTS client.

    Args:
        tenant_id: Optional tenant ID
        user_id: Optional user ID

    Returns:
        TTSClient instance
    """
    return TTSClient(tenant_id=tenant_id, user_id=user_id)
