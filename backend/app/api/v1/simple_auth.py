# Simple auth endpoint that handles everything in one place
from fastapi import APIRouter, HTTPException, Request, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.async_database import get_async_db
from app.db.models import User, Tenant
from app.schemas.user import UserSync
from uuid import uuid4
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/create-or-sync-user")
async def create_or_sync_user(
    request: Request,
    user_data: UserSync,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Simple endpoint that creates or syncs a user without complexity.
    This handles everything: user creation, tenant creation, trial setup.
    """
    try:
        async with db as session:
            # Check if user exists
            result = await session.execute(
                select(User).where(User.clerk_user_id == user_data.clerk_user_id)
            )
            existing_user = result.scalar_one_or_none()
            
            if existing_user:
                logger.info(f"User already exists: {existing_user.email}")
                
                # If user doesn't have trial_ends_at, set it
                if not existing_user.trial_ends_at:
                    existing_user.trial_ends_at = datetime.utcnow() + timedelta(days=14)
                    existing_user.subscription_plan = 'trial'
                    existing_user.subscription_status = 'trialing'
                    await session.commit()
                    logger.info(f"Added trial to existing user: {existing_user.email}")
                
                return {
                    "success": True,
                    "user": {
                        "id": str(existing_user.id),
                        "email": existing_user.email,
                        "tenant_id": str(existing_user.tenant_id),
                        "onboarding_completed": existing_user.onboarding_completed,
                        "subscription_plan": getattr(existing_user, 'subscription_plan', 'trial'),
                        "trial_ends_at": existing_user.trial_ends_at.isoformat() if existing_user.trial_ends_at else None,
                        "is_new": False
                    }
                }
            
            # Create tenant for new user
            tenant_name = user_data.email.split('@')[0].replace('.', '-')
            tenant = Tenant(
                id=uuid4(),
                name=f"{tenant_name}-org",
                bucket_name=f"nexus-{tenant_name}-{uuid4().hex[:8]}",
                is_active=True
            )
            session.add(tenant)
            
            # Create user with trial
            new_user = User(
                id=uuid4(),
                email=user_data.email,
                full_name=user_data.full_name or user_data.email.split('@')[0],
                clerk_user_id=user_data.clerk_user_id,
                tenant_id=tenant.id,
                is_active=True,
                is_superuser=False,
                onboarding_completed=False,
                subscription_plan='trial',
                subscription_status='trialing',
                trial_ends_at=datetime.utcnow() + timedelta(days=14),
                hashed_password="clerk_managed"  # Not used with Clerk
            )
            session.add(new_user)
            
            await session.commit()
            
            logger.info(f"Created new user: {new_user.email} with tenant: {tenant.id}")
            
            return {
                "success": True,
                "user": {
                    "id": str(new_user.id),
                    "email": new_user.email,
                    "tenant_id": str(new_user.tenant_id),
                    "onboarding_completed": False,
                    "subscription_plan": "trial",
                    "is_new": True
                }
            }
            
    except Exception as e:
        logger.error(f"Error in create_or_sync_user: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/test-token")
async def get_test_token(db: AsyncSession = Depends(get_async_db)):
    """
    Get a test token for development purposes.
    This creates or uses a test user and returns their details.
    ONLY FOR DEVELOPMENT - DO NOT USE IN PRODUCTION!
    """
    import os
    if os.getenv("ENVIRONMENT", "development") == "production":
        raise HTTPException(status_code=403, detail="Not available in production")
    
    try:
        async with db as session:
            # Check if test user exists
            test_clerk_id = "test_user_clerk_001"
            result = await session.execute(
                select(User).where(User.clerk_user_id == test_clerk_id)
            )
            test_user = result.scalar_one_or_none()
            
            if not test_user:
                # Create test tenant
                test_tenant = Tenant(
                    id=uuid4(),
                    name="test-tenant",
                    bucket_name=f"nexus-test-{uuid4().hex[:8]}",
                    is_active=True
                )
                session.add(test_tenant)
                
                # Create test user
                test_user = User(
                    id=uuid4(),
                    email="test@nexusdocs.com",
                    full_name="Test User",
                    clerk_user_id=test_clerk_id,
                    tenant_id=test_tenant.id,
                    is_active=True,
                    is_superuser=False,
                    onboarding_completed=True,
                    subscription_plan='pro',
                    subscription_status='active',
                    trial_ends_at=datetime.utcnow() + timedelta(days=30),
                    hashed_password="test_only"
                )
                session.add(test_user)
                await session.commit()
                logger.info(f"Created test user: {test_user.email}")
            
            # Return test authentication details
            return {
                "success": True,
                "message": "Test token for development",
                "auth": {
                    "method": "Use X-User-Id header",
                    "header_name": "X-User-Id",
                    "header_value": test_user.clerk_user_id,
                    "alternative": "Authorization: Bearer test_token_12345"
                },
                "user": {
                    "id": str(test_user.id),
                    "email": test_user.email,
                    "clerk_user_id": test_user.clerk_user_id,
                    "tenant_id": str(test_user.tenant_id),
                    "subscription_plan": test_user.subscription_plan
                },
                "example_curl": f'curl -X GET http://localhost:8000/api/v1/documents -H "X-User-Id: {test_user.clerk_user_id}"'
            }
            
    except Exception as e:
        logger.error(f"Error getting test token: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))