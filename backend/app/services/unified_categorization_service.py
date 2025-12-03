"""
Servicio unificado de categorización de documentos.
Centraliza toda la lógica de categorización usando LangExtract como motor.
NO usa mapeos hardcodeados - el LLM decide basándose en análisis de contenido.
"""
import logging
from typing import Dict, Any, Optional
import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class UnifiedCategorizationService:
    """
    Servicio que orquesta la categorización inteligente de documentos.
    Delega la detección de tipo al servicio LangExtract especializado.
    """

    def __init__(self):
        self.langextract_url = settings.LANGEXTRACT_SERVICE_URL.rstrip("/")
        self.api_key = settings.MICROSERVICES_API_KEY
        self.timeout = httpx.Timeout(90.0, connect=5.0)

    async def categorize_document(
        self,
        text: str,
        filename: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        extract_entities: bool = True
    ) -> Dict[str, Any]:
        """
        Categoriza un documento de forma inteligente usando LangExtract.

        Args:
            text: Contenido del documento
            filename: Nombre del archivo (ayuda a la detección)
            metadata: Metadata adicional del documento
            extract_entities: Si debe extraer entidades además de categorizar

        Returns:
            {
                "success": bool,
                "category": str,
                "confidence": float,
                "reasoning": str,
                "alternative_types": List[Dict],
                "extractions": List[Dict],  # si extract_entities=True
                "summary": Dict,             # si extract_entities=True
                "method": str,
                "error": Optional[str]
            }
        """
        logger.info(f"🔍 Categorizando documento: {filename or 'Sin nombre'}")

        try:
            # 1. Construir contexto opcional para ayudar a la detección
            context = self._build_context(text, filename, metadata)

            # 2. Llamar a LangExtract para categorización inteligente
            categorization = await self._call_langextract_categorize(
                text=text,
                filename=filename,
                context=context
            )

            if not categorization.get("detected_type"):
                logger.warning("⚠️  LangExtract no pudo detectar tipo de documento")
                return {
                    "success": False,
                    "error": "No se pudo detectar el tipo de documento",
                    "category": "general",
                    "confidence": 0.0,
                    "method": "unified_categorization_failed"
                }

            detected_type = categorization["detected_type"]
            confidence = categorization.get("confidence", 0.0)

            logger.info(
                f"✅ Categorizado como '{detected_type}' "
                f"(confianza: {confidence:.2f})"
            )

            # 3. Validar y ajustar categorización si es necesario
            validated = self._validate_categorization(categorization, text)

            # 4. Si la confianza es suficiente y se requieren entidades, extraerlas
            extractions = []
            summary = {}
            visualization_html = None

            if extract_entities and validated["confidence"] >= 0.5:
                logger.info(f"📝 Extrayendo entidades para tipo '{validated['category']}'")
                entity_result = await self._call_langextract_extract(
                    text=text,
                    document_type=validated["category"],
                    filename=filename
                )
                extractions = entity_result.get("extractions", [])
                summary = entity_result.get("summary", {})
                visualization_html = entity_result.get("visualization_html")
                logger.info(f"✅ Extraídas {len(extractions)} entidades")
                if visualization_html:
                    logger.info(f"✅ Generado visualization_html")

            # 5. Retornar resultado completo
            return {
                "success": True,
                "category": validated["category"],
                "confidence": validated["confidence"],
                "reasoning": validated["reasoning"],
                "alternative_types": validated.get("alternative_types", []),
                "extractions": extractions,
                "summary": summary,
                "visualization_html": visualization_html,
                "method": "langextract_unified_categorization",
                "metadata": {
                    "service": "unified_categorization",
                    "langextract_version": "1.0",
                    "context_used": bool(context),
                    "entities_extracted": len(extractions)
                }
            }

        except Exception as e:
            logger.error(f"❌ Error en categorización unificada: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "category": "general",
                "confidence": 0.0,
                "method": "unified_categorization_error",
                "reasoning": f"Error durante categorización: {str(e)}"
            }

    def _build_context(
        self,
        text: str,
        filename: Optional[str],
        metadata: Optional[Dict[str, Any]]
    ) -> str:
        """
        Construye contexto adicional para ayudar al LLM en la detección.
        Analiza rápidamente el texto para dar hints sin hacer detección completa.
        """
        hints = []
        text_lower = text.lower()[:1000]  # Solo primeros 1000 chars para hints

        # Detectar idioma aproximado
        spanish_markers = ["ñ", "á", "é", "í", "ó", "ú", "modelo", "nómina", "empresa"]
        if sum(1 for marker in spanish_markers if marker in text_lower) >= 3:
            hints.append("documento en español")

        # Detectar posible contexto laboral
        labor_markers = ["trabajador", "empresa", "salario", "contrato", "nómina", "seguridad social"]
        if sum(1 for marker in labor_markers if marker in text_lower) >= 2:
            hints.append("posible documento laboral")

        # Detectar posible contexto fiscal/tributario
        fiscal_markers = ["modelo", "hacienda", "irpf", "iva", "trimestre", "ejercicio", "declaración"]
        if sum(1 for marker in fiscal_markers if marker in text_lower) >= 2:
            hints.append("posible documento fiscal/tributario")

        # Información del filename
        if filename:
            hints.append(f"archivo: {filename}")

        # Información de metadata
        if metadata:
            if metadata.get("language"):
                hints.append(f"idioma: {metadata['language']}")
            if metadata.get("original_category"):
                hints.append(f"categoría previa: {metadata['original_category']}")

        return ", ".join(hints) if hints else ""

    async def _call_langextract_categorize(
        self,
        text: str,
        filename: Optional[str],
        context: Optional[str]
    ) -> Dict[str, Any]:
        """Llama al endpoint de categorización de LangExtract"""
        url = f"{self.langextract_url}/api/v1/extraction/categorize"

        payload = {
            "text": text[:3000],  # Limitar para categorización (suficiente para análisis)
            "filename": filename,
            "context": context
        }

        headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json"
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                logger.debug(f"📞 Llamando a LangExtract categorize: {url}")
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                result = response.json()
                logger.debug(f"📥 Respuesta LangExtract: {result.get('detected_type')} (conf: {result.get('confidence')})")
                return result
        except httpx.HTTPError as e:
            logger.error(f"❌ Error HTTP llamando a LangExtract categorize: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ Error inesperado en categorización: {e}")
            raise

    async def _call_langextract_extract(
        self,
        text: str,
        document_type: str,
        filename: Optional[str]
    ) -> Dict[str, Any]:
        """Llama al endpoint de extracción de LangExtract"""
        url = f"{self.langextract_url}/api/v1/extraction/extract"

        payload = {
            "text": text,
            "document_type": document_type,
            "filename": filename
        }

        headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json"
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                logger.debug(f"📞 Llamando a LangExtract extract: {url}")
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                result = response.json()
                logger.debug(f"📥 Extracción completada: {len(result.get('extractions', []))} entidades")
                return result
        except httpx.HTTPError as e:
            logger.error(f"❌ Error HTTP llamando a LangExtract extract: {e}")
            # No fallar si la extracción falla, solo retornar vacío
            return {"extractions": [], "summary": {}}
        except Exception as e:
            logger.error(f"❌ Error inesperado en extracción: {e}")
            return {"extractions": [], "summary": {}}

    def _validate_categorization(
        self,
        categorization: Dict[str, Any],
        text: str
    ) -> Dict[str, Any]:
        """
        Valida y ajusta el resultado de categorización.
        Puede reducir confianza o cambiar a 'general' si algo no cuadra.
        """
        detected_type = categorization.get("detected_type", "general")
        confidence = categorization.get("confidence", 0.0)
        reasoning = categorization.get("reasoning", "")

        # Si la confianza es muy baja, marcar como general
        if confidence < 0.3:
            logger.warning(
                f"⚠️  Confianza muy baja ({confidence:.2f}) para '{detected_type}', "
                f"marcando como 'general'"
            )
            return {
                "category": "general",
                "confidence": 0.5,
                "reasoning": (
                    f"Confianza insuficiente en detección original de '{detected_type}' "
                    f"({confidence:.2f}). Clasificado como general por seguridad."
                ),
                "alternative_types": categorization.get("alternative_types", [])
            }

        # Validaciones adicionales futuras pueden agregarse aquí
        # Por ejemplo: verificar que tipos fiscales tengan números de modelo

        return {
            "category": detected_type,
            "confidence": confidence,
            "reasoning": reasoning,
            "alternative_types": categorization.get("alternative_types", [])
        }


# Instancia singleton
_categorization_service = None


def get_categorization_service() -> UnifiedCategorizationService:
    """Obtener instancia singleton del servicio de categorización unificado"""
    global _categorization_service
    if _categorization_service is None:
        _categorization_service = UnifiedCategorizationService()
    return _categorization_service
