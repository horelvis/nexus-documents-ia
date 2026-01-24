"""
Podcast Generator Service

Main orchestrator for podcast generation.
Coordinates script generation, audio synthesis, and storage.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from uuid import UUID

import httpx

from app.core.config import settings
from app.schemas import (
    SourceInfo, AudioConfig, AudioStatus,
    ScriptSegment, TranscriptSegment,
)
from .script_generator import ScriptGenerator
from .audio_synthesizer import AudioSynthesizer

logger = logging.getLogger(__name__)


class PodcastGenerator:
    """
    Main orchestrator for podcast generation.

    Manages the complete pipeline:
    1. Script generation (via ScriptGenerator)
    2. Audio synthesis (via AudioSynthesizer)
    3. Storage upload
    4. Status updates to main API
    """

    def __init__(self):
        self.script_generator = ScriptGenerator()
        self.audio_synthesizer = AudioSynthesizer()
        self.client = httpx.AsyncClient(timeout=30.0)

        # Track active generations
        self._active_jobs: Dict[UUID, Dict[str, Any]] = {}

    async def _update_audio_status(
        self,
        audio_id: UUID,
        status: AudioStatus,
        status_message: str,
        progress_percent: int,
        error_message: Optional[str] = None,
        script: Optional[List[dict]] = None,
        transcript: Optional[List[dict]] = None,
        audio_url: Optional[str] = None,
        duration_ms: Optional[int] = None,
        file_size_bytes: Optional[int] = None,
    ):
        """Update audio status in the main API database."""
        # Update local tracking
        if audio_id in self._active_jobs:
            self._active_jobs[audio_id].update({
                "status": status,
                "status_message": status_message,
                "progress_percent": progress_percent,
                "error_message": error_message,
            })

        # Update in main API
        url = f"{settings.main_api_url}/api/v1/internal/podcast/status"

        payload = {
            "audio_id": str(audio_id),
            "status": status.value,
            "status_message": status_message,
            "progress_percent": progress_percent,
            "error_message": error_message,
        }

        if script:
            payload["script"] = script
        if transcript:
            payload["transcript"] = transcript
        if audio_url:
            payload["audio_url"] = audio_url
        if duration_ms:
            payload["duration_ms"] = duration_ms
        if file_size_bytes:
            payload["file_size_bytes"] = file_size_bytes

        if status == AudioStatus.COMPLETED:
            payload["generation_completed_at"] = datetime.now(timezone.utc).isoformat()

        try:
            headers = {"X-API-Key": settings.api_key}
            response = await self.client.patch(url, json=payload, headers=headers)
            response.raise_for_status()
        except Exception as e:
            logger.error(f"Failed to update audio status: {e}")

    async def _upload_audio(
        self,
        audio_bytes: bytes,
        tenant_id: UUID,
        audio_id: UUID,
    ) -> str:
        """Upload audio to storage and return URL."""
        # Use storage service to upload
        url = f"{settings.storage_service_url}/api/v1/storage/upload"

        # Create multipart form data
        files = {
            "file": (f"podcast_{audio_id}.mp3", audio_bytes, "audio/mpeg"),
        }

        data = {
            "bucket_path": f"podcasts/{tenant_id}/{audio_id}.mp3",
            "content_type": "audio/mpeg",
        }

        headers = {"X-API-Key": settings.api_key}

        try:
            response = await self.client.post(
                url,
                files=files,
                data=data,
                headers=headers,
                timeout=120.0,  # Longer timeout for upload
            )
            response.raise_for_status()
            result = response.json()
            return result.get("url", "")

        except Exception as e:
            logger.error(f"Failed to upload audio: {e}")
            raise RuntimeError(f"Audio upload failed: {e}")

    async def generate(
        self,
        audio_id: UUID,
        notebook_id: UUID,
        tenant_id: UUID,
        sources: List[SourceInfo],
        config: AudioConfig,
    ):
        """
        Generate a complete podcast.

        This is the main entry point called by the API endpoint.
        Runs the full pipeline and updates status throughout.

        Args:
            audio_id: ID of the NotebookAudio record
            notebook_id: ID of the notebook
            tenant_id: Tenant ID for storage
            sources: Source documents
            config: Audio configuration
        """
        logger.info(f"Starting podcast generation for audio_id: {audio_id}")

        # Track this job
        self._active_jobs[audio_id] = {
            "status": AudioStatus.PENDING,
            "started_at": datetime.now(timezone.utc),
            "cancelled": False,
        }

        try:
            # Check for cancellation
            if self._active_jobs.get(audio_id, {}).get("cancelled"):
                return

            # Phase 1: Analyze sources
            await self._update_audio_status(
                audio_id=audio_id,
                status=AudioStatus.ANALYZING,
                status_message="Analizando documentos fuente...",
                progress_percent=5,
            )

            if self._is_cancelled(audio_id):
                return

            # Phase 2: Generate script
            await self._update_audio_status(
                audio_id=audio_id,
                status=AudioStatus.GENERATING_SCRIPT,
                status_message="Generando guion del podcast...",
                progress_percent=10,
            )

            script = await self.script_generator.generate_full_script(
                sources=sources,
                config=config,
            )

            if self._is_cancelled(audio_id):
                return

            await self._update_audio_status(
                audio_id=audio_id,
                status=AudioStatus.GENERATING_SCRIPT,
                status_message=f"Guion generado: {script.total_segments} segmentos",
                progress_percent=30,
                script=[seg.model_dump() for seg in script.segments],
            )

            # Phase 3: Generate audio
            await self._update_audio_status(
                audio_id=audio_id,
                status=AudioStatus.GENERATING_AUDIO,
                status_message="Sintetizando audio...",
                progress_percent=35,
            )

            async def audio_progress(percent, message):
                # Map 0-100 to 35-85
                mapped_percent = 35 + int(percent * 0.5)
                await self._update_audio_status(
                    audio_id=audio_id,
                    status=AudioStatus.GENERATING_AUDIO,
                    status_message=message,
                    progress_percent=mapped_percent,
                )

            mp3_bytes, transcript, duration_ms = await self.audio_synthesizer.generate_podcast_audio(
                segments=script.segments,
                voice_a=config.voice_a,
                voice_b=config.voice_b,
                language=config.language,
                progress_callback=audio_progress,
            )

            if self._is_cancelled(audio_id):
                return

            # Phase 4: Stitch and finalize
            await self._update_audio_status(
                audio_id=audio_id,
                status=AudioStatus.STITCHING,
                status_message="Finalizando audio...",
                progress_percent=88,
            )

            # Phase 5: Upload
            await self._update_audio_status(
                audio_id=audio_id,
                status=AudioStatus.UPLOADING,
                status_message="Subiendo archivo...",
                progress_percent=92,
            )

            audio_url = await self._upload_audio(
                audio_bytes=mp3_bytes,
                tenant_id=tenant_id,
                audio_id=audio_id,
            )

            # Complete
            await self._update_audio_status(
                audio_id=audio_id,
                status=AudioStatus.COMPLETED,
                status_message="Podcast generado exitosamente",
                progress_percent=100,
                transcript=[seg.model_dump() for seg in transcript],
                audio_url=audio_url,
                duration_ms=duration_ms,
                file_size_bytes=len(mp3_bytes),
            )

            logger.info(f"Podcast generation completed for audio_id: {audio_id}")

        except Exception as e:
            logger.error(f"Podcast generation failed for audio_id {audio_id}: {e}")
            await self._update_audio_status(
                audio_id=audio_id,
                status=AudioStatus.FAILED,
                status_message="Error en la generación",
                progress_percent=0,
                error_message=str(e),
            )

        finally:
            # Clean up tracking
            if audio_id in self._active_jobs:
                del self._active_jobs[audio_id]

    def _is_cancelled(self, audio_id: UUID) -> bool:
        """Check if a job has been cancelled."""
        return self._active_jobs.get(audio_id, {}).get("cancelled", False)

    async def get_status(self, audio_id: UUID) -> Optional[Dict[str, Any]]:
        """Get the current status of a generation job."""
        if audio_id in self._active_jobs:
            job = self._active_jobs[audio_id]
            return {
                "audio_id": audio_id,
                "status": job.get("status", AudioStatus.PENDING),
                "status_message": job.get("status_message"),
                "progress_percent": job.get("progress_percent", 0),
                "error_message": job.get("error_message"),
            }

        # Not tracking locally, query main API
        try:
            url = f"{settings.main_api_url}/api/v1/internal/podcast/status/{audio_id}"
            headers = {"X-API-Key": settings.api_key}
            response = await self.client.get(url, headers=headers)

            if response.status_code == 404:
                return None

            response.raise_for_status()
            return response.json()

        except Exception as e:
            logger.error(f"Failed to get status: {e}")
            return None

    async def cancel(self, audio_id: UUID) -> bool:
        """Cancel an ongoing generation."""
        if audio_id in self._active_jobs:
            self._active_jobs[audio_id]["cancelled"] = True
            logger.info(f"Cancellation requested for audio_id: {audio_id}")
            return True
        return False

    async def health_check(self) -> Dict[str, bool]:
        """Check health of dependencies."""
        health = {
            "vllm_healthy": False,
            "tts_healthy": False,
            "storage_healthy": False,
        }

        # Headers for authenticated services
        auth_headers = {"X-API-Key": settings.api_key} if settings.api_key else {}

        # Check vLLM (no auth required)
        try:
            response = await self.client.get(
                f"{settings.vllm_base_url}/models",
                timeout=5.0,
            )
            health["vllm_healthy"] = response.status_code == 200
        except Exception:
            pass

        # Check TTS (requires API key)
        try:
            response = await self.client.get(
                f"{settings.tts_service_url}/api/v1/tts/health",
                headers=auth_headers,
                timeout=5.0,
            )
            health["tts_healthy"] = response.status_code == 200
        except Exception:
            pass

        # Check Storage (requires API key)
        try:
            response = await self.client.get(
                f"{settings.storage_service_url}/health",
                headers=auth_headers,
                timeout=5.0,
            )
            health["storage_healthy"] = response.status_code == 200
        except Exception:
            pass

        return health

    async def close(self):
        """Clean up resources."""
        await self.script_generator.close()
        await self.audio_synthesizer.close()
        await self.client.aclose()
