"""
Domain Router for Emma v2

Detects the legal/business domain of a query to load appropriate prompts.
Replaces the heavyweight NexusRouter by leveraging SIL structural context.

Architecture:
    ┌─────────────────────────────────────────────────────────────┐
    │                    Domain Router                            │
    │                                                             │
    │   Query → Keyword Match → Document Type → SIL Context       │
    │                                                             │
    │   Domains:                                                  │
    │   ├── labor      → Estatuto Trabajadores, convenios         │
    │   ├── fiscal     → IVA, IRPF, facturas                      │
    │   ├── privacy    → RGPD, LOPD, protección datos            │
    │   ├── realestate → LAU, arrendamientos                      │
    │   ├── contract   → Contratos generales                      │
    │   ├── compliance → Auditorías, cumplimiento                 │
    │   └── general    → Otros                                    │
    │                                                             │
    │   Output: Domain type for dynamic prompt loading            │
    └─────────────────────────────────────────────────────────────┘

Unlike NexusRouter which required ML classification, this router uses:
1. Keyword matching (fast, ~0.1ms)
2. Document type inference from SIL metadata
3. Entity detection from structural context

This reduces latency from ~50-100ms to <1ms while maintaining accuracy.
"""

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


class DomainType(str, Enum):
    """Legal/business domains for Spanish document management."""
    LABOR = "labor"
    FISCAL = "fiscal"
    PRIVACY = "privacy"
    REALESTATE = "realestate"
    CONTRACT = "contract"
    COMPLIANCE = "compliance"
    EDUCATION = "education"
    LEGAL = "legal"
    DOCGEN = "docgen"
    GENERAL = "general"


@dataclass
class DomainDetectionResult:
    """Result from domain detection."""
    domain: DomainType
    confidence: float
    matched_keywords: List[str] = field(default_factory=list)
    inferred_from: str = "keywords"  # keywords, document_type, sil_context


# Domain keyword patterns - Spanish legal terminology
DOMAIN_KEYWORDS: Dict[DomainType, List[str]] = {
    DomainType.LABOR: [
        # Core labor terms
        "laboral", "trabajador", "trabajadores", "empleado", "empleados",
        "contrato de trabajo", "contrato laboral", "nómina", "nóminas",
        "despido", "despidos", "indemnización", "indemnizaciones",
        "convenio colectivo", "estatuto de los trabajadores", "estatuto trabajadores",
        # Specific concepts
        "jornada laboral", "horas extraordinarias", "vacaciones",
        "período de prueba", "preaviso", "finiquito",
        "seguridad social", "cotización", "cotizaciones",
        "permiso de maternidad", "permiso de paternidad",
        "excedencia", "reducción de jornada",
        # Legal references
        "art. 34 et", "art. 35 et", "art. 38 et", "artículo 34",
        "rdl 2/2015", "boe-a-2015-11430",
    ],
    DomainType.FISCAL: [
        # Tax types
        "iva", "irpf", "impuesto", "impuestos", "tributo", "tributos",
        "impuesto de sociedades", "is",
        # Documents
        "factura", "facturas", "declaración", "declaraciones",
        "modelo 303", "modelo 390", "modelo 100", "modelo 200",
        "autoliquidación", "liquidación",
        # Concepts
        "base imponible", "tipo impositivo", "cuota tributaria",
        "deducción", "deducciones", "desgravación",
        "retención", "retenciones",
        "ejercicio fiscal", "período impositivo",
        # Entities
        "hacienda", "agencia tributaria", "aeat",
        # Legal references
        "ley general tributaria", "lgt", "ley 58/2003",
    ],
    DomainType.PRIVACY: [
        # Core terms
        "rgpd", "gdpr", "lopd", "lopdgdd",
        "protección de datos", "privacidad", "datos personales",
        "tratamiento de datos", "responsable del tratamiento",
        "encargado del tratamiento",
        # Rights
        "derecho de acceso", "derecho de rectificación",
        "derecho de supresión", "derecho al olvido",
        "derecho de oposición", "portabilidad",
        # Concepts
        "consentimiento", "base de legitimación",
        "transferencia internacional", "delegado de protección",
        "dpo", "evaluación de impacto", "eipd",
        "brecha de seguridad", "notificación aepd",
        # Entity
        "aepd", "agencia española de protección de datos",
        # Legal references
        "reglamento 2016/679", "lo 3/2018",
    ],
    DomainType.REALESTATE: [
        # Contracts
        "arrendamiento", "alquiler", "inquilino", "arrendatario",
        "arrendador", "propietario",
        # Property types
        "vivienda", "local comercial", "inmueble", "finca",
        "propiedad horizontal",
        # Concepts
        "renta", "fianza", "depósito", "garantía adicional",
        "actualización de renta", "ipc",
        "prórroga", "renovación", "desahucio",
        # Legal references
        "lau", "ley de arrendamientos urbanos",
        "ley 29/1994", "boe-a-1994-26003",
        # Transactions
        "compraventa", "hipoteca", "escritura",
    ],
    DomainType.CONTRACT: [
        # General contract terms (not covered by other domains)
        "contrato", "contratos", "cláusula", "cláusulas",
        "acuerdo", "convenio", "pacto",
        # Parties
        "parte", "partes", "firmante", "firmantes",
        "representante", "apoderado",
        # Elements
        "objeto", "obligaciones", "derechos",
        "vigencia", "duración", "resolución",
        "penalización", "penalizaciones",
        # Types
        "contrato de servicios", "contrato de suministro",
        "contrato de confidencialidad", "nda",
        "contrato mercantil",
    ],
    DomainType.COMPLIANCE: [
        # Core terms
        "cumplimiento", "compliance", "normativa", "normativo",
        "auditoría", "auditoria", "control interno",
        # Frameworks
        "iso 27001", "iso 9001", "iso 14001",
        "sox", "sarbanes-oxley",
        # Concepts
        "riesgo", "riesgos", "gestión de riesgos",
        "debido control", "debida diligencia",
        "prevención de blanqueo", "pbc/ft",
        "canal de denuncias", "whistleblowing",
        # Regulatory
        "regulación", "regulador", "supervisión",
        "sanción", "sanciones", "infracción",
    ],
    DomainType.EDUCATION: [
        # Core terms
        "educación", "educativo", "formación", "académico",
        "estudiante", "alumno", "docente", "profesor",
        # Documents
        "matrícula", "expediente académico", "título",
        "certificado", "diploma", "notas",
        # Institutions
        "universidad", "colegio", "instituto",
        "centro educativo", "centro de formación",
        # Concepts
        "curso", "asignatura", "crédito", "ects",
        "evaluación", "calificación",
    ],
    DomainType.LEGAL: [
        # Generic legal (not covered by specific domains)
        "jurídico", "legal", "derecho", "ley", "leyes",
        "jurisprudencia", "sentencia", "sentencias",
        "tribunal", "juzgado", "audiencia",
        "demanda", "recurso", "apelación",
        "abogado", "letrado", "procurador",
    ],
    DomainType.DOCGEN: [
        # Document generation verbs
        "genera un", "genera una", "generar un", "generar una",
        "redacta un", "redacta una", "redactar un", "redactar una",
        "elabora un", "elabora una", "elaborar un", "elaborar una",
        "crea un contrato", "crea una demanda", "crea un escrito",
        "escribe un", "escribe una", "escribir un", "escribir una",
        "prepara un documento", "prepara un contrato", "prepara un escrito",
        "modelo de contrato", "modelo de demanda", "modelo de escrito",
        "plantilla de contrato", "plantilla de demanda", "plantilla de escrito",
        "borrador de contrato", "borrador de demanda", "borrador de escrito",
        "redacción de contrato", "redacción de demanda",
    ],
}

# Document type to domain mapping
DOCUMENT_TYPE_TO_DOMAIN: Dict[str, DomainType] = {
    # Labor
    "contrato_laboral": DomainType.LABOR,
    "nomina": DomainType.LABOR,
    "finiquito": DomainType.LABOR,
    "convenio_colectivo": DomainType.LABOR,
    # Fiscal
    "factura": DomainType.FISCAL,
    "declaracion_fiscal": DomainType.FISCAL,
    "modelo_303": DomainType.FISCAL,
    "modelo_390": DomainType.FISCAL,
    # Privacy
    "politica_privacidad": DomainType.PRIVACY,
    "consentimiento_datos": DomainType.PRIVACY,
    "clausula_rgpd": DomainType.PRIVACY,
    # Real estate
    "contrato_arrendamiento": DomainType.REALESTATE,
    "contrato_alquiler": DomainType.REALESTATE,
    "escritura": DomainType.REALESTATE,
    # Contract
    "contrato": DomainType.CONTRACT,
    "acuerdo": DomainType.CONTRACT,
    "nda": DomainType.CONTRACT,
    # Education
    "certificado_academico": DomainType.EDUCATION,
    "titulo": DomainType.EDUCATION,
    "matricula": DomainType.EDUCATION,
}


class DomainRouter:
    """
    Fast domain router for loading specialized prompts.

    Uses a three-tier detection strategy:
    1. Keyword matching in query (fastest, ~0.1ms)
    2. Document type inference (if document context available)
    3. SIL structural context (if available)

    This is much faster than the ML-based NexusRouter while
    maintaining high accuracy for Spanish legal documents.
    """

    def __init__(self):
        # Pre-compile keyword patterns for faster matching
        self._patterns: Dict[DomainType, re.Pattern] = {}
        self._compile_patterns()

    def _compile_patterns(self) -> None:
        """Compile regex patterns for each domain."""
        for domain, keywords in DOMAIN_KEYWORDS.items():
            # Create pattern with word boundaries
            # Escape special regex characters in keywords
            escaped = [re.escape(kw) for kw in keywords]
            pattern = r'\b(' + '|'.join(escaped) + r')\b'
            self._patterns[domain] = re.compile(pattern, re.IGNORECASE)

    def detect_domain(
        self,
        query: str,
        document_type: Optional[str] = None,
        sil_context: Optional[Dict] = None,
    ) -> DomainDetectionResult:
        """
        Detect domain for a query.

        Args:
            query: User's query text
            document_type: Document type from SIL structural metadata
            sil_context: Full SIL structural context (optional)

        Returns:
            DomainDetectionResult with domain and confidence
        """
        query_lower = query.lower()

        # Strategy 1: Keyword matching (primary)
        keyword_result = self._detect_from_keywords(query_lower)
        if keyword_result.confidence >= 0.7:
            return keyword_result

        # Strategy 2: Document type inference
        if document_type:
            doc_result = self._detect_from_document_type(document_type)
            if doc_result.confidence >= 0.6:
                return doc_result

        # Strategy 3: SIL context
        if sil_context:
            sil_result = self._detect_from_sil_context(sil_context)
            if sil_result.confidence >= 0.5:
                return sil_result

        # Default to general if no strong signal
        if keyword_result.confidence > 0:
            return keyword_result

        return DomainDetectionResult(
            domain=DomainType.GENERAL,
            confidence=1.0,
            inferred_from="default",
        )

    def _detect_from_keywords(self, query: str) -> DomainDetectionResult:
        """Detect domain from query keywords."""
        scores: Dict[DomainType, Tuple[float, List[str]]] = {}

        for domain, pattern in self._patterns.items():
            matches = pattern.findall(query)
            if matches:
                # Score based on number of unique matches
                unique_matches = list(set(m.lower() for m in matches))
                score = min(len(unique_matches) * 0.4, 1.0)
                scores[domain] = (score, unique_matches)

        if not scores:
            return DomainDetectionResult(
                domain=DomainType.GENERAL,
                confidence=0.0,
                inferred_from="keywords",
            )

        # Get domain with highest score
        best_domain = max(scores, key=lambda d: scores[d][0])
        score, matches = scores[best_domain]

        return DomainDetectionResult(
            domain=best_domain,
            confidence=score,
            matched_keywords=matches,
            inferred_from="keywords",
        )

    def _detect_from_document_type(self, document_type: str) -> DomainDetectionResult:
        """Detect domain from document type metadata."""
        doc_type_lower = document_type.lower().replace(" ", "_")

        # Direct mapping
        if doc_type_lower in DOCUMENT_TYPE_TO_DOMAIN:
            return DomainDetectionResult(
                domain=DOCUMENT_TYPE_TO_DOMAIN[doc_type_lower],
                confidence=0.9,
                inferred_from="document_type",
            )

        # Partial matching
        for type_key, domain in DOCUMENT_TYPE_TO_DOMAIN.items():
            if type_key in doc_type_lower or doc_type_lower in type_key:
                return DomainDetectionResult(
                    domain=domain,
                    confidence=0.7,
                    inferred_from="document_type",
                )

        return DomainDetectionResult(
            domain=DomainType.GENERAL,
            confidence=0.3,
            inferred_from="document_type",
        )

    def _detect_from_sil_context(self, sil_context: Dict) -> DomainDetectionResult:
        """Detect domain from SIL structural context."""
        # Check semantic domain
        if semantic_domain := sil_context.get("semantic_domain"):
            domain_mapping = {
                "labor": DomainType.LABOR,
                "laboral": DomainType.LABOR,
                "fiscal": DomainType.FISCAL,
                "tributario": DomainType.FISCAL,
                "privacy": DomainType.PRIVACY,
                "privacidad": DomainType.PRIVACY,
                "inmobiliario": DomainType.REALESTATE,
                "real_estate": DomainType.REALESTATE,
            }
            if semantic_domain.lower() in domain_mapping:
                return DomainDetectionResult(
                    domain=domain_mapping[semantic_domain.lower()],
                    confidence=0.8,
                    inferred_from="sil_context",
                )

        # Check document types in context
        if doc_types := sil_context.get("document_types"):
            for doc_type in doc_types:
                result = self._detect_from_document_type(doc_type)
                if result.confidence >= 0.6:
                    result.inferred_from = "sil_context"
                    return result

        return DomainDetectionResult(
            domain=DomainType.GENERAL,
            confidence=0.3,
            inferred_from="sil_context",
        )

    def get_domains_for_query(
        self,
        query: str,
        threshold: float = 0.3,
    ) -> List[DomainDetectionResult]:
        """
        Get all potentially relevant domains for a query.

        Useful when a query might span multiple domains.

        Args:
            query: User's query
            threshold: Minimum confidence to include

        Returns:
            List of domain results above threshold, sorted by confidence
        """
        query_lower = query.lower()
        results = []

        for domain, pattern in self._patterns.items():
            matches = pattern.findall(query_lower)
            if matches:
                unique_matches = list(set(m.lower() for m in matches))
                score = min(len(unique_matches) * 0.4, 1.0)
                if score >= threshold:
                    results.append(DomainDetectionResult(
                        domain=domain,
                        confidence=score,
                        matched_keywords=unique_matches,
                        inferred_from="keywords",
                    ))

        # Sort by confidence descending
        results.sort(key=lambda r: r.confidence, reverse=True)

        # Always include general as fallback
        if not results:
            results.append(DomainDetectionResult(
                domain=DomainType.GENERAL,
                confidence=1.0,
                inferred_from="default",
            ))

        return results


# Global singleton
domain_router = DomainRouter()
