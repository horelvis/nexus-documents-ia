"""Security utilities for Weaviate service"""
from typing import Optional

from fastapi import HTTPException, Header
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

async def verify_api_key(x_api_key: Optional[str] = Header(None, alias="X-API-Key")) -> bool:
    """Verify the API key for microservice communication"""
    if not x_api_key:
        logger.warning("⚠️ No API key provided in X-API-Key header")
        raise HTTPException(
            status_code=401,
            detail="Missing API key"
        )
    
    if x_api_key != settings.MICROSERVICES_API_KEY:
        logger.warning(f"⚠️ Invalid API key provided: {x_api_key[:10]}...")
        raise HTTPException(
            status_code=401,
            detail="Invalid API key"
        )
    
    return True

def get_tenant_collection_name(tenant_id: str, collection_type: str = "documents") -> str:
    """Generate tenant-specific collection name for Weaviate"""
    # Note: Keep prefix case (Nouxcube_) but normalize tenant_id (replace hyphens with underscores)
    tenant_normalized = tenant_id.replace("-", "_")
    return f"{settings.collection_prefix}{tenant_normalized}_{collection_type}"


def get_channel_collection_name(tenant_id: str, channel_id: str) -> str:
    """
    Generate channel-specific collection name for Weaviate.

    This creates a separate collection for each information channel (Gmail, Drive, etc.)
    to keep data organized and enable channel-specific queries.

    Format: nexus_{tenant_id}_channel_{channel_id}

    Args:
        tenant_id: The tenant's UUID
        channel_id: The channel's UUID from the InformationChannel table

    Returns:
        Normalized collection name (lowercase, underscores instead of hyphens)

    Example:
        get_channel_collection_name(
            "1a94d369-8426-4d2b-afec-8971073fce1e",
            "4498a4a3-712c-47bf-8eeb-2927510bf4fc"
        )
        -> "nexus_1a94d369_8426_4d2b_afec_8971073fce1e_channel_4498a4a3_712c_47bf_8eeb_2927510bf4fc"
    """
    tenant_normalized = tenant_id.lower().replace("-", "_")
    channel_normalized = channel_id.lower().replace("-", "_")
    return f"{settings.collection_prefix}{tenant_normalized}_channel_{channel_normalized}"


def parse_channel_collection_name(collection_name: str) -> tuple[str, str] | None:
    """
    Parse a channel collection name to extract tenant_id and channel_id.

    Args:
        collection_name: The collection name to parse

    Returns:
        Tuple of (tenant_id, channel_id) or None if not a channel collection

    Example:
        parse_channel_collection_name(
            "nexus_1a94d369_8426_4d2b_afec_8971073fce1e_channel_4498a4a3_712c_47bf_8eeb_2927510bf4fc"
        )
        -> ("1a94d369-8426-4d2b-afec-8971073fce1e", "4498a4a3-712c-47bf-8eeb-2927510bf4fc")
    """
    import re

    # Pattern: nexus_{tenant_uuid}_channel_{channel_uuid}
    # UUID format after normalization: 8_4_4_4_12 (with underscores)
    pattern = r"^nexus_([a-f0-9]{8}_[a-f0-9]{4}_[a-f0-9]{4}_[a-f0-9]{4}_[a-f0-9]{12})_channel_([a-f0-9]{8}_[a-f0-9]{4}_[a-f0-9]{4}_[a-f0-9]{4}_[a-f0-9]{12})$"

    match = re.match(pattern, collection_name.lower())
    if not match:
        return None

    # Convert back to UUID format (underscores to hyphens)
    tenant_id = match.group(1).replace("_", "-")
    channel_id = match.group(2).replace("_", "-")

    return (tenant_id, channel_id)
