"""
Refactored main application module - clean and modular
"""
import logging

from app.api.api import api_router as v1_api_router
from app.api.docs import router as docs_router
from app.core.app_config import create_application, configure_static_files
from app.core.basic_routes import basic_router
from app.core.config import settings
from app.core.debug_routes import debug_router
from app.core.error_handlers import register_error_handlers
from app.core.middlewares import configure_middlewares
from app.core.openapi_config import custom_openapi

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
