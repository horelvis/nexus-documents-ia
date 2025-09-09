"""
Debug routes and utilities - only available in development mode
"""
import logging
from typing import Dict, Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.logging import enable_auth_debug, disable_auth_debug

logger = logging.getLogger(__name__)

# Create router for debug endpoints
debug_router = APIRouter(prefix="/debug", tags=["debug"])


def _check_debug_mode() -> None:
    """Check if debug mode is enabled, raise exception if not"""
    if not settings.DEBUG:
        raise HTTPException(
            status_code=403,
            detail="Debug endpoints only available in development mode"
        )


@debug_router.get("/routes")
async def list_routes(request: Request) -> Dict[str, Any]:
    """List all registered routes"""
    _check_debug_mode()

    routes = []
    for route in request.app.routes:
        if hasattr(route, 'path') and hasattr(route, 'methods'):
            routes.append({
                "path": route.path,
                "methods": list(route.methods) if route.methods else []
            })
    return {"routes": routes}


@debug_router.post("/logging/auth/enable")
async def enable_debug_logging() -> Dict[str, str]:
    """Enable debug logging for authentication components"""
    _check_debug_mode()

    enable_auth_debug()
    return {"status": "success", "message": "Debug logging enabled for authentication"}


@debug_router.post("/logging/auth/disable")
async def disable_debug_logging() -> Dict[str, str]:
    """Disable debug logging for authentication components"""
    _check_debug_mode()

    disable_auth_debug()
    return {"status": "success", "message": "Debug logging disabled for authentication"}


@debug_router.get("/logging/status")
async def get_logging_status() -> Dict[str, Any]:
    """Show current logging status"""
    _check_debug_mode()

    import logging
    auth_loggers = [
        "app.api.dependencies",
        "app.services.auth_service",
        "app.api.v1.auth",
        "app.main"
    ]

    logger_status = {}
    for logger_name in auth_loggers:
        logger_obj = logging.getLogger(logger_name)
        logger_status[logger_name] = {
            "level": logging.getLevelName(logger_obj.level),
            "effective_level": logging.getLevelName(logger_obj.getEffectiveLevel())
        }

    return {
        "debug_mode": settings.DEBUG,
        "loggers": logger_status
    }


@debug_router.get("/check-users-table")
async def check_users_table() -> Dict[str, Any]:
    """Check users table structure"""
    _check_debug_mode()

    try:
        from app.db.database import engine
        from sqlalchemy import text

        with engine.connect() as conn:
            # Get all columns from users table
            result = conn.execute(text("""
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_name='users'
                ORDER BY ordinal_position
            """))

            columns = []
            for row in result.fetchall():
                columns.append({
                    "name": row[0],
                    "type": row[1],
                    "nullable": row[2],
                    "default": row[3]
                })

            # Check specifically for onboarding_completed
            onboarding_exists = any(col["name"] == "onboarding_completed" for col in columns)

            return {
                "status": "success",
                "table_exists": len(columns) > 0,
                "onboarding_completed_exists": onboarding_exists,
                "total_columns": len(columns),
                "columns": columns
            }

    except Exception as e:
        logger.error(f"❌ Error checking users table: {str(e)}")
        return {
            "status": "error",
            "message": f"Error checking users table: {str(e)}"
        }


@debug_router.post("/force-add-onboarding-column")
async def force_add_onboarding_column() -> Dict[str, Any]:
    """Force add onboarding_completed column"""
    _check_debug_mode()

    try:
        from app.db.migrations import manual_add_onboarding_column

        success = manual_add_onboarding_column()

        if success:
            return {
                "status": "success",
                "message": "Columna onboarding_completed procesada exitosamente"
            }
        else:
            return {
                "status": "error",
                "message": "No se pudo agregar la columna onboarding_completed"
            }

    except Exception as e:
        logger.error(f"❌ Error forcing column addition: {str(e)}")
        return {
            "status": "error",
            "message": f"Error forcing column addition: {str(e)}"
        }


@debug_router.post("/create-migration")
async def create_migration_endpoint(message: str) -> Dict[str, Any]:
    """Create new Alembic migration"""
    _check_debug_mode()

    try:
        from app.db.migrations import create_migration
        create_migration(message)
        return {
            "status": "success",
            "message": f"Migration '{message}' created successfully (DEVELOPMENT ONLY)",
            "warning": "This endpoint should NOT be used in production"
        }
    except Exception as e:
        logger.error(f"❌ Migration creation failed: {str(e)}")
        return {
            "status": "error",
            "message": f"Migration creation failed: {str(e)}"
        }


@debug_router.post("/init-db")
async def init_database() -> Dict[str, Any]:
    """Initialize database with tables and initial data"""
    _check_debug_mode()

    try:
        from app.db.models import Base
        from app.db.database import engine, SessionLocal
        from app.services.auth_service import AuthService
        from app.db.models import Tenant, User
        import uuid

        logger.warning("🚨 DEVELOPMENT ONLY: Initializing database via API endpoint")

        # Create all tables
        Base.metadata.create_all(bind=engine)
        logger.info("✅ Tables created")

        # Create initial data
        db = SessionLocal()
        try:
            # Create default tenant
            tenant = db.query(Tenant).filter(Tenant.name == settings.DEFAULT_TENANT).first()
            if not tenant:
                tenant = Tenant(
                    id=uuid.uuid4(),
                    name=settings.DEFAULT_TENANT,
                    description="Default tenant",
                    bucket_name=f"nexus-{settings.DEFAULT_TENANT}"
                )
                db.add(tenant)
                db.flush()
                logger.info(f"✅ Default tenant created: {tenant.id}")

            # Create admin user
            admin_user = db.query(User).filter(User.email == "admin@example.com").first()
            if not admin_user:
                admin_user = User(
                    id=uuid.uuid4(),
                    email="admin@example.com",
                    hashed_password=AuthService.get_password_hash("admin123"),
                    full_name="Admin User",
                    is_superuser=True,
                    is_active=True,
                    tenant_id=tenant.id
                )
                db.add(admin_user)
                logger.info("✅ Admin user created")

            db.commit()

        finally:
            db.close()

        return {
            "status": "success",
            "message": "Database initialized successfully (DEVELOPMENT ONLY)",
            "tenant_id": str(tenant.id) if tenant else None,
            "warning": "This endpoint should NOT be used in production"
        }

    except Exception as e:
        logger.error(f"❌ Database initialization failed: {str(e)}")
        return {
            "status": "error",
            "message": f"Database initialization failed: {str(e)}"
        }