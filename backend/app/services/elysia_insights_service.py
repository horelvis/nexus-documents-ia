"""
STUB: ElysiaInsightsService placeholder.

This service was referenced but never implemented. This stub provides
the interface to allow the codebase to compile. The actual functionality
should be delegated to the Weaviate microservice.

TODO: Remove this stub and refactor search_service.py to use weaviate_client directly.
"""
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class ElysiaInsightsService:
    """
    STUB: Placeholder for Elysia insights functionality.

    The actual AI/RAG capabilities are in the Weaviate microservice.
    This stub allows legacy code to compile while awaiting refactoring.
    """

    def __init__(
        self,
        default_tenant: str = "",
        default_user: str = "system"
    ):
        self.default_tenant = default_tenant
        self.default_user = default_user
        logger.debug(f"ElysiaInsightsService stub initialized for tenant: {default_tenant}")

    async def generate_response(
        self,
        query: str,
        tenant_id: str,
        user_id: str,
        doc_ids: Optional[List[str]] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Generate a response using RAG.

        STUB: Returns placeholder. Use Weaviate /emma/query endpoint instead.
        """
        logger.warning("ElysiaInsightsService.generate_response is a STUB - use Weaviate microservice")
        return {
            "answer": "Esta funcionalidad ha sido migrada al microservicio Weaviate. Por favor usa el endpoint /emma/query.",
            "sources": [],
            "status": "stub"
        }

    async def suggest_tags(
        self,
        text: str,
        tenant_id: str,
        user_id: str,
        num_tags: int = 5
    ) -> List[str]:
        """
        Suggest tags for text.

        STUB: Returns generic tags. Should use LLM-based extraction.
        """
        logger.warning("ElysiaInsightsService.suggest_tags is a STUB")
        return ["documento", "texto", "información"]

    async def extract_metadata(
        self,
        text: str,
        tenant_id: str,
        user_id: str
    ) -> Dict[str, str]:
        """
        Extract metadata from text.

        STUB: Returns placeholder metadata.
        """
        logger.warning("ElysiaInsightsService.extract_metadata is a STUB")
        return {
            "título": "Documento",
            "tipo": "texto",
            "status": "stub"
        }

    async def summarize_text(
        self,
        text: str,
        tenant_id: str,
        user_id: str,
        max_length: int = 200
    ) -> str:
        """
        Summarize text.

        STUB: Returns truncated text. Should use LLM summarization.
        """
        logger.warning("ElysiaInsightsService.summarize_text is a STUB")
        if len(text) <= max_length:
            return text
        return text[:max_length] + "..."
