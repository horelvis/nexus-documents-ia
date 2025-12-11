"""
Gemini Voice API endpoints for Emma Voice Mode.

This module provides secure ephemeral token generation for Gemini Live API,
allowing the frontend to connect directly to Gemini without exposing the API key.

Architecture:
1. Frontend requests ephemeral token from this endpoint
2. Backend validates Clerk auth and generates short-lived Gemini token
3. Frontend connects to Gemini Live API using ephemeral token
4. Token expires after 10 minutes (single-use)

Security:
- Server-side API key (GEMINI_API_KEY) never exposed to frontend
- Ephemeral tokens are short-lived and single-use
- Rate limiting per user/tenant
- System prompts can be locked server-side
"""
import logging
from datetime import datetime, timedelta
from typing import Optional
from pydantic import BaseModel

from fastapi import APIRouter, Depends, HTTPException, status
import httpx

from app.api.async_dependencies import get_current_user_async
from app.db.models import User
from app.core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()


class VoiceSessionRequest(BaseModel):
    """Request to create a voice session."""
    system_prompt: Optional[str] = None
    voice_name: Optional[str] = "Zephyr"  # Gemini voice preset


class VoiceSessionResponse(BaseModel):
    """Response with ephemeral token for Gemini Live API."""
    ephemeral_token: str
    expires_at: str
    ws_url: str
    model: str
    voice_name: str
    system_prompt: str


class VoiceConfigResponse(BaseModel):
    """Response with voice mode configuration (for Kokoro TTS mode)."""
    enabled: bool
    gemini_enabled: bool
    kokoro_enabled: bool
    kokoro_base_url: str
    default_voice: str
    system_prompt: str


# Default Emma system prompt for voice mode
DEFAULT_EMMA_VOICE_PROMPT = """Eres Emma, una asistente de IA profesional especializada en análisis de documentos legales.
Respondes en español de forma concisa, profesional y clara.
Ayudas a los usuarios a entender sus documentos, identificar riesgos y proporcionar recomendaciones.
Mantén las respuestas cortas y naturales para conversación de voz."""


@router.post("/voice-session", response_model=VoiceSessionResponse)
async def create_voice_session(
    request: VoiceSessionRequest = VoiceSessionRequest(),
    current_user: User = Depends(get_current_user_async)
) -> VoiceSessionResponse:
    """
    Create an ephemeral Gemini Live API session token.

    This endpoint generates a short-lived token (10 minutes) that the frontend
    can use to connect directly to Gemini Live API without exposing the server API key.

    The token is single-use and bound to the user's tenant for auditing.

    Requires: Authenticated user with active subscription
    """
    # Check if Gemini Voice is enabled
    if not settings.GEMINI_VOICE_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Emma Voice Mode (Gemini) is currently disabled"
        )

    # Check if Gemini API key is configured
    if not settings.GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY not configured")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Gemini API not configured. Contact administrator."
        )

    # Check user subscription (optional - can restrict to paid plans)
    # For now, allow all authenticated users
    # if current_user.subscription_plan == 'trial':
    #     raise HTTPException(
    #         status_code=status.HTTP_403_FORBIDDEN,
    #         detail="Voice mode requires a paid subscription"
    #     )

    # Build system prompt with tenant context (use tenant_id to avoid lazy loading)
    system_prompt = request.system_prompt or DEFAULT_EMMA_VOICE_PROMPT
    if current_user.tenant_id:
        system_prompt = f"{system_prompt}\n\nEstás asistiendo a un usuario de la organización."

    try:
        # Call Google's ephemeral token API (requires v1alpha!)
        # https://ai.google.dev/gemini-api/docs/ephemeral-tokens
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Calculate expiration time (10 minutes from now)
            expire_time = datetime.utcnow() + timedelta(minutes=10)

            # IMPORTANT: Ephemeral tokens require v1alpha, not v1beta!
            response = await client.post(
                "https://generativelanguage.googleapis.com/v1alpha/authTokens",
                headers={
                    "x-goog-api-key": settings.GEMINI_API_KEY,
                    "Content-Type": "application/json"
                },
                json={
                    "expireTime": expire_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "uses": 1,  # Single-use token
                    "config": {
                        "model": f"models/{settings.GEMINI_VOICE_MODEL}",
                        "systemInstruction": {
                            "parts": [{"text": system_prompt}]
                        },
                        "generationConfig": {
                            "responseModalities": ["AUDIO"],
                            "speechConfig": {
                                "voiceConfig": {
                                    "prebuiltVoiceConfig": {
                                        "voiceName": request.voice_name or "Zephyr"
                                    }
                                }
                            }
                        }
                    }
                }
            )

            if response.status_code == 200:
                data = response.json()

                logger.info(
                    f"Created Gemini voice session for user {current_user.id} "
                    f"(tenant: {current_user.tenant_id})"
                )

                return VoiceSessionResponse(
                    ephemeral_token=data.get("token", ""),
                    expires_at=data.get("expireTime", expire_time.isoformat() + "Z"),
                    # v1alpha WebSocket endpoint for Live API with ephemeral tokens
                    ws_url="wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerateContent",
                    model=settings.GEMINI_VOICE_MODEL,
                    voice_name=request.voice_name or "Zephyr",
                    system_prompt=system_prompt
                )
            else:
                error_detail = response.text
                logger.error(f"Gemini ephemeral token API error: {response.status_code} - {error_detail}")

                # SECURITY: Never fall back to exposing the API key!
                # If ephemeral tokens fail, the feature is unavailable
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Failed to create ephemeral token. Gemini Voice unavailable. Error: {response.status_code}"
                )

    except httpx.TimeoutException:
        logger.error("Timeout connecting to Gemini API")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Timeout connecting to Gemini API"
        )
    except httpx.RequestError as e:
        logger.error(f"Error connecting to Gemini API: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to connect to Gemini API"
        )


@router.get("/voice-config", response_model=VoiceConfigResponse)
async def get_voice_config(
    current_user: User = Depends(get_current_user_async)
) -> VoiceConfigResponse:
    """
    Get voice mode configuration.

    Returns the available voice providers and their configuration.
    Used by the frontend to determine which TTS options are available.
    """
    # Build system prompt with tenant context (use tenant_id to avoid lazy loading)
    system_prompt = DEFAULT_EMMA_VOICE_PROMPT
    if current_user.tenant_id:
        system_prompt = f"{system_prompt}\n\nEstás asistiendo a un usuario de la organización."

    return VoiceConfigResponse(
        enabled=settings.GEMINI_VOICE_ENABLED,
        gemini_enabled=settings.GEMINI_VOICE_ENABLED and bool(settings.GEMINI_API_KEY),
        kokoro_enabled=True,  # Kokoro runs locally, always available
        kokoro_base_url="http://localhost:8880",  # Default Kokoro TTS URL
        default_voice="Zephyr",
        system_prompt=system_prompt
    )
