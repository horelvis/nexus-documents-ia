"""Pairing Service — Links external channel users to KeyCloak identities.

Flow:
1. External user sends first message -> receives a 6-digit pairing code
2. User enters code in NouxCubeIA web UI -> confirms pairing
3. Future messages from that external ID are mapped to the internal user
"""
import logging
import random
import string
from typing import Any, Dict, Optional

import redis.asyncio as aioredis

from app.core.config import settings

logger = logging.getLogger(__name__)

PAIRING_PREFIX = "emma:pairing"
PAIRED_PREFIX = "emma:paired"
PAIRING_CODE_TTL = 600  # 10 minutes


class PairingService:
    """Manages channel user <-> KeyCloak user pairing."""

    def __init__(self):
        self._redis: Optional[aioredis.Redis] = None

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                decode_responses=True,
            )
        return self._redis

    async def generate_pairing_code(
        self, channel_type: str, external_id: str
    ) -> str:
        """Generate a 6-digit pairing code for an external user."""
        r = await self._get_redis()
        code = "".join(random.choices(string.digits, k=6))

        # Store code -> external identity mapping
        key = f"{PAIRING_PREFIX}:code:{code}"
        import json
        await r.set(
            key,
            json.dumps({
                "channel_type": channel_type,
                "external_id": external_id,
            }),
            ex=PAIRING_CODE_TTL,
        )
        logger.info(f"Generated pairing code {code} for {channel_type}:{external_id}")
        return code

    async def confirm_pairing(
        self, code: str, user_id: str
    ) -> Optional[Dict[str, Any]]:
        """Confirm a pairing code, linking external user to internal user_id."""
        r = await self._get_redis()
        key = f"{PAIRING_PREFIX}:code:{code}"
        data = await r.get(key)

        if not data:
            return None

        import json
        pairing_info = json.loads(data)
        channel_type = pairing_info["channel_type"]
        external_id = pairing_info["external_id"]

        # Store the permanent pairing
        pair_key = f"{PAIRED_PREFIX}:{channel_type}:{external_id}"
        await r.set(
            pair_key,
            json.dumps({"user_id": user_id}),
        )

        # Delete the code
        await r.delete(key)

        logger.info(f"Paired {channel_type}:{external_id} -> user {user_id}")
        return {"channel_type": channel_type, "external_id": external_id, "user_id": user_id}

    async def get_pairing(
        self, channel_type: str, external_id: str
    ) -> Optional[Dict[str, Any]]:
        """Look up the internal user for an external channel identity."""
        r = await self._get_redis()
        pair_key = f"{PAIRED_PREFIX}:{channel_type}:{external_id}"
        data = await r.get(pair_key)
        if data:
            import json
            return json.loads(data)
        return None

    async def revoke_pairing(
        self, channel_type: str, external_id: str
    ) -> bool:
        """Remove a pairing."""
        r = await self._get_redis()
        pair_key = f"{PAIRED_PREFIX}:{channel_type}:{external_id}"
        return await r.delete(pair_key) > 0


# Global singleton
pairing_service = PairingService()
