"""
Webhook handlers for external services integration
"""
import logging
import json
from datetime import datetime
from typing import Any, Dict
from fastapi import APIRouter, Request, HTTPException, status, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.async_database import get_async_db
from app.db.models import User
from app.services.async_auth_service import AsyncAuthService
from app.schemas.user import UserSync
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/clerk/user", tags=["webhooks"])
async def clerk_user_webhook(
    request: Request,
    db: AsyncSession = Depends(get_async_db)
) -> Dict[str, Any]:
    """
    Handle Clerk user webhooks for automatic user synchronization.
    
    Clerk sends webhooks for:
    - user.created: When a new user signs up
    - user.updated: When user data is updated
    - user.deleted: When a user is deleted
    """
    try:
        # Get the raw body
        raw_body = await request.body()
        
        # Parse the JSON payload
        try:
            payload = json.loads(raw_body.decode('utf-8'))
        except json.JSONDecodeError:
            logger.error("Invalid JSON payload in Clerk webhook")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid JSON payload"
            )
        
        # Extract event type and data
        event_type = payload.get('type')
        event_data = payload.get('data', {})
        
        logger.info(f"🎯 Received Clerk webhook: {event_type}")
        
        if not event_type:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing event type"
            )
        
        # Handle different event types
        if event_type == 'user.created':
            return await handle_user_created(db, event_data)
        elif event_type == 'user.updated':
            return await handle_user_updated(db, event_data)
        elif event_type == 'user.deleted':
            return await handle_user_deleted(db, event_data)
        else:
            logger.warning(f"Unhandled Clerk webhook event type: {event_type}")
            return {"status": "ignored", "event_type": event_type}
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing Clerk webhook: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error processing webhook"
        )


async def handle_user_created(db: AsyncSession, user_data: Dict[str, Any]) -> Dict[str, Any]:
    """Handle user.created webhook from Clerk"""
    try:
        clerk_user_id = user_data.get('id')
        email_addresses = user_data.get('email_addresses', [])
        
        if not clerk_user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing user ID in webhook data"
            )
        
        # Get primary email
        primary_email = None
        for email_obj in email_addresses:
            if email_obj.get('id') == user_data.get('primary_email_address_id'):
                primary_email = email_obj.get('email_address')
                break
        
        if not primary_email:
            logger.warning(f"No primary email found for Clerk user {clerk_user_id}")
            return {"status": "error", "message": "No primary email found"}
        
        # Extract user information
        first_name = user_data.get('first_name', '')
        last_name = user_data.get('last_name', '')
        full_name = f"{first_name} {last_name}".strip() or primary_email
        
        logger.info(f"📝 Creating user from Clerk webhook: {primary_email}")
        
        # Check if user already exists
        result = await db.execute(
            select(User).filter(User.clerk_user_id == clerk_user_id)
        )
        existing_user = result.scalar_one_or_none()
        
        if existing_user:
            logger.info(f"User {clerk_user_id} already exists, updating...")
            return await handle_user_updated(db, user_data)
        
        # Extract metadata for invitation handling
        unsafe_metadata = user_data.get('unsafe_metadata', {})
        
        # Create new user via sync_user_from_clerk
        user = await AsyncAuthService.sync_user_from_clerk(
            db=db,
            clerk_user_id=clerk_user_id,
            email=primary_email,
            full_name=full_name,
            metadata=unsafe_metadata
        )
        
        logger.info(f"✅ User created successfully: {user.id}")
        
        return {
            "status": "success",
            "action": "user_created",
            "user_id": str(user.id),
            "clerk_user_id": clerk_user_id,
            "email": primary_email
        }
        
    except Exception as e:
        logger.error(f"Error creating user from webhook: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create user: {str(e)}"
        )


async def handle_user_updated(db: AsyncSession, user_data: Dict[str, Any]) -> Dict[str, Any]:
    """Handle user.updated webhook from Clerk"""
    try:
        clerk_user_id = user_data.get('id')
        
        if not clerk_user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing user ID in webhook data"
            )
        
        # Find existing user
        result = await db.execute(
            select(User).filter(User.clerk_user_id == clerk_user_id)
        )
        existing_user = result.scalar_one_or_none()
        
        if not existing_user:
            logger.info(f"User {clerk_user_id} not found, creating...")
            return await handle_user_created(db, user_data)
        
        # Update user information
        email_addresses = user_data.get('email_addresses', [])
        primary_email = None
        
        for email_obj in email_addresses:
            if email_obj.get('id') == user_data.get('primary_email_address_id'):
                primary_email = email_obj.get('email_address')
                break
        
        if primary_email and primary_email != existing_user.email:
            existing_user.email = primary_email
        
        # Update full name if provided
        first_name = user_data.get('first_name', '')
        last_name = user_data.get('last_name', '')
        if first_name or last_name:
            full_name = f"{first_name} {last_name}".strip()
            if full_name:
                existing_user.full_name = full_name
        
        # Update active status based on Clerk data
        banned = user_data.get('banned', False)
        existing_user.is_active = not banned
        
        await db.commit()
        await db.refresh(existing_user)
        
        logger.info(f"✅ User updated successfully: {existing_user.id}")
        
        return {
            "status": "success",
            "action": "user_updated",
            "user_id": str(existing_user.id),
            "clerk_user_id": clerk_user_id,
            "email": existing_user.email
        }
        
    except Exception as e:
        logger.error(f"Error updating user from webhook: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update user: {str(e)}"
        )


async def handle_user_deleted(db: AsyncSession, user_data: Dict[str, Any]) -> Dict[str, Any]:
    """Handle user.deleted webhook from Clerk"""
    try:
        clerk_user_id = user_data.get('id')
        
        if not clerk_user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing user ID in webhook data"
            )
        
        # Find existing user
        result = await db.execute(
            select(User).filter(User.clerk_user_id == clerk_user_id)
        )
        existing_user = result.scalar_one_or_none()
        
        if not existing_user:
            logger.warning(f"User {clerk_user_id} not found for deletion")
            return {
                "status": "ignored",
                "action": "user_not_found",
                "clerk_user_id": clerk_user_id
            }
        
        # Soft delete - deactivate user instead of hard delete
        existing_user.is_active = False
        
        await db.commit()
        
        logger.info(f"✅ User deactivated successfully: {existing_user.id}")
        
        return {
            "status": "success",
            "action": "user_deactivated",
            "user_id": str(existing_user.id),
            "clerk_user_id": clerk_user_id
        }
        
    except Exception as e:
        logger.error(f"Error deleting user from webhook: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete user: {str(e)}"
        )


@router.get("/clerk/test", tags=["webhooks"])
async def test_clerk_webhook():
    """Test endpoint to verify webhook setup"""
    return {
        "status": "ok",
        "service": "nexus-backend",
        "webhook_type": "clerk",
        "timestamp": datetime.utcnow().isoformat()
    }