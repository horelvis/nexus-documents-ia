"""
Servicio para gestión de suscripciones y control de acceso basado en planes.
"""

from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from enum import Enum

from sqlalchemy.orm import Session
from app.db.models import User, Subscription
from app.core.config import settings

import logging
logger = logging.getLogger(__name__)


class SubscriptionStatus(Enum):
    """Estados de suscripción"""
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"
    UNPAID = "unpaid"
    INCOMPLETE = "incomplete"
    INCOMPLETE_EXPIRED = "incomplete_expired"
    TRIALING = "trialing"
    EXPIRED = "expired"  # Custom status for expired subscriptions


class PlanType(Enum):
    """Tipos de planes disponibles"""
    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class SubscriptionPermissions:
    """Define qué acciones puede realizar cada tipo de suscripción"""
    
    PERMISSIONS = {
        # Plan gratuito
        PlanType.FREE: {
            "max_documents": 10,
            "max_monthly_uploads": 5,
            "can_upload_documents": True,
            "can_view_documents": True,
            "can_search_documents": True,
            "can_use_chat": True,
            "can_use_agents": False,
            "can_export_documents": False,
            "can_use_api": False,
            "max_file_size_mb": 10,
        },
        
        # Plan pro activo
        PlanType.PRO: {
            "max_documents": 1000,
            "max_monthly_uploads": 100,
            "can_upload_documents": True,
            "can_view_documents": True,
            "can_search_documents": True,
            "can_use_chat": True,
            "can_use_agents": True,
            "can_export_documents": True,
            "can_use_api": True,
            "max_file_size_mb": 100,
        },
        
        # Plan enterprise activo
        PlanType.ENTERPRISE: {
            "max_documents": -1,  # Ilimitado
            "max_monthly_uploads": -1,  # Ilimitado
            "can_upload_documents": True,
            "can_view_documents": True,
            "can_search_documents": True,
            "can_use_chat": True,
            "can_use_agents": True,
            "can_export_documents": True,
            "can_use_api": True,
            "max_file_size_mb": 500,
        },
        
        # Modo limitado (para suscripciones expiradas/canceladas)
        "limited": {
            "max_documents": 0,  # No puede subir más
            "max_monthly_uploads": 0,  # No puede subir más
            "can_upload_documents": False,
            "can_view_documents": True,  # Solo leer documentos existentes
            "can_search_documents": True,  # Solo buscar en documentos existentes
            "can_use_chat": False,
            "can_use_agents": False,
            "can_export_documents": False,
            "can_use_api": False,
            "max_file_size_mb": 0,
        }
    }


class SubscriptionService:
    
    @staticmethod
    def get_user_subscription_status(db: Session, user: User) -> Dict[str, Any]:
        """
        Obtiene el estado completo de la suscripción del usuario.
        Obtiene datos de Stripe en tiempo real para asegurar consistencia.
        
        Returns:
            dict con información del estado de la suscripción y permisos
        """
        subscription = db.query(Subscription).filter(
            Subscription.user_id == user.id
        ).first()
        
        # Si tenemos customer_id de Stripe, verificar estado real en Stripe
        if user.stripe_customer_id and subscription:
            try:
                import stripe
                from app.core.config import settings
                stripe.api_key = settings.STRIPE_SECRET_KEY
                
                # Obtener suscripciones activas de Stripe
                stripe_subscriptions = stripe.Subscription.list(
                    customer=user.stripe_customer_id,
                    status='all',
                    limit=1
                )
                
                if stripe_subscriptions.data:
                    stripe_sub = stripe_subscriptions.data[0]
                    # Actualizar datos locales si difieren
                    if subscription.status != stripe_sub.status:
                        logger.info(f"🔄 Updating subscription status from Stripe: {subscription.status} -> {stripe_sub.status}")
                        subscription.status = stripe_sub.status
                        subscription.current_period_end = datetime.fromtimestamp(stripe_sub.current_period_end, tz=timezone.utc)
                        db.commit()
                        
            except Exception as e:
                logger.warning(f"⚠️ Could not sync with Stripe: {str(e)}")
                # Continuar con datos locales
        
        # Usuario sin suscripción = plan gratuito
        if not subscription:
            return {
                "plan_type": PlanType.FREE.value,
                "status": SubscriptionStatus.ACTIVE.value,
                "is_active": True,
                "is_limited": False,
                "current_period_end": None,
                "can_reactivate": False,
                "permissions": SubscriptionPermissions.PERMISSIONS[PlanType.FREE],
                "message": "Plan gratuito activo"
            }
        
        # Verificar si la suscripción ha expirado
        now = datetime.now(timezone.utc)
        is_expired = subscription.current_period_end < now
        
        # Determinar el estado real
        if subscription.status == SubscriptionStatus.CANCELED.value:
            if is_expired:
                # Suscripción cancelada y expirada -> modo limitado
                return {
                    "plan_type": subscription.stripe_plan_id or PlanType.FREE.value,
                    "status": SubscriptionStatus.EXPIRED.value,
                    "is_active": False,
                    "is_limited": True,
                    "current_period_end": subscription.current_period_end,
                    "can_reactivate": True,
                    "permissions": SubscriptionPermissions.PERMISSIONS["limited"],
                    "message": f"Tu suscripción {subscription.stripe_plan_id} expiró el {subscription.current_period_end.strftime('%d/%m/%Y')}. Solo puedes ver documentos existentes."
                }
            else:
                # Suscripción cancelada pero aún dentro del período pagado
                plan_type = PlanType(subscription.stripe_plan_id) if subscription.stripe_plan_id in [p.value for p in PlanType] else PlanType.FREE
                return {
                    "plan_type": subscription.stripe_plan_id,
                    "status": SubscriptionStatus.CANCELED.value,
                    "is_active": True,  # Aún tiene acceso hasta que expire
                    "is_limited": False,
                    "current_period_end": subscription.current_period_end,
                    "can_reactivate": True,
                    "permissions": SubscriptionPermissions.PERMISSIONS[plan_type],
                    "message": f"Tu suscripción está cancelada pero tienes acceso hasta el {subscription.current_period_end.strftime('%d/%m/%Y')}."
                }
        
        elif subscription.status in [SubscriptionStatus.PAST_DUE.value, SubscriptionStatus.UNPAID.value]:
            if is_expired:
                # Suscripción impaga y expirada -> modo limitado
                return {
                    "plan_type": subscription.stripe_plan_id or PlanType.FREE.value,
                    "status": SubscriptionStatus.EXPIRED.value,
                    "is_active": False,
                    "is_limited": True,
                    "current_period_end": subscription.current_period_end,
                    "can_reactivate": True,
                    "permissions": SubscriptionPermissions.PERMISSIONS["limited"],
                    "message": f"Tu suscripción no pudo renovarse. Solo puedes ver documentos existentes."
                }
            else:
                # Suscripción impaga pero aún dentro del período de gracia
                plan_type = PlanType(subscription.stripe_plan_id) if subscription.stripe_plan_id in [p.value for p in PlanType] else PlanType.FREE
                return {
                    "plan_type": subscription.stripe_plan_id,
                    "status": subscription.status,
                    "is_active": True,
                    "is_limited": False,
                    "current_period_end": subscription.current_period_end,
                    "can_reactivate": True,
                    "permissions": SubscriptionPermissions.PERMISSIONS[plan_type],
                    "message": f"Hay un problema con tu pago. Por favor actualiza tu método de pago."
                }
        
        elif subscription.status == SubscriptionStatus.ACTIVE.value:
            # Suscripción activa
            plan_type = PlanType(subscription.stripe_plan_id) if subscription.stripe_plan_id in [p.value for p in PlanType] else PlanType.FREE
            return {
                "plan_type": subscription.stripe_plan_id,
                "status": SubscriptionStatus.ACTIVE.value,
                "is_active": True,
                "is_limited": False,
                "current_period_end": subscription.current_period_end,
                "can_reactivate": False,
                "permissions": SubscriptionPermissions.PERMISSIONS[plan_type],
                "message": f"Suscripción {subscription.stripe_plan_id} activa hasta el {subscription.current_period_end.strftime('%d/%m/%Y')}."
            }
        
        else:
            # Estado desconocido -> modo limitado por seguridad
            return {
                "plan_type": subscription.stripe_plan_id or PlanType.FREE.value,
                "status": subscription.status,
                "is_active": False,
                "is_limited": True,
                "current_period_end": subscription.current_period_end,
                "can_reactivate": True,
                "permissions": SubscriptionPermissions.PERMISSIONS["limited"],
                "message": f"Estado de suscripción desconocido: {subscription.status}"
            }
    
    @staticmethod
    def can_user_perform_action(db: Session, user: User, action: str) -> tuple[bool, str]:
        """
        Verifica si un usuario puede realizar una acción específica.
        
        Args:
            db: Sesión de base de datos
            user: Usuario a verificar
            action: Acción a verificar (ej: 'can_upload_documents', 'can_use_chat')
            
        Returns:
            tuple[bool, str]: (puede_realizar_accion, mensaje_de_error)
        """
        subscription_status = SubscriptionService.get_user_subscription_status(db, user)
        permissions = subscription_status["permissions"]
        
        if action not in permissions:
            return False, f"Acción '{action}' no reconocida"
        
        can_perform = permissions[action]
        
        if not can_perform:
            if subscription_status["is_limited"]:
                return False, f"Tu suscripción ha expirado. {subscription_status['message']} Para continuar usando esta función, reactiva tu suscripción."
            else:
                return False, f"Esta función no está disponible en tu plan actual. Considera actualizar tu suscripción."
        
        return True, ""
    
    @staticmethod
    def get_document_count_for_user(db: Session, user: User) -> int:
        """Obtiene el número de documentos del usuario"""
        from app.db.models import Document
        return db.query(Document).filter(Document.created_by == user.id).count()
    
    @staticmethod
    def can_user_upload_document(db: Session, user: User) -> tuple[bool, str]:
        """
        Verifica si un usuario puede subir un documento.
        
        Returns:
            tuple[bool, str]: (puede_subir, mensaje_de_error)
        """
        # Verificar permiso básico
        can_upload, message = SubscriptionService.can_user_perform_action(db, user, "can_upload_documents")
        if not can_upload:
            return False, message
        
        # Verificar límite de documentos
        subscription_status = SubscriptionService.get_user_subscription_status(db, user)
        max_documents = subscription_status["permissions"]["max_documents"]
        
        if max_documents > 0:  # -1 significa ilimitado
            current_count = SubscriptionService.get_document_count_for_user(db, user)
            if current_count >= max_documents:
                return False, f"Has alcanzado el límite de {max_documents} documentos para tu plan. Actualiza tu suscripción para subir más documentos."
        
        return True, ""
    
    @staticmethod
    def update_subscription_status(db: Session, stripe_subscription_id: str, new_status: str) -> bool:
        """
        Actualiza el estado de una suscripción basado en webhooks de Stripe.
        """
        subscription = db.query(Subscription).filter(
            Subscription.stripe_subscription_id == stripe_subscription_id
        ).first()
        
        if not subscription:
            logger.warning(f"Subscription not found: {stripe_subscription_id}")
            return False
        
        old_status = subscription.status
        subscription.status = new_status
        
        try:
            db.commit()
            logger.info(f"Subscription {stripe_subscription_id} status updated: {old_status} -> {new_status}")
            return True
        except Exception as e:
            logger.error(f"Error updating subscription status: {str(e)}")
            db.rollback()
            return False