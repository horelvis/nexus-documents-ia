"""
Semantic Router for fast intent classification.

Uses embeddings instead of LLM calls for ~10ms latency.
This replaces the keyword-based and LLM-based pattern detection
with a more robust semantic similarity approach.

Reference: https://github.com/aurelio-labs/semantic-router
Version: 0.1.2 (uses SemanticRouter, not RouteLayer)
"""
import os

# IMPORTANT: Set environment variable BEFORE importing semantic_router
# The library configures its colorlog logger at import time and respects this var
os.environ.setdefault('SEMANTIC_ROUTER_LOG_LEVEL', 'ERROR')

from typing import Optional
import logging

logger = logging.getLogger(__name__)

# Import OrchestrationPattern from base (avoid circular import)
from enum import Enum


class OrchestrationPattern(str, Enum):
    """Available orchestration patterns."""
    HANDOFF = "handoff"      # Default: LLM decides via .as_tool()
    SEQUENTIAL = "sequential"  # Pipeline: A -> B -> C
    CONCURRENT = "concurrent"  # Parallel: A | B | C


class SemanticPatternRouter:
    """
    Fast pattern classification using semantic embeddings.

    Classifies user queries into orchestration patterns:
    - CONVERSATIONAL -> HANDOFF (preserves memory via AgentThread)
    - SEQUENTIAL (pipeline: A -> B -> C)
    - CONCURRENT (parallel: A | B | C)
    - HANDOFF (default, simple queries)

    Uses all-MiniLM-L6-v2 for local embeddings - no API needed.
    Latency: ~10ms per classification.
    """

    def __init__(self):
        self._route_layer = None
        self._encoder = None
        self._initialized = False

    def initialize(self):
        """Initialize the semantic router with routes."""
        if self._initialized:
            return

        try:
            from semantic_router import Route
            from semantic_router.encoders import HuggingFaceEncoder
            from semantic_router.routers import SemanticRouter as RouterLayer

            # Local encoder - no API needed, uses sentence-transformers
            logger.info("Loading HuggingFace encoder for Semantic Router...")
            self._encoder = HuggingFaceEncoder(name="sentence-transformers/all-MiniLM-L6-v2")

            # Define routes with multi-language utterances
            # Each route captures semantic similarity, so queries similar to these
            # examples will be routed appropriately even in other languages
            conversational = Route(
                name="conversational",
                utterances=[
                    # === Greetings ===
                    # English
                    "Hello", "Hi there", "Hey", "Good morning", "Good afternoon",
                    "Good evening", "Hi Emma", "Hello Emma",
                    # Spanish
                    "Hola", "Buenos dias", "Buenas tardes", "Buenas noches",
                    "Hola Emma", "Que tal",
                    # French
                    "Bonjour", "Bonsoir", "Salut", "Bonjour Emma",
                    # German
                    "Hallo", "Guten Tag", "Guten Morgen",
                    # Portuguese
                    "Ola", "Bom dia", "Boa tarde",

                    # === Identity/Memory Questions ===
                    # English
                    "What is my name?", "Who am I?", "Do you remember me?",
                    "What did I say?", "Do you know who I am?",
                    "Can you remember what I told you?",
                    # Spanish
                    "Como me llamo?", "Quien soy?", "Te acuerdas de mi?",
                    "Que te dije?", "Recuerdas mi nombre?",
                    # French
                    "Comment je m'appelle?", "Tu te souviens de moi?",
                    "Qui suis-je?", "Tu connais mon nom?",

                    # === Introductions ===
                    # English
                    "My name is", "I am", "Call me", "I'm called",
                    # Spanish
                    "Me llamo", "Mi nombre es", "Soy", "Llamame",
                    # French
                    "Je m'appelle", "Je suis", "Mon nom est",

                    # === Thanks/Farewells ===
                    # English
                    "Thank you", "Thanks", "Goodbye", "Bye", "See you later",
                    "Thanks Emma", "Thank you Emma",
                    # Spanish
                    "Gracias", "Adios", "Hasta luego", "Nos vemos",
                    "Muchas gracias",
                    # French
                    "Merci", "Au revoir", "A bientot", "Merci beaucoup",

                    # === Help Requests (simple) ===
                    "Help me", "Can you help?", "I need help",
                    "Ayudame", "Necesito ayuda",
                    "Aidez-moi", "J'ai besoin d'aide",
                ]
            )

            sequential = Route(
                name="sequential",
                utterances=[
                    # === English ===
                    "First analyze, then summarize",
                    "Step by step analysis",
                    "First search, then analyze, finally summarize",
                    "Analyze the document and then give me a summary",
                    "Start by finding the document, then analyze it",
                    "Do this step by step",
                    "First extract the data, then process it",

                    # === Spanish ===
                    "Primero analiza, despues resume",
                    "Paso a paso",
                    "Analiza y luego dame un resumen",
                    "Primero busca el documento, despues analizalo",
                    "Hazlo paso a paso",
                    "Primero extrae, luego procesa",
                    "Empieza por buscar, luego analiza",

                    # === French ===
                    "D'abord analyse, ensuite resume",
                    "Etape par etape",
                    "Analyse puis resume",
                    "Commence par chercher, puis analyse",
                ]
            )

            concurrent = Route(
                name="concurrent",
                utterances=[
                    # === English ===
                    "Analyze from legal and fiscal perspectives",
                    "Compare from multiple angles",
                    "Get opinions from all areas",
                    "Analyze from legal, fiscal, and labor perspectives",
                    "Review from all perspectives simultaneously",
                    "Give me analysis from different viewpoints",
                    "Parallel analysis from multiple experts",

                    # === Spanish ===
                    "Analiza desde perspectiva legal y fiscal",
                    "Desde el punto de vista legal, fiscal y laboral",
                    "Compara todas las areas",
                    "Dame analisis desde multiples perspectivas",
                    "Revisa desde todos los angulos",
                    "Analisis paralelo de diferentes areas",
                    "Perspectiva legal y perspectiva fiscal",

                    # === French ===
                    "Analyse des perspectives legale et fiscale",
                    "Compare tous les domaines",
                    "Analyse de plusieurs points de vue",
                    "Du point de vue juridique et fiscal",
                ]
            )

            # HANDOFF is the default - queries that don't match any route
            # will be routed to HANDOFF automatically

            routes = [conversational, sequential, concurrent]
            self._route_layer = RouterLayer(
                encoder=self._encoder,
                routes=routes,
                auto_sync='local'  # Required for semantic-router 0.1.2 to index embeddings
            )
            self._initialized = True
            logger.info("SemanticPatternRouter initialized with 3 routes")

        except ImportError as e:
            logger.error(f"Failed to import semantic-router: {e}")
            logger.error("Install with: pip install semantic-router")
            raise
        except Exception as e:
            logger.error(f"Failed to initialize SemanticPatternRouter: {e}")
            raise

    def classify(self, query: str) -> OrchestrationPattern:
        """
        Classify a query into an orchestration pattern.

        Args:
            query: User's query text

        Returns:
            OrchestrationPattern (HANDOFF, SEQUENTIAL, or CONCURRENT)
        """
        if not self._initialized:
            self.initialize()

        try:
            result = self._route_layer(query)

            if result is None or result.name is None:
                logger.debug(f"Semantic: No route matched -> HANDOFF (default)")
                return OrchestrationPattern.HANDOFF

            route_name = result.name.lower()

            if route_name == "conversational":
                # CONVERSATIONAL maps to HANDOFF to preserve AgentThread memory
                logger.info(f"Semantic: CONVERSATIONAL -> HANDOFF (memory preservation)")
                return OrchestrationPattern.HANDOFF
            elif route_name == "sequential":
                logger.info(f"Semantic: SEQUENTIAL")
                return OrchestrationPattern.SEQUENTIAL
            elif route_name == "concurrent":
                logger.info(f"Semantic: CONCURRENT")
                return OrchestrationPattern.CONCURRENT
            else:
                logger.debug(f"Semantic: Unknown route '{route_name}' -> HANDOFF")
                return OrchestrationPattern.HANDOFF

        except Exception as e:
            logger.warning(f"Semantic Router classification failed: {e}")
            return OrchestrationPattern.HANDOFF


# Singleton instance for reuse across requests
_router: Optional[SemanticPatternRouter] = None


def get_semantic_router() -> SemanticPatternRouter:
    """
    Get or create the semantic router singleton.

    The router is initialized lazily on first use and reused
    for subsequent calls to avoid reloading the encoder.
    """
    global _router
    if _router is None:
        _router = SemanticPatternRouter()
        _router.initialize()
    return _router


def classify_pattern(query: str) -> OrchestrationPattern:
    """
    Convenience function to classify a query pattern.

    Args:
        query: User's query text

    Returns:
        OrchestrationPattern
    """
    router = get_semantic_router()
    return router.classify(query)


# =============================================================================
# SEMANTIC DOMAIN ROUTER - Classifies queries by legal/business domain
# =============================================================================

class SemanticDomainRouter:
    """
    Domain classification using semantic embeddings.

    Classifies user queries into legal/business domains to select
    the appropriate specialist agents:
    - contract → contract_agent
    - labor → labor_agent
    - fiscal → fiscal_agent
    - compliance → compliance_agent (GDPR/RGPD)
    - privacy → privacy_agent (LOPDGDD)
    - search → search_agent
    - summary → summarizer_agent
    - general → analyst_agent

    Uses the same all-MiniLM-L6-v2 encoder as PatternRouter.
    Latency: ~10ms per classification.
    """

    def __init__(self):
        self._route_layer = None
        self._encoder = None
        self._initialized = False

    def initialize(self):
        """Initialize the domain router with routes."""
        if self._initialized:
            return

        try:
            from semantic_router import Route
            from semantic_router.encoders import HuggingFaceEncoder
            from semantic_router.routers import SemanticRouter as RouterLayer

            # Reuse encoder if pattern router already loaded it
            logger.info("Loading HuggingFace encoder for Domain Router...")
            self._encoder = HuggingFaceEncoder(name="sentence-transformers/all-MiniLM-L6-v2")

            # Define domain routes with multi-language utterances
            contract = Route(
                name="contract",
                utterances=[
                    # English
                    "Analyze the contract", "Contract clause", "Terms and conditions",
                    "Contract obligations", "Review the agreement", "NDA analysis",
                    "Service level agreement", "Contract risks", "Lease agreement",
                    "What does clause 5 say", "Contract termination",
                    # Spanish
                    "Analiza el contrato", "Cláusula del contrato", "Términos y condiciones",
                    "Obligaciones contractuales", "Revisar el acuerdo", "Análisis de NDA",
                    "Acuerdo de nivel de servicio", "Riesgos del contrato",
                    "Qué dice la cláusula", "Rescisión del contrato",
                    "Contrato de arrendamiento", "Contrato de trabajo",
                    # French
                    "Analyser le contrat", "Clause contractuelle", "Termes et conditions",
                    "Obligations contractuelles", "Accord de niveau de service",
                ]
            )

            labor = Route(
                name="labor",
                utterances=[
                    # English
                    "Employment law", "Wrongful termination", "Payroll issues",
                    "Worker rights", "Collective agreement", "Labor dispute",
                    "Severance package", "Working hours", "Employee benefits",
                    "Workplace harassment", "Union negotiations",
                    # Spanish
                    "Derecho laboral", "Despido improcedente", "Nómina",
                    "Derechos del trabajador", "Convenio colectivo", "Conflicto laboral",
                    "Indemnización", "Jornada laboral", "Prestaciones",
                    "Acoso laboral", "Negociación sindical", "Estatuto de los trabajadores",
                    "Despido", "Finiquito", "Baja laboral",
                    # French
                    "Droit du travail", "Licenciement abusif", "Salaire",
                    "Droits des travailleurs", "Convention collective",
                ]
            )

            fiscal = Route(
                name="fiscal",
                utterances=[
                    # English
                    "Tax analysis", "Income tax", "Corporate tax", "Tax deductions",
                    "VAT calculation", "Tax compliance", "Tax returns",
                    "Capital gains", "Tax planning", "Tax audit",
                    # Spanish
                    "Análisis fiscal", "Impuesto sobre la renta", "Impuesto de sociedades",
                    "Deducciones fiscales", "Cálculo de IVA", "Cumplimiento fiscal",
                    "Declaración de la renta", "Ganancias de capital", "IRPF",
                    "Hacienda", "Tributación", "Impuestos", "Modelo 303",
                    # French
                    "Analyse fiscale", "Impôt sur le revenu", "TVA",
                    "Déductions fiscales", "Déclaration d'impôts",
                ]
            )

            compliance = Route(
                name="compliance",
                utterances=[
                    # English
                    "GDPR compliance", "Data protection regulation", "Privacy policy review",
                    "Data breach notification", "Consent management", "Right to be forgotten",
                    "Data processing agreement", "Privacy impact assessment",
                    "Cross-border data transfer", "Data subject rights",
                    # Spanish
                    "Cumplimiento RGPD", "Reglamento de protección de datos",
                    "Revisión de política de privacidad", "Notificación de brechas",
                    "Gestión del consentimiento", "Derecho al olvido",
                    "Acuerdo de procesamiento de datos", "Evaluación de impacto",
                    "Transferencia internacional de datos", "Derechos del interesado",
                    "GDPR", "RGPD",
                    # French
                    "Conformité RGPD", "Protection des données",
                    "Politique de confidentialité", "Droits des personnes",
                ]
            )

            privacy = Route(
                name="privacy",
                utterances=[
                    # English (LOPDGDD specific - Spanish law)
                    "LOPDGDD compliance", "Spanish data protection law",
                    "ARCO rights", "Data protection officer", "DPO requirements",
                    # Spanish
                    "Cumplimiento LOPDGDD", "Ley orgánica de protección de datos",
                    "Derechos ARCO", "Delegado de protección de datos",
                    "Requisitos DPD", "Garantía de derechos digitales",
                    "Protección de datos personales", "LOPDGDD",
                    "Registro de actividades de tratamiento",
                ]
            )

            search = Route(
                name="search",
                utterances=[
                    # English
                    "Find documents", "Search for files", "Look for emails",
                    "Show me contracts", "Where is the file", "Locate document",
                    "List all invoices", "Find recent reports",
                    # Spanish
                    "Busca documentos", "Encuentra archivos", "Buscar emails",
                    "Muéstrame contratos", "Dónde está el archivo", "Localiza documento",
                    "Lista todas las facturas", "Encuentra informes recientes",
                    "Buscar", "Encontrar", "Mostrar documentos",
                    # French
                    "Chercher documents", "Trouver fichiers", "Rechercher emails",
                    "Montrer contrats", "Où est le fichier",
                ]
            )

            summary = Route(
                name="summary",
                utterances=[
                    # English
                    "Summarize the document", "Give me a summary", "Key points",
                    "Executive summary", "Brief overview", "Main takeaways",
                    "Synthesize the information", "TL;DR",
                    # Spanish
                    "Resume el documento", "Dame un resumen", "Puntos clave",
                    "Resumen ejecutivo", "Vista general", "Ideas principales",
                    "Sintetiza la información", "Resúmeme",
                    # French
                    "Résumer le document", "Donne-moi un résumé", "Points clés",
                    "Résumé exécutif", "Synthétiser l'information",
                ]
            )

            # General analysis (default domain)
            general = Route(
                name="general",
                utterances=[
                    # English
                    "Analyze the document", "Evaluate risks", "Review this file",
                    "What are the issues", "Assess the situation",
                    # Spanish
                    "Analiza el documento", "Evalúa los riesgos", "Revisa este archivo",
                    "Cuáles son los problemas", "Evalúa la situación",
                    # French
                    "Analyser le document", "Évaluer les risques",
                ]
            )

            routes = [contract, labor, fiscal, compliance, privacy, search, summary, general]
            self._route_layer = RouterLayer(
                encoder=self._encoder,
                routes=routes,
                auto_sync='local'  # Required for semantic-router 0.1.2 to index embeddings
            )
            self._initialized = True
            logger.info("SemanticDomainRouter initialized with 8 domain routes")

        except ImportError as e:
            logger.error(f"Failed to import semantic-router: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to initialize SemanticDomainRouter: {e}")
            raise

    def classify(self, query: str) -> list[str]:
        """
        Classify a query into one or more domains.

        Args:
            query: User's query text

        Returns:
            List of domain names (agent types) that match the query.
            Returns ["general"] if no specific domain matches.
        """
        if not self._initialized:
            self.initialize()

        try:
            result = self._route_layer(query)

            if result is None or result.name is None:
                logger.debug(f"Domain: No route matched -> general")
                return ["general"]

            domain = result.name.lower()
            logger.info(f"Domain: {domain} for: {query[:50]}...")
            return [domain]

        except Exception as e:
            logger.warning(f"Domain Router classification failed: {e}")
            return ["general"]

    def get_agent_names(self, query: str) -> list[str]:
        """
        Get the agent names to use for a query based on domain classification.

        Args:
            query: User's query text

        Returns:
            List of agent names (e.g., ["contract_agent", "summarizer_agent"])
        """
        domains = self.classify(query)

        # Map domains to agent names
        domain_to_agent = {
            "contract": "contract_agent",
            "labor": "labor_agent",
            "fiscal": "fiscal_agent",
            "compliance": "compliance_agent",
            "privacy": "privacy_agent",
            "search": "search_agent",
            "summary": "summarizer_agent",
            "general": "analyst_agent",
        }

        agents = []
        for domain in domains:
            agent_name = domain_to_agent.get(domain)
            if agent_name:
                agents.append(agent_name)

        return agents if agents else ["analyst_agent"]


# Singleton for domain router
_domain_router: Optional[SemanticDomainRouter] = None


def get_domain_router() -> SemanticDomainRouter:
    """
    Get or create the domain router singleton.

    The router is initialized lazily on first use.
    """
    global _domain_router
    if _domain_router is None:
        _domain_router = SemanticDomainRouter()
        _domain_router.initialize()
    return _domain_router


def classify_domain(query: str) -> list[str]:
    """
    Convenience function to classify a query's domain.

    Args:
        query: User's query text

    Returns:
        List of domain names
    """
    router = get_domain_router()
    return router.classify(query)


def preload_semantic_routers() -> None:
    """
    Preload all semantic routers at service startup.

    This downloads and caches the HuggingFace encoder model if not already cached,
    then initializes both routers. This prevents the ~45s delay on the first
    user request.

    The model (all-MiniLM-L6-v2, ~23MB) is cached in:
    - ~/.cache/huggingface/hub/ (default)
    - Or HF_HOME environment variable if set

    Call this function during service startup for optimal user experience.
    """
    import time
    start = time.perf_counter()

    logger.info("🚀 Preloading Semantic Routers (downloading model if needed)...")

    try:
        # Preload pattern router (also loads the encoder)
        pattern_router = get_semantic_router()
        pattern_time = time.perf_counter() - start
        logger.info(f"✅ SemanticPatternRouter preloaded in {pattern_time:.2f}s")

        # Preload domain router (reuses encoder from cache)
        domain_start = time.perf_counter()
        domain_router = get_domain_router()
        domain_time = time.perf_counter() - domain_start
        logger.info(f"✅ SemanticDomainRouter preloaded in {domain_time:.2f}s")

        total_time = time.perf_counter() - start
        logger.info(f"✅ All Semantic Routers preloaded in {total_time:.2f}s")

    except Exception as e:
        logger.error(f"❌ Failed to preload Semantic Routers: {e}")
        logger.warning("⚠️ First request will experience delay while loading routers")
