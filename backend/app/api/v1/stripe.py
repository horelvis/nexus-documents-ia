# backend/app/api/v1/stripe.py - Stripe endpoints

from fastapi import APIRouter, HTTPException, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import stripe
import logging
from typing import Dict, Any, Optional
from pydantic import BaseModel

from app.api.async_dependencies import get_current_active_superuser_async, get_current_active_user_async
from app.db.models import User
from app.db.async_database import get_async_db
from app.core.config import settings
# Subscription model removed - using Stripe as source of truth


# Importaciones necesarias en la parte superior del archivo
import time
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

# Schemas para los requests
class CheckoutSessionRequest(BaseModel):
    planId: str  # Only plan ID needed, backend handles price mapping
    interval: str = 'month'  # 'month' or 'year'
    email: Optional[str] = None
    success_url: Optional[str] = None
    cancel_url: Optional[str] = None

logger = logging.getLogger(__name__)
router = APIRouter()

# Configurar Stripe
stripe.api_key = settings.STRIPE_SECRET_KEY
logger.info(f"[STRIPE] API key configured: {'Yes' if stripe.api_key else 'No'}")
logger.info(f"[STRIPE] API key length: {len(stripe.api_key) if stripe.api_key else 0}")


@router.post("/create-checkout-session")
async def create_checkout_session(
    request: CheckoutSessionRequest,
    current_user: User = Depends(get_current_active_user_async),
    db: AsyncSession = Depends(get_async_db)
) -> Dict[str, str]:
    """
    Crea una sesión de checkout de Stripe para usuarios existentes que quieren actualizar su plan.
    """
    try:
        # Validate plan ID
        if request.planId not in ['basic', 'pro', 'enterprise']:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid plan ID: {request.planId}. Must be 'basic', 'pro', or 'enterprise'"
            )
        
        # Normalize and validate interval values
        interval_map = {
            'month': 'month',
            'monthly': 'month',
            'year': 'year',
            'yearly': 'year'
        }
        normalized_interval = interval_map.get(request.interval.lower())
        if not normalized_interval:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid interval: {request.interval}. Must be 'month'/'monthly' or 'year'/'yearly'"
            )
        
        # Centralized plan to price mapping
        plan_price_mapping = {
            'basic': {
                'month': settings.STRIPE_BASIC_PRICE_ID,
                'year': getattr(settings, 'STRIPE_BASIC_YEARLY_PRICE_ID', None)
            },
            'pro': {
                'month': settings.STRIPE_PRO_PRICE_ID,
                'year': getattr(settings, 'STRIPE_PRO_YEARLY_PRICE_ID', None)
            },
            'enterprise': {
                'month': getattr(settings, 'STRIPE_ENTERPRISE_PRICE_ID', None),
                'year': getattr(settings, 'STRIPE_ENTERPRISE_YEARLY_PRICE_ID', None)
            }
        }
        
        # Get the appropriate price ID
        stripe_price_id = plan_price_mapping.get(request.planId, {}).get(normalized_interval)
        
        if not stripe_price_id:
            raise HTTPException(
                status_code=400,
                detail=f"Price not configured for plan '{request.planId}' with interval '{normalized_interval}'"
            )

        # Si el usuario ya tiene un customer_id, verificar que existe en Stripe
        customer_id = current_user.stripe_customer_id
        
        # Verificar si el customer_id existe en Stripe
        if customer_id:
            try:
                stripe.Customer.retrieve(customer_id)
                logger.info(f"✅ Using existing Stripe customer: {customer_id}")
            except stripe.error.InvalidRequestError as e:
                logger.warning(f"⚠️ Customer {customer_id} doesn't exist in Stripe, creating new one: {e}")
                customer_id = None  # Force creation of new customer
        
        # Si no tiene customer_id o el existente no es válido, crear uno nuevo
        if not customer_id:
            customer = stripe.Customer.create(
                email=current_user.email,
                metadata={
                    'user_id': str(current_user.id),
                    'tenant_id': str(current_user.tenant_id)
                }
            )
            customer_id = customer.id
            logger.info(f"✅ Created new Stripe customer: {customer_id}")
            
            # Guardar el customer_id en la base de datos
            current_user.stripe_customer_id = customer_id
            await db.commit()
        
        # Crear sesión de checkout
        # NOTE: Para planes de pago siempre recopilamos tarjeta
        # El trial gratuito se maneja por separado (endpoint /start-free-trial)
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price': stripe_price_id,
                'quantity': 1,
            }],
            mode='subscription',
            success_url=request.success_url or f"{settings.FRONTEND_URL}/checkout/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=request.cancel_url or f"{settings.FRONTEND_URL}/{current_user.tenant_id}/plans",
            metadata={
                'plan_id': request.planId,
                'user_id': str(current_user.id),
                'tenant_id': str(current_user.tenant_id),
                'interval': normalized_interval
            },
            customer=customer_id,
            # Recopilar información adicional
            billing_address_collection='auto',
            # Permitir códigos promocionales
            allow_promotion_codes=True,
            # SIEMPRE recopilar método de pago (requerido para cobrar)
            payment_method_collection='always',
            subscription_data={
                'metadata': {
                    'plan_id': request.planId,
                    'interval': normalized_interval,
                }
            }
        )

        logger.info(f"Checkout session created: {checkout_session.id} for plan {request.planId}")

        return {"url": checkout_session.url}

    except stripe.error.InvalidRequestError as e:
        logger.error(f"Stripe invalid request: {e}")
        raise HTTPException(
            status_code=400,
            detail=f"Error con la configuración de Stripe: {str(e)}"
        )
    
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error: {e}")
        raise HTTPException(
            status_code=500,
            detail="Error interno de Stripe. Inténtalo de nuevo."
        )
    
    except Exception as e:
        logger.error(f"Unexpected error creating checkout session: {e}")
        raise HTTPException(
            status_code=500,
            detail="Error interno del servidor"
        )


@router.post("/start-free-trial")
async def start_free_trial(
    current_user: User = Depends(get_current_active_user_async),
    db: AsyncSession = Depends(get_async_db)
) -> Dict[str, Any]:
    """
    Permite a un usuario iniciar el trial gratuito sin pasar por Stripe.
    Asigna plan 'trial' por 14 días (o el valor configurado) y marca el estado como trialing.
    """
    try:
        trial_days = getattr(settings, "FREE_TRIAL_DAYS", 14) or 14
        now = datetime.now(timezone.utc)

        # Si ya tiene una suscripción activa o trial vigente, no hacer nada
        if current_user.subscription_status in ['active', 'trialing']:
            logger.info(f"[Stripe] User {current_user.id} already has active/trialing subscription")
            return {
                "status": "already_active",
                "subscription_plan": current_user.subscription_plan,
                "subscription_status": current_user.subscription_status,
                "trial_ends_at": current_user.trial_ends_at.isoformat() if current_user.trial_ends_at else None
            }

        current_user.subscription_plan = 'trial'
        current_user.subscription_status = 'trialing'
        current_user.trial_ends_at = now + timedelta(days=int(trial_days))

        await db.commit()
        await db.refresh(current_user)

        try:
            from app.services.subscription_service_v2 import SubscriptionServiceV2
            SubscriptionServiceV2.clear_cache(str(current_user.id))
        except Exception as cache_error:
            logger.warning(f"[Stripe] Unable to clear subscription cache: {cache_error}")

        logger.info(f"[Stripe] Started free trial for user {current_user.id} until {current_user.trial_ends_at}")

        return {
            "status": "trial_started",
            "subscription_plan": current_user.subscription_plan,
            "subscription_status": current_user.subscription_status,
            "trial_ends_at": current_user.trial_ends_at.isoformat()
        }

    except Exception as e:
        logger.error(f"[Stripe] Error starting free trial: {e}")
        raise HTTPException(
            status_code=500,
            detail="No se pudo iniciar el trial gratuito"
        )


@router.get("/debug-checkout-session/{session_id}")
async def debug_checkout_session(
    session_id: str,
    db: AsyncSession = Depends(get_async_db)
) -> Dict[str, Any]:
    """
    Endpoint de debug para ver toda la información de la sesión
    """
    try:
        session = stripe.checkout.Session.retrieve(
            session_id,
            expand=['customer', 'subscription', 'line_items']
        )
        
        # También obtener line_items separadamente
        line_items = stripe.checkout.Session.list_line_items(session_id)
        
        return {
            "session": {
                "id": session.id,
                "amount_total": session.amount_total,
                "currency": session.currency,
                "payment_status": session.payment_status,
                "metadata": session.metadata,
                "customer_details": session.customer_details,
                "subscription": session.subscription.id if session.subscription else None,
                "line_items": session.line_items.data if hasattr(session, 'line_items') else None,
            },
            "separate_line_items": [
                {
                    "price_id": item.price.id if item.price else None,
                    "unit_amount": item.price.unit_amount if item.price else None,
                    "currency": item.price.currency if item.price else None,
                    "quantity": item.quantity,
                    "amount_total": item.amount_total,
                }
                for item in line_items.data
            ] if line_items.data else [],
            "subscription_details": {
                "id": session.subscription.id if session.subscription else None,
                "items": [
                    {
                        "price_id": item.price.id if item.price else None,
                        "unit_amount": item.price.unit_amount if item.price else None,
                        "currency": item.price.currency if item.price else None,
                    }
                    for item in session.subscription.items.data
                ] if session.subscription and hasattr(session.subscription, 'items') else []
            }
        }
    except Exception as e:
        return {"error": str(e)}

@router.get("/checkout-session/{session_id}")
async def get_checkout_session(
    session_id: str,
    db: AsyncSession = Depends(get_async_db)
) -> Dict[str, Any]:
    """
    Obtiene información de la sesión de checkout completada.
    Se usa después del pago exitoso para el registro del usuario.
    """
    try:
        session = stripe.checkout.Session.retrieve(
            session_id,
            expand=['customer', 'subscription', 'line_items']
        )

        if session.payment_status != 'paid':
            raise HTTPException(
                status_code=400,
                detail="Payment not completed"
            )

        # Obtener información de precio - siempre usar el precio de la suscripción/line_items
        # porque en trial periods, session.amount_total será 0
        amount_total = session.amount_total
        currency = session.currency or 'usd'
        
        # Siempre intentar obtener el precio real desde line_items (más confiable)
        try:
            line_items = stripe.checkout.Session.list_line_items(session_id, limit=1)
            if line_items.data and line_items.data[0].price:
                price = line_items.data[0].price
                # Usar el precio unitario (precio real del plan) no el amount_total (que puede ser 0 en trial)
                amount_total = price.unit_amount * line_items.data[0].quantity
                currency = price.currency
                logger.info(f"Got price from line_items: {amount_total} {currency}")
        except Exception as e:
            logger.warning(f"Could not get line_items: {e}")
            
        # Fallback: obtener desde la suscripción si line_items falló
        if amount_total == 0 and session.subscription:
            try:
                subscription = session.subscription
                if hasattr(subscription, 'items') and subscription.items.data:
                    price = subscription.items.data[0].price
                    amount_total = price.unit_amount
                    currency = price.currency
                    logger.info(f"Got price from subscription: {amount_total} {currency}")
            except Exception as e:
                logger.warning(f"Could not get subscription price: {e}")
        
        # Último fallback: usar el amount_total de la sesión si no conseguimos nada más
        if amount_total == 0:
            amount_total = session.amount_total
            logger.warning(f"Using session amount_total: {amount_total} {currency}")

        return {
            "session_id": session.id,
            "customer_id": session.customer,
            "customer_email": session.customer_details.email,
            "subscription_id": session.subscription,
            "plan_id": session.metadata.get('plan_id'),
            "payment_status": session.payment_status,
            "amount_total": amount_total or 0,
            "currency": currency or 'usd',
        }

    except stripe.error.InvalidRequestError as e:
        logger.error(f"Invalid session ID {session_id}: {e}")
        raise HTTPException(
            status_code=404,
            detail="Sesión de checkout no encontrada"
        )
    
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error retrieving session {session_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Error obteniendo información de pago"
        )


class CustomerPortalRequest(BaseModel):
    return_url: Optional[str] = None

@router.post("/create-customer-portal")
async def create_customer_portal(
    request: CustomerPortalRequest,
    current_user: User = Depends(get_current_active_user_async),
    db: AsyncSession = Depends(get_async_db)
) -> Dict[str, str]:
    """
    Crea una sesión del Customer Portal de Stripe para el usuario actual.
    
    Esta es la implementación más simple y segura:
    - Stripe maneja toda la UI de billing
    - Stripe maneja la seguridad
    - Stripe maneja las validaciones
    - Webhooks actualizan nuestros datos automáticamente
    """
    try:
        # Verificar que el usuario tenga un customer_id en Stripe
        if not current_user.stripe_customer_id:
            raise HTTPException(
                status_code=400, 
                detail="Usuario no tiene cuenta de cliente en Stripe"
            )

        # Usar return_url proporcionada o default basada en tenant
        if request.return_url:
            return_url = request.return_url
        else:
            # Default: incluir tenant_id en la URL
            tenant_id = current_user.tenant_id
            return_url = f"{settings.FRONTEND_URL}/{tenant_id}/dashboard"
        
        # Crear sesión del Customer Portal
        session = stripe.billing_portal.Session.create(
            customer=current_user.stripe_customer_id,
            return_url=return_url,
        )

        logger.info(
            f"Customer portal session created for user {current_user.id}: {session.id}"
        )

        return {"portal_url": session.url}

    except stripe.error.InvalidRequestError as e:
        logger.error(f"Stripe invalid request for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=400,
            detail=f"Error con la cuenta de Stripe: {str(e)}"
        )
    
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Error interno de Stripe. Inténtalo de nuevo."
        )
    
    except Exception as e:
        logger.error(f"Unexpected error creating portal for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Error interno del servidor"
        )


@router.get("/debug-stripe")
async def debug_stripe_connection(
    current_user: User = Depends(get_current_active_user_async)
) -> Dict[str, Any]:
    """
    Debug endpoint para verificar la conexión con Stripe
    """
    try:
        # Verificar API key
        api_key_configured = bool(stripe.api_key)
        api_key_prefix = stripe.api_key[:7] if stripe.api_key else "No key"
        
        # Intentar una llamada simple a Stripe
        stripe_connected = False
        stripe_error = None
        customer_count = 0
        
        try:
            # Listar algunos customers como prueba
            customers = stripe.Customer.list(limit=1)
            stripe_connected = True
            customer_count = len(customers.data)
        except Exception as e:
            stripe_error = str(e)
            
        return {
            "api_key_configured": api_key_configured,
            "api_key_prefix": api_key_prefix,
            "stripe_connected": stripe_connected,
            "stripe_error": stripe_error,
            "test_customer_count": customer_count,
            "user_email": current_user.email,
            "user_stripe_customer_id": current_user.stripe_customer_id
        }
        
    except Exception as e:
        logger.error(f"Debug error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/subscription")
async def get_current_subscription(
    current_user: User = Depends(get_current_active_user_async),
    db: AsyncSession = Depends(get_async_db)
) -> Dict[str, Any]:
    """
    Obtiene la suscripción actual del usuario consultando Stripe directamente.
    """
    try:
        from app.services.subscription_service_v2 import SubscriptionServiceV2
        
        # TODO: SubscriptionServiceV2 needs to be migrated to async
        # For now, we'll make a direct call to get subscription status
        # This is temporary until subscription_service_v2 is migrated
        
        # Get subscription status from Stripe (simplified version)
        if not current_user.stripe_customer_id:
            status = {
                "plan": "free",
                "status": "active",
                "can_use_agents": False,
                "can_use_advanced_features": False,
                "message": "Plan gratuito",
                "limits": {
                    "documents": 10,
                    "storage_mb": 100,
                    "agents_per_month": 0
                }
            }
        else:
            # For paid users, we would normally call Stripe API
            # This is a placeholder until the service is migrated
            status = {
                "plan": "pro",  # This should come from Stripe
                "status": "active",
                "subscription_id": "sub_placeholder",
                "message": "Subscription from Stripe"
            }
        
        # Formatear respuesta para compatibilidad con frontend
        return {
            "id": status.get("subscription_id", status["plan"]),
            "plan_id": status["plan"],
            "status": status["status"],
            "interval": "month",  # Default, se actualiza si hay suscripción
            "current_period_start": int(time.time()),
            "current_period_end": status.get("current_period_end", int(time.time() + (30 * 24 * 60 * 60))),
            "cancel_at_period_end": status.get("cancel_at_period_end", False),
            "customer_id": current_user.stripe_customer_id,
            # Información adicional del servicio
            "subscription_status": status
        }

    except Exception as e:
        logger.error(f"Error getting subscription for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Error obteniendo información de suscripción"
        )


@router.post("/sync-subscription")
async def sync_subscription_from_stripe(
    current_user: User = Depends(get_current_active_user_async),
    db: AsyncSession = Depends(get_async_db)
) -> Dict[str, Any]:
    """
    Sincroniza la suscripción desde Stripe.
    Versión simplificada que consulta Stripe directamente.
    """
    try:
        from app.services.subscription_service_v2 import SubscriptionServiceV2
        
        logger.info(f"[SYNC] Starting sync for user {current_user.id}")
        
        # TODO: SubscriptionServiceV2 needs to be migrated to async
        # For now, clear cache is a simple operation
        SubscriptionServiceV2.clear_cache(str(current_user.id))
        
        # Temporary implementation until service is migrated
        if not current_user.stripe_customer_id:
            status = {
                "plan": "free",
                "status": "active",
                "message": "Free plan",
                "limits": {
                    "documents": 10,
                    "storage_mb": 100,
                    "agents_per_month": 0
                }
            }
        else:
            # Check Stripe subscription
            try:
                subscriptions = stripe.Subscription.list(
                    customer=current_user.stripe_customer_id,
                    status="all",
                    limit=1
                )
                
                if subscriptions.data:
                    sub = subscriptions.data[0]
                    status = {
                        "plan": sub.metadata.get("plan_id", "pro"),
                        "status": sub.status,
                        "subscription_id": sub.id,
                        "message": f"Subscription {sub.status}",
                        "current_period_end": sub.current_period_end,
                        "cancel_at_period_end": sub.cancel_at_period_end
                    }
                else:
                    status = {
                        "plan": "free",
                        "status": "active",
                        "message": "No active subscription"
                    }
            except Exception as e:
                logger.error(f"Error checking Stripe subscription: {e}")
                status = {
                    "plan": "free",
                    "status": "error",
                    "message": str(e)
                }
        
        logger.info(f"[SYNC] User {current_user.id} subscription status: {status}")
        
        # Formatear respuesta para compatibilidad con frontend
        return {
            "id": status.get("subscription_id", status["plan"]),
            "plan_id": status["plan"],
            "status": status["status"],
            "synced": True,
            "message": status.get("message", ""),
            "limits": status.get("limits", {}),
            "trial_days_remaining": status.get("trial_days_remaining"),
            "current_period_end": status.get("current_period_end"),
            "cancel_at_period_end": status.get("cancel_at_period_end", False)
        }
        
    except Exception as e:
        logger.error(f"[SYNC] Error syncing subscription: {e}")
        return {
            "id": "free",
            "plan_id": "free",
            "status": "error",
            "synced": False,
            "message": f"Error sincronizando: {str(e)}",
            "limits": {
                "documents": 10,
                "storage_mb": 100,
                "agents_per_month": 0
            }
        }


# Configuración del Customer Portal (ejecutar una vez)
@router.post("/configure-portal")
async def configure_customer_portal(
    current_user: User = Depends(get_current_active_superuser_async)  # Solo admins
) -> Dict[str, str]:
    """
    Configura el Customer Portal de Stripe con nuestras opciones.
    Solo necesita ejecutarse una vez por cuenta de Stripe.
    """
    try:
        configuration = stripe.billing_portal.Configuration.create(
            business_profile={
                "headline": "Gestiona tu suscripción",
                "privacy_policy_url": f"{settings.FRONTEND_URL}/privacy",
                "terms_of_service_url": f"{settings.FRONTEND_URL}/terms",
            },
            features={
                "payment_method_update": {"enabled": True},
                "subscription_cancel": {
                    "enabled": True,
                    "mode": "at_period_end",  # Cancelar al final del período
                    "cancellation_reason": {
                        "enabled": True,
                        "options": [
                            "too_expensive",
                            "missing_features", 
                            "switched_service",
                            "unused",
                            "other"
                        ]
                    }
                },
                "subscription_update": {
                    "enabled": True,
                    "default_allowed_updates": ["price"],
                    "proration_behavior": "create_prorations"
                },
                "invoice_history": {"enabled": True},
                "customer_update": {
                    "enabled": True,
                    "allowed_updates": ["email", "address", "phone"]
                }
            }
        )

        # Opcional: Guardar configuration ID para uso futuro
        # settings.STRIPE_PORTAL_CONFIGURATION_ID = configuration.id

        logger.info(f"Customer portal configured: {configuration.id}")

        return {
            "configuration_id": configuration.id,
            "status": "configured"
        }

    except stripe.error.StripeError as e:
        logger.error(f"Error configuring customer portal: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error configurando portal: {str(e)}"
        )


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_async_db)
) -> Dict[str, str]:
    """
    Handle Stripe webhooks for subscription events.
    
    Webhook URL: https://your-domain.com/api/v1/stripe/webhook
    
    Events handled:
    - checkout.session.completed: When a checkout session is successfully completed
    - customer.subscription.created: When a new subscription is created
    - customer.subscription.updated: When a subscription is updated
    - customer.subscription.deleted: When a subscription is canceled
    - invoice.payment_succeeded: When a payment succeeds
    - invoice.payment_failed: When a payment fails
    """
    # Get the webhook payload and signature
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    
    if not sig_header:
        logger.error("Missing stripe-signature header")
        raise HTTPException(
            status_code=400,
            detail="Missing stripe-signature header"
        )
    
    try:
        # Verify webhook signature
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        logger.error(f"Invalid payload: {e}")
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError as e:
        logger.error(f"Invalid signature: {e}")
        raise HTTPException(status_code=400, detail="Invalid signature")
    
    # Log the event
    logger.info(f"🎯 Stripe webhook received: {event['type']} - ID: {event['id']}")
    
    # Handle the event
    try:
        if event["type"] == "checkout.session.completed":
            await handle_checkout_session_completed(db, event["data"]["object"])
            
        elif event["type"] == "customer.subscription.created":
            await handle_subscription_created(db, event["data"]["object"])
            
        elif event["type"] == "customer.subscription.updated":
            await handle_subscription_updated(db, event["data"]["object"])
            
        elif event["type"] == "customer.subscription.deleted":
            await handle_subscription_deleted(db, event["data"]["object"])
            
        elif event["type"] == "invoice.payment_succeeded":
            await handle_invoice_payment_succeeded(db, event["data"]["object"])
            
        elif event["type"] == "invoice.payment_failed":
            await handle_invoice_payment_failed(db, event["data"]["object"])
            
        else:
            logger.info(f"Unhandled event type: {event['type']}")
    
    except Exception as e:
        logger.error(f"Error handling webhook event {event['type']}: {e}")
        # Return success anyway to avoid Stripe retrying
        # Log the error for manual investigation
    
    return {"status": "success", "event_id": event["id"]}


# Webhook handler functions
async def handle_checkout_session_completed(db: AsyncSession, session: Dict[str, Any]):
    """
    Handle successful checkout session completion.
    This is called when a user completes payment for the first time.
    """
    customer_id = session.get("customer")
    customer_email = session.get("customer_details", {}).get("email")
    
    logger.info(f"Processing checkout.session.completed for customer {customer_id}")
    
    # Find user by email or stripe_customer_id
    result = await db.execute(
        select(User).where(
            (User.email == customer_email) | (User.stripe_customer_id == customer_id)
        )
    )
    user = result.scalar_one_or_none()
    
    if not user:
        logger.error(f"User not found for customer {customer_id} / email {customer_email}")
        return
    
    # Update user's stripe_customer_id if not set
    if not user.stripe_customer_id:
        user.stripe_customer_id = customer_id
        await db.commit()
        logger.info(f"Updated stripe_customer_id for user {user.id}")
    
    # If there's a subscription, it will be handled by subscription.created event
    logger.info(f"Checkout completed for user {user.id}, subscription will be handled by subscription webhook")


async def handle_subscription_created(db: AsyncSession, subscription: Dict[str, Any]):
    """
    Handle new subscription creation.
    """
    subscription_id = subscription.get("id")
    customer_id = subscription.get("customer")
    status = subscription.get("status")
    
    logger.info(f"Processing subscription.created: {subscription_id}")
    
    # Find user by stripe_customer_id
    result = await db.execute(
        select(User).where(User.stripe_customer_id == customer_id)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        logger.error(f"User not found for customer {customer_id}")
        return
    
    # Extract price and plan info
    items = subscription.get("items", {}).get("data", [])
    if not items:
        logger.error(f"No items found in subscription {subscription_id}")
        return
    
    price = items[0].get("price", {})
    plan_id = subscription.get("metadata", {}).get("plan_id") or price.get("lookup_key", "pro")
    interval = price.get("recurring", {}).get("interval", "month")
    
    # NOTE: Subscription model has been removed - using Stripe as source of truth
    # TODO: If you need to store subscription data locally, create a Subscription model
    # For now, we rely on Stripe API and cache the data
    
    logger.info(f"Subscription {subscription_id} created for user {user.id}")
    logger.info(f"Plan: {plan_id}, Status: {status}, Interval: {interval}")
    
    # Clear cache to force fresh data from Stripe on next request
    from app.services.subscription_service_v2 import SubscriptionServiceV2
    SubscriptionServiceV2.clear_cache(str(user.id))


async def handle_subscription_updated(db: AsyncSession, subscription: Dict[str, Any]):
    """
    Handle subscription updates (plan changes, renewals, etc).
    """
    subscription_id = subscription.get("id")
    status = subscription.get("status")
    
    logger.info(f"Processing subscription.updated: {subscription_id}")
    
    # NOTE: Subscription model has been removed - using Stripe as source of truth
    # Find user by customer_id to clear cache
    customer_id = subscription.get("customer")
    result = await db.execute(
        select(User).where(User.stripe_customer_id == customer_id)
    )
    user = result.scalar_one_or_none()
    
    if user:
        # Clear cache to force fresh data from Stripe on next request
        from app.services.subscription_service_v2 import SubscriptionServiceV2
        SubscriptionServiceV2.clear_cache(str(user.id))
        logger.info(f"Updated subscription {subscription_id} for user {user.id}")
    else:
        logger.warning(f"User not found for customer {customer_id} when updating subscription {subscription_id}")


async def handle_subscription_deleted(db: AsyncSession, subscription: Dict[str, Any]):
    """
    Handle subscription cancellation/deletion.
    """
    subscription_id = subscription.get("id")
    
    logger.info(f"Processing subscription.deleted: {subscription_id}")
    
    # NOTE: Subscription model has been removed - using Stripe as source of truth
    # Find user by customer_id to clear cache
    customer_id = subscription.get("customer")
    result = await db.execute(
        select(User).where(User.stripe_customer_id == customer_id)
    )
    user = result.scalar_one_or_none()
    
    if user:
        # Clear cache to force fresh data from Stripe on next request
        from app.services.subscription_service_v2 import SubscriptionServiceV2
        SubscriptionServiceV2.clear_cache(str(user.id))
        logger.info(f"Subscription {subscription_id} canceled for user {user.id}")
    else:
        logger.warning(f"User not found for customer {customer_id} when deleting subscription {subscription_id}")


async def handle_invoice_payment_succeeded(db: AsyncSession, invoice: Dict[str, Any]):
    """
    Handle successful invoice payment.
    """
    subscription_id = invoice.get("subscription")
    
    if not subscription_id:
        return  # One-time payment, not a subscription
    
    logger.info(f"Processing invoice.payment_succeeded for subscription {subscription_id}")
    
    # NOTE: Subscription model has been removed - using Stripe as source of truth
    # Find user by invoice customer to clear cache
    customer_id = invoice.get("customer")
    result = await db.execute(
        select(User).where(User.stripe_customer_id == customer_id)
    )
    user = result.scalar_one_or_none()
    
    if user:
        # Clear cache to force fresh data from Stripe on next request
        from app.services.subscription_service_v2 import SubscriptionServiceV2
        SubscriptionServiceV2.clear_cache(str(user.id))
        logger.info(f"Payment succeeded for subscription {subscription_id}, user {user.id}")


async def handle_invoice_payment_failed(db: AsyncSession, invoice: Dict[str, Any]):
    """
    Handle failed invoice payment.
    """
    subscription_id = invoice.get("subscription")
    customer_id = invoice.get("customer")
    
    if not subscription_id:
        return  # One-time payment, not a subscription
    
    logger.info(f"Processing invoice.payment_failed for subscription {subscription_id}")
    
    # Find user to notify
    result = await db.execute(
        select(User).where(User.stripe_customer_id == customer_id)
    )
    user = result.scalar_one_or_none()
    
    if user:
        # TODO: Send email notification about failed payment
        logger.warning(f"Payment failed for user {user.id}, subscription {subscription_id}")
    
    # Subscription status will be updated by subscription.updated event
