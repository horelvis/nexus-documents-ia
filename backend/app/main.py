"""
Refactored main application module - clean and modular

Supports deployment-specific modules:
    - SaaS: Clerk auth, Stripe billing, DocumentACL table
    - On-Premise: OIDC auth, connectors, JSONB ACL
"""
import logging

from app.api.api import api_router as v1_api_router
from app.api.docs import router as docs_router
from app.core.app_config import create_application, configure_static_files
from app.core.basic_routes import basic_router
from app.core.config import settings
from app.core.debug_routes import debug_router
from app.core.error_handlers import register_error_handlers
from app.core.features import FeatureFlags, is_on_premise_mode, is_saas_mode
from app.core.middlewares import configure_middlewares
from app.core.openapi_config import custom_openapi

logger = logging.getLogger(__name__)


def _load_deployment_module(app):
    """
    Load the appropriate module based on deployment mode.

    Modules configure:
        - ACL provider (Table vs JSONB)
        - Auth provider (Clerk vs OIDC)
        - Module-specific routers
    """
    mode = FeatureFlags.get_deployment_mode()
    logger.info(f"Loading deployment module for mode: {mode}")

    try:
        if is_on_premise_mode():
            from modules.on_premise import OnPremiseModule
            OnPremiseModule.register(app)
            logger.info("On-Premise module loaded successfully")

        elif is_saas_mode():
            from modules.saas import SaaSModule
            SaaSModule.register(app)
            logger.info("SaaS module loaded successfully")

        else:
            # Custom mode - load both modules but don't set defaults
            # This allows manual configuration via environment
            logger.info(f"Custom deployment mode: {mode}")
            try:
                from modules.on_premise import OnPremiseModule
                # Don't register (set default) - just make available
                logger.debug("On-Premise module available but not registered as default")
            except ImportError:
                pass
            try:
                from modules.saas import SaaSModule
                logger.debug("SaaS module available but not registered as default")
            except ImportError:
                pass

    except ImportError as e:
        logger.warning(f"Could not load deployment module: {e}")
        logger.warning("Running without deployment-specific module - using defaults")
    except Exception as e:
        logger.error(f"Error loading deployment module: {e}")


# Create FastAPI application
app = create_application()

# Configure custom OpenAPI schema
app.openapi = custom_openapi

# Configure static files
configure_static_files(app)

# Configure middlewares (CORS, logging, etc.)
configure_middlewares(app)

# Register error handlers
register_error_handlers(app)

# Load deployment-specific module (SaaS or On-Premise)
_load_deployment_module(app)

# Include routers
app.include_router(
    docs_router,
    prefix=settings.API_PREFIX,
    tags=["documentation"]
)

app.include_router(v1_api_router, prefix=settings.API_PREFIX)
app.include_router(basic_router)

# Include debug routes only in development
if settings.DEBUG:
    app.include_router(debug_router)

# Store reference for OpenAPI generation
settings._app = app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
