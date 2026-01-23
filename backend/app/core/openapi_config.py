"""
OpenAPI configuration and customization
"""
from fastapi.openapi.utils import get_openapi

from app.core.config import settings


def custom_openapi():
    """Custom OpenAPI schema generator"""
    if hasattr(settings, '_openapi_schema') and settings._openapi_schema:
        return settings._openapi_schema

    openapi_schema = get_openapi(
        title=settings.SERVER_NAME,
        version="1.0.0",
        description="""
        # NouxCubeIA - API de Gestión Documental Potenciada por IA 🧠

        La primera plataforma donde la Inteligencia Artificial transforma radicalmente la gestión documental empresarial.

        ## 🤖 Capacidades de IA Integradas:

        * **Procesamiento Cognitivo**: IA que comprende, analiza y genera insights automáticamente
        * **Agentes Especializados**: Legal, Financiero, Compliance - cada uno experto en su dominio
        * **Chat Inteligente**: Conversa con tus documentos usando procesamiento de lenguaje natural
        * **Extracción Automática**: 99% de precisión en datos estructurados y no estructurados
        * **Predicción y Recomendaciones**: IA que anticipa necesidades y sugiere acciones
        * **Multimodal AI**: Procesa texto, imágenes, tablas con igual eficacia

        ## 🚀 Powered by:
        GPT-4 | Claude | Llama 3.2 | LangChain | Qdrant | Vision AI

        Para más información, consulta el [repositorio del proyecto](https://github.com/tuorganizacion/doc-management).
        """,
        routes=settings._app.routes if hasattr(settings, '_app') else [],
    )

    # Set OpenAPI version explicitly
    openapi_schema["openapi"] = "3.0.2"

    # Store the schema to avoid regenerating it
    if not hasattr(settings, '_openapi_schema'):
        settings._openapi_schema = openapi_schema

    return openapi_schema