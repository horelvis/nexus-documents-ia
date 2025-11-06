# app/services/subscription_service_v2.py
"""
Production-ready subscription service using Stripe as the single source of truth.

This service handles all subscription-related operations including:
- Fetching subscription status from Stripe
- Caching subscription data for performance
- Checking permissions based on subscription plan
- Managing team member inheritance
"""

import stripe
import logging
from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.db.models import User, Document
from app.core.config import settings
from app.core.cache import cache, user_cache_key
from enum import Enum
import asyncio
from functools import wraps

logger = logging.getLogger(__name__)

# Configure Stripe
stripe.api_key = settings.STRIPE_SECRET_KEY
if not stripe.api_key:
    logger.warning("⚠️ Stripe API key not configured. Subscription features will be limited.")


class SubscriptionPlan(str, Enum):
    """Subscription plan types"""
    TRIAL = "trial"
    BASIC = "basic"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class SubscriptionStatus(str, Enum):
    """Subscription status types"""
    ACTIVE = "active"
    TRIAL = "trial"
    PAST_DUE = "past_due"
    CANCELED = "canceled"
    INCOMPLETE = "incomplete"
    EXPIRED = "expired"
    ERROR = "error"
    UNKNOWN = "unknown"


class PlanLimits:
    """Plan limits configuration"""
    LIMITS = {
        SubscriptionPlan.TRIAL: {
            "documents": 10,
            "storage_mb": 100,
            "agents_per_month": 0,
            "team_members": 0,
            "api_calls_per_day": 100
        },
        SubscriptionPlan.BASIC: {
            "documents": 500,
            "storage_mb": 10240,  # 10 GB
            "agents_per_month": 10,
            "team_members": 0,
            "api_calls_per_day": 1000
        },
        SubscriptionPlan.PRO: {
            "documents": 1000,
            "storage_mb": 10000,
            "agents_per_month": 100,
            "team_members": 5,
            "api_calls_per_day": 5000
        },
        SubscriptionPlan.ENTERPRISE: {
            "documents": -1,  # Unlimited
            "storage_mb": -1,  # Unlimited
            "agents_per_month": -1,  # Unlimited
            "team_members": -1,  # Unlimited
            "api_calls_per_day": -1  # Unlimited
        }
    }

    @classmethod
    def get_limits(cls, plan: str) -> Dict[str, int]:
        """Get limits for a specific plan"""
        return cls.LIMITS.get(SubscriptionPlan(plan), cls.LIMITS[SubscriptionPlan.TRIAL])


class PermissionManager:
    """Manages permissions based on subscription plans"""
    
    PERMISSIONS = {
        SubscriptionPlan.TRIAL: {
            'view_documents',
            'basic_search',
            'upload_documents'
        },
        SubscriptionPlan.BASIC: {
            'view_documents',
            'basic_search',
            'upload_documents',
            'advanced_search',
            'use_agents',  # Limited agents
            'export_documents'
        },
        SubscriptionPlan.PRO: {
            'view_documents',
            'basic_search',
            'upload_documents',
            'advanced_search',
            'use_agents',
            'can_use_agents',
            'export_documents',
            'api_access',
            'invite_team_members',
            'create_shared_links'
        },
        SubscriptionPlan.ENTERPRISE: {
            'view_documents',
            'basic_search',
            'upload_documents',
            'advanced_search',
            'use_agents',
            'can_use_agents',
            'export_documents',
            'api_access',
            'invite_team_members',
            'create_shared_links',
            'admin_features',
            'custom_integrations',
            'advanced_analytics',
            'priority_support'
        }
    }

    @classmethod
    def has_permission(cls, plan: str, permission: str) -> bool:
        """Check if a plan has a specific permission"""
        try:
            plan_enum = SubscriptionPlan(plan)
            return permission in cls.PERMISSIONS.get(plan_enum, set())
        except ValueError:
            return permission in cls.PERMISSIONS[SubscriptionPlan.TRIAL]


def handle_stripe_errors(func):
    """Decorator to handle Stripe errors gracefully"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except stripe.error.RateLimitError as e:
            logger.error(f"🚫 Stripe rate limit error: {e}")
            raise Exception("Too many requests to payment service. Please try again later.")
        except stripe.error.InvalidRequestError as e:
            logger.error(f"❌ Invalid Stripe request: {e}")
            raise Exception("Invalid request to payment service.")
        except stripe.error.AuthenticationError as e:
            logger.error(f"🔐 Stripe authentication error: {e}")
            raise Exception("Payment service authentication failed.")
        except stripe.error.APIConnectionError as e:
            logger.error(f"🌐 Stripe API connection error: {e}")
            raise Exception("Cannot connect to payment service.")
        except stripe.error.StripeError as e:
            logger.error(f"💳 General Stripe error: {e}")
            raise Exception("Payment service error occurred.")
        except Exception as e:
            logger.error(f"🔥 Unexpected error in {func.__name__}: {e}")
            raise
    return wrapper


class SubscriptionServiceV2:
    """
    Production-ready subscription service with caching and error handling
    """
    
    # Cache configuration
    CACHE_TTL = 300  # 5 minutes
    CACHE_TTL_ERROR = 60  # 1 minute for error states
    
    @staticmethod
    @handle_stripe_errors
    async def get_user_subscription_status(
        db: AsyncSession,
        user: User,
        force_refresh: bool = False
    ) -> Dict[str, Any]:
        """
        Get subscription status for a user with caching and team member support.
        
        Args:
            db: Database session
            user: User object
            force_refresh: Force refresh from Stripe
            
        Returns:
            Dictionary containing subscription status and permissions
        """
        # Handle team members
        if user.is_team_member:
            return await SubscriptionServiceV2._get_team_member_status(db, user)
        
        # Check cache first (unless force refresh)
        if not force_refresh:
            cached_status = SubscriptionServiceV2._get_cached_status(user)
            if cached_status:
                return cached_status
        
        # Get status from Stripe
        status = await SubscriptionServiceV2._fetch_stripe_status(user)
        
        # Cache the result
        SubscriptionServiceV2._cache_status(user, status)
        
        return status
    
    @staticmethod
    async def _get_team_member_status(db: AsyncSession, user: User) -> Dict[str, Any]:
        """Get subscription status for team members"""
        # Find the tenant admin
        result = await db.execute(
            select(User).where(
                User.tenant_id == user.tenant_id,
                User.is_team_member == False,
                User.is_active == True
            ).order_by(User.created_at)  # Get the oldest user (likely the admin)
        )
        admin_user = result.scalars().first()
        
        if admin_user:
            # Get admin's subscription status
            admin_status = await SubscriptionServiceV2.get_user_subscription_status(db, admin_user)
            
            # Check if admin's plan allows team members
            plan_limits = PlanLimits.get_limits(admin_status['plan'])
            if plan_limits['team_members'] == 0:
                return SubscriptionServiceV2._get_free_plan_status(
                    message="Team members not allowed on admin's plan"
                )
            
            # Inherit admin's status
            admin_status.update({
                "is_team_member": True,
                "inherited_from": admin_user.email,
                "inherited_from_id": str(admin_user.id)
            })
            return admin_status
        
        # No admin found
        return SubscriptionServiceV2._get_free_plan_status(
            message="Team member without admin"
        )
    
    @staticmethod
    def _get_cached_status(user: User) -> Optional[Dict[str, Any]]:
        """Get cached subscription status"""
        cache_key = user_cache_key(str(user.id), "subscription")
        cached_data = cache.get_json(cache_key)
        
        if cached_data:
            logger.debug(f"✨ Using cached subscription data for user {user.id}")
            # Add timestamp for frontend
            cached_data['cached_at'] = datetime.utcnow().isoformat()
        
        return cached_data
    
    @staticmethod
    def _cache_status(user: User, status: Dict[str, Any], ttl: Optional[int] = None):
        """Cache subscription status"""
        cache_key = user_cache_key(str(user.id), "subscription")
        ttl = ttl or (
            SubscriptionServiceV2.CACHE_TTL_ERROR 
            if status['status'] == SubscriptionStatus.ERROR 
            else SubscriptionServiceV2.CACHE_TTL
        )
        cache.set_json(cache_key, status, ttl=ttl)
        logger.debug(f"💾 Cached subscription status for user {user.id} (TTL: {ttl}s)")
    
    @staticmethod
    async def _fetch_stripe_status(user: User) -> Dict[str, Any]:
        """Fetch subscription status from Stripe"""
        # Free plan for users without Stripe customer
        if not user.stripe_customer_id:
            return SubscriptionServiceV2._get_free_plan_status()
        
        try:
            # Verify Stripe is configured
            if not stripe.api_key:
                logger.error("Stripe API key not configured")
                return SubscriptionServiceV2._get_error_status(
                    "Payment service not configured"
                )
            
            # Verify customer exists in Stripe before fetching subscriptions
            try:
                stripe.Customer.retrieve(user.stripe_customer_id)
                logger.debug(f"✅ Customer {user.stripe_customer_id} verified in Stripe")
            except stripe.error.InvalidRequestError:
                logger.warning(f"⚠️ Customer {user.stripe_customer_id} doesn't exist in Stripe")
                return SubscriptionServiceV2._get_free_plan_status(
                    message="Invalid customer - please re-authenticate"
                )
            
            # Fetch subscriptions from Stripe
            logger.debug(f"🔍 Fetching subscription from Stripe for customer {user.stripe_customer_id}")
            
            subscriptions = stripe.Subscription.list(
                customer=user.stripe_customer_id,
                limit=10,
                expand=['data.default_payment_method']
            )
            
            logger.debug(f"🔍 Subscriptions type: {type(subscriptions)}")
            logger.debug(f"🔍 Subscriptions dir: {[attr for attr in dir(subscriptions) if not attr.startswith('_')]}")
            logger.debug(f"🔍 Has data attr: {hasattr(subscriptions, 'data')}")
            if hasattr(subscriptions, 'data'):
                logger.debug(f"🔍 Data type: {type(subscriptions.data)}")
            else:
                logger.debug(f"🔍 Available attrs: {list(subscriptions.__dict__.keys()) if hasattr(subscriptions, '__dict__') else 'No __dict__'}")
            
            # Find active subscription
            if not hasattr(subscriptions, 'data'):
                logger.error(f"❌ Subscriptions object has no 'data' attribute: {type(subscriptions)}")
                return SubscriptionServiceV2._get_error_status("Invalid subscription data format")
                
            if not isinstance(subscriptions.data, list):
                logger.error(f"❌ Subscriptions data is not a list: {type(subscriptions.data)}")
                return SubscriptionServiceV2._get_error_status("Invalid subscription data type")
                
            logger.debug(f"🔍 Found {len(subscriptions.data)} subscriptions for customer {user.stripe_customer_id}")
            
            try:
                active_subscription = SubscriptionServiceV2._find_active_subscription(subscriptions.data)
                logger.debug(f"🔍 Active subscription found: {active_subscription is not None}")
            except Exception as e:
                logger.error(f"❌ Error in _find_active_subscription: {e}")
                return SubscriptionServiceV2._get_error_status(f"Error finding active subscription: {str(e)}")
            
            if not active_subscription:
                return SubscriptionServiceV2._get_free_plan_status(
                    message="No active subscription"
                )
            
            # Build subscription status
            try:
                return SubscriptionServiceV2._build_subscription_status(active_subscription)
            except Exception as e:
                logger.error(f"❌ Error in _build_subscription_status: {e}")
                return SubscriptionServiceV2._get_error_status(f"Error building subscription status: {str(e)}")
            
        except Exception as e:
            logger.error(f"❌ Error fetching subscription for user {user.id}: {e}")
            return SubscriptionServiceV2._get_error_status(str(e))
    
    @staticmethod
    def _find_active_subscription(subscriptions: List[Any]) -> Optional[Any]:
        """Find the most recent active subscription"""
        active_subs = [
            sub for sub in subscriptions
            if sub.status in ['active', 'trialing', 'past_due']
        ]
        
        if not active_subs:
            return None
        
        # If multiple active subscriptions, prioritize trialing first (as they might be newer trials)
        # then active, then past_due
        priority_order = {'trialing': 3, 'active': 2, 'past_due': 1}
        
        # Sort by priority first, then by creation date
        return max(active_subs, key=lambda x: (
            priority_order.get(x.status, 0), 
            getattr(x, 'created', 0) if hasattr(x, 'created') and not callable(getattr(x, 'created', None)) else 0
        ))
    
    @staticmethod
    def _build_subscription_status(subscription: Any) -> Dict[str, Any]:
        """Build subscription status dictionary from Stripe subscription"""
        # Determine plan
        plan_id = subscription.metadata.get('plan_id', 'pro')
        
        # Check for enterprise plan
        if hasattr(subscription, 'items') and hasattr(subscription.items, 'data') and subscription.items.data:
            price_id = subscription.items.data[0].price.id
            if price_id == settings.STRIPE_ENTERPRISE_PRICE_ID:
                plan_id = 'enterprise'
        
        # Map status
        status_map = {
            'active': SubscriptionStatus.ACTIVE,
            'trialing': SubscriptionStatus.TRIAL,
            'past_due': SubscriptionStatus.PAST_DUE,
            'canceled': SubscriptionStatus.CANCELED,
            'incomplete': SubscriptionStatus.INCOMPLETE,
            'incomplete_expired': SubscriptionStatus.EXPIRED
        }
        status = status_map.get(subscription.status, SubscriptionStatus.UNKNOWN)
        
        # Calculate trial days
        trial_days_remaining = None
        if subscription.status == 'trialing' and subscription.trial_end:
            trial_end = datetime.fromtimestamp(subscription.trial_end)
            trial_days_remaining = max(0, (trial_end - datetime.now()).days)
        
        # Determine permissions
        can_use = status in [SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL]
        plan_limits = PlanLimits.get_limits(plan_id)
        
        # Determine end date (use trial_end for trialing subscriptions, current_period_end for others)
        period_end = None
        if subscription.status == 'trialing' and subscription.trial_end:
            period_end = datetime.fromtimestamp(subscription.trial_end).isoformat()
        elif hasattr(subscription, 'current_period_end') and subscription.current_period_end:
            period_end = datetime.fromtimestamp(subscription.current_period_end).isoformat()
        # Fallback: try to get period_end from subscription items
        elif hasattr(subscription, 'items') and hasattr(subscription.items, 'data') and subscription.items.data:
            item = subscription.items.data[0]
            if hasattr(item, 'current_period_end') and item.current_period_end:
                period_end = datetime.fromtimestamp(item.current_period_end).isoformat()
        
        # Build response
        result = {
            "plan": plan_id,
            "status": status.value,
            "can_use_agents": can_use and PermissionManager.has_permission(plan_id, 'can_use_agents'),
            "can_use_advanced_features": can_use and plan_id == SubscriptionPlan.ENTERPRISE,
            "message": SubscriptionServiceV2._get_status_message(plan_id, status, trial_days_remaining),
            "limits": plan_limits,
            "subscription_id": subscription.id,
            "current_period_end": period_end,
            "cancel_at_period_end": getattr(subscription, 'cancel_at_period_end', False),
            "created_at": datetime.fromtimestamp(
                getattr(subscription, 'created', 0) if hasattr(subscription, 'created') 
                and not callable(getattr(subscription, 'created', None)) else 0
            ).isoformat() if getattr(subscription, 'created', 0) else datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }
        
        if trial_days_remaining is not None:
            result["trial_days_remaining"] = trial_days_remaining
            result["trial_end"] = trial_end.isoformat()
        
        # Add payment method info if available
        if subscription.default_payment_method:
            pm = subscription.default_payment_method
            if hasattr(pm, 'card'):
                result["payment_method"] = {
                    "brand": pm.card.brand,
                    "last4": pm.card.last4,
                    "exp_month": pm.card.exp_month,
                    "exp_year": pm.card.exp_year
                }
        
        return result
    
    @staticmethod
    def _get_status_message(plan: str, status: SubscriptionStatus, trial_days: Optional[int]) -> str:
        """Generate user-friendly status message"""
        if status == SubscriptionStatus.TRIAL and trial_days is not None:
            return f"Trial period - {trial_days} days remaining"
        elif status == SubscriptionStatus.PAST_DUE:
            return "⚠️ Payment failed - Please update your payment method"
        elif status == SubscriptionStatus.CANCELED:
            return "❌ Subscription canceled"
        elif status == SubscriptionStatus.INCOMPLETE:
            return "⚠️ Subscription setup incomplete"
        elif status == SubscriptionStatus.ACTIVE:
            return f"{plan.title()} Plan - Active"
        else:
            return f"{plan.title()} Plan - {status.value}"
    
    @staticmethod
    def _get_free_plan_status(message: str = "Free Plan") -> Dict[str, Any]:
        """Get free plan status"""
        return {
            "plan": SubscriptionPlan.TRIAL.value,
            "status": SubscriptionStatus.ACTIVE.value,
            "can_use_agents": False,
            "can_use_advanced_features": False,
            "message": message,
            "limits": PlanLimits.get_limits(SubscriptionPlan.TRIAL),
            "updated_at": datetime.utcnow().isoformat()
        }
    
    @staticmethod
    def _get_error_status(error: str) -> Dict[str, Any]:
        """Get error status"""
        return {
            "plan": SubscriptionPlan.TRIAL.value,
            "status": SubscriptionStatus.ERROR.value,
            "can_use_agents": False,
            "can_use_advanced_features": False,
            "message": "Error checking subscription",
            "error": error,
            "limits": PlanLimits.get_limits(SubscriptionPlan.TRIAL),
            "updated_at": datetime.utcnow().isoformat()
        }
    
    @staticmethod
    def clear_cache(user_id: str):
        """Clear subscription cache for a user"""
        cache_key = user_cache_key(user_id, "subscription")
        cache.delete(cache_key)
        logger.info(f"🧹 Cleared subscription cache for user {user_id}")
    
    @staticmethod
    async def verify_on_login(db: AsyncSession, user: User) -> Dict[str, Any]:
        """
        Verify subscription status on login and update Stripe customer if needed
        """
        logger.info(f"🔐 Verifying subscription on login for user {user.id}")
        
        # Try to find/update Stripe customer if missing
        if not user.stripe_customer_id and stripe.api_key:
            user.stripe_customer_id = await SubscriptionServiceV2._find_or_create_stripe_customer(
                db, user
            )
        
        # Get current status (force refresh on login)
        status = await SubscriptionServiceV2.get_user_subscription_status(
            db, user, force_refresh=True
        )
        
        # Log result
        logger.info(
            f"📊 User {user.id} login - Plan: {status['plan']}, "
            f"Status: {status['status']}, Can use agents: {status['can_use_agents']}"
        )
        
        return status
    
    @staticmethod
    async def _find_or_create_stripe_customer(db: AsyncSession, user: User) -> Optional[str]:
        """Find existing or create new Stripe customer"""
        try:
            # First verify if user already has a customer_id and it's valid
            if user.stripe_customer_id:
                try:
                    stripe.Customer.retrieve(user.stripe_customer_id)
                    logger.info(f"✅ Verified existing Stripe customer {user.stripe_customer_id} for {user.email}")
                    return user.stripe_customer_id
                except stripe.error.InvalidRequestError:
                    logger.warning(f"⚠️ Customer {user.stripe_customer_id} doesn't exist in Stripe for {user.email}")
                    # Continue to create new customer
            
            # Search for existing customer by email
            customers = stripe.Customer.list(email=user.email, limit=1)
            
            if customers.data:
                customer_id = customers.data[0].id
                logger.info(f"✅ Found existing Stripe customer {customer_id} for {user.email}")
            else:
                # Create new customer
                customer = stripe.Customer.create(
                    email=user.email,
                    name=user.full_name or user.email,
                    metadata={
                        "user_id": str(user.id),
                        "tenant_id": str(user.tenant_id)
                    }
                )
                customer_id = customer.id
                logger.info(f"✅ Created new Stripe customer {customer_id} for {user.email}")
            
            # Update user with valid customer_id
            user.stripe_customer_id = customer_id
            await db.commit()
            
            return customer_id
            
        except Exception as e:
            logger.error(f"❌ Error managing Stripe customer for {user.email}: {e}")
            return None
    
    @staticmethod
    async def check_document_permission(
        db: AsyncSession,
        user: User
    ) -> Tuple[bool, Optional[str]]:
        """Check if user can upload more documents"""
        status = await SubscriptionServiceV2.get_user_subscription_status(db, user)
        
        # Check plan status
        if status['status'] not in [SubscriptionStatus.ACTIVE.value, SubscriptionStatus.TRIAL.value]:
            return False, f"Your subscription is {status['status']}. Please update your subscription."
        
        # Get limits
        limits = status.get('limits', {})
        max_documents = limits.get('documents', 10)
        
        # Unlimited check
        if max_documents == -1:
            return True, None
        
        # Count current documents
        result = await db.execute(
            select(func.count()).select_from(Document).where(
                Document.tenant_id == user.tenant_id
            )
        )
        current_count = result.scalar() or 0
        
        if current_count >= max_documents:
            upgrade_message = (
                "You've reached the document limit for your plan. "
                f"Upgrade to {'Pro' if status['plan'] == 'free' else 'Enterprise'} "
                "for more storage."
            )
            return False, upgrade_message
        
        # Calculate remaining
        remaining = max_documents - current_count
        logger.debug(f"📄 User {user.id} has {remaining} documents remaining")
        
        return True, None
    
    @staticmethod
    async def can_user_perform_action(
        db: AsyncSession,
        user: User,
        permission: str
    ) -> Tuple[bool, Optional[str]]:
        """Check if user can perform a specific action"""
        status = await SubscriptionServiceV2.get_user_subscription_status(db, user)
        
        # Check subscription is active
        if status['status'] not in [SubscriptionStatus.ACTIVE.value, SubscriptionStatus.TRIAL.value]:
            return False, f"Your subscription is {status['status']}. Please update your subscription."
        
        # Check permission
        plan = status.get('plan', SubscriptionPlan.TRIAL.value)
        if PermissionManager.has_permission(plan, permission):
            return True, None
        
        # Generate helpful upgrade message
        required_plan = None
        for p in [SubscriptionPlan.PRO, SubscriptionPlan.ENTERPRISE]:
            if PermissionManager.has_permission(p.value, permission):
                required_plan = p.value
                break
        
        if required_plan:
            return False, f"'{permission}' requires {required_plan.title()} plan or higher."
        else:
            return False, f"Permission '{permission}' is not available."
    
    @staticmethod
    async def check_agent_permission(
        db: AsyncSession,
        user: User
    ) -> Tuple[bool, Optional[str]]:
        """Check if user can use AI agents"""
        return await SubscriptionServiceV2.can_user_perform_action(
            db, user, 'can_use_agents'
        )
    
    @staticmethod
    async def get_usage_stats(db: AsyncSession, user: User) -> Dict[str, Any]:
        """Get current usage statistics for a user"""
        # Get subscription status
        status = await SubscriptionServiceV2.get_user_subscription_status(db, user)
        limits = status.get('limits', {})
        
        # Count documents
        doc_result = await db.execute(
            select(func.count()).select_from(Document).where(
                Document.tenant_id == user.tenant_id
            )
        )
        document_count = doc_result.scalar() or 0
        
        # Calculate storage (simplified - you might want to sum actual file sizes)
        storage_mb = document_count * 10  # Rough estimate
        
        return {
            "documents": {
                "used": document_count,
                "limit": limits.get('documents', 10),
                "percentage": (
                    (document_count / limits.get('documents', 10) * 100)
                    if limits.get('documents', 10) > 0 else 0
                )
            },
            "storage_mb": {
                "used": storage_mb,
                "limit": limits.get('storage_mb', 100),
                "percentage": (
                    (storage_mb / limits.get('storage_mb', 100) * 100)
                    if limits.get('storage_mb', 100) > 0 else 0
                )
            },
            "agents_per_month": {
                "used": 0,  # TODO: Implement agent usage tracking
                "limit": limits.get('agents_per_month', 0)
            },
            "team_members": {
                "used": 0,  # TODO: Implement team member counting
                "limit": limits.get('team_members', 0)
            }
        }
    
    @staticmethod
    async def handle_webhook_event(event: Dict[str, Any]) -> bool:
        """
        Handle Stripe webhook events for subscription changes
        
        Returns:
            bool: True if event was handled successfully
        """
        event_type = event.get('type')
        
        if event_type in [
            'customer.subscription.updated',
            'customer.subscription.deleted',
            'customer.subscription.created'
        ]:
            # Extract customer ID
            subscription = event['data']['object']
            customer_id = subscription.get('customer')
            
            if customer_id:
                # Find user by customer ID
                from app.db.database import get_async_db
                async with get_async_db() as db:
                    result = await db.execute(
                        select(User).where(User.stripe_customer_id == customer_id)
                    )
                    user = result.scalars().first()
                    
                    if user:
                        # Clear cache to force refresh
                        SubscriptionServiceV2.clear_cache(str(user.id))
                        logger.info(
                            f"🔄 Handled {event_type} for user {user.id}, "
                            f"cleared cache"
                        )
                        return True
        
        return False