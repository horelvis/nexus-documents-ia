"""
TTS API Endpoints (Proxy)

Proxy endpoints for the TTS microservice.
Handles authentication and forwards requests to the TTS service.
Includes WebSocket proxy for streaming TTS.
"""

import asyncio
import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import websockets

from app.api.async_dependencies import get_current_user_async
from app.db.models import User
from app.services.tts_client import get_tts_client
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


class SynthesizeRequest(BaseModel):
    """Request model for TTS synthesis."""

    text: str = Field(..., min_length=1, max_length=5000, description="Text to synthesize")
    voice_id: Optional[str] = Field(default=None, description="Voice identifier")
    language: Optional[str] = Field(default=None, description="Language code (en-US, es-ES)")
    speed: float = Field(default=1.0, ge=0.5, le=2.0, description="Playback speed")


class SynthesizeResponse(BaseModel):
    """Response model for TTS synthesis."""

    audio_base64: str
    format: str
    duration_ms: int
    sample_rate: int
    text_length: int


class VoiceInfo(BaseModel):
    """Voice information model."""

    voice_id: str
    name: str
    language: str
    gender: Optional[str] = None
    description: Optional[str] = None
    provider: str


class VoicesResponse(BaseModel):
    """Response model for listing voices."""

    voices: list[VoiceInfo]
    default_voice_id: str


class TTSHealthResponse(BaseModel):
    """TTS service health response."""

    status: str
    service: str
    version: str
    provider: str
    model_loaded: bool
    gpu_available: bool


class WebSocketInfoResponse(BaseModel):
    """WebSocket connection information."""

    websocket_url: str
    protocol: str = "wss"


@router.post("/synthesize", response_model=SynthesizeResponse)
async def synthesize_text(
    request: SynthesizeRequest,
    current_user: User = Depends(get_current_user_async)
):
    """
    Synthesize text to speech.

    Converts text to audio using the configured TTS provider (VibeVoice or Google TTS).

    Args:
        request: Text and synthesis parameters
        current_user: Authenticated user

    Returns:
        Audio as base64 with metadata
    """
    try:
        client = get_tts_client(
            tenant_id=str(current_user.tenant_id),
            user_id=str(current_user.id)
        )

        result = await client.synthesize(
            text=request.text,
            voice_id=request.voice_id,
            language=request.language,
            speed=request.speed
        )

        return SynthesizeResponse(**result)

    except Exception as e:
        logger.error(f"TTS synthesis failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"TTS synthesis failed: {str(e)}"
        )


@router.get("/voices", response_model=VoicesResponse)
async def list_voices(
    current_user: User = Depends(get_current_user_async)
):
    """
    List available TTS voices.

    Returns all voices supported by the configured TTS provider.
    """
    try:
        client = get_tts_client(
            tenant_id=str(current_user.tenant_id),
            user_id=str(current_user.id)
        )

        result = await client.get_voices()

        return VoicesResponse(
            voices=[VoiceInfo(**v) for v in result.get("voices", [])],
            default_voice_id=result.get("default_voice_id", "Carter")
        )

    except Exception as e:
        logger.error(f"Failed to list TTS voices: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list voices: {str(e)}"
        )


@router.get("/health", response_model=TTSHealthResponse)
async def tts_health(
    current_user: User = Depends(get_current_user_async)
):
    """
    Check TTS service health.

    Returns detailed status of the TTS service including provider and GPU info.
    """
    try:
        client = get_tts_client(
            tenant_id=str(current_user.tenant_id),
            user_id=str(current_user.id)
        )

        result = await client.health_check()

        return TTSHealthResponse(
            status=result.get("status", "unknown"),
            service=result.get("service", "tts-service"),
            version=result.get("version", "unknown"),
            provider=result.get("provider", "unknown"),
            model_loaded=result.get("model_loaded", False),
            gpu_available=result.get("gpu_available", False)
        )

    except Exception as e:
        logger.error(f"TTS health check failed: {e}")
        return TTSHealthResponse(
            status="unhealthy",
            service="tts-service",
            version="unknown",
            provider="unknown",
            model_loaded=False,
            gpu_available=False
        )


@router.get("/websocket-info", response_model=WebSocketInfoResponse)
async def get_websocket_info(
    current_user: User = Depends(get_current_user_async)
):
    """
    Get WebSocket connection information for streaming TTS.

    Returns the WebSocket URL for the proxy endpoint (not direct TTS service).
    Frontend connects to this backend's WebSocket which proxies to TTS service.
    """
    # Return the proxy endpoint URL (frontend will construct full URL)
    return WebSocketInfoResponse(
        websocket_url="/api/v1/tts/stream",
        protocol="wss"
    )


async def _verify_websocket_token(token: str) -> Optional[dict]:
    """
    Verify Clerk JWT token for WebSocket connections.
    Returns payload dict with user info or None if invalid.
    """
    import jwt
    from jwt import PyJWKClient

    if not token:
        return None

    try:
        # Decode without verification to get issuer
        unverified = jwt.decode(token, options={"verify_signature": False})
        issuer = unverified.get('iss', '')

        if not issuer:
            return None

        # Verify with JWKS
        jwks_client = PyJWKClient(f"{issuer}/.well-known/jwks.json")
        signing_key = jwks_client.get_signing_key_from_jwt(token)

        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            options={"verify_aud": False}
        )

        return payload

    except Exception as e:
        logger.warning(f"WebSocket token verification failed: {e}")
        return None


@router.websocket("/stream")
async def stream_tts_proxy(
    websocket: WebSocket,
    token: Optional[str] = Query(None, alias="token"),
):
    """
    WebSocket proxy endpoint for streaming TTS.

    Proxies WebSocket connections from frontend to internal TTS service.
    Handles authentication via Clerk token in query params.

    Protocol:
    - Client sends: {"text": "...", "voice_id": "...", "language": "...", "is_final": false}
    - Server sends: {"audio_chunk": "base64...", "chunk_index": 0, "is_final": false}

    Query Parameters:
        token: Clerk JWT token for authentication
    """
    # Verify token
    if not token:
        await websocket.close(code=4001, reason="Missing authentication token")
        return

    payload = await _verify_websocket_token(token)
    if not payload:
        await websocket.close(code=4001, reason="Invalid authentication token")
        return

    clerk_user_id = payload.get('sub')
    if not clerk_user_id:
        await websocket.close(code=4001, reason="Invalid token: no user ID")
        return

    # Accept WebSocket connection from frontend
    await websocket.accept()
    logger.info(f"TTS WebSocket proxy connected for user: {clerk_user_id}")

    # Get internal TTS service WebSocket URL
    tts_client = get_tts_client()
    internal_ws_url = tts_client.get_websocket_url()

    try:
        # Connect to internal TTS service
        async with websockets.connect(internal_ws_url) as tts_ws:
            logger.info(f"Connected to TTS service WebSocket")

            async def forward_to_tts():
                """Forward messages from frontend to TTS service"""
                try:
                    async for message in websocket.iter_text():
                        await tts_ws.send(message)
                except WebSocketDisconnect:
                    logger.info("Frontend WebSocket disconnected")
                except Exception as e:
                    logger.error(f"Error forwarding to TTS: {e}")

            async def forward_to_frontend():
                """Forward messages from TTS service to frontend"""
                try:
                    async for message in tts_ws:
                        await websocket.send_text(message)
                except Exception as e:
                    logger.error(f"Error forwarding to frontend: {e}")

            # Run both forwarding tasks concurrently
            await asyncio.gather(
                forward_to_tts(),
                forward_to_frontend(),
                return_exceptions=True
            )

    except websockets.exceptions.ConnectionClosed as e:
        logger.info(f"TTS service WebSocket closed: {e}")
    except Exception as e:
        logger.error(f"TTS WebSocket proxy error: {e}")
        try:
            await websocket.send_json({"error": str(e), "is_final": True})
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
        logger.info("TTS WebSocket proxy connection closed")
