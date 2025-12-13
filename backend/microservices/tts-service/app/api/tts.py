"""
TTS API Endpoints

REST and WebSocket endpoints for text-to-speech synthesis.
"""

import asyncio
import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, Query, status
from fastapi.responses import Response

from app.core.config import settings
from app.core.security import verify_api_key, get_tenant_context, verify_websocket_api_key
from app.schemas.tts import (
    SynthesizeRequest,
    SynthesizeResponse,
    StreamMessage,
    StreamChunk,
    VoicesResponse,
    HealthResponse,
    ErrorResponse,
)
from app.services.tts_provider_factory import TTSProviderFactory
from app.services.audio_utils import (
    audio_to_base64,
    generate_cache_key,
    calculate_duration_ms,
    get_audio_cache,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/tts", tags=["TTS"])


@router.get("/voices", response_model=VoicesResponse)
async def list_voices(
    _: bool = Depends(verify_api_key)
) -> VoicesResponse:
    """
    List available TTS voices.

    Returns all voices supported by the configured TTS provider.
    """
    try:
        provider = await TTSProviderFactory.get_provider()
        voices = provider.get_available_voices()

        return VoicesResponse(
            voices=voices,
            default_voice_id=settings.vibevoice_default_voice
            if settings.tts_provider == "vibevoice"
            else settings.google_tts_default_voice
        )
    except Exception as e:
        logger.error(f"Failed to list voices: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/synthesize", response_model=SynthesizeResponse)
async def synthesize(
    request: SynthesizeRequest,
    _: bool = Depends(verify_api_key),
    tenant_context: dict = Depends(get_tenant_context)
) -> SynthesizeResponse:
    """
    Synthesize text to speech (batch mode).

    Converts the entire text to audio and returns the complete result.
    For longer texts, consider using the streaming endpoint.

    Args:
        request: Synthesis request with text and voice parameters

    Returns:
        Complete audio as base64 with metadata
    """
    try:
        logger.info(
            f"Synthesis request: {len(request.text)} chars, "
            f"voice={request.voice_id}, lang={request.language}"
        )

        # Check cache first
        cache = await get_audio_cache()
        cache_key = generate_cache_key(
            text=request.text,
            voice_id=request.voice_id or settings.vibevoice_default_voice,
            language=request.language or "en-US",
            speed=request.speed or 1.0,
            provider=TTSProviderFactory.get_provider_name()
        )

        cached_audio = await cache.get(cache_key)
        if cached_audio:
            logger.info("Returning cached audio")
            return SynthesizeResponse(
                audio_base64=audio_to_base64(cached_audio),
                format="wav",
                duration_ms=calculate_duration_ms(cached_audio),
                sample_rate=settings.audio_sample_rate,
                text_length=len(request.text)
            )

        # Get TTS provider and synthesize
        provider = await TTSProviderFactory.get_provider()

        audio_bytes, duration_ms = await provider.synthesize(
            text=request.text,
            voice_id=request.voice_id or settings.vibevoice_default_voice,
            language=request.language or "en-US",
            speed=request.speed or 1.0
        )

        # Cache the result
        await cache.set(cache_key, audio_bytes)

        return SynthesizeResponse(
            audio_base64=audio_to_base64(audio_bytes),
            format="wav",
            duration_ms=duration_ms,
            sample_rate=settings.audio_sample_rate,
            text_length=len(request.text)
        )

    except ValueError as e:
        logger.error(f"Synthesis error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Synthesis failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"TTS synthesis failed: {str(e)}"
        )


@router.websocket("/stream")
async def stream_tts(
    websocket: WebSocket,
    api_key: Optional[str] = Query(None, alias="api_key"),
    tenant_id: Optional[str] = Query(None, alias="tenant_id"),
    user_id: Optional[str] = Query(None, alias="user_id")
):
    """
    WebSocket endpoint for streaming TTS.

    Accepts text chunks and streams back audio chunks in real-time.
    Provides low-latency audio for interactive applications.

    Protocol:
    - Client sends: {"text": "...", "voice_id": "...", "language": "...", "is_final": false}
    - Server sends: {"audio_chunk": "base64...", "chunk_index": 0, "is_final": false}

    Query Parameters:
        api_key: API key for authentication
        tenant_id: Tenant ID for multi-tenancy
        user_id: User ID for tracking
    """
    # Verify API key
    if not verify_websocket_api_key(api_key):
        await websocket.close(code=4001, reason="Invalid or missing API key")
        return

    await websocket.accept()
    logger.info(f"WebSocket connected: tenant={tenant_id}, user={user_id}")

    try:
        provider = await TTSProviderFactory.get_provider()

        while True:
            # Receive message from client
            try:
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=settings.websocket_ping_timeout
                )
            except asyncio.TimeoutError:
                # Send ping to keep connection alive
                await websocket.send_json({"type": "ping"})
                continue

            try:
                message = StreamMessage.model_validate_json(data)
            except Exception as e:
                await websocket.send_json({
                    "error": f"Invalid message format: {e}",
                    "is_final": True
                })
                continue

            logger.debug(f"Stream request: {len(message.text)} chars")

            # Stream audio chunks
            chunk_index = 0
            try:
                async for audio_chunk in provider.stream_synthesize(
                    text=message.text,
                    voice_id=message.voice_id or settings.vibevoice_default_voice,
                    language=message.language or "en-US"
                ):
                    response = StreamChunk(
                        audio_chunk=audio_to_base64(audio_chunk),
                        chunk_index=chunk_index,
                        is_final=False
                    )
                    await websocket.send_text(response.model_dump_json())
                    chunk_index += 1

                # Send final message
                final_response = StreamChunk(
                    audio_chunk="",
                    chunk_index=chunk_index,
                    is_final=True
                )
                await websocket.send_text(final_response.model_dump_json())

            except Exception as e:
                logger.error(f"Streaming error: {e}")
                error_response = StreamChunk(
                    audio_chunk="",
                    chunk_index=chunk_index,
                    is_final=True,
                    error=str(e)
                )
                await websocket.send_text(error_response.model_dump_json())

            # If client indicates this is the final chunk, close connection
            if message.is_final:
                logger.info("Client indicated final message, closing connection")
                break

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected by client")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        try:
            await websocket.close(code=1011, reason=str(e))
        except Exception:
            pass


@router.get("/health", response_model=HealthResponse)
async def health_check(
    _: bool = Depends(verify_api_key)
) -> HealthResponse:
    """
    Authenticated health check endpoint.

    Returns detailed health status including provider and GPU info.
    """
    try:
        health = await TTSProviderFactory.health_check()

        return HealthResponse(
            status=health.get("status", "unknown"),
            service=settings.service_name,
            version=settings.service_version,
            provider=health.get("provider", settings.tts_provider),
            model_loaded=health.get("model_loaded", False),
            gpu_available=health.get("gpu_available", False)
        )
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return HealthResponse(
            status="unhealthy",
            service=settings.service_name,
            version=settings.service_version,
            provider=settings.tts_provider,
            model_loaded=False,
            gpu_available=False
        )
