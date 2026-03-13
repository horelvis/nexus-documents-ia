"""
Verified Context Cache for Agent Self-Verifies pattern.

Provides Redis-backed storage for verified claims during document generation.
Claims are stored per session with automatic TTL expiration.

Key format: verified:{tenant_id}:{session_id}
Type: Redis List (lpush/lrange for ordered claims)
TTL: Configurable (default 3600 seconds)
"""

from __future__ import annotations

import json
import logging
from typing import List, Optional

import redis.asyncio as redis

from app.core.config import settings
from app.schemas.verified_generation import VerifiedClaim, VerificationStatus

logger = logging.getLogger(__name__)


class VerifiedContextCache:
    """
    Redis-backed cache for verified claims.

    Stores verified claims in order as they are generated and validated.
    Each session has its own list of claims with automatic expiration.

    Key Structure:
        verified:{tenant_id}:{session_id} -> List of JSON-serialized VerifiedClaim
        verify:job:{job_id} -> Hash with job status

    Usage:
        cache = VerifiedContextCache()
        await cache.connect()

        # Add a verified claim
        await cache.add_verified_claim(tenant_id, session_id, claim)

        # Get all verified claims
        claims = await cache.get_verified_claims(tenant_id, session_id)

        # Clear session
        await cache.clear_session(tenant_id, session_id)
    """

    # Key prefixes
    CLAIMS_KEY_PREFIX = "verified"
    JOB_KEY_PREFIX = "verify:job"

    # Default TTL: 1 hour
    DEFAULT_TTL_SECONDS = 3600

    def __init__(
        self,
        redis_url: Optional[str] = None,
        ttl_seconds: int = DEFAULT_TTL_SECONDS
    ):
        """
        Initialize the verified context cache.

        Args:
            redis_url: Redis connection URL. Uses settings if not provided.
            ttl_seconds: TTL for cached data in seconds.
        """
        self._redis_url = redis_url or settings.redis_url
        self._ttl = ttl_seconds
        self._redis: Optional[redis.Redis] = None

    async def connect(self) -> None:
        """Establish Redis connection."""
        if self._redis is None:
            self._redis = redis.from_url(
                self._redis_url,
                encoding="utf-8",
                decode_responses=True
            )
            logger.info("✅ VerifiedContextCache connected to Redis")

    async def close(self) -> None:
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()
            self._redis = None

    def _make_claims_key(self, tenant_id: str, session_id: str) -> str:
        """Generate Redis key for claims list."""
        return f"{self.CLAIMS_KEY_PREFIX}:{tenant_id}:{session_id}"

    def _make_job_key(self, job_id: str) -> str:
        """Generate Redis key for verification job status."""
        return f"{self.JOB_KEY_PREFIX}:{job_id}"

    def _make_meta_key(self, tenant_id: str, session_id: str) -> str:
        """Generate Redis key for session metadata."""
        return f"{self.CLAIMS_KEY_PREFIX}:meta:{tenant_id}:{session_id}"

    async def store_session_metadata(
        self,
        tenant_id: str,
        session_id: str,
        metadata: dict,
    ) -> None:
        """Store session metadata (query, created_at, etc.) in Redis."""
        await self.connect()
        key = self._make_meta_key(tenant_id, session_id)
        await self._redis.set(key, json.dumps(metadata), ex=self._ttl)
        logger.info(f"📝 Stored session metadata for {session_id[:16]}...")

    async def get_session_metadata(
        self,
        tenant_id: str,
        session_id: str,
    ) -> dict:
        """Retrieve session metadata from Redis."""
        await self.connect()
        key = self._make_meta_key(tenant_id, session_id)
        data = await self._redis.get(key)
        if data:
            return json.loads(data)
        return {}

    async def add_verified_claim(
        self,
        tenant_id: str,
        session_id: str,
        claim: VerifiedClaim
    ) -> int:
        """
        Add a verified claim to the session cache.

        Claims are stored in order using Redis RPUSH (append to end).
        This maintains the generation order for document assembly.

        Args:
            tenant_id: Tenant identifier
            session_id: Session identifier
            claim: The verified claim to add

        Returns:
            Number of claims in the session after adding
        """
        await self.connect()

        key = self._make_claims_key(tenant_id, session_id)

        try:
            # Serialize claim to JSON
            claim_json = json.dumps(claim.to_dict())

            # RPUSH to maintain order (append to end)
            count = await self._redis.rpush(key, claim_json)

            # Set/refresh TTL
            await self._redis.expire(key, self._ttl)

            logger.info(
                f"📝 Added verified claim #{claim.generation_order} "
                f"(confidence={claim.confidence:.2f}, status={claim.status.value}) "
                f"to session {session_id[:16]}..."
            )

            return count

        except Exception as e:
            logger.error(f"❌ Failed to add verified claim: {e}")
            raise

    async def get_verified_claims(
        self,
        tenant_id: str,
        session_id: str
    ) -> List[VerifiedClaim]:
        """
        Get all verified claims for a session.

        Returns claims in generation order (oldest first).

        Args:
            tenant_id: Tenant identifier
            session_id: Session identifier

        Returns:
            List of VerifiedClaim objects
        """
        await self.connect()

        key = self._make_claims_key(tenant_id, session_id)

        try:
            # LRANGE 0 -1 gets all elements
            claims_json = await self._redis.lrange(key, 0, -1)

            claims = []
            for claim_json in claims_json:
                try:
                    data = json.loads(claim_json)
                    claim = VerifiedClaim.from_dict(data)
                    claims.append(claim)
                except (json.JSONDecodeError, KeyError) as e:
                    logger.warning(f"⚠️ Failed to deserialize claim: {e}")
                    continue

            logger.debug(
                f"📖 Retrieved {len(claims)} verified claims "
                f"for session {session_id[:16]}..."
            )

            return claims

        except Exception as e:
            logger.error(f"❌ Failed to get verified claims: {e}")
            return []

    async def get_claims_count(
        self,
        tenant_id: str,
        session_id: str
    ) -> int:
        """
        Get the number of verified claims in a session.

        Args:
            tenant_id: Tenant identifier
            session_id: Session identifier

        Returns:
            Number of claims
        """
        await self.connect()

        key = self._make_claims_key(tenant_id, session_id)

        try:
            return await self._redis.llen(key)
        except Exception as e:
            logger.error(f"❌ Failed to get claims count: {e}")
            return 0

    async def get_latest_claim(
        self,
        tenant_id: str,
        session_id: str
    ) -> Optional[VerifiedClaim]:
        """
        Get the most recently added claim.

        Args:
            tenant_id: Tenant identifier
            session_id: Session identifier

        Returns:
            The latest VerifiedClaim or None
        """
        await self.connect()

        key = self._make_claims_key(tenant_id, session_id)

        try:
            # LINDEX -1 gets the last element
            claim_json = await self._redis.lindex(key, -1)

            if claim_json:
                data = json.loads(claim_json)
                return VerifiedClaim.from_dict(data)

            return None

        except Exception as e:
            logger.error(f"❌ Failed to get latest claim: {e}")
            return None

    async def clear_session(
        self,
        tenant_id: str,
        session_id: str
    ) -> bool:
        """
        Clear all claims for a session.

        Args:
            tenant_id: Tenant identifier
            session_id: Session identifier

        Returns:
            True if cleared successfully
        """
        await self.connect()

        key = self._make_claims_key(tenant_id, session_id)

        try:
            await self._redis.delete(key)
            logger.info(f"🗑️ Cleared verified claims for session {session_id[:16]}...")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to clear session: {e}")
            return False

    async def extend_ttl(
        self,
        tenant_id: str,
        session_id: str
    ) -> bool:
        """
        Extend TTL for an active session.

        Call this periodically during generation to prevent expiration.

        Args:
            tenant_id: Tenant identifier
            session_id: Session identifier

        Returns:
            True if TTL extended
        """
        await self.connect()

        key = self._make_claims_key(tenant_id, session_id)

        try:
            result = await self._redis.expire(key, self._ttl)
            return result
        except Exception as e:
            logger.error(f"❌ Failed to extend TTL: {e}")
            return False

    async def get_ttl_remaining(
        self,
        tenant_id: str,
        session_id: str
    ) -> Optional[int]:
        """
        Get remaining TTL for a session in seconds.

        Args:
            tenant_id: Tenant identifier
            session_id: Session identifier

        Returns:
            Remaining TTL in seconds, or None if key doesn't exist
        """
        await self.connect()

        key = self._make_claims_key(tenant_id, session_id)

        try:
            ttl = await self._redis.ttl(key)
            return ttl if ttl > 0 else None
        except Exception as e:
            logger.error(f"❌ Failed to get TTL: {e}")
            return None

    # =========================================================================
    # HITL Review — Claim Mutation Methods
    # =========================================================================

    async def remove_claim(
        self,
        tenant_id: str,
        session_id: str,
        claim_id: str,
    ) -> bool:
        """
        Remove a single claim from the session by ID.

        Used by HITL review to reject individual claims.
        Redis Lists don't support removal by index efficiently, so we
        read all, filter, delete, and re-push.

        Args:
            tenant_id: Tenant identifier
            session_id: Session identifier
            claim_id: ID of the claim to remove

        Returns:
            True if the claim was found and removed
        """
        await self.connect()
        key = self._make_claims_key(tenant_id, session_id)

        try:
            claims_json = await self._redis.lrange(key, 0, -1)
            new_claims = []
            removed = False

            for cj in claims_json:
                try:
                    data = json.loads(cj)
                    if data.get("id") == claim_id:
                        removed = True
                        continue
                    new_claims.append(cj)
                except json.JSONDecodeError:
                    new_claims.append(cj)

            if removed:
                # Atomic replace: delete + re-push
                pipe = self._redis.pipeline()
                pipe.delete(key)
                if new_claims:
                    pipe.rpush(key, *new_claims)
                    pipe.expire(key, self._ttl)
                await pipe.execute()
                logger.info(
                    f"🗑️ Removed claim {claim_id[:16]}... "
                    f"from session {session_id[:16]}..."
                )

            return removed

        except Exception as e:
            logger.error(f"❌ Failed to remove claim: {e}")
            return False

    async def update_claim_text(
        self,
        tenant_id: str,
        session_id: str,
        claim_id: str,
        new_text: str,
    ) -> bool:
        """
        Update a claim's text and set its status to 'corrected'.

        Used by HITL review when a human edits a claim.

        Args:
            tenant_id: Tenant identifier
            session_id: Session identifier
            claim_id: ID of the claim to update
            new_text: New claim text

        Returns:
            True if the claim was found and updated
        """
        await self.connect()
        key = self._make_claims_key(tenant_id, session_id)

        try:
            claims_json = await self._redis.lrange(key, 0, -1)
            updated = False

            new_claims = []
            for cj in claims_json:
                try:
                    data = json.loads(cj)
                    if data.get("id") == claim_id:
                        data["original_text"] = data.get("text", "")
                        data["text"] = new_text
                        data["status"] = "corrected"
                        updated = True
                    new_claims.append(json.dumps(data))
                except json.JSONDecodeError:
                    new_claims.append(cj)

            if updated:
                pipe = self._redis.pipeline()
                pipe.delete(key)
                if new_claims:
                    pipe.rpush(key, *new_claims)
                    pipe.expire(key, self._ttl)
                await pipe.execute()
                logger.info(
                    f"✏️ Updated claim {claim_id[:16]}... "
                    f"in session {session_id[:16]}..."
                )

            return updated

        except Exception as e:
            logger.error(f"❌ Failed to update claim text: {e}")
            return False

    # =========================================================================
    # Verification Job Status Methods
    # =========================================================================

    async def set_job_status(
        self,
        job_id: str,
        status: str,
        result: Optional[dict] = None
    ) -> None:
        """
        Set verification job status.

        Args:
            job_id: Celery task ID
            status: Job status (pending, running, completed, failed)
            result: Optional result data
        """
        await self.connect()

        key = self._make_job_key(job_id)

        try:
            data = {
                "status": status,
                "result": json.dumps(result) if result else "",
            }
            await self._redis.hset(key, mapping=data)
            await self._redis.expire(key, 300)  # 5 min TTL for job status

        except Exception as e:
            logger.error(f"❌ Failed to set job status: {e}")

    async def get_job_status(self, job_id: str) -> Optional[dict]:
        """
        Get verification job status.

        Args:
            job_id: Celery task ID

        Returns:
            Job status dict or None
        """
        await self.connect()

        key = self._make_job_key(job_id)

        try:
            data = await self._redis.hgetall(key)
            if data:
                result = {
                    "status": data.get("status", "unknown"),
                }
                if data.get("result"):
                    result["result"] = json.loads(data["result"])
                return result
            return None

        except Exception as e:
            logger.error(f"❌ Failed to get job status: {e}")
            return None

    # =========================================================================
    # Statistics and Debugging
    # =========================================================================

    async def get_session_stats(
        self,
        tenant_id: str,
        session_id: str
    ) -> dict:
        """
        Get statistics for a verification session.

        Args:
            tenant_id: Tenant identifier
            session_id: Session identifier

        Returns:
            Dict with session statistics
        """
        claims = await self.get_verified_claims(tenant_id, session_id)
        ttl = await self.get_ttl_remaining(tenant_id, session_id)

        if not claims:
            return {
                "session_id": session_id,
                "exists": False,
                "claims_count": 0,
            }

        verified_count = sum(1 for c in claims if c.status == VerificationStatus.VERIFIED)
        corrected_count = sum(1 for c in claims if c.status == VerificationStatus.CORRECTED)
        rejected_count = sum(1 for c in claims if c.status == VerificationStatus.REJECTED)

        avg_confidence = sum(c.confidence for c in claims) / len(claims) if claims else 0

        return {
            "session_id": session_id,
            "exists": True,
            "claims_count": len(claims),
            "verified_count": verified_count,
            "corrected_count": corrected_count,
            "rejected_count": rejected_count,
            "average_confidence": round(avg_confidence, 3),
            "ttl_remaining_seconds": ttl,
        }


# =============================================================================
# Singleton Instance
# =============================================================================

_verified_cache: Optional[VerifiedContextCache] = None


def get_verified_cache() -> VerifiedContextCache:
    """Get the global VerifiedContextCache singleton."""
    global _verified_cache
    if _verified_cache is None:
        _verified_cache = VerifiedContextCache(ttl_seconds=settings.verified_cache_ttl_seconds)
    return _verified_cache


async def initialize_verified_cache() -> VerifiedContextCache:
    """Initialize and return the VerifiedContextCache singleton."""
    cache = get_verified_cache()
    await cache.connect()
    return cache
