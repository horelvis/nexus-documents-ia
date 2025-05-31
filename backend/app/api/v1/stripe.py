# backend/app/api/v1/stripe.py - Endpoint para Customer Portal

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
import stripe
import logging
from typing import Dict, Any

from app.api.dependencies import get_current_user, get_current_active_superuser, get_current_admin_user
from app.db.models import User, Subscription
from app.db.database import get_db
from app.core.config import settings
from app.api.dependencies import settings

logger = logging.getLogger(__name__)
router = APIRouter()

# Configurar Stripe
stripe.api_key = settings.STRIPE_SECRET_KEY


@router.post("/create-customer-portal")
async def create_customer_portal(
    current_user: User = Depends(get_current_user),
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


@router.get("/subscription")
async def get_current_subscription(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Obtiene la suscripción actual del usuario.
    Datos mínimos necesarios para mostrar en el frontend.
    """
    try:
        # Buscar suscripción en nuestra base de datos
        subscription = db.query(Subscription).filter(
            Subscription.user_id == current_user.id,
            Subscription.status.in_(["active", "past_due", "unpaid"])
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
                "customer_id": current_user.stripe_customer_id
            }

        # Retornar datos de la suscripción
        return {
            "id": subscription.stripe_subscription_id,
            "plan_id": subscription.plan_id,
            "status": subscription.status,
            "interval": subscription.interval,
            "current_period_start": int(subscription.current_period_start.timestamp()),
            "current_period_end": int(subscription.current_period_end.timestamp()),
            "cancel_at_period_end": subscription.cancel_at_period_end,
            "customer_id": current_user.stripe_customer_id
        }

    except Exception as e:
        logger.error(f"Error getting subscription for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Error obteniendo información de suscripción"
        )


@router.post("/sync-subscription")
async def sync_subscription_from_stripe(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Sincroniza la suscripción desde Stripe (útil después del checkout).
    Opcional: Solo si necesitas forzar una sincronización.
    """
    try:
        if not current_user.stripe_customer_id:
            raise HTTPException(
                status_code=400,
                detail="Usuario no tiene cuenta de cliente en Stripe"
            )

        # Obtener suscripciones activas del customer en Stripe
        subscriptions = stripe.Subscription.list(
            customer=current_user.stripe_customer_id,
            status="active",
            limit=1
        )

        if not subscriptions.data:
            # No hay suscripciones activas, usuario está en plan gratuito
            # Actualizar o crear registro local
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
            # Crear nueva suscripción local
            local_sub = Subscription(
                user_id=current_user.id,
                stripe_subscription_id=stripe_sub.id,
                stripe_customer_id=current_user.stripe_customer_id,
                plan_id=stripe_sub.items.data[0].price.lookup_key or "pro",
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
            "plan_id": local_sub.plan_id,
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
    current_user: User = Depends(get_current_admin_user)  # Solo admins
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


# Importaciones necesarias en la parte superior del archivo
import time
from datetime import datetime
from app.models.subscription import Subscription
from app.core.deps import get_current_admin_user  # Para configuración