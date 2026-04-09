"""Channels API — CRUD for multi-channel configuration + webhook endpoints.

Endpoints:
    POST   /channels                              — Create channel
    GET    /channels                              — List channels
    GET    /channels/{id}                         — Get channel
    PATCH  /channels/{id}                         — Update channel
    DELETE /channels/{id}                         — Delete channel
    GET    /channels/{id}/health                  — Health check
    POST   /channels/webhooks/{channel_type}      — Inbound webhook
    POST   /channels/pairing/confirm              — Confirm pairing code
"""
import json
import logging
import uuid
from typing import Any, Dict, List, Optional

from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.core.auth_headers import extract_user_id, extract_user_roles
from app.core.config import settings
from app.services.channel_router import channel_router
from app.services.pairing_service import pairing_service

logger = logging.getLogger(__name__)
router = APIRouter()

# Encryption for channel credentials
_fernet: Optional[Fernet] = None


def _get_fernet() -> Optional[Fernet]:
    global _fernet
    if _fernet is None:
        key = getattr(settings, "credentials_encryption_key", None) or settings.__dict__.get("CREDENTIALS_ENCRYPTION_KEY")
        if not key:
            import os
            key = os.getenv("CREDENTIALS_ENCRYPTION_KEY", "")
        if key:
            _fernet = Fernet(key.encode() if isinstance(key, str) else key)
    return _fernet


def _encrypt_credentials(plaintext: str) -> str:
    f = _get_fernet()
    if f:
        return f.encrypt(plaintext.encode()).decode()
    return plaintext  # Fallback: store unencrypted (dev only)


def _decrypt_credentials(ciphertext: str) -> str:
    f = _get_fernet()
    if f and ciphertext:
        try:
            return f.decrypt(ciphertext.encode()).decode()
        except Exception:
            return ciphertext
    return ciphertext


# Redis-backed channel storage (same pattern as triggers)
import redis.asyncio as aioredis

CHANNELS_PREFIX = "emma:channels"
_redis = None


async def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.Redis(
            host=settings.redis_host, port=settings.redis_port, decode_responses=True
        )
    return _redis


# ── Schemas ──────────────────────────────────────────────────────────

class ChannelCreate(BaseModel):
    channel_type: str = Field(..., description="whatsapp | telegram | slack | email")
    channel_name: str = Field(..., max_length=255)
    config: Dict[str, Any]
    credentials: Optional[str] = Field(None, description="Plain-text credentials (will be encrypted)")
    auto_respond: bool = True
    default_agent: Optional[str] = None
    routing_rules: Optional[Dict[str, Any]] = None


class ChannelUpdate(BaseModel):
    channel_name: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    credentials: Optional[str] = None
    auto_respond: Optional[bool] = None
    default_agent: Optional[str] = None
    routing_rules: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


class PairingConfirm(BaseModel):
    code: str
    user_id: str


# ── CRUD ─────────────────────────────────────────────────────────────

@router.post("/channels")
async def create_channel(
    body: ChannelCreate,
    user_id: Optional[str] = Depends(extract_user_id),
):
    """Create a new messaging channel."""
    r = await _get_redis()
    channel_id = str(uuid.uuid4())

    channel_data = {
        "id": channel_id,
        **body.model_dump(exclude={"credentials"}),
        "credentials_encrypted": _encrypt_credentials(body.credentials or "") if body.credentials else None,
        "is_active": True,
        "created_by": user_id,
    }
    await r.set(f"{CHANNELS_PREFIX}:{channel_id}", json.dumps(channel_data))
    await r.sadd(f"{CHANNELS_PREFIX}:index", channel_id)

    # Don't return encrypted credentials
    channel_data.pop("credentials_encrypted", None)
    return channel_data


@router.get("/channels")
async def list_channels():
    """List all channels."""
    r = await _get_redis()
    channel_ids = await r.smembers(f"{CHANNELS_PREFIX}:index")
    channels = []
    for cid in channel_ids:
        data = await r.get(f"{CHANNELS_PREFIX}:{cid}")
        if data:
            ch = json.loads(data)
            ch.pop("credentials_encrypted", None)
            channels.append(ch)
    return {"channels": channels, "total": len(channels)}


@router.get("/channels/{channel_id}")
async def get_channel(channel_id: str):
    r = await _get_redis()
    data = await r.get(f"{CHANNELS_PREFIX}:{channel_id}")
    if not data:
        raise HTTPException(status_code=404, detail="Channel not found")
    ch = json.loads(data)
    ch.pop("credentials_encrypted", None)
    return ch


@router.patch("/channels/{channel_id}")
async def update_channel(
    channel_id: str,
    body: ChannelUpdate,
):
    r = await _get_redis()
    key = f"{CHANNELS_PREFIX}:{channel_id}"
    data = await r.get(key)
    if not data:
        raise HTTPException(status_code=404, detail="Channel not found")

    channel = json.loads(data)
    updates = body.model_dump(exclude_unset=True)

    if "credentials" in updates:
        channel["credentials_encrypted"] = _encrypt_credentials(updates.pop("credentials"))

    channel.update(updates)
    await r.set(key, json.dumps(channel))
    channel.pop("credentials_encrypted", None)
    return channel


@router.delete("/channels/{channel_id}")
async def delete_channel(channel_id: str):
    r = await _get_redis()
    deleted = await r.delete(f"{CHANNELS_PREFIX}:{channel_id}")
    await r.srem(f"{CHANNELS_PREFIX}:index", channel_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Channel not found")
    return {"deleted": True}


@router.get("/channels/{channel_id}/health")
async def channel_health(channel_id: str):
    """Check channel connectivity."""
    r = await _get_redis()
    data = await r.get(f"{CHANNELS_PREFIX}:{channel_id}")
    if not data:
        raise HTTPException(status_code=404, detail="Channel not found")

    ch = json.loads(data)
    credentials = _decrypt_credentials(ch.get("credentials_encrypted", ""))
    instance = channel_router.get_channel_instance(
        channel_id, ch["channel_type"], ch["config"], credentials
    )
    return await instance.health_check()


# ── Webhook Endpoints ────────────────────────────────────────────────

@router.post("/channels/webhooks/{channel_type}")
async def inbound_webhook(
    channel_type: str,
    request: Request,
):
    """Receive inbound messages from external channels."""
    # Parse body based on content type
    content_type = request.headers.get("content-type", "")
    if "json" in content_type:
        webhook_data = await request.json()
    else:
        form_data = await request.form()
        webhook_data = dict(form_data)

    # Slack URL verification challenge
    if channel_type == "slack" and webhook_data.get("type") == "url_verification":
        return {"challenge": webhook_data.get("challenge")}

    # Find the channel config for this type
    r = await _get_redis()
    channel_ids = await r.smembers(f"{CHANNELS_PREFIX}:index")
    target_channel = None

    for cid in channel_ids:
        data = await r.get(f"{CHANNELS_PREFIX}:{cid}")
        if data:
            ch = json.loads(data)
            if ch.get("channel_type") == channel_type and ch.get("is_active"):
                target_channel = ch
                break

    if not target_channel:
        raise HTTPException(status_code=404, detail=f"No active {channel_type} channel found")

    credentials = _decrypt_credentials(target_channel.get("credentials_encrypted", ""))

    result = await channel_router.route_inbound(
        channel_id=target_channel["id"],
        channel_type=channel_type,
        config=target_channel["config"],
        credentials=credentials,
        webhook_data=webhook_data,
    )
    return result


# ── Pairing ──────────────────────────────────────────────────────────

@router.post("/channels/pairing/confirm")
async def confirm_pairing(body: PairingConfirm):
    """Confirm a pairing code to link external user → internal user."""
    result = await pairing_service.confirm_pairing(body.code, body.user_id)
    if not result:
        raise HTTPException(status_code=400, detail="Invalid or expired pairing code")
    return result
