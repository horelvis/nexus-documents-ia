"""
Edge TTS Service

Integration with Microsoft Edge TTS for free text-to-speech synthesis.
Uses edge-tts library which interfaces with Microsoft's online TTS service.
No GPU or credentials required.
"""

import asyncio
import io
import logging
from typing import AsyncGenerator, List, Optional

import edge_tts

from app.core.config import settings
from app.schemas.tts import VoiceInfo

logger = logging.getLogger(__name__)

# Singleton instance
_edge_tts_service: Optional["EdgeTTSService"] = None


class EdgeTTSService:
    """
    Edge TTS Service for free speech synthesis.

    Uses Microsoft Edge's online TTS service via edge-tts library.
    """

    # Available Spanish voices in Edge TTS
    AVAILABLE_VOICES = [
        # Spanish (Spain) voices
        VoiceInfo(voice_id="es-ES-AlvaroNeural", name="Alvaro", language="es-ES", gender="male", description="Spanish male voice - Alvaro", provider="edge"),
        VoiceInfo(voice_id="es-ES-ElviraNeural", name="Elvira", language="es-ES", gender="female", description="Spanish female voice - Elvira", provider="edge"),
        # Spanish (Mexico) voices
        VoiceInfo(voice_id="es-MX-DaliaNeural", name="Dalia", language="es-MX", gender="female", description="Mexican Spanish female voice", provider="edge"),
        VoiceInfo(voice_id="es-MX-JorgeNeural", name="Jorge", language="es-MX", gender="male", description="Mexican Spanish male voice", provider="edge"),
        # English voices
        VoiceInfo(voice_id="en-US-GuyNeural", name="Guy", language="en-US", gender="male", description="English male voice - Guy", provider="edge"),
        VoiceInfo(voice_id="en-US-JennyNeural", name="Jenny", language="en-US", gender="female", description="English female voice - Jenny", provider="edge"),
        VoiceInfo(voice_id="en-US-AriaNeural", name="Aria", language="en-US", gender="female", description="English female voice - Aria", provider="edge"),
        VoiceInfo(voice_id="en-GB-SoniaNeural", name="Sonia", language="en-GB", gender="female", description="British English female voice", provider="edge"),
        VoiceInfo(voice_id="en-GB-RyanNeural", name="Ryan", language="en-GB", gender="male", description="British English male voice", provider="edge"),
    ]

    def __init__(self):
        self._initialized = False
        self._default_voice = "es-ES-AlvaroNeural"

    async def initialize(self) -> bool:
        """Initialize the Edge TTS service."""
        try:
            # Test that edge-tts is working by checking available voices
            voices = await edge_tts.list_voices()
            if voices:
                logger.info(f"Edge TTS initialized with {len(voices)} available voices")
                self._initialized = True
                return True
            else:
                logger.error("Edge TTS: No voices available")
                return False
        except Exception as e:
            logger.error(f"Failed to initialize Edge TTS: {e}")
            return False

    @property
    def is_initialized(self) -> bool:
        """Check if service is ready."""
        return self._initialized

    def get_available_voices(self) -> List[VoiceInfo]:
        """Get available voices."""
        return self.AVAILABLE_VOICES

    def _get_voice_id(self, voice_id: str, language: str) -> str:
        """Get the appropriate voice ID for the given language."""
        # If voice_id matches one of our known voices, use it
        for voice in self.AVAILABLE_VOICES:
            if voice.voice_id == voice_id:
                return voice_id

        # Default voices by language
        language_defaults = {
            "es-ES": "es-ES-AlvaroNeural",
            "es-MX": "es-MX-JorgeNeural",
            "en-US": "en-US-GuyNeural",
            "en-GB": "en-GB-RyanNeural",
        }

        # Try exact match first
        if language in language_defaults:
            return language_defaults[language]

        # Try language prefix match
        lang_prefix = language.split("-")[0]
        for lang, voice in language_defaults.items():
            if lang.startswith(lang_prefix):
                return voice

        # Fallback to Spanish
        return self._default_voice

    async def synthesize(
        self,
        text: str,
        voice_id: str,
        language: str,
        speed: float = 1.0
    ) -> tuple[bytes, int]:
        """
        Synthesize text to speech.

        Args:
            text: Text to synthesize
            voice_id: Voice identifier
            language: Language code
            speed: Speech rate (0.5 to 2.0)

        Returns:
            Tuple of (audio_bytes, sample_rate)
        """
        actual_voice = self._get_voice_id(voice_id, language)

        # Convert speed to rate string (edge-tts uses percentage)
        rate = f"+{int((speed - 1) * 100)}%" if speed >= 1 else f"{int((speed - 1) * 100)}%"

        logger.info(f"Edge TTS synthesizing: {len(text)} chars, voice={actual_voice}, rate={rate}")

        try:
            communicate = edge_tts.Communicate(text, actual_voice, rate=rate)

            # Collect audio data
            audio_data = io.BytesIO()
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_data.write(chunk["data"])

            audio_bytes = audio_data.getvalue()

            # Edge TTS outputs MP3 at 24kHz
            sample_rate = 24000

            logger.info(f"Edge TTS synthesis complete: {len(audio_bytes)} bytes")

            return audio_bytes, sample_rate

        except Exception as e:
            logger.error(f"Edge TTS synthesis failed: {e}")
            raise RuntimeError(f"Edge TTS synthesis failed: {e}")

    async def stream_synthesize(
        self,
        text: str,
        voice_id: str,
        language: str
    ) -> AsyncGenerator[bytes, None]:
        """
        Stream synthesize text to speech.

        Args:
            text: Text to synthesize
            voice_id: Voice identifier
            language: Language code

        Yields:
            Audio chunks
        """
        actual_voice = self._get_voice_id(voice_id, language)

        try:
            communicate = edge_tts.Communicate(text, actual_voice)

            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    yield chunk["data"]

        except Exception as e:
            logger.error(f"Edge TTS stream synthesis failed: {e}")
            raise

    def check_gpu_available(self) -> bool:
        """Check GPU availability (not used for Edge TTS)."""
        return False  # Edge TTS is cloud-based, no GPU needed


def get_edge_tts_service() -> EdgeTTSService:
    """Get singleton Edge TTS service instance."""
    global _edge_tts_service
    if _edge_tts_service is None:
        _edge_tts_service = EdgeTTSService()
    return _edge_tts_service
