# backend/app/services/async_auth_service.py
"""
Minimal auth service.

Most auth logic is now in async_dependencies.py (JIT provisioning).
This file only contains helpers that might be needed elsewhere.
"""
from typing import Optional
from uuid import uuid4
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.models import User, Tenant

logger = logging.getLogger(__name__)


class AsyncAuthService:
    """Minimal auth service for utility functions."""

    @staticmethod
    async def get_user_by_clerk_id(db: AsyncSession, clerk_user_id: str) -> Optional[User]:
        """Get user by Clerk ID."""
        result = await db.execute(
            select(User).where(User.clerk_user_id == clerk_user_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
        """Get user by email."""
        result = await db.execute(
            select(User).where(User.email == email)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create_tenant(
        db: AsyncSession,
        name: str,
        description: Optional[str] = None,
        settings: Optional[dict] = None
    ) -> Tenant:
        """Create a new tenant."""
        sanitized_name = name.lower().replace(' ', '-').replace('_', '-')
        bucket_name = f"{sanitized_name}-{uuid4().hex[:8]}"

        tenant = Tenant(
            id=uuid4(),
            name=name,
            description=description,
            bucket_name=bucket_name,
            settings=settings or {},
            is_active=True
        )

        db.add(tenant)
        await db.commit()
        await db.refresh(tenant)
        return tenant
