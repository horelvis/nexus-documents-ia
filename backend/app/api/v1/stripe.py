# backend/app/api/v1/stripe.py - Stripe endpoints

from fastapi import APIRouter, HTTPException, Depends, Request
from sqlalchemy.orm import Session
import stripe
import logging
from typing import Dict, Any, Optional
from pydantic import BaseModel

from app.api.dependencies import get_current_active_superuser, get_current_active_user
from app.db.models import User
from app.db.database import get_db
from app.core.config import settings
from app.db.models import Subscription


# Importaciones necesarias en la parte superior del archivo
import time
from datetime import datetime, timezone

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
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> Dict[str, str]:
    """
    Crea una sesión de checkout de Stripe para usuarios existentes que quieren actualizar su plan.
    """
    try:
        # Validate plan ID
        if request.planId not in ['pro', 'enterprise']:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid plan ID: {request.planId}. Must be 'pro' or 'enterprise'"
            )
        
        # Validate interval
        if request.interval not in ['month', 'year']:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid interval: {request.interval}. Must be 'month' or 'year'"
            )
        
        # Centralized plan to price mapping
        plan_price_mapping = {
            'pro': {
                'month': settings.STRIPE_PRO_PRICE_ID,
                'year': getattr(settings, 'STRIPE_PRO_YEARLY_PRICE_ID', None)
            },
            'enterprise': {
                'month': settings.STRIPE_ENTERPRISE_PRICE_ID,
                'year': getattr(settings, 'STRIPE_ENTERPRISE_YEARLY_PRICE_ID', None)
            }
        }
        
        # Get the appropriate price ID
        stripe_price_id = plan_price_mapping.get(request.planId, {}).get(request.interval)
        
        if not stripe_price_id:
            raise HTTPException(
                status_code=400,
                detail=f"Price not configured for plan '{request.planId}' with interval '{request.interval}'"
            )

        # Si el usuario ya tiene un customer_id, usarlo
        customer_id = current_user.stripe_customer_id
        
        # Si no tiene customer_id, crear uno nuevo
        if not customer_id:
            customer = stripe.Customer.create(
                email=current_user.email,
                metadata={
                    'user_id': str(current_user.id),
                    'tenant_id': str(current_user.tenant_id)
                }
            )
            customer_id = customer.id
            
            # Guardar el customer_id en la base de datos
            current_user.stripe_customer_id = customer_id
            db.commit()
        
        # Crear sesión de checkout
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price': stripe_price_id,
                'quantity': 1,
            }],
            mode='subscription',
            success_url=request.success_url or f"{settings.FRONTEND_URL}/{current_user.tenant_id}/dashboard?upgraded=true&sync=true",
            cancel_url=request.cancel_url or f"{settings.FRONTEND_URL}/plans/{current_user.tenant_id}",
            metadata={
                'plan_id': request.planId,
                'user_id': str(current_user.id),
                'tenant_id': str(current_user.tenant_id)
            },
            customer=customer_id,
            # Recopilar información adicional
            billing_address_collection='auto',
            # Permitir códigos promocionales
            allow_promotion_codes=True,
            # Configurar el trial si aplica
            subscription_data={
                'trial_period_days': 14 if request.planId == 'pro' else None,
                'metadata': {
                    'plan_id': request.planId,
                    'interval': request.interval,
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


@router.get("/checkout-session/{session_id}")
async def get_checkout_session(
    session_id: str,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Obtiene información de la sesión de checkout completada.
    Se usa después del pago exitoso para el registro del usuario.
    """
    try:
        session = stripe.checkout.Session.retrieve(
            session_id,
            expand=['customer', 'subscription']
        )

        if session.payment_status != 'paid':
            raise HTTPException(
                status_code=400,
                detail="Payment not completed"
            )

        return {
            "session_id": session.id,
            "customer_id": session.customer,
            "customer_email": session.customer_details.email,
            "subscription_id": session.subscription,
            "plan_id": session.metadata.get('plan_id'),
            "payment_status": session.payment_status,
            "amount_total": session.amount_total,
            "currency": session.currency,
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


@router.post("/create-customer-portal")
async def create_customer_portal(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
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

        # Crear sesión del Customer Portal
        session = stripe.billing_portal.Session.create(
            customer=current_user.stripe_customer_id,
            return_url=f"{settings.FRONTEND_URL}/dashboard/settings/billing",
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
    current_user: User = Depends(get_current_active_user)
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
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Obtiene la suscripción actual del usuario con estado detallado y permisos.
    """
    try:
        from app.services.subscription_service import SubscriptionService
        
        # Obtener estado completo de la suscripción
        subscription_status = SubscriptionService.get_user_subscription_status(db, current_user)
        
        # Buscar datos de suscripción en la base de datos
        subscription = db.query(Subscription).filter(
            Subscription.user_id == current_user.id
        ).first()

        if not subscription:
            # Usuario sin suscripción = plan gratuito
            return {
                "id": "free",
                "plan_id": "free",
                "status": "active",
                "interval": "month",
                "current_period_start": int(time.time()),
                "current_period_end": int(time.time() + (30 * 24 * 60 * 60)),
                "cancel_at_period_end": False,
                "customer_id": current_user.stripe_customer_id,
                # Información adicional del servicio de suscripciones
                "subscription_status": subscription_status
            }

        # Retornar datos completos de la suscripción
        return {
            "id": subscription.stripe_subscription_id,
            "plan_id": subscription.stripe_plan_id,
            "status": subscription.status,
            "interval": subscription.interval,
            "current_period_start": int(subscription.current_period_start.timestamp()),
            "current_period_end": int(subscription.current_period_end.timestamp()),
            "cancel_at_period_end": subscription.cancel_at_period_end,
            "customer_id": current_user.stripe_customer_id,
            # Información adicional del servicio de suscripciones
            "subscription_status": subscription_status
        }

    except Exception as e:
        logger.error(f"Error getting subscription for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Error obteniendo información de suscripción"
        )


@router.post("/sync-subscription")
async def sync_subscription_from_stripe(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Sincroniza la suscripción desde Stripe (útil después del checkout).
    """
    try:
        logger.info(f"[SYNC] Starting sync for user {current_user.id} ({current_user.email})")
        logger.info(f"[SYNC] Current stripe_customer_id: {current_user.stripe_customer_id}")
        
        if not current_user.stripe_customer_id:
            logger.warning(f"[SYNC] User {current_user.id} has no stripe_customer_id")
            
            # Intentar buscar el customer por email en Stripe
            logger.info(f"[SYNC] Searching for customer by email: {current_user.email}")
            customers = stripe.Customer.list(email=current_user.email, limit=1)
            
            if customers.data:
                customer = customers.data[0]
                logger.info(f"[SYNC] Found customer in Stripe: {customer.id}")
                
                # Actualizar el customer_id en la base de datos
                current_user.stripe_customer_id = customer.id
                db.commit()
                logger.info(f"[SYNC] Updated user with stripe_customer_id: {customer.id}")
            else:
                logger.error(f"[SYNC] No customer found in Stripe for email: {current_user.email}")
                return {
                    "error": "No se encontró cliente en Stripe",
                    "plan_id": "free",
                    "status": "no_customer",
                    "synced": False
                }

        # Obtener suscripciones activas del customer en Stripe
        logger.info(f"[SYNC] Fetching subscriptions from Stripe for customer: {current_user.stripe_customer_id}")
        try:
            subscriptions = stripe.Subscription.list(
                customer=current_user.stripe_customer_id,
                status="active",
                limit=1
            )
            logger.info(f"[SYNC] Stripe API call successful")
            logger.info(f"[SYNC] Found {len(subscriptions.data)} active subscriptions")
        except stripe.error.StripeError as e:
            logger.error(f"[SYNC] Stripe API error: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Error al consultar Stripe: {str(e)}"
            )

        if not subscriptions.data:
            # No hay suscripciones activas, buscar TODAS las suscripciones
            logger.info("No active subscriptions found, checking all subscription statuses...")
            all_subscriptions = stripe.Subscription.list(
                customer=current_user.stripe_customer_id,
                limit=10
            )
            
            if all_subscriptions.data:
                logger.info(f"Found {len(all_subscriptions.data)} total subscriptions:")
                for sub in all_subscriptions.data:
                    logger.info(f"  - ID: {sub.id}, Status: {sub.status}, Plan: {sub.items.data[0].price.id}")
                    
                # Si hay alguna suscripción en trial o incomplete, usarla
                for sub in all_subscriptions.data:
                    if sub.status in ["trialing", "incomplete", "incomplete_expired"]:
                        logger.info(f"Found subscription in status '{sub.status}', will sync it")
                        subscriptions.data = [sub]
                        break
            
            if not subscriptions.data:
                # Realmente no hay suscripciones
                existing_sub = db.query(Subscription).filter(
                    Subscription.user_id == current_user.id
                ).first()
                
                if existing_sub:
                    existing_sub.status = "canceled"
                    db.commit()

                return {
                    "id": "free",
                    "plan_id": "free", 
                    "status": "active",
                    "synced": True
                }

        # Hay suscripción activa, sincronizar datos
        stripe_sub = subscriptions.data[0]
        
        # Buscar o crear suscripción local
        local_sub = db.query(Subscription).filter(
            Subscription.stripe_subscription_id == stripe_sub.id
        ).first()

        if not local_sub:
            # Determinar el plan_id basado en el price_id o metadata
            plan_id = "pro"  # Default
            price_id = stripe_sub.items.data[0].price.id
            
            # Mapear price_id a plan_id
            if price_id == settings.STRIPE_PRO_PRICE_ID:
                plan_id = "pro"
            elif price_id == settings.STRIPE_ENTERPRISE_PRICE_ID:
                plan_id = "enterprise"
            elif stripe_sub.metadata.get("plan_id"):
                plan_id = stripe_sub.metadata["plan_id"]
            
            logger.info(f"Creating subscription: price_id={price_id}, plan_id={plan_id}")
            
            # Crear nueva suscripción local
            local_sub = Subscription(
                user_id=current_user.id,
                stripe_subscription_id=stripe_sub.id,
                stripe_customer_id=current_user.stripe_customer_id,
                stripe_plan_id=plan_id,
                status=stripe_sub.status,
                interval=stripe_sub.items.data[0].price.recurring.interval,
                current_period_start=datetime.fromtimestamp(stripe_sub.current_period_start),
                current_period_end=datetime.fromtimestamp(stripe_sub.current_period_end),
                cancel_at_period_end=stripe_sub.cancel_at_period_end
            )
            db.add(local_sub)
        else:
            # Actualizar suscripción existente
            local_sub.status = stripe_sub.status
            local_sub.current_period_start = datetime.fromtimestamp(stripe_sub.current_period_start)
            local_sub.current_period_end = datetime.fromtimestamp(stripe_sub.current_period_end)
            local_sub.cancel_at_period_end = stripe_sub.cancel_at_period_end

        db.commit()
        db.refresh(local_sub)

        logger.info(f"Subscription synced for user {current_user.id}: {stripe_sub.id}")

        return {
            "id": local_sub.stripe_subscription_id,
            "plan_id": local_sub.stripe_plan_id,
            "status": local_sub.status,
            "interval": local_sub.interval,
            "current_period_start": int(local_sub.current_period_start.timestamp()),
            "current_period_end": int(local_sub.current_period_end.timestamp()),
            "cancel_at_period_end": local_sub.cancel_at_period_end,
            "synced": True
        }

    except stripe.error.StripeError as e:
        logger.error(f"Stripe error syncing subscription for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error sincronizando con Stripe: {str(e)}"
        )
    
    except Exception as e:
        logger.error(f"Error syncing subscription for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Error interno sincronizando suscripción"
        )


# Configuración del Customer Portal (ejecutar una vez)
@router.post("/configure-portal")
async def configure_customer_portal(
    current_user: User = Depends(get_current_active_superuser)  # Solo admins
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
    db: Session = Depends(get_db)
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
async def handle_checkout_session_completed(db: Session, session: Dict[str, Any]):
    """
    Handle successful checkout session completion.
    This is called when a user completes payment for the first time.
    """
    customer_id = session.get("customer")
    customer_email = session.get("customer_details", {}).get("email")
    
    logger.info(f"Processing checkout.session.completed for customer {customer_id}")
    
    # Find user by email or stripe_customer_id
    user = db.query(User).filter(
        (User.email == customer_email) | (User.stripe_customer_id == customer_id)
    ).first()
    
    if not user:
        logger.error(f"User not found for customer {customer_id} / email {customer_email}")
        return
    
    # Update user's stripe_customer_id if not set
    if not user.stripe_customer_id:
        user.stripe_customer_id = customer_id
        db.commit()
        logger.info(f"Updated stripe_customer_id for user {user.id}")
    
    # If there's a subscription, it will be handled by subscription.created event
    logger.info(f"Checkout completed for user {user.id}, subscription will be handled by subscription webhook")


async def handle_subscription_created(db: Session, subscription: Dict[str, Any]):
    """
    Handle new subscription creation.
    """
    subscription_id = subscription.get("id")
    customer_id = subscription.get("customer")
    status = subscription.get("status")
    
    logger.info(f"Processing subscription.created: {subscription_id}")
    
    # Find user by stripe_customer_id
    user = db.query(User).filter(User.stripe_customer_id == customer_id).first()
    
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
    
    # Check if subscription already exists
    existing_sub = db.query(Subscription).filter(
        Subscription.stripe_subscription_id == subscription_id
    ).first()
    
    if existing_sub:
        logger.info(f"Subscription {subscription_id} already exists, updating...")
        existing_sub.status = status
        existing_sub.current_period_start = datetime.fromtimestamp(subscription.get("current_period_start"))
        existing_sub.current_period_end = datetime.fromtimestamp(subscription.get("current_period_end"))
    else:
        # Create new subscription record
        new_subscription = Subscription(
            user_id=user.id,
            stripe_subscription_id=subscription_id,
            stripe_customer_id=customer_id,
            stripe_plan_id=plan_id,
            status=status,
            interval=interval,
            current_period_start=datetime.fromtimestamp(subscription.get("current_period_start")),
            current_period_end=datetime.fromtimestamp(subscription.get("current_period_end")),
            cancel_at_period_end=subscription.get("cancel_at_period_end", False)
        )
        db.add(new_subscription)
        logger.info(f"Created new subscription {subscription_id} for user {user.id}")
    
    db.commit()


async def handle_subscription_updated(db: Session, subscription: Dict[str, Any]):
    """
    Handle subscription updates (plan changes, renewals, etc).
    """
    subscription_id = subscription.get("id")
    status = subscription.get("status")
    
    logger.info(f"Processing subscription.updated: {subscription_id}")
    
    # Find existing subscription
    existing_sub = db.query(Subscription).filter(
        Subscription.stripe_subscription_id == subscription_id
    ).first()
    
    if not existing_sub:
        logger.warning(f"Subscription {subscription_id} not found, creating new one")
        await handle_subscription_created(db, subscription)
        return
    
    # Update subscription details
    existing_sub.status = status
    existing_sub.current_period_start = datetime.fromtimestamp(subscription.get("current_period_start"))
    existing_sub.current_period_end = datetime.fromtimestamp(subscription.get("current_period_end"))
    existing_sub.cancel_at_period_end = subscription.get("cancel_at_period_end", False)
    
    # Update plan if changed
    items = subscription.get("items", {}).get("data", [])
    if items:
        price = items[0].get("price", {})
        plan_id = subscription.get("metadata", {}).get("plan_id") or price.get("lookup_key", existing_sub.stripe_plan_id)
        interval = price.get("recurring", {}).get("interval", existing_sub.interval)
        
        existing_sub.stripe_plan_id = plan_id
        existing_sub.interval = interval
    
    db.commit()
    logger.info(f"Updated subscription {subscription_id}")


async def handle_subscription_deleted(db: Session, subscription: Dict[str, Any]):
    """
    Handle subscription cancellation/deletion.
    """
    subscription_id = subscription.get("id")
    
    logger.info(f"Processing subscription.deleted: {subscription_id}")
    
    # Find existing subscription
    existing_sub = db.query(Subscription).filter(
        Subscription.stripe_subscription_id == subscription_id
    ).first()
    
    if not existing_sub:
        logger.warning(f"Subscription {subscription_id} not found for deletion")
        return
    
    # Update status to canceled
    existing_sub.status = "canceled"
    existing_sub.canceled_at = datetime.now(timezone.utc)
    
    db.commit()
    logger.info(f"Marked subscription {subscription_id} as canceled")


async def handle_invoice_payment_succeeded(db: Session, invoice: Dict[str, Any]):
    """
    Handle successful invoice payment.
    """
    subscription_id = invoice.get("subscription")
    
    if not subscription_id:
        return  # One-time payment, not a subscription
    
    logger.info(f"Processing invoice.payment_succeeded for subscription {subscription_id}")
    
    # Update subscription status if needed
    existing_sub = db.query(Subscription).filter(
        Subscription.stripe_subscription_id == subscription_id
    ).first()
    
    if existing_sub and existing_sub.status != "active":
        existing_sub.status = "active"
        db.commit()
        logger.info(f"Reactivated subscription {subscription_id} after successful payment")


async def handle_invoice_payment_failed(db: Session, invoice: Dict[str, Any]):
    """
    Handle failed invoice payment.
    """
    subscription_id = invoice.get("subscription")
    customer_id = invoice.get("customer")
    
    if not subscription_id:
        return  # One-time payment, not a subscription
    
    logger.info(f"Processing invoice.payment_failed for subscription {subscription_id}")
    
    # Find user to notify
    user = db.query(User).filter(User.stripe_customer_id == customer_id).first()
    
    if user:
        # TODO: Send email notification about failed payment
        logger.warning(f"Payment failed for user {user.id}, subscription {subscription_id}")
    
    # Subscription status will be updated by subscription.updated event
