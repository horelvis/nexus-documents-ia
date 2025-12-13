"""
Audio Utilities

Helper functions for audio processing, conversion, and caching.
"""

import base64
import hashlib
import io
import logging
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


def audio_to_base64(audio_bytes: bytes) -> str:
    """
    Convert audio bytes to base64 string.

    Args:
        audio_bytes: Raw audio data

    Returns:
        Base64 encoded string
    """
    return base64.b64encode(audio_bytes).decode('utf-8')


def base64_to_audio(base64_str: str) -> bytes:
    """
    Convert base64 string to audio bytes.

    Args:
        base64_str: Base64 encoded audio

    Returns:
        Raw audio bytes
    """
    return base64.b64decode(base64_str)


def generate_cache_key(
    text: str,
    voice_id: str,
    language: str,
    speed: float = 1.0,
    provider: str = "vibevoice"
) -> str:
    """
    Generate cache key for TTS result.

    Args:
        text: Text to synthesize
        voice_id: Voice identifier
        language: Language code
        speed: Playback speed
        provider: TTS provider name

    Returns:
        Cache key string
    """
    content = f"{provider}:{voice_id}:{language}:{speed}:{text}"
    return f"tts:{hashlib.sha256(content.encode()).hexdigest()}"


def calculate_duration_ms(audio_bytes: bytes, sample_rate: int = 24000, sample_width: int = 2) -> int:
    """
    Calculate audio duration from bytes.

    Args:
        audio_bytes: Raw PCM audio data
        sample_rate: Sample rate in Hz
        sample_width: Bytes per sample (2 for 16-bit)

    Returns:
        Duration in milliseconds
    """
    num_samples = len(audio_bytes) // sample_width
    return int(num_samples / sample_rate * 1000)


def pcm_to_wav(pcm_data: bytes, sample_rate: int = 24000, channels: int = 1, sample_width: int = 2) -> bytes:
    """
    Convert raw PCM data to WAV format.

    Args:
        pcm_data: Raw PCM audio data
        sample_rate: Sample rate in Hz
        channels: Number of audio channels
        sample_width: Bytes per sample

    Returns:
        WAV file as bytes
    """
    import wave

    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(sample_width)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm_data)

    buffer.seek(0)
    return buffer.read()


def wav_to_pcm(wav_data: bytes) -> tuple[bytes, int, int, int]:
    """
    Extract PCM data from WAV file.

    Args:
        wav_data: WAV file as bytes

    Returns:
        Tuple of (pcm_data, sample_rate, channels, sample_width)
    """
    import wave

    buffer = io.BytesIO(wav_data)
    with wave.open(buffer, 'rb') as wav:
        pcm_data = wav.readframes(wav.getnframes())
        sample_rate = wav.getframerate()
        channels = wav.getnchannels()
        sample_width = wav.getsampwidth()

    return pcm_data, sample_rate, channels, sample_width


class AudioCache:
    """
    Redis-based cache for TTS audio.

    Caches synthesized audio to avoid redundant API calls.
    """

    def __init__(self):
        self._client = None
        self._initialized = False

    async def initialize(self) -> bool:
        """Initialize Redis connection."""
        if not settings.cache_enabled:
            logger.info("Audio cache disabled by configuration")
            return False

        try:
            import redis.asyncio as redis

            self._client = redis.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                db=settings.redis_db,
                decode_responses=False
            )

            # Test connection
            await self._client.ping()
            self._initialized = True
            logger.info("Audio cache initialized")
            return True

        except Exception as e:
            logger.warning(f"Failed to initialize audio cache: {e}")
            return False

    async def get(self, key: str) -> Optional[bytes]:
        """
        Get cached audio.

        Args:
            key: Cache key

        Returns:
            Audio bytes if found, None otherwise
        """
        if not self._initialized:
            return None

        try:
            data = await self._client.get(key)
            if data:
                logger.debug(f"Cache hit: {key[:20]}...")
            return data
        except Exception as e:
            logger.warning(f"Cache get error: {e}")
            return None

    async def set(self, key: str, audio_bytes: bytes) -> bool:
        """
        Cache audio data.

        Args:
            key: Cache key
            audio_bytes: Audio data to cache

        Returns:
            True if cached successfully
        """
        if not self._initialized:
            return False

        try:
            await self._client.setex(
                key,
                settings.cache_ttl_seconds,
                audio_bytes
            )
            logger.debug(f"Cached: {key[:20]}...")
            return True
        except Exception as e:
            logger.warning(f"Cache set error: {e}")
            return False

    async def close(self):
        """Close Redis connection."""
        if self._client:
            await self._client.close()


# Singleton cache instance
_cache_instance: Optional[AudioCache] = None


async def get_audio_cache() -> AudioCache:
    """Get or create audio cache instance."""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = AudioCache()
        await _cache_instance.initialize()
    return _cache_instance
