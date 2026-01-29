"""
Knowledge Source Router - Fast classification of knowledge sources.

Uses semantic embeddings to classify queries into knowledge sources:
- TENANT_DOCUMENTS: User's own documents (contracts, invoices, reports)
- PUBLIC_KNOWLEDGE: Public legislation, BOE, labor statutes, tax laws
- HYBRID: Both sources needed (compare my contract with the law)

OPTIMIZATION: Uses FastEmbedEncoder (ONNX Runtime) for ~1-3ms latency.
This is Stage 1 of the 2-stage routing strategy (semantic fast-path).

Reference: https://github.com/aurelio-labs/semantic-router
"""
import os

# IMPORTANT: Set environment variable BEFORE importing semantic_router
os.environ.setdefault('SEMANTIC_ROUTER_LOG_LEVEL', 'ERROR')

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class KnowledgeSource(str, Enum):
    """
    Knowledge source classification for RAG routing.

    Determines where to search for information:
    - TENANT_DOCUMENTS: Search in user's uploaded documents (Weaviate)
    - PUBLIC_KNOWLEDGE: Search in public legislation/BOE (legal_search tool)
    - HYBRID: Search in both sources (compare user docs against law)
    """
    TENANT_DOCUMENTS = "tenant_documents"
    PUBLIC_KNOWLEDGE = "public_knowledge"
    HYBRID = "hybrid"


@dataclass
class KnowledgeSourceResult:
    """Result of knowledge source classification."""
    source: KnowledgeSource
    confidence: float
    route_name: Optional[str] = None  # Name of matched route (for debugging)

    @property
    def needs_tenant_search(self) -> bool:
        """Whether to search in tenant documents."""
        return self.source in [KnowledgeSource.TENANT_DOCUMENTS, KnowledgeSource.HYBRID]

    @property
    def needs_public_search(self) -> bool:
        """Whether to search in public knowledge (legal_search)."""
        return self.source in [KnowledgeSource.PUBLIC_KNOWLEDGE, KnowledgeSource.HYBRID]


class SemanticKnowledgeRouter:
    """
    Fast knowledge source classification using semantic embeddings.

    Stage 1 of 2-stage routing strategy:
    - High confidence (>=0.9): Use this result directly (fast-path)
    - Low confidence (<0.9): Fall back to SetFit ML classifier

    Classifies queries into:
    - TENANT_DOCUMENTS: Queries about user's own documents
    - PUBLIC_KNOWLEDGE: Queries about legislation, laws, regulations
    - HYBRID: Queries comparing user docs against legal standards

    Uses FastEmbed (ONNX Runtime) for ultra-low latency embeddings.
    Latency: ~1-3ms per classification.
    """

    # Confidence threshold for fast-path (skip ML fallback)
    FAST_PATH_THRESHOLD = 0.9

    def __init__(self):
        self._route_layer = None
        self._encoder = None
        self._initialized = False

    def initialize(self):
        """Initialize the knowledge source router with routes."""
        if self._initialized:
            return

        try:
            from semantic_router import Route
            from semantic_router.routers import SemanticRouter as RouterLayer

            # Try FastEmbed first (ONNX optimized, ~1-3ms latency)
            try:
                from semantic_router.encoders import FastEmbedEncoder
                logger.info("Loading FastEmbed encoder for KnowledgeSourceRouter...")
                self._encoder = FastEmbedEncoder(model_name="sentence-transformers/all-MiniLM-L6-v2")
                logger.info("✅ KnowledgeSourceRouter using FastEmbedEncoder (ONNX) - ~1-3ms latency")
            except ImportError:
                from semantic_router.encoders import HuggingFaceEncoder
                logger.warning("⚠️ FastEmbed not available, falling back to HuggingFaceEncoder (~10ms)")
                self._encoder = HuggingFaceEncoder(name="sentence-transformers/all-MiniLM-L6-v2")

            # Define knowledge source routes with multi-language utterances
            tenant_documents = Route(
                name="tenant_documents",
                utterances=[
                    # === Spanish - User's Own Documents ===
                    "Busca en mis documentos", "Analiza mi contrato",
                    "Qué dice mi factura", "Revisa mi archivo",
                    "Documentos de mi empresa", "Mis contratos",
                    "Mi nómina", "Facturas de este mes",
                    "En mi contrato de arrendamiento", "Mi acuerdo de confidencialidad",
                    "Revisa mis documentos", "En mis archivos",
                    "Qué tengo en mis documentos", "Analiza mi documento",
                    "Busca en mis facturas", "En mi expediente",
                    "En mi contrato dice", "Mi documento de trabajo",
                    "Los contratos que tengo", "Mis informes",
                    "Mi factura de proveedor", "Documentos que subí",
                    "Archivos que he cargado", "Mis PDFs",
                    "En el contrato que firmé", "Mi última factura",

                    # === English - User's Own Documents ===
                    "Search my documents", "Analyze my contract",
                    "What does my invoice say", "Review my file",
                    "My company documents", "My contracts",
                    "My payroll", "This month's invoices",
                    "In my lease agreement", "My NDA",
                    "Check my documents", "In my files",
                    "What do I have in my documents", "Analyze my document",
                    "Search my invoices", "In my records",
                    "My employment contract", "My work document",
                    "Contracts I have", "My reports",
                    "My vendor invoice", "Documents I uploaded",
                    "Files I've uploaded", "My PDFs",

                    # === French ===
                    "Cherche dans mes documents", "Analyse mon contrat",
                    "Que dit ma facture", "Révise mon fichier",
                    "Mes documents d'entreprise", "Mes contrats",
                ]
            )

            public_knowledge = Route(
                name="public_knowledge",
                utterances=[
                    # === Spanish - Legal/BOE/Legislation ===
                    "Según la ley", "El estatuto de los trabajadores dice",
                    "Qué dice el BOE", "Artículo del código civil",
                    "Derecho laboral", "Normativa fiscal", "Legislación vigente",
                    "Días de vacaciones por ley", "Derechos del trabajador",
                    "Cuántos días de vacaciones corresponden",
                    "Ley de protección de datos", "RGPD", "LOPDGDD",
                    "Derecho a indemnización", "Despido improcedente ley",
                    "Qué dice la normativa", "Según el estatuto",
                    "La ley establece", "Marco legal", "Regulación vigente",
                    "Código de comercio", "Ley de sociedades",
                    "Normativa laboral", "Qué dice la ley sobre",
                    "Regulación fiscal", "Impuestos según la ley",
                    "Convenio colectivo general", "Ley de arrendamientos",
                    "LAU dice", "Estatuto de los trabajadores",
                    "Derechos ARCO", "Ley orgánica de protección de datos",
                    "Indemnización legal", "Preaviso legal",
                    "Período de prueba legal", "Jornada máxima legal",
                    "Salario mínimo interprofesional", "SMI actual",
                    "Horas extras máximas", "Descanso semanal obligatorio",

                    # === English - Legal/Regulations ===
                    "According to the law", "The labor statute says",
                    "Legal requirements", "Tax regulations",
                    "What does the law say", "Legislation in force",
                    "Vacation days by law", "Worker rights by law",
                    "Data protection law", "GDPR", "Legal framework",
                    "Severance according to law", "Wrongful termination law",
                    "What does the regulation say", "According to the statute",
                    "The law establishes", "Current regulation",
                    "Commercial code", "Company law",
                    "Labor regulations", "What does the law say about",
                    "Tax regulation", "Taxes according to law",
                    "Collective bargaining agreement", "Lease law",
                    "Minimum wage", "Maximum working hours",

                    # === French ===
                    "Selon la loi", "Le code du travail dit",
                    "Exigences légales", "Réglementation fiscale",
                    "Que dit la loi", "Législation en vigueur",
                ]
            )

            hybrid = Route(
                name="hybrid",
                utterances=[
                    # === Spanish - Compare User Docs vs Law ===
                    "Compara mi contrato con la ley",
                    "Mi contrato cumple con el estatuto",
                    "Revisa si mi documento es legal",
                    "Analiza mi contrato según la normativa",
                    "Cumple mi nómina con el convenio",
                    "Mi contrato respeta la ley",
                    "Es legal mi contrato",
                    "Verifica que mi documento cumpla",
                    "Contrasta mi contrato con la legislación",
                    "Mi acuerdo cumple con el RGPD",
                    "Mi empresa cumple con la normativa",
                    "Revisa mi contrato contra la ley",
                    "Mi factura cumple con hacienda",
                    "Cumple mi nómina con el salario mínimo",
                    "Mi contrato de trabajo es legal",
                    "Verifica mi documento contra la regulación",
                    "Compara mis cláusulas con la ley",
                    "Están mis documentos al día con la ley",
                    "Mi política cumple con LOPDGDD",
                    "Audita mi contrato contra la normativa",

                    # === English - Compare User Docs vs Law ===
                    "Compare my contract with the law",
                    "Does my contract comply with regulations",
                    "Check if my document is legal",
                    "Analyze my contract against regulations",
                    "Does my payroll comply with the agreement",
                    "My contract respects the law",
                    "Is my contract legal",
                    "Verify my document complies",
                    "Contrast my contract with legislation",
                    "Does my agreement comply with GDPR",
                    "Is my company compliant with regulations",
                    "Review my contract against the law",
                    "Does my invoice comply with tax law",
                    "Verify my document against regulations",
                    "Compare my clauses with the law",
                    "Are my documents up to date with the law",
                    "Audit my contract against regulations",

                    # === French ===
                    "Compare mon contrat avec la loi",
                    "Mon contrat est-il conforme",
                    "Vérifie que mon document respecte la loi",
                    "Analyse mon contrat selon la réglementation",
                ]
            )

            routes = [tenant_documents, public_knowledge, hybrid]
            self._route_layer = RouterLayer(
                encoder=self._encoder,
                routes=routes,
                auto_sync='local'  # Required for semantic-router 0.1.2
            )
            self._initialized = True
            logger.info("✅ SemanticKnowledgeRouter initialized with 3 knowledge source routes")

        except ImportError as e:
            logger.error(f"Failed to import semantic-router: {e}")
            logger.error("Install with: pip install semantic-router")
            raise
        except Exception as e:
            logger.error(f"Failed to initialize SemanticKnowledgeRouter: {e}")
            raise

    def classify(self, query: str) -> KnowledgeSourceResult:
        """
        Classify a query into a knowledge source.

        Args:
            query: User's query text

        Returns:
            KnowledgeSourceResult with source, confidence, and route_name
        """
        if not self._initialized:
            self.initialize()

        try:
            result = self._route_layer(query)

            if result is None or result.name is None:
                # No route matched - default to TENANT_DOCUMENTS (user's docs)
                logger.debug(f"KnowledgeSource: No route matched -> TENANT_DOCUMENTS (default)")
                return KnowledgeSourceResult(
                    source=KnowledgeSource.TENANT_DOCUMENTS,
                    confidence=0.5,  # Low confidence triggers ML fallback
                    route_name=None
                )

            route_name = result.name.lower()

            # Map route name to knowledge source
            source_map = {
                "tenant_documents": KnowledgeSource.TENANT_DOCUMENTS,
                "public_knowledge": KnowledgeSource.PUBLIC_KNOWLEDGE,
                "hybrid": KnowledgeSource.HYBRID,
            }

            source = source_map.get(route_name, KnowledgeSource.TENANT_DOCUMENTS)

            # semantic-router returns similarity score (0-1)
            # Higher is better match
            confidence = getattr(result, 'similarity', 0.8)

            logger.info(
                f"🎯 KnowledgeSource: {source.value} "
                f"(conf={confidence:.2f}, route={route_name}) "
                f"for: '{query[:50]}...'"
            )

            return KnowledgeSourceResult(
                source=source,
                confidence=confidence,
                route_name=route_name
            )

        except Exception as e:
            logger.warning(f"KnowledgeSourceRouter classification failed: {e}")
            # Default to TENANT_DOCUMENTS with low confidence
            return KnowledgeSourceResult(
                source=KnowledgeSource.TENANT_DOCUMENTS,
                confidence=0.3,
                route_name=None
            )

    def classify_with_threshold(
        self,
        query: str,
        threshold: float = None
    ) -> Tuple[KnowledgeSourceResult, bool]:
        """
        Classify with confidence threshold check.

        Args:
            query: User's query text
            threshold: Confidence threshold (defaults to FAST_PATH_THRESHOLD)

        Returns:
            Tuple of (result, is_confident) where is_confident indicates
            whether the result meets the threshold for fast-path.
        """
        if threshold is None:
            threshold = self.FAST_PATH_THRESHOLD

        result = self.classify(query)
        is_confident = result.confidence >= threshold

        return result, is_confident


# =============================================================================
# SINGLETON PATTERN
# =============================================================================

_knowledge_router: Optional[SemanticKnowledgeRouter] = None


def get_knowledge_source_router() -> SemanticKnowledgeRouter:
    """
    Get or create the knowledge source router singleton.

    The router is initialized lazily on first use and reused
    for subsequent calls to avoid reloading the encoder.
    """
    global _knowledge_router
    if _knowledge_router is None:
        _knowledge_router = SemanticKnowledgeRouter()
        _knowledge_router.initialize()
    return _knowledge_router


def classify_knowledge_source(query: str) -> KnowledgeSourceResult:
    """
    Convenience function to classify a query's knowledge source.

    Args:
        query: User's query text

    Returns:
        KnowledgeSourceResult with source and confidence
    """
    router = get_knowledge_source_router()
    return router.classify(query)


def preload_knowledge_source_router() -> None:
    """
    Preload the knowledge source router at service startup.

    This initializes the router and loads the encoder model,
    preventing delay on first user request.
    """
    import time
    start = time.perf_counter()

    logger.info("🚀 Preloading KnowledgeSourceRouter...")

    try:
        router = get_knowledge_source_router()
        elapsed = time.perf_counter() - start
        logger.info(f"✅ KnowledgeSourceRouter preloaded in {elapsed:.2f}s")
    except Exception as e:
        logger.error(f"❌ Failed to preload KnowledgeSourceRouter: {e}")
        logger.warning("⚠️ First request will experience delay while loading router")
