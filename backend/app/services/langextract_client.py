"""
Cliente para el LangExtract microservice (categorización y extracción de entidades).
ACTUALIZADO: Sin mapeos hardcodeados (_TYPE_MAPPING eliminado).
El LLM decide el tipo basándose en análisis inteligente del contenido.
"""
import logging
from typing import Dict, Any, Optional

from app.core.config import settings
from app.clients.base import BaseHTTPClient
from app.clients.exceptions import HTTPClientError

logger = logging.getLogger(__name__)


class LangExtractClient(BaseHTTPClient):
    """Cliente async para llamar a langextract-service con categorización inteligente."""

    # ❌ ELIMINADO: _TYPE_MAPPING hardcodeado
    # El LLM ahora decide el tipo directamente mediante análisis de contenido

    def __init__(self):
        base_url = settings.LANGEXTRACT_SERVICE_URL.rstrip("/")
        super().__init__(
            service_name="langextract",
            base_url=base_url,
            timeout_type="ai",
        )
        # No override provider - let langextract use its own configuration
        self.default_provider = None

    async def categorize_document(
        self,
        text: str,
        filename: Optional[str] = None,
        context: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Categoriza un documento usando detección inteligente del LLM.
        NO usa mapeos - el LLM analiza el contenido y estructura para decidir.

        Args:
            text: Contenido del documento
            filename: Nombre del archivo (opcional, ayuda a la detección)
            context: Contexto adicional (opcional, hints sobre el documento)

        Returns:
            {
                "detected_type": str,
                "confidence": float,
                "reasoning": str,
                "alternative_types": List[Dict],
                "extractions": List[Dict],
                "summary": Dict,
                "error": Optional[str]
            }
        """
        logger.info(f"📋 Solicitando categorización LangExtract: {filename or 'documento'}")

        payload = {
            "text": text[:3000],  # Primeros 3000 chars suficientes para categorización
            "filename": filename,
            "context": context
        }

        try:
            result = await self.post_json("/api/v1/extraction/categorize", json=payload)

            logger.info(
                f"✅ Categorizado como '{result.get('detected_type')}' "
                f"(confianza: {result.get('confidence', 0):.2f})"
            )
            return result

        except HTTPClientError as e:
            error_msg = f"HTTP {e.status_code}: {e.response_body or e.message}"
            logger.error(f"❌ Error en categorización: {error_msg}")
            return {
                "detected_type": "general",
                "confidence": 0.0,
                "reasoning": f"Error en servicio: {error_msg}",
                "error": error_msg
            }
        except Exception as exc:
            logger.error(f"❌ Error inesperado en categorización: {exc}")
            return {
                "detected_type": "general",
                "confidence": 0.0,
                "reasoning": f"Error: {str(exc)}",
                "error": str(exc)
            }

    async def extract_entities(
        self,
        text: str,
        document_type: str = "general",
        filename: Optional[str] = None,
        provider: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Extrae entidades estructuradas de un documento.

        Args:
            text: Contenido del documento
            document_type: Tipo de documento REAL (sin mapeos intermedios)
            filename: Nombre del archivo (opcional)
            provider: Provider LLM a usar (opcional, usa default si no se especifica)

        Returns:
            {
                "success": bool,
                "extractions": List[Dict],
                "summary": Dict,
                "total_extractions": int,
                "document_type": str,
                "provider": str,
                "visualization_html": Optional[str],
                "error": Optional[str]
            }
        """
        logger.info(
            f"📝 LangExtract extracción ({document_type}) - "
            f"Provider: {provider or 'service-default'}"
        )

        # Build payload - only include provider if explicitly passed
        payload = {
            "text": text[:50000],  # Limitar payload a 50K chars
            "document_type": document_type,  # ✅ Tipo directo, sin mapeo
            "filename": filename,
        }
        # Only pass provider if explicitly specified, otherwise let service use its config
        if provider:
            payload["provider"] = provider.lower()

        try:
            result = await self.post_json("/api/v1/extraction/extract", json=payload)

            extractions = result.get("extractions") or []
            logger.info(f"✅ Extraídas {len(extractions)} entidades de tipo '{document_type}'")

            # Formatear entidades para compatibilidad con código existente
            # NOTA: Usar "or {}" porque result.get("metadata", {}) devuelve None si metadata es null
            metadata = result.get("metadata") or {}
            used_provider = metadata.get("provider", "unknown")
            used_model = metadata.get("model", "unknown")

            formatted_entities = []
            for extraction in extractions:
                attributes = extraction.get("attributes") or {}
                formatted_entities.append({
                    "name": extraction.get("text", ""),
                    "type": extraction.get("class", "other"),
                    "role": attributes.get("role", ""),
                    "context": attributes.get("type", ""),
                    "metadata": {
                        "extraction_method": "langextract",
                        "provider": used_provider,
                        "model": used_model,
                        "confidence": attributes.get("confidence", 0.8),
                        "source_indices": extraction.get("source_indices"),
                        "document_type": document_type,
                    },
                })

            return {
                "success": True,
                "extractions": formatted_entities,
                "summary": result.get("summary", {}),
                "total_extractions": len(formatted_entities),
                "document_type": document_type,
                "provider": used_provider,
                "visualization_html": result.get("visualization_html"),
            }

        except HTTPClientError as e:
            error_msg = f"HTTP {e.status_code}: {e.response_body or e.message}"
            logger.error(f"❌ Error en extracción: {error_msg}")
            return {
                "success": False,
                "error": error_msg,
                "extractions": [],
                "document_type": document_type,
            }
        except Exception as exc:
            logger.error(f"❌ Error inesperado en extracción: {exc}")
            return {
                "success": False,
                "error": str(exc),
                "extractions": [],
                "document_type": document_type,
            }


# Instancia singleton
langextract_client = LangExtractClient()
