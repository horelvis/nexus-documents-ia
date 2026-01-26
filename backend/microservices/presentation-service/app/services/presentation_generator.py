"""
Presentation Generator Service

Main orchestrator for presentation generation pipeline.
Coordinates outline generation, PPTX building, and status updates.
"""
import asyncio
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List

import httpx

from app.core.config import settings
from app.schemas import (
    SourceInfo, PresentationConfig, SlideOutline,
    PresentationStatus,
)
from app.services.outline_generator import OutlineGenerator
from app.services.pptx_builder import PPTXBuilder

logger = logging.getLogger(__name__)


class PresentationGenerator:
    """Orchestrates the presentation generation pipeline."""

    def __init__(self):
        self.outline_generator = OutlineGenerator()
        self.pptx_builder = PPTXBuilder()
        self._status_cache: Dict[str, Dict[str, Any]] = {}
        self._main_api_url = settings.main_api_url
        self._storage_url = settings.storage_service_url
        self._api_key = settings.api_key

    async def generate(
        self,
        presentation_id: str,
        notebook_id: str,
        tenant_id: str,
        sources: List[SourceInfo],
        config: PresentationConfig,
    ):
        """
        Main generation pipeline.

        Args:
            presentation_id: ID of the presentation record
            notebook_id: ID of the source notebook
            tenant_id: Tenant ID for storage
            sources: List of source documents
            config: Presentation configuration
        """
        logger.info(f"Starting generation for presentation {presentation_id}")

        try:
            # Stage 1: Analyzing
            await self._update_status(
                presentation_id,
                status=PresentationStatus.ANALYZING,
                status_message="Analyzing source documents...",
                progress_percent=10,
            )

            # Validate sources
            source_objects = [
                SourceInfo(**s) if isinstance(s, dict) else s
                for s in sources
            ]

            total_words = sum(s.word_count for s in source_objects)
            logger.info(f"Total content: {len(source_objects)} sources, {total_words} words")

            # Stage 2: Generate outline
            await self._update_status(
                presentation_id,
                status=PresentationStatus.GENERATING_OUTLINE,
                status_message="Generating presentation outline with AI...",
                progress_percent=30,
            )

            config_obj = PresentationConfig(**config) if isinstance(config, dict) else config
            outlines = await self.outline_generator.generate_outline(source_objects, config_obj)

            # Update with outline
            await self._update_status(
                presentation_id,
                status=PresentationStatus.GENERATING_OUTLINE,
                status_message=f"Generated {len(outlines)} slide outlines",
                progress_percent=50,
                outline=[o.model_dump() for o in outlines],
            )

            # Stage 3: Build PPTX
            await self._update_status(
                presentation_id,
                status=PresentationStatus.GENERATING_SLIDES,
                status_message="Building PowerPoint presentation...",
                progress_percent=60,
            )

            pptx_bytes, slide_count = self.pptx_builder.build_presentation(outlines, config_obj)
            file_size = len(pptx_bytes)

            logger.info(f"Built PPTX: {slide_count} slides, {file_size} bytes")

            # Stage 4: Upload to storage
            await self._update_status(
                presentation_id,
                status=PresentationStatus.UPLOADING,
                status_message="Uploading presentation file...",
                progress_percent=80,
            )

            pptx_url = await self._upload_file(
                presentation_id=presentation_id,
                notebook_id=notebook_id,
                tenant_id=tenant_id,
                file_bytes=pptx_bytes,
                filename=f"presentation_{presentation_id}.pptx",
            )

            if not pptx_url:
                raise Exception("Failed to upload presentation file")

            # Stage 5: Completed
            await self._update_status(
                presentation_id,
                status=PresentationStatus.COMPLETED,
                status_message="Presentation generated successfully",
                progress_percent=100,
                outline=[o.model_dump() for o in outlines],
                pptx_url=pptx_url,
                slide_count=slide_count,
                file_size_bytes=file_size,
            )

            logger.info(f"Presentation {presentation_id} completed successfully")

        except Exception as e:
            logger.error(f"Presentation generation failed: {e}", exc_info=True)
            await self._update_status(
                presentation_id,
                status=PresentationStatus.FAILED,
                status_message="Generation failed",
                error_message=str(e),
            )

    async def _update_status(
        self,
        presentation_id: str,
        status: PresentationStatus,
        status_message: str = None,
        progress_percent: int = 0,
        error_message: str = None,
        outline: List[dict] = None,
        pptx_url: str = None,
        thumbnail_url: str = None,
        slide_count: int = None,
        file_size_bytes: int = None,
    ):
        """Update presentation status in the main API and local cache."""
        # Update local cache
        self._status_cache[presentation_id] = {
            "presentation_id": presentation_id,
            "status": status.value,
            "status_message": status_message,
            "progress_percent": progress_percent,
            "error_message": error_message,
            "outline": outline,
            "pptx_url": pptx_url,
            "thumbnail_url": thumbnail_url,
            "slide_count": slide_count,
            "file_size_bytes": file_size_bytes,
        }

        # Update main API
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                payload = {
                    "status": status.value,
                    "status_message": status_message,
                    "progress_percent": progress_percent,
                }

                if error_message:
                    payload["error_message"] = error_message
                if outline:
                    payload["outline"] = outline
                if pptx_url:
                    payload["pptx_url"] = pptx_url
                if thumbnail_url:
                    payload["thumbnail_url"] = thumbnail_url
                if slide_count is not None:
                    payload["slide_count"] = slide_count
                if file_size_bytes is not None:
                    payload["file_size_bytes"] = file_size_bytes

                response = await client.put(
                    f"{self._main_api_url}/api/v1/notebooks/internal/presentation/{presentation_id}/status",
                    json=payload,
                    headers={"X-API-Key": self._api_key},
                )
                response.raise_for_status()
                logger.debug(f"Updated status in main API: {status.value}")

        except Exception as e:
            logger.warning(f"Failed to update status in main API: {e}")

    async def _upload_file(
        self,
        presentation_id: str,
        notebook_id: str,
        tenant_id: str,
        file_bytes: bytes,
        filename: str,
    ) -> Optional[str]:
        """Save the PPTX file to local storage and return download URL."""
        try:
            # Use local storage path
            storage_base = Path(settings.local_storage_path)
            tenant_dir = storage_base / f"tenant-{tenant_id}" / "presentations" / presentation_id
            tenant_dir.mkdir(parents=True, exist_ok=True)

            # Write file
            file_path = tenant_dir / filename
            file_path.write_bytes(file_bytes)

            logger.info(f"Saved presentation to: {file_path}")

            # Generate download URL through the notebooks API
            download_url = f"{settings.public_api_url}/api/v1/notebooks/{notebook_id}/presentations/{presentation_id}/download"

            return download_url

        except Exception as e:
            logger.error(f"Failed to save file: {e}")
            return None

    async def get_status(self, presentation_id: str) -> Optional[Dict[str, Any]]:
        """Get the current status of a presentation generation."""
        return self._status_cache.get(presentation_id)

    async def cancel(self, presentation_id: str) -> bool:
        """Cancel an ongoing presentation generation."""
        if presentation_id in self._status_cache:
            status_info = self._status_cache[presentation_id]
            if status_info["status"] not in ["completed", "failed"]:
                await self._update_status(
                    presentation_id,
                    status=PresentationStatus.FAILED,
                    status_message="Generation cancelled by user",
                    error_message="Cancelled",
                )
                return True
        return False

    async def health_check(self) -> Dict[str, Any]:
        """Check health of dependencies."""
        vllm_healthy = await self.outline_generator.health_check()

        return {
            "vllm_healthy": vllm_healthy,
            "storage_healthy": True,  # Assume healthy for now
        }
