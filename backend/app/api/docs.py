# app/api/docs.py
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html
from fastapi import APIRouter, Request, Depends
from fastapi.openapi.utils import get_openapi
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.responses import RedirectResponse

from app.core.config import settings
from app.api.dependencies import get_current_active_superuser

router = APIRouter()

@router.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html(request: Request):
    """
    Proporciona la interfaz de Swagger UI personalizada.
    """
    openapi_url = request.app.openapi_url
    title = request.app.title + " - API Documentation"
    
    # Personaliza la apariencia de Swagger UI
    return get_swagger_ui_html(
        openapi_url=openapi_url,
        title=title,
        swagger_js_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@4/swagger-ui-bundle.js",
        swagger_css_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@4/swagger-ui.css",
        swagger_favicon_url="/static/favicon.ico",
        oauth2_redirect_url=request.url_for("oauth2_redirect"),
        init_oauth={
            "clientId": "your-client-id", # Opcional para OAuth2
        }
    )

@router.get("/redoc", include_in_schema=False)
async def redoc_html(request: Request):
    """
    Proporciona la interfaz de ReDoc personalizada.
    """
    openapi_url = request.app.openapi_url
    title = request.app.title + " - API Documentation"
    
    return get_redoc_html(
        openapi_url=openapi_url,
        title=title,
        redoc_js_url="https://cdn.jsdelivr.net/npm/redoc@next/bundles/redoc.standalone.js",
        redoc_favicon_url="/static/favicon.ico",
    )

@router.get("/openapi.json", include_in_schema=False)
async def get_open_api_endpoint(request: Request):
    """
    Devuelve el esquema OpenAPI con personalización dinámica.
    """
    openapi_schema = get_openapi(
        title=request.app.title,
        version=request.app.version,
        description=request.app.description,
        routes=request.app.routes,
        servers=[{"url": settings.SERVER_HOST}],
        tags=request.app.openapi_tags
    )
    
    # Personalizar OpenAPI Schema con más detalles
    openapi_schema["info"]["x-logo"] = {
        "url": "/static/logo.png",
        "altText": "Sistema de Gestión Documental Logo"
    }
    
    openapi_schema["info"]["contact"] = {
        "name": "Equipo de Soporte",
        "url": "https://example.com/support",
        "email": "support@example.com"
    }
    
    openapi_schema["info"]["termsOfService"] = "https://example.com/terms/"
    
    return JSONResponse(openapi_schema)

@router.get("/download-openapi", include_in_schema=False)
async def download_openapi_spec(
    request: Request,
    current_user = Depends(get_current_active_superuser)
):
    """
    Descarga el esquema OpenAPI como archivo JSON (solo admin).
    """
    openapi_schema = get_openapi(
        title=request.app.title,
        version=request.app.version,
        description=request.app.description,
        routes=request.app.routes,
    )
    
    from fastapi.responses import JSONResponse
    resp = JSONResponse(content=openapi_schema)
    resp.headers["Content-Disposition"] = "attachment; filename=openapi-schema.json"
    return resp

@router.get("/", include_in_schema=False)
async def docs_redirect():
    """
    Redirecciona la raíz del API a la documentación.
    """
    return RedirectResponse(url="/api/v1/docs")

# Manejador para OAuth2 redirect
@router.get("/oauth2-redirect", include_in_schema=False)
async def oauth2_redirect():
    return HTMLResponse("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>OAuth2 Redirect</title>
    </head>
    <body>
        <script>
            window.onload = function() {
                window.opener.swaggerUIRedirectOauth2(window.location.href);
                window.close();
            };
        </script>
    </body>
    </html>
    """)