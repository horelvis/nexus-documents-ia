"""
Audio Synthesizer Service

Converts podcast scripts to audio using the TTS microservice (VibeVoice).
Handles:
- Individual segment synthesis
- Audio stitching with pydub
- Crossfades and natural pauses
- Final MP3 encoding
"""
import asyncio
import base64
import io
import logging
from typing import List, Optional, Tuple
from uuid import UUID

import httpx
from pydub import AudioSegment

from app.core.config import settings
from app.schemas import ScriptSegment, TranscriptSegment, VoiceConfig

logger = logging.getLogger(__name__)


class AudioSynthesizer:
    """
    Synthesizes podcast audio from script segments.

    Uses the TTS microservice for voice synthesis and pydub for
    audio manipulation (stitching, crossfades, pauses).
    """

    def __init__(self):
        self.tts_url = settings.tts_service_url
        self.sample_rate = settings.audio_sample_rate
        self.segment_pause_ms = settings.segment_pause_ms
        self.crossfade_ms = settings.crossfade_ms
        self.client = httpx.AsyncClient(timeout=60.0)

        # Default voices for hosts
        self.default_voice_a = settings.default_voice_a  # Spk0 (female Spanish)
        self.default_voice_b = settings.default_voice_b  # Spk1 (male Spanish)

    async def _synthesize_text(
        self,
        text: str,
        voice_id: str,
        language: str = "es-ES",
    ) -> Tuple[bytes, int]:
        """
        Synthesize a single text segment to audio.

        Args:
            text: Text to synthesize
            voice_id: Voice ID for TTS
            language: Language code

        Returns:
            Tuple of (audio_bytes, duration_ms)
        """
        url = f"{self.tts_url}/api/v1/tts/synthesize"

        payload = {
            "text": text,
            "voice_id": voice_id,
            "language": language,
            "speed": 1.0,
        }

        headers = {
            "X-API-Key": settings.api_key,
            "Content-Type": "application/json",
        }

        try:
            response = await self.client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            result = response.json()

            # Decode base64 audio
            audio_b64 = result.get("audio_base64", "")
            audio_bytes = base64.b64decode(audio_b64)
            duration_ms = result.get("duration_ms", 0)

            return audio_bytes, duration_ms

        except httpx.HTTPError as e:
            logger.error(f"TTS request failed: {e}")
            raise RuntimeError(f"TTS synthesis failed: {e}")

    async def synthesize_segment(
        self,
        segment: ScriptSegment,
        voice_a: Optional[VoiceConfig] = None,
        voice_b: Optional[VoiceConfig] = None,
        language: str = "es-ES",
    ) -> Tuple[AudioSegment, int]:
        """
        Synthesize a single script segment.

        Args:
            segment: Script segment with speaker and text
            voice_a: Voice config for speaker A (Emma)
            voice_b: Voice config for speaker B (Alex)
            language: Language code

        Returns:
            Tuple of (AudioSegment, duration_ms)
        """
        # Select voice based on speaker
        if segment.speaker == "A":
            voice_id = voice_a.id if voice_a else self.default_voice_a
        else:
            voice_id = voice_b.id if voice_b else self.default_voice_b

        # Synthesize text
        audio_bytes, duration_ms = await self._synthesize_text(
            text=segment.text,
            voice_id=voice_id,
            language=language,
        )

        # Convert to AudioSegment
        audio = AudioSegment.from_wav(io.BytesIO(audio_bytes))

        return audio, duration_ms

    async def synthesize_all_segments(
        self,
        segments: List[ScriptSegment],
        voice_a: Optional[VoiceConfig] = None,
        voice_b: Optional[VoiceConfig] = None,
        language: str = "es-ES",
        progress_callback=None,
    ) -> Tuple[List[AudioSegment], List[TranscriptSegment]]:
        """
        Synthesize all script segments to audio.

        Args:
            segments: List of script segments
            voice_a: Voice config for speaker A
            voice_b: Voice config for speaker B
            language: Language code
            progress_callback: Optional callback for progress updates

        Returns:
            Tuple of (list of AudioSegments, list of TranscriptSegments with timestamps)
        """
        audio_segments = []
        transcript_segments = []
        current_time_ms = 0
        total_segments = len(segments)

        for i, segment in enumerate(segments):
            logger.info(f"Synthesizing segment {i+1}/{total_segments}")

            try:
                audio, duration_ms = await self.synthesize_segment(
                    segment=segment,
                    voice_a=voice_a,
                    voice_b=voice_b,
                    language=language,
                )

                audio_segments.append(audio)

                # Create transcript segment with timestamps
                transcript_segments.append(TranscriptSegment(
                    speaker=segment.speaker,
                    text=segment.text,
                    start_ms=current_time_ms,
                    end_ms=current_time_ms + duration_ms,
                ))

                current_time_ms += duration_ms + self.segment_pause_ms

                # Progress callback
                if progress_callback:
                    progress = int((i + 1) / total_segments * 100)
                    await progress_callback(progress, f"Synthesized segment {i+1}/{total_segments}")

            except Exception as e:
                logger.error(f"Failed to synthesize segment {i+1}: {e}")
                raise

        return audio_segments, transcript_segments

    def stitch_audio(
        self,
        audio_segments: List[AudioSegment],
        pause_ms: Optional[int] = None,
        crossfade_ms: Optional[int] = None,
    ) -> AudioSegment:
        """
        Stitch audio segments together with pauses and crossfades.

        Args:
            audio_segments: List of AudioSegment objects
            pause_ms: Pause duration between segments (default from settings)
            crossfade_ms: Crossfade duration (default from settings)

        Returns:
            Combined AudioSegment
        """
        if not audio_segments:
            return AudioSegment.silent(duration=0)

        pause_ms = pause_ms or self.segment_pause_ms
        crossfade_ms = crossfade_ms or self.crossfade_ms

        # Create silence for pauses
        pause = AudioSegment.silent(duration=pause_ms)

        # Start with first segment
        combined = audio_segments[0]

        # Add remaining segments with pauses
        for segment in audio_segments[1:]:
            # Add pause
            combined = combined + pause

            # Add crossfade if enabled and segments are long enough
            if crossfade_ms > 0 and len(segment) > crossfade_ms * 2:
                combined = combined.append(segment, crossfade=crossfade_ms)
            else:
                combined = combined + segment

        return combined

    def export_mp3(
        self,
        audio: AudioSegment,
        bitrate: str = "192k",
    ) -> bytes:
        """
        Export AudioSegment to MP3 bytes.

        Args:
            audio: AudioSegment to export
            bitrate: MP3 bitrate

        Returns:
            MP3 audio as bytes
        """
        buffer = io.BytesIO()
        audio.export(
            buffer,
            format="mp3",
            bitrate=bitrate,
            parameters=["-q:a", "0"],  # High quality
        )
        buffer.seek(0)
        return buffer.read()

    async def generate_podcast_audio(
        self,
        segments: List[ScriptSegment],
        voice_a: Optional[VoiceConfig] = None,
        voice_b: Optional[VoiceConfig] = None,
        language: str = "es-ES",
        progress_callback=None,
    ) -> Tuple[bytes, List[TranscriptSegment], int]:
        """
        Generate complete podcast audio from script segments.

        This is the main entry point for audio generation.

        Args:
            segments: List of script segments
            voice_a: Voice config for speaker A (Emma)
            voice_b: Voice config for speaker B (Alex)
            language: Language code
            progress_callback: Optional progress callback

        Returns:
            Tuple of (mp3_bytes, transcript_segments, duration_ms)
        """
        logger.info(f"Starting podcast audio generation: {len(segments)} segments")

        # Synthesize all segments
        audio_segments, transcript = await self.synthesize_all_segments(
            segments=segments,
            voice_a=voice_a,
            voice_b=voice_b,
            language=language,
            progress_callback=progress_callback,
        )

        if progress_callback:
            await progress_callback(90, "Stitching audio segments")

        # Stitch audio together
        combined_audio = self.stitch_audio(audio_segments)

        if progress_callback:
            await progress_callback(95, "Encoding to MP3")

        # Export to MP3
        mp3_bytes = self.export_mp3(combined_audio, settings.audio_bitrate)

        duration_ms = len(combined_audio)

        logger.info(f"Podcast audio generated: {duration_ms}ms, {len(mp3_bytes)} bytes")

        return mp3_bytes, transcript, duration_ms

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()
