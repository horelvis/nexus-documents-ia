"""
VibeVoice TTS Service

Integration with Microsoft VibeVoice for real-time text-to-speech synthesis.
Supports both batch and streaming modes.
"""

import asyncio
import copy
import gc
import io
import logging
import os
from pathlib import Path
from typing import AsyncGenerator, Optional, List, Dict, Any
import numpy as np

from app.core.config import settings
from app.schemas.tts import VoiceInfo

logger = logging.getLogger(__name__)

# Global model and processor instances (loaded once at startup)
_model = None
_processor = None
_voice_cache: Dict[str, Any] = {}
_model_lock = asyncio.Lock()
_torch_available = False

try:
    import torch
    _torch_available = True
except ImportError:
    pass


class VibeVoiceService:
    """
    VibeVoice TTS Service for real-time speech synthesis.

    Uses microsoft/VibeVoice-Realtime-0.5B for low-latency streaming TTS.
    """

    # Base URL for downloading voice prompts from Microsoft VibeVoice repository
    VOICE_PROMPTS_BASE_URL = "https://raw.githubusercontent.com/microsoft/VibeVoice/main/demo/voices/streaming_model"

    # Available voices in VibeVoice (pre-computed voice prompts)
    # voice_id matches the .pt filename (without extension)
    AVAILABLE_VOICES = [
        # English voices
        VoiceInfo(voice_id="en-Carter_man", name="Carter", language="en-US", gender="male", description="English male voice - Carter", provider="vibevoice"),
        VoiceInfo(voice_id="en-Davis_man", name="Davis", language="en-US", gender="male", description="English male voice - Davis", provider="vibevoice"),
        VoiceInfo(voice_id="en-Mike_man", name="Mike", language="en-US", gender="male", description="English male voice - Mike", provider="vibevoice"),
        VoiceInfo(voice_id="en-Frank_man", name="Frank", language="en-US", gender="male", description="English male voice - Frank", provider="vibevoice"),
        VoiceInfo(voice_id="en-Emma_woman", name="Emma", language="en-US", gender="female", description="English female voice - Emma", provider="vibevoice"),
        VoiceInfo(voice_id="en-Grace_woman", name="Grace", language="en-US", gender="female", description="English female voice - Grace", provider="vibevoice"),
        # Spanish voices
        VoiceInfo(voice_id="sp-Spk0_woman", name="Spanish Female", language="es-ES", gender="female", description="Spanish female voice", provider="vibevoice"),
        VoiceInfo(voice_id="sp-Spk1_man", name="Spanish Male", language="es-ES", gender="male", description="Spanish male voice", provider="vibevoice"),
        # German voices
        VoiceInfo(voice_id="de-Spk0_man", name="German Male", language="de-DE", gender="male", description="German male voice", provider="vibevoice"),
        VoiceInfo(voice_id="de-Spk1_woman", name="German Female", language="de-DE", gender="female", description="German female voice", provider="vibevoice"),
        # French voices
        VoiceInfo(voice_id="fr-Spk0_man", name="French Male", language="fr-FR", gender="male", description="French male voice", provider="vibevoice"),
        VoiceInfo(voice_id="fr-Spk1_woman", name="French Female", language="fr-FR", gender="female", description="French female voice", provider="vibevoice"),
        # Italian voices
        VoiceInfo(voice_id="it-Spk0_woman", name="Italian Female", language="it-IT", gender="female", description="Italian female voice", provider="vibevoice"),
        VoiceInfo(voice_id="it-Spk1_man", name="Italian Male", language="it-IT", gender="male", description="Italian male voice", provider="vibevoice"),
        # Portuguese voices
        VoiceInfo(voice_id="pt-Spk0_woman", name="Portuguese Female", language="pt-PT", gender="female", description="Portuguese female voice", provider="vibevoice"),
        VoiceInfo(voice_id="pt-Spk1_man", name="Portuguese Male", language="pt-PT", gender="male", description="Portuguese male voice", provider="vibevoice"),
        # Dutch voices
        VoiceInfo(voice_id="nl-Spk0_man", name="Dutch Male", language="nl-NL", gender="male", description="Dutch male voice", provider="vibevoice"),
        VoiceInfo(voice_id="nl-Spk1_woman", name="Dutch Female", language="nl-NL", gender="female", description="Dutch female voice", provider="vibevoice"),
        # Polish voices
        VoiceInfo(voice_id="pl-Spk0_man", name="Polish Male", language="pl-PL", gender="male", description="Polish male voice", provider="vibevoice"),
        VoiceInfo(voice_id="pl-Spk1_woman", name="Polish Female", language="pl-PL", gender="female", description="Polish female voice", provider="vibevoice"),
        # Japanese voices
        VoiceInfo(voice_id="jp-Spk0_man", name="Japanese Male", language="ja-JP", gender="male", description="Japanese male voice", provider="vibevoice"),
        VoiceInfo(voice_id="jp-Spk1_woman", name="Japanese Female", language="ja-JP", gender="female", description="Japanese female voice", provider="vibevoice"),
        # Korean voices
        VoiceInfo(voice_id="kr-Spk0_woman", name="Korean Female", language="ko-KR", gender="female", description="Korean female voice", provider="vibevoice"),
        VoiceInfo(voice_id="kr-Spk1_man", name="Korean Male", language="ko-KR", gender="male", description="Korean male voice", provider="vibevoice"),
        # Indian voice
        VoiceInfo(voice_id="in-Samuel_man", name="Samuel", language="en-IN", gender="male", description="Indian English male voice - Samuel", provider="vibevoice"),
    ]

    # Mapping from old voice IDs to new ones for backward compatibility
    VOICE_ID_ALIASES = {
        "Carter": "en-Carter_man",
        "sp-Spk0": "sp-Spk0_woman",
        "sp-Spk1": "sp-Spk1_man",
    }

    def __init__(self):
        self.model = None
        self.processor = None
        self.voice_cache: Dict[str, Any] = {}
        self.device = settings.vibevoice_device
        self.model_path = settings.vibevoice_model_path
        self.sample_rate = settings.audio_sample_rate
        self._initialized = False

    async def initialize(self) -> bool:
        """
        Initialize the VibeVoice model and processor.

        Returns:
            True if initialization successful, False otherwise
        """
        global _model, _processor, _voice_cache

        async with _model_lock:
            if _model is not None and _processor is not None:
                self.model = _model
                self.processor = _processor
                self.voice_cache = _voice_cache
                self._initialized = True
                return True

            try:
                logger.info(f"Loading VibeVoice model: {self.model_path}")
                logger.info(f"Device: {self.device}")

                # Import VibeVoice components
                from vibevoice.modular.modeling_vibevoice_streaming_inference import (
                    VibeVoiceStreamingForConditionalGenerationInference
                )
                from vibevoice.processor.vibevoice_streaming_processor import (
                    VibeVoiceStreamingProcessor
                )

                # Determine dtype based on device
                if self.device == "cuda":
                    load_dtype = torch.bfloat16
                    # Try FlashAttention2, fall back to SDPA or eager if not available
                    try:
                        import flash_attn
                        attn_impl = "flash_attention_2"
                        logger.info("Using FlashAttention2 for faster inference")
                    except ImportError:
                        # SDPA (Scaled Dot Product Attention) is the next best option
                        # Available in PyTorch 2.0+ and doesn't require extra packages
                        attn_impl = "sdpa"
                        logger.warning(
                            "FlashAttention2 not available, using SDPA. "
                            "For better performance, install: pip install flash-attn --no-build-isolation"
                        )
                else:
                    load_dtype = torch.float32
                    attn_impl = "eager"

                # Load processor
                logger.info("Loading VibeVoice processor...")
                self.processor = VibeVoiceStreamingProcessor.from_pretrained(
                    self.model_path
                )

                # Load model
                logger.info("Loading VibeVoice model (this may take a moment)...")
                self.model = VibeVoiceStreamingForConditionalGenerationInference.from_pretrained(
                    self.model_path,
                    torch_dtype=load_dtype,
                    device_map=self.device,
                    attn_implementation=attn_impl
                )
                self.model.eval()
                self.model.set_ddpm_inference_steps(num_steps=5)

                # Load voice prompts
                await self._load_voice_prompts()

                # Update globals
                _model = self.model
                _processor = self.processor
                _voice_cache = self.voice_cache
                self._initialized = True

                # Log VRAM usage
                if _torch_available and torch.cuda.is_available():
                    allocated = torch.cuda.memory_allocated() / (1024**3)
                    logger.info(f"VibeVoice model loaded - VRAM usage: {allocated:.2f}GB")

                logger.info("VibeVoice model loaded successfully")
                return True

            except ImportError as e:
                logger.error(f"VibeVoice import error: {e}")
                logger.error("Ensure vibevoice is installed: pip install git+https://github.com/microsoft/VibeVoice.git")
                return False
            except Exception as e:
                logger.error(f"Failed to load VibeVoice model: {e}")
                import traceback
                logger.error(traceback.format_exc())
                return False

    async def _load_voice_prompts(self) -> None:
        """Load pre-computed voice prompts for available speakers."""
        import httpx

        voice_prompts_dir = Path(settings.vibevoice_voice_prompts_dir)
        voice_prompts_dir.mkdir(parents=True, exist_ok=True)

        target_device = self.device if self.device != "cuda" else "cuda:0"

        # Load default voices (Spanish) on startup
        default_voices = ["sp-Spk0_woman", "sp-Spk1_man", "en-Carter_man"]

        for voice_id in default_voices:
            voice_file = voice_prompts_dir / f"{voice_id}.pt"

            # Download if not exists
            if not voice_file.exists():
                await self._download_voice_prompt(voice_id, voice_file)

            # Load if exists
            if voice_file.exists():
                try:
                    self.voice_cache[voice_id] = torch.load(
                        voice_file,
                        map_location=target_device,
                        weights_only=False
                    )
                    logger.info(f"Loaded voice prompt: {voice_id} from {voice_file}")
                except Exception as e:
                    logger.warning(f"Failed to load voice prompt {voice_id}: {e}")

        logger.info(f"Loaded {len(self.voice_cache)} voice prompts: {list(self.voice_cache.keys())}")

    async def _download_voice_prompt(self, voice_id: str, target_path: Path) -> bool:
        """
        Download a voice prompt from the Microsoft VibeVoice repository.

        Args:
            voice_id: Voice identifier (e.g., "en-Carter_man")
            target_path: Path where to save the .pt file

        Returns:
            True if download successful, False otherwise
        """
        import httpx

        url = f"{self.VOICE_PROMPTS_BASE_URL}/{voice_id}.pt"
        logger.info(f"Downloading voice prompt: {voice_id} from {url}")

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.get(url)
                response.raise_for_status()

                # Verify it's not an HTML error page
                content = response.content
                if content[:15].startswith(b'<!DOCTYPE') or content[:5].startswith(b'<html'):
                    logger.error(f"Received HTML instead of voice prompt for {voice_id}")
                    return False

                # Save to file
                target_path.parent.mkdir(parents=True, exist_ok=True)
                target_path.write_bytes(content)

                logger.info(f"Downloaded voice prompt: {voice_id} ({len(content) / 1024:.1f} KB)")
                return True

        except Exception as e:
            logger.error(f"Failed to download voice prompt {voice_id}: {e}")
            return False

    async def _ensure_voice_loaded(self, voice_id: str) -> bool:
        """
        Ensure a voice is loaded, downloading if necessary.

        Args:
            voice_id: Voice identifier

        Returns:
            True if voice is available, False otherwise
        """
        # Handle aliases for backward compatibility
        voice_id = self.VOICE_ID_ALIASES.get(voice_id, voice_id)

        # Already loaded
        if voice_id in self.voice_cache:
            return True

        # Try to load from disk or download
        voice_prompts_dir = Path(settings.vibevoice_voice_prompts_dir)
        voice_file = voice_prompts_dir / f"{voice_id}.pt"

        # Download if not exists
        if not voice_file.exists():
            success = await self._download_voice_prompt(voice_id, voice_file)
            if not success:
                return False

        # Load into cache
        target_device = self.device if self.device != "cuda" else "cuda:0"
        try:
            self.voice_cache[voice_id] = torch.load(
                voice_file,
                map_location=target_device,
                weights_only=False
            )
            logger.info(f"Loaded voice prompt on-demand: {voice_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to load voice prompt {voice_id}: {e}")
            return False

    @property
    def is_initialized(self) -> bool:
        """Check if model is loaded and ready."""
        return self._initialized and self.model is not None and self.processor is not None

    def get_available_voices(self) -> List[VoiceInfo]:
        """Get list of available voices."""
        return self.AVAILABLE_VOICES

    async def synthesize(
        self,
        text: str,
        voice_id: str = "sp-Spk0_woman",
        language: str = "es-ES",
        speed: float = 1.0
    ) -> tuple[bytes, int]:
        """
        Synthesize text to speech (batch mode).

        Args:
            text: Text to synthesize
            voice_id: Voice identifier
            language: Language code
            speed: Playback speed multiplier

        Returns:
            Tuple of (audio_bytes, duration_ms)

        Raises:
            RuntimeError: If model not initialized
            ValueError: If synthesis fails
        """
        if not self.is_initialized:
            raise RuntimeError("VibeVoice model not initialized")

        # Handle aliases for backward compatibility
        voice_id = self.VOICE_ID_ALIASES.get(voice_id, voice_id)

        # Ensure voice is loaded (download on-demand if needed)
        voice_available = await self._ensure_voice_loaded(voice_id)
        if not voice_available:
            # Fallback to default Spanish voice
            logger.warning(f"Voice {voice_id} not available, falling back to sp-Spk0_woman")
            voice_id = "sp-Spk0_woman"
            await self._ensure_voice_loaded(voice_id)

        try:
            logger.debug(f"Synthesizing text: {text[:50]}...")

            # Run synthesis in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            audio_array = await loop.run_in_executor(
                None,
                self._synthesize_sync,
                text,
                voice_id,
                language,
                speed
            )

            # Convert to WAV bytes
            audio_bytes = self._array_to_wav(audio_array)

            # Calculate duration
            duration_ms = int(len(audio_array) / self.sample_rate * 1000)

            logger.debug(f"Synthesis complete: {duration_ms}ms")
            return audio_bytes, duration_ms

        except Exception as e:
            logger.error(f"Synthesis failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            raise ValueError(f"TTS synthesis failed: {str(e)}")

    def _synthesize_sync(
        self,
        text: str,
        voice_id: str,
        language: str,
        speed: float
    ) -> np.ndarray:
        """
        Synchronous synthesis for thread pool execution.

        Args:
            text: Text to synthesize
            voice_id: Voice identifier
            language: Language code
            speed: Playback speed

        Returns:
            Audio as numpy array
        """
        # Handle aliases for backward compatibility
        voice_id = self.VOICE_ID_ALIASES.get(voice_id, voice_id)

        # Get voice prompt (pre-computed speaker embedding)
        voice_prompt = self.voice_cache.get(voice_id)
        if voice_prompt is None:
            raise ValueError(f"Voice '{voice_id}' not loaded. Available: {list(self.voice_cache.keys())}")

        # Process input text with cached voice prompt
        inputs = self.processor.process_input_with_cached_prompt(
            text=text,
            cached_prompt=voice_prompt,
            padding=True,
            return_tensors="pt",
            return_attention_mask=True,
        )

        # Move inputs to device
        target_device = self.device if self.device != "cuda" else "cuda:0"
        inputs = {k: v.to(target_device) if hasattr(v, 'to') else v for k, v in inputs.items()}

        # Generate audio
        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                cfg_scale=1.5,
                tokenizer=self.processor.tokenizer,
                generation_config={'do_sample': False},
                all_prefilled_outputs=copy.deepcopy(voice_prompt),
            )

        # Extract audio from outputs
        audio = outputs.speech_outputs[0]

        # Convert to numpy if tensor
        # Note: numpy doesn't support BFloat16, so we convert to float32 first
        if hasattr(audio, 'cpu'):
            audio = audio.cpu().float().numpy()

        # Flatten if needed
        if len(audio.shape) > 1:
            audio = audio.squeeze()

        # Apply speed adjustment if needed
        if speed != 1.0:
            audio = self._adjust_speed(audio, speed)

        return audio

    async def stream_synthesize(
        self,
        text: str,
        voice_id: str = "Carter",
        language: str = "en-US"
    ) -> AsyncGenerator[bytes, None]:
        """
        Stream synthesize text to speech.

        Yields audio chunks as they are generated for real-time playback.

        Args:
            text: Text to synthesize
            voice_id: Voice identifier
            language: Language code

        Yields:
            Audio chunks as bytes
        """
        if not self.is_initialized:
            raise RuntimeError("VibeVoice model not initialized")

        try:
            logger.debug(f"Starting streaming synthesis: {text[:50]}...")

            # VibeVoice streaming mode
            # The model generates audio chunks in real-time
            chunk_samples = int(self.sample_rate * settings.stream_chunk_size_ms / 1000)

            # Use the streaming API
            async for audio_chunk in self._stream_generator(text, voice_id):
                # Convert chunk to bytes
                chunk_bytes = self._array_to_wav_chunk(audio_chunk)
                yield chunk_bytes

            logger.debug("Streaming synthesis complete")

        except Exception as e:
            logger.error(f"Streaming synthesis failed: {e}")
            raise

    async def _stream_generator(
        self,
        text: str,
        voice_id: str
    ) -> AsyncGenerator[np.ndarray, None]:
        """
        Internal generator for streaming synthesis.

        Uses VibeVoice's streaming capability to yield audio chunks.
        """
        # Run the streaming synthesis in chunks
        # VibeVoice Realtime model supports streaming natively
        loop = asyncio.get_event_loop()

        # For VibeVoice, we use the streaming interface
        # This is a simplified implementation - actual implementation
        # may need to interface with VibeVoice's WebSocket server
        def generate_chunks():
            """Generate audio chunks synchronously."""
            # VibeVoice streaming synthesis
            for chunk in self.model.stream_synthesize(
                text=text,
                speaker_name=voice_id
            ):
                yield chunk

        # Wrap sync generator in async
        chunk_queue = asyncio.Queue()
        done_event = asyncio.Event()

        async def producer():
            """Produce chunks in thread pool."""
            try:
                for chunk in await loop.run_in_executor(None, list, generate_chunks()):
                    await chunk_queue.put(chunk)
            finally:
                done_event.set()

        # Start producer task
        producer_task = asyncio.create_task(producer())

        try:
            while not done_event.is_set() or not chunk_queue.empty():
                try:
                    chunk = await asyncio.wait_for(chunk_queue.get(), timeout=0.1)
                    yield chunk
                except asyncio.TimeoutError:
                    continue
        finally:
            producer_task.cancel()

    def _array_to_wav(self, audio_array: np.ndarray) -> bytes:
        """
        Convert numpy audio array to WAV bytes.

        Args:
            audio_array: Audio samples as numpy array

        Returns:
            WAV file as bytes
        """
        import wave

        # Ensure correct format
        if audio_array.dtype != np.int16:
            # Normalize to int16 range
            if audio_array.dtype == np.float32 or audio_array.dtype == np.float64:
                audio_array = (audio_array * 32767).astype(np.int16)
            else:
                audio_array = audio_array.astype(np.int16)

        # Create WAV in memory
        buffer = io.BytesIO()
        with wave.open(buffer, 'wb') as wav:
            wav.setnchannels(1)  # Mono
            wav.setsampwidth(2)  # 16-bit
            wav.setframerate(self.sample_rate)
            wav.writeframes(audio_array.tobytes())

        buffer.seek(0)
        return buffer.read()

    def _array_to_wav_chunk(self, audio_array: np.ndarray) -> bytes:
        """
        Convert numpy audio chunk to raw PCM bytes for streaming.

        For streaming, we send raw PCM data without WAV header.
        The client reconstructs the audio stream.

        Args:
            audio_array: Audio samples as numpy array

        Returns:
            Raw PCM audio as bytes
        """
        # Ensure correct format
        if audio_array.dtype != np.int16:
            if audio_array.dtype == np.float32 or audio_array.dtype == np.float64:
                audio_array = (audio_array * 32767).astype(np.int16)
            else:
                audio_array = audio_array.astype(np.int16)

        return audio_array.tobytes()

    def _adjust_speed(self, audio: np.ndarray, speed: float) -> np.ndarray:
        """
        Adjust playback speed of audio.

        Uses simple resampling for speed adjustment.

        Args:
            audio: Audio samples
            speed: Speed multiplier (1.0 = normal)

        Returns:
            Speed-adjusted audio
        """
        if speed == 1.0:
            return audio

        # Calculate new length
        new_length = int(len(audio) / speed)

        # Resample using linear interpolation
        indices = np.linspace(0, len(audio) - 1, new_length)
        return np.interp(indices, np.arange(len(audio)), audio).astype(audio.dtype)

    def check_gpu_available(self) -> bool:
        """Check if GPU is available for inference."""
        if _torch_available:
            import torch
            return torch.cuda.is_available()
        return False

    async def unload_model(self) -> None:
        """
        Unload the model and release GPU memory.

        This should be called during service shutdown to properly
        free VRAM and avoid memory leaks.
        """
        global _model, _processor, _voice_cache

        async with _model_lock:
            if self.model is not None:
                logger.info("Unloading VibeVoice model from GPU...")

                try:
                    # Clear voice cache first (releases speaker embeddings)
                    self.voice_cache.clear()
                    _voice_cache.clear()

                    # Delete the processor
                    if self.processor is not None:
                        del self.processor
                        self.processor = None
                    _processor = None

                    # Delete the model reference
                    del self.model
                    self.model = None
                    _model = None
                    self._initialized = False

                    # Force garbage collection
                    gc.collect()

                    # Clear CUDA cache if available
                    if _torch_available:
                        import torch
                        if torch.cuda.is_available():
                            torch.cuda.empty_cache()
                            torch.cuda.synchronize()

                            # Log memory status after cleanup
                            allocated = torch.cuda.memory_allocated() / (1024**2)
                            reserved = torch.cuda.memory_reserved() / (1024**2)
                            logger.info(f"VRAM after cleanup - Allocated: {allocated:.1f}MB, Reserved: {reserved:.1f}MB")

                    logger.info("VibeVoice model unloaded successfully")

                except Exception as e:
                    logger.error(f"Error unloading model: {e}")
                    raise


# Singleton instance
_service_instance: Optional[VibeVoiceService] = None


def get_vibevoice_service() -> VibeVoiceService:
    """Get or create VibeVoice service instance."""
    global _service_instance
    if _service_instance is None:
        _service_instance = VibeVoiceService()
    return _service_instance


async def cleanup_vibevoice_service() -> None:
    """
    Cleanup function to properly release GPU resources.

    Call this during application shutdown to free VRAM.
    """
    global _service_instance

    if _service_instance is not None:
        await _service_instance.unload_model()
        _service_instance = None
        logger.info("VibeVoice service cleaned up")
