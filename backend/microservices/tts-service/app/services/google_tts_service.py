"""
Google Cloud TTS Service

Fallback TTS provider using Google Cloud Text-to-Speech API.
Provides high-quality neural voices in multiple languages including Spanish.
"""

import asyncio
import base64
import logging
from typing import AsyncGenerator, Optional, List

from app.core.config import settings
from app.schemas.tts import VoiceInfo

logger = logging.getLogger(__name__)


class GoogleTTSService:
    """
    Google Cloud Text-to-Speech service.

    Uses WaveNet/Neural2 voices for high-quality speech synthesis.
    Supports Spanish (es-ES, es-MX) and English (en-US, en-GB).
    """

    # Available Google TTS voices
    AVAILABLE_VOICES = [
        # Spanish voices
        VoiceInfo(
            voice_id="es-ES-Neural2-A",
            name="Spanish (Spain) - Female",
            language="es-ES",
            gender="female",
            description="Neural2 female voice for Spanish (Spain)",
            provider="google"
        ),
        VoiceInfo(
            voice_id="es-ES-Neural2-B",
            name="Spanish (Spain) - Male",
            language="es-ES",
            gender="male",
            description="Neural2 male voice for Spanish (Spain)",
            provider="google"
        ),
        VoiceInfo(
            voice_id="es-MX-Neural2-A",
            name="Spanish (Mexico) - Female",
            language="es-MX",
            gender="female",
            description="Neural2 female voice for Spanish (Mexico)",
            provider="google"
        ),
        VoiceInfo(
            voice_id="es-MX-Neural2-B",
            name="Spanish (Mexico) - Male",
            language="es-MX",
            gender="male",
            description="Neural2 male voice for Spanish (Mexico)",
            provider="google"
        ),
        # English voices
        VoiceInfo(
            voice_id="en-US-Neural2-A",
            name="English (US) - Male",
            language="en-US",
            gender="male",
            description="Neural2 male voice for English (US)",
            provider="google"
        ),
        VoiceInfo(
            voice_id="en-US-Neural2-C",
            name="English (US) - Female",
            language="en-US",
            gender="female",
            description="Neural2 female voice for English (US)",
            provider="google"
        ),
        VoiceInfo(
            voice_id="en-GB-Neural2-A",
            name="English (UK) - Female",
            language="en-GB",
            gender="female",
            description="Neural2 female voice for English (UK)",
            provider="google"
        ),
        VoiceInfo(
            voice_id="en-GB-Neural2-B",
            name="English (UK) - Male",
            language="en-GB",
            gender="male",
            description="Neural2 male voice for English (UK)",
            provider="google"
        ),
    ]

    def __init__(self):
        self.client = None
        self.sample_rate = settings.audio_sample_rate
        self._initialized = False

    async def initialize(self) -> bool:
        """
        Initialize Google Cloud TTS client.

        Returns:
            True if initialization successful
        """
        try:
            logger.info("Initializing Google Cloud TTS client")

            # Import Google Cloud TTS
            from google.cloud import texttospeech

            # Create client (uses GOOGLE_APPLICATION_CREDENTIALS env var)
            self.client = texttospeech.TextToSpeechClient()
            self._initialized = True

            logger.info("Google Cloud TTS client initialized")
            return True

        except ImportError as e:
            logger.error(f"Google Cloud TTS package not installed: {e}")
            logger.error("Install with: pip install google-cloud-texttospeech")
            return False
        except Exception as e:
            logger.error(f"Failed to initialize Google Cloud TTS: {e}")
            return False

    @property
    def is_initialized(self) -> bool:
        """Check if client is initialized."""
        return self._initialized and self.client is not None

    def get_available_voices(self) -> List[VoiceInfo]:
        """Get list of available voices."""
        return self.AVAILABLE_VOICES

    async def synthesize(
        self,
        text: str,
        voice_id: str = "es-ES-Neural2-A",
        language: str = "es-ES",
        speed: float = 1.0
    ) -> tuple[bytes, int]:
        """
        Synthesize text to speech.

        Args:
            text: Text to synthesize
            voice_id: Google voice name
            language: Language code
            speed: Speaking rate (0.25 to 4.0, 1.0 = normal)

        Returns:
            Tuple of (audio_bytes, duration_ms)
        """
        if not self.is_initialized:
            raise RuntimeError("Google TTS client not initialized")

        try:
            from google.cloud import texttospeech

            logger.debug(f"Synthesizing with Google TTS: {text[:50]}...")

            # Build synthesis input
            synthesis_input = texttospeech.SynthesisInput(text=text)

            # Extract language from voice_id if not provided
            voice_language = voice_id.rsplit('-', 2)[0] + '-' + voice_id.rsplit('-', 2)[1]

            # Configure voice
            voice = texttospeech.VoiceSelectionParams(
                language_code=voice_language,
                name=voice_id
            )

            # Configure audio output
            audio_config = texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.LINEAR16,
                sample_rate_hertz=self.sample_rate,
                speaking_rate=speed
            )

            # Run synthesis in thread pool
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.client.synthesize_speech(
                    input=synthesis_input,
                    voice=voice,
                    audio_config=audio_config
                )
            )

            audio_bytes = response.audio_content

            # Calculate duration from audio length
            # LINEAR16 = 2 bytes per sample, mono
            num_samples = len(audio_bytes) // 2
            duration_ms = int(num_samples / self.sample_rate * 1000)

            logger.debug(f"Google TTS synthesis complete: {duration_ms}ms")
            return audio_bytes, duration_ms

        except Exception as e:
            logger.error(f"Google TTS synthesis failed: {e}")
            raise ValueError(f"Google TTS synthesis failed: {str(e)}")

    async def stream_synthesize(
        self,
        text: str,
        voice_id: str = "es-ES-Neural2-A",
        language: str = "es-ES"
    ) -> AsyncGenerator[bytes, None]:
        """
        Stream synthesize text to speech.

        Note: Google TTS doesn't support true streaming, so we simulate it
        by splitting text into sentences and synthesizing each.

        Args:
            text: Text to synthesize
            voice_id: Voice identifier
            language: Language code

        Yields:
            Audio chunks as bytes
        """
        if not self.is_initialized:
            raise RuntimeError("Google TTS client not initialized")

        try:
            # Split text into sentences for pseudo-streaming
            sentences = self._split_into_sentences(text)

            for sentence in sentences:
                if sentence.strip():
                    audio_bytes, _ = await self.synthesize(
                        text=sentence,
                        voice_id=voice_id,
                        language=language
                    )
                    yield audio_bytes

        except Exception as e:
            logger.error(f"Google TTS streaming failed: {e}")
            raise

    def _split_into_sentences(self, text: str) -> List[str]:
        """
        Split text into sentences for pseudo-streaming.

        Args:
            text: Input text

        Returns:
            List of sentences
        """
        import re

        # Split on sentence boundaries
        sentences = re.split(r'(?<=[.!?])\s+', text)

        # Group very short sentences
        result = []
        current = ""

        for sentence in sentences:
            if len(current) + len(sentence) < 200:
                current = (current + " " + sentence).strip()
            else:
                if current:
                    result.append(current)
                current = sentence

        if current:
            result.append(current)

        return result if result else [text]

    def check_gpu_available(self) -> bool:
        """Google TTS uses cloud API, no local GPU needed."""
        return True  # Always "available" since it's cloud-based


# Singleton instance
_service_instance: Optional[GoogleTTSService] = None


def get_google_tts_service() -> GoogleTTSService:
    """Get or create Google TTS service instance."""
    global _service_instance
    if _service_instance is None:
        _service_instance = GoogleTTSService()
    return _service_instance
