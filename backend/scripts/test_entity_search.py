#!/usr/bin/env python3
"""Test entity search functionality"""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, func, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.async_database import get_async_db, async_session_factory
from app.db.models import User, Tenant
from uuid import UUID
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_entity_search():
    """Test entity search functionality"""
    async with async_session_factory() as db:
        try:
            # First, list all tenants
            logger.info("Listing all tenants...")
            tenant_result = await db.execute(select(Tenant))
            tenants = tenant_result.scalars().all()
            
            for tenant in tenants:
                logger.info(f"Tenant: {tenant.name} (ID: {tenant.id})")
                
                # Count users in this tenant
                user_count_result = await db.execute(
                    select(func.count(User.id)).where(User.tenant_id == tenant.id)
                )
                user_count = user_count_result.scalar()
                logger.info(f"  Total users: {user_count}")
                
                # List users
                if user_count > 0:
                    user_result = await db.execute(
                        select(User).where(User.tenant_id == tenant.id).limit(5)
                    )
                    users = user_result.scalars().all()
                    for user in users:
                        logger.info(f"    - {user.email} (Name: {user.full_name or 'No name'})")
                
                # Test search
                if user_count > 0:
                    search_query = "jo"
                    search_pattern = f"%{search_query.lower()}%"
                    logger.info(f"\n  Testing search for '{search_query}'...")
                    
                    search_result = await db.execute(
                        select(User).where(
                            and_(
                                User.tenant_id == tenant.id,
                                or_(
                                    func.lower(func.coalesce(User.full_name, '')).like(search_pattern),
                                    func.lower(User.email).like(search_pattern)
                                )
                            )
                        ).limit(10)
                    )
                    search_users = search_result.scalars().all()
                    logger.info(f"  Found {len(search_users)} users matching '{search_query}':")
                    for user in search_users:
                        logger.info(f"    - {user.email} (Name: {user.full_name or 'No name'})")
                
                logger.info("\n" + "-" * 50 + "\n")
                
        except Exception as e:
            logger.error(f"Error during test: {e}")
            raise

if __name__ == "__main__":
    asyncio.run(test_entity_search())