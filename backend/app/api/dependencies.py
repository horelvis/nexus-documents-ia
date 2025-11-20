from typing import Optional

from fastapi import Depends, HTTPException, status, Header
from sqlalchemy.orm import Session

from app.db.database import get_db # SQLAlchemy session
from app.db.models import User # SQLAlchemy User model
from app.services.auth_service import AuthService # AuthService is now SQLAlchemy-based
from app.core.config import settings

# SQLAlchemy-based dependencies

def get_current_user(
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
) -> User:
    """
    Gets the current authenticated user from the token.
    Uses SQLAlchemy-based AuthService.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    logger.info(f"🔑 [DEPENDENCIES] get_current_user called with authorization: {'Yes' if authorization else 'No'}")
    
    # Development helper: allow X-User-Id override
    if settings.DEBUG and x_user_id:
        logger.info(f"🔧 [DEPENDENCIES] Development mode: Using X-User-Id: {x_user_id}")
        from sqlalchemy.orm import selectinload
        user = (
            db.query(User)
            .options(selectinload(User.roles), selectinload(User.image))
            .filter(User.clerk_user_id == x_user_id)
            .first()
        )
        if user:
            logger.info(f"✅ [DEPENDENCIES] Found user via X-User-Id: {user.email}")
            return user
        else:
            logger.warning(f"⚠️ [DEPENDENCIES] User not found with X-User-Id: {x_user_id}")
    
    if not authorization:
        logger.warning("⚠️ No Authorization header provided")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated - missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not authorization.startswith("Bearer "):
        logger.warning("⚠️ Invalid Authorization header format")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated - invalid Authorization header format",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = authorization.split(" ")[1]
    logger.info(f"🔑 [DEPENDENCIES] Extracted token: {token[:20]}...")
    
    try:
        logger.info(f"📞 [DEPENDENCIES] Calling AuthService.verify_clerk_token")
        clerk_payload = AuthService.verify_clerk_token(token=token)
        
        if not clerk_payload or not clerk_payload.get('sub'):
            logger.warning("⚠️ [DEPENDENCIES] Invalid Clerk token payload")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        clerk_user_id = clerk_payload.get('sub')
        logger.info(f"🔍 [DEPENDENCIES] Looking for user with Clerk ID: {clerk_user_id}")
        
        from sqlalchemy.orm import selectinload
        user = db.query(User).options(
            selectinload(User.roles),
            selectinload(User.image)
        ).filter(User.clerk_user_id == clerk_user_id).first()
        if not user:
            logger.warning(f"⚠️ [DEPENDENCIES] User not found for Clerk ID: {clerk_user_id}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User is not registered in Nexus. Complete the signup flow first.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        logger.info(f"✅ [DEPENDENCIES] User authenticated: {user.email}")
        return user
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Authentication error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed",
            headers={"WWW-Authenticate": "Bearer"},
        )

def get_current_tenant_id(
    current_user: User = Depends(get_current_user),
    x_tenant_id: Optional[str] = Header(None)
) -> str:
    """
    Gets the ID of the current tenant.
    If the X-Tenant-ID header is present and valid for a superuser, it's used.
    Otherwise, uses the tenant of the current user.
    """
    if settings.MULTI_TENANT and x_tenant_id and current_user.is_superuser:
        # In a multi-tenant mode, allow superusers to override tenant via header
        # Additional validation for x_tenant_id (e.g., checking if tenant exists) could be added here.
        return x_tenant_id
    
    return str(current_user.tenant_id)

def get_current_tenant(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    x_tenant_id: Optional[str] = Header(None)
):
    """
    Gets the current tenant object.
    If the X-Tenant-ID header is present and valid for a superuser, it's used.
    Otherwise, uses the tenant of the current user.
    """
    from app.db.models import Tenant
    
    if settings.MULTI_TENANT and x_tenant_id and current_user.is_superuser:
        # In a multi-tenant mode, allow superusers to override tenant via header
        tenant = db.query(Tenant).filter(Tenant.id == x_tenant_id).first()
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tenant not found"
            )
        return tenant
    
    # Use the tenant from the current user's relationship
    if current_user.tenant:
        return current_user.tenant
        
    # Fallback: query by tenant_id
    tenant = db.query(Tenant).filter(Tenant.id == current_user.tenant_id).first()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User tenant not found"
        )
    
    return tenant

def get_current_active_user( # This is a more specific version of get_current_user
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Ensures the current user is active.
    """
    if not current_user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user")
    return current_user


def require_microservice_api_key(
    authorization: str = Header(..., alias="Authorization"),
) -> str:
    """
    Validates internal microservice calls using the shared API key.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format",
        )
    api_key = authorization.split(" ")[1]
    if api_key != settings.MICROSERVICES_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid microservice API key",
        )
    return api_key

def get_current_active_superuser(
    current_user: User = Depends(get_current_active_user), # Depends on active user check
) -> User:
    """
    Verifies that the current active user has superuser privileges.
    """
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The user doesn't have enough privileges"
        )
    return current_user

def get_current_tenant_admin(
    current_user: User = Depends(get_current_active_user),
) -> User:
    """
    Verifies that the current active user is a tenant admin (not a team member).
    Tenant admins are users who are NOT team members (is_team_member = False).
    """
    if current_user.is_team_member:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only team administrators can perform this action"
        )
    return current_user


def require_subscription_permission(permission: str):
    """
    Dependencia para verificar permisos de suscripción.
    
    Args:
        permission: El permiso a verificar (ej: 'can_upload_documents', 'can_use_chat')
    
    Returns:
        Function que puede ser usada como dependencia en FastAPI
    """
    def permission_checker(
        current_user: User = Depends(get_current_active_user),
        db: Session = Depends(get_db)
    ) -> User:
        from app.services.subscription_service_v2 import SubscriptionServiceV2
        
        can_perform, error_message = SubscriptionServiceV2.can_user_perform_action(
            db, current_user, permission
        )
        
        if not can_perform:
            # Obtener información de suscripción para personalizar la respuesta
            subscription_status = SubscriptionServiceV2.get_user_subscription_status(db, current_user)
            
            if subscription_status["plan"] == "free":
                # Usuario con suscripción expirada
                raise HTTPException(
                    status_code=status.HTTP_402_PAYMENT_REQUIRED,
                    detail={
                        "message": error_message,
                        "subscription_status": subscription_status,
                        "action_required": "reactivate_subscription"
                    }
                )
            else:
                # Usuario necesita upgrade de plan
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "message": error_message,
                        "subscription_status": subscription_status,
                        "action_required": "upgrade_plan"
                    }
                )
        
        return current_user
    
    return permission_checker


def require_admin_role(
    current_user: User = Depends(get_current_active_user),
) -> User:
    """
    Ensures the current user has tenant admin privileges.
    Owners (non team members), users with the 'admin' role or superusers pass.
    """
    if getattr(current_user, "is_admin", False):
        return current_user
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Administrative privileges required",
    )


def require_document_upload_permission(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> User:
    """
    Dependencia específica para verificar permisos de subida de documentos.
    Incluye verificación de límites de documentos.
    """
    from app.services.subscription_service_v2 import SubscriptionServiceV2
    
    # Check document upload permission
    can_upload, error_message = SubscriptionServiceV2.check_document_permission(db, current_user)
    
    if not can_upload:
        # Get subscription status for error details
        subscription_status = SubscriptionServiceV2.get_user_subscription_status(db, current_user)
        
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED if subscription_status["plan"] == "free" else status.HTTP_403_FORBIDDEN,
            detail={
                "message": error_message,
                "subscription_status": subscription_status,
                "action_required": "upgrade_plan" if subscription_status["plan"] == "free" else "check_subscription",
                "limits": subscription_status.get("limits", {})
            }
        )
    
    return current_user


def require_agent_permission(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> User:
    """
    Dependencia específica para verificar permisos de uso de agentes AI.
    """
    from app.services.subscription_service_v2 import SubscriptionServiceV2
    
    # Check agent permission
    can_use_agents, error_message = SubscriptionServiceV2.check_agent_permission(db, current_user)
    
    if not can_use_agents:
        # Get subscription status for error details
        subscription_status = SubscriptionServiceV2.get_user_subscription_status(db, current_user)
        
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED if subscription_status["plan"] == "free" else status.HTTP_403_FORBIDDEN,
            detail={
                "message": error_message,
                "subscription_status": subscription_status,
                "action_required": "upgrade_plan" if subscription_status["plan"] == "free" else "check_subscription",
                "limits": subscription_status.get("limits", {})
            }
        )
    
    return current_user
