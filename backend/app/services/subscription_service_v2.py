# app/services/subscription_service_v2.py
"""
Servicio simplificado de suscripciones que usa Stripe como fuente de verdad
"""
import stripe
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.db.models import User
from app.core.config import settings
import json
from app.core.cache import cache, user_cache_key

logger = logging.getLogger(__name__)

# Configurar Stripe
stripe.api_key = settings.STRIPE_SECRET_KEY
logger.info(f"Stripe configured with API key: {stripe.api_key[:7]}..." if stripe.api_key else "NO API KEY")

class SubscriptionServiceV2:
    """
    Servicio simplificado que consulta Stripe directamente
    """
    
    # Cache duration for subscription data (5 minutes)
    CACHE_TTL = 300
    
    @staticmethod
    def get_user_subscription_status(db: Session, user: User) -> Dict[str, Any]:
        """
        Obtiene el estado de suscripción consultando Stripe directamente
        con cache para evitar demasiadas llamadas
        """
        # Si no tiene stripe_customer_id, es usuario gratuito
        if not user.stripe_customer_id:
            return {
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
        
        # Intentar obtener del cache primero
        cache_key = user_cache_key(str(user.id), "subscription")
        cached_data = cache.get_json(cache_key)
        
        if cached_data:
            logger.info(f"✨ Using cached subscription data for user {user.id}")
            return cached_data
        
        try:
            # Consultar Stripe
            logger.info(f"🔍 Fetching subscription from Stripe for customer {user.stripe_customer_id}")
            
            # Verificar que tenemos API key
            if not stripe.api_key:
                logger.error("Stripe API key not configured")
                raise Exception("Stripe API key not configured")
            
            # Listar todas las suscripciones del cliente
            logger.info(f"Fetching subscriptions for customer: {user.stripe_customer_id}")
            try:
                subscriptions = stripe.Subscription.list(
                    customer=user.stripe_customer_id,
                    limit=10,
                    expand=['data.default_payment_method']
                )
                logger.info(f"Subscriptions result type: {type(subscriptions)}")
            except Exception as e:
                logger.error(f"Error calling stripe.Subscription.list: {type(e).__name__}: {e}")
                raise
            
            # Buscar suscripción activa o en trial
            # Si hay múltiples suscripciones, tomar la más reciente
            active_subscription = None
            active_subscriptions = []
            
            if hasattr(subscriptions, 'data'):
                for sub in subscriptions.data:
                    if sub.status in ['active', 'trialing', 'past_due']:
                        active_subscriptions.append(sub)
            
            # Si hay múltiples suscripciones activas, tomar la más reciente
            if active_subscriptions:
                active_subscription = max(active_subscriptions, key=lambda x: x.created)
                logger.info(f"Found {len(active_subscriptions)} active subscriptions for user {user.id}, using most recent: {active_subscription.id}")
            
            if not active_subscription:
                # No hay suscripción activa - usuario gratuito
                result = {
                    "plan": "free",
                    "status": "active",
                    "can_use_agents": False,
                    "can_use_advanced_features": False,
                    "message": "Sin suscripción activa",
                    "limits": {
                        "documents": 10,
                        "storage_mb": 100,
                        "agents_per_month": 0
                    }
                }
            else:
                # Determinar el plan basado en metadata o price_id
                plan_id = active_subscription.metadata.get('plan_id', 'pro')
                
                # Si no hay metadata, intentar deducir del price_id
                if plan_id == 'pro' and hasattr(active_subscription.items, 'data') and active_subscription.items.data:
                    price_id = active_subscription.items.data[0].price.id
                    if price_id == settings.STRIPE_ENTERPRISE_PRICE_ID:
                        plan_id = 'enterprise'
                
                # Mapear estado y permisos
                status_map = {
                    'active': 'active',
                    'trialing': 'trial',
                    'past_due': 'past_due',
                    'canceled': 'canceled',
                    'incomplete': 'incomplete',
                    'incomplete_expired': 'expired'
                }
                
                status = status_map.get(active_subscription.status, 'unknown')
                
                # Calcular días restantes si está en trial
                trial_days_remaining = None
                if active_subscription.status == 'trialing' and active_subscription.trial_end:
                    trial_end = datetime.fromtimestamp(active_subscription.trial_end)
                    trial_days_remaining = (trial_end - datetime.now()).days
                
                # Determinar permisos según plan y estado
                can_use = status in ['active', 'trial']
                
                limits = {
                    'free': {
                        "documents": 10,
                        "storage_mb": 100,
                        "agents_per_month": 0
                    },
                    'pro': {
                        "documents": 1000,
                        "storage_mb": 10000,
                        "agents_per_month": 100
                    },
                    'enterprise': {
                        "documents": -1,  # Ilimitado
                        "storage_mb": -1,  # Ilimitado
                        "agents_per_month": -1  # Ilimitado
                    }
                }
                
                result = {
                    "plan": plan_id,
                    "status": status,
                    "can_use_agents": can_use and plan_id in ['pro', 'enterprise'],
                    "can_use_advanced_features": can_use and plan_id == 'enterprise',
                    "message": f"Plan {plan_id.title()} - {status}",
                    "limits": limits.get(plan_id, limits['free']),
                    "subscription_id": active_subscription.id,
                    "current_period_end": datetime.fromtimestamp(active_subscription.current_period_end).isoformat(),
                    "cancel_at_period_end": active_subscription.cancel_at_period_end
                }
                
                if trial_days_remaining is not None:
                    result["trial_days_remaining"] = trial_days_remaining
                    result["message"] = f"Periodo de prueba - {trial_days_remaining} días restantes"
                
                # Advertencias especiales
                if status == 'past_due':
                    result["message"] = "⚠️ Pago pendiente - Actualiza tu método de pago"
                elif active_subscription.cancel_at_period_end:
                    result["message"] = "⚠️ Suscripción se cancelará al final del periodo"
            
            # Guardar en cache
            cache.set_json(cache_key, result, ttl=SubscriptionServiceV2.CACHE_TTL)
            
            return result
            
        except stripe.error.StripeError as e:
            logger.error(f"❌ Stripe error for user {user.id}: {e}")
            # En caso de error, dar acceso básico
            return {
                "plan": "free",
                "status": "error",
                "can_use_agents": False,
                "can_use_advanced_features": False,
                "message": "Error consultando suscripción",
                "error": str(e),
                "limits": {
                    "documents": 10,
                    "storage_mb": 100,
                    "agents_per_month": 0
                }
            }
    
    @staticmethod
    def clear_cache(user_id: str):
        """Limpia el cache de suscripción para un usuario"""
        cache_key = user_cache_key(user_id, "subscription")
        cache.delete(cache_key)
        logger.info(f"🧹 Cleared subscription cache for user {user_id}")
    
    @staticmethod
    def verify_on_login(db: Session, user: User) -> Dict[str, Any]:
        """
        Verifica el estado de suscripción en cada login
        Actualiza el stripe_customer_id si es necesario
        """
        logger.info(f"🔐 Verifying subscription on login for user {user.id}")
        
        # Si no tiene stripe_customer_id, intentar buscarlo por email
        if not user.stripe_customer_id:
            try:
                logger.info(f"Searching Stripe customer for email: {user.email}")
                
                # Verificar que stripe está configurado
                if not stripe.api_key:
                    logger.error("Stripe API key not configured for customer search")
                    return SubscriptionServiceV2.get_user_subscription_status(db, user)
                
                # Intentar listar clientes
                try:
                    customers = stripe.Customer.list(email=user.email, limit=1)
                    logger.info(f"Customer search result type: {type(customers)}, hasattr data: {hasattr(customers, 'data')}")
                    
                    if hasattr(customers, 'data') and customers.data:
                        user.stripe_customer_id = customers.data[0].id
                        db.commit()
                        logger.info(f"✅ Updated stripe_customer_id for user {user.id}")
                    else:
                        logger.info(f"No Stripe customer found for email {user.email}")
                except AttributeError as ae:
                    logger.error(f"AttributeError calling stripe.Customer.list: {ae}")
                    logger.error(f"stripe.Customer type: {type(stripe.Customer)}")
                    logger.error(f"stripe.Customer.list type: {type(stripe.Customer.list) if hasattr(stripe.Customer, 'list') else 'NO LIST ATTR'}")
                except Exception as e:
                    logger.error(f"Error calling stripe.Customer.list: {type(e).__name__}: {e}")
                    raise
            except Exception as e:
                logger.error(f"Error searching customer: {type(e).__name__}: {e}")
        
        # Obtener estado actual
        status = SubscriptionServiceV2.get_user_subscription_status(db, user)
        
        # Log del resultado
        logger.info(f"📊 User {user.id} subscription: {status['plan']} - {status['status']}")
        
        return status
    
    @staticmethod
    def check_document_permission(db: Session, user: User) -> tuple[bool, Optional[str]]:
        """
        Verifica si el usuario puede subir más documentos
        """
        status = SubscriptionServiceV2.get_user_subscription_status(db, user)
        limits = status.get('limits', {})
        max_documents = limits.get('documents', 10)
        
        # Count current documents for the user's tenant
        from app.db.models import Document
        current_count = db.query(Document).filter(
            Document.tenant_id == user.tenant_id
        ).count()
        
        if current_count >= max_documents:
            return False, f"Has alcanzado el límite de {max_documents} documentos para tu plan {status['plan']}"
        
        return True, None
    
    @staticmethod
    def check_agent_permission(db: Session, user: User) -> tuple[bool, Optional[str]]:
        """
        Verifica si el usuario puede usar agentes
        Retorna (puede_usar, mensaje_error)
        """
        status = SubscriptionServiceV2.get_user_subscription_status(db, user)
        
        if not status['can_use_agents']:
            if status['plan'] == 'free':
                return False, "Los agentes AI requieren una suscripción Pro o Enterprise"
            elif status['status'] == 'past_due':
                return False, "Tu suscripción tiene un pago pendiente. Por favor actualiza tu método de pago."
            else:
                return False, f"Tu plan {status['plan']} no incluye acceso a agentes AI"
        
        return True, None