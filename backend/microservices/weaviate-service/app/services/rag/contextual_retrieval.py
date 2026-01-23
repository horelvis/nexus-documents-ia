"""
Contextual Retrieval Pipeline

Based on Anthropic's Contextual Retrieval pattern, this module generates and prepends
contextual information to document chunks BEFORE indexing. This approach:

- Improves retrieval accuracy by 35-67% (Anthropic research)
- Encodes domain knowledge IN chunks instead of in prompts
- Reduces token usage at query time (no need for 4000+ token domain prompts)
- Makes chunks self-contained with legal/business context

How it works:
1. Analyze document to detect type and domain (labor, fiscal, privacy, etc.)
2. Identify applicable legislation based on document content
3. Generate a contextual prefix for each chunk
4. Prepend context to chunk BEFORE embedding

Example:
    Original chunk:
        "El trabajador tendrá una jornada de 40 horas semanales..."

    Contextualized chunk:
        "[CONTEXTO] Este es un contrato laboral regido por el Estatuto de los
        Trabajadores (RDL 2/2015). Aplican: Art. 34 (jornada), Art. 35 (horas extra).
        [CONTENIDO] El trabajador tendrá una jornada de 40 horas semanales..."

Usage:
    from app.services.rag.contextual_retrieval import contextual_retrieval

    # Generate context for a document
    context_result = await contextual_retrieval.analyze_document(
        document_id="doc-123",
        text=document_text,
        metadata={"document_type": "contrato_laboral"},
        tenant_id="tenant-abc"
    )

    # Apply context to chunks
    contextualized_chunks = contextual_retrieval.apply_context_to_chunks(
        chunks=raw_chunks,
        context_result=context_result
    )

References:
    - https://www.anthropic.com/news/contextual-retrieval
    - backend/architecture/SIL-structural-intelligence-layer.md
"""

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import settings

logger = logging.getLogger(__name__)


# =============================================================================
# Domain Definitions
# =============================================================================

class LegalDomain(str, Enum):
    """Spanish legal domains for document classification."""
    LABOR = "labor"           # Estatuto de los Trabajadores
    FISCAL = "fiscal"         # IVA, IRPF, IS
    PRIVACY = "privacy"       # RGPD, LOPDGDD
    REALESTATE = "realestate" # LAU, arrendamientos
    CONTRACT = "contract"     # Código Civil, obligaciones
    COMPLIANCE = "compliance" # Blanqueo, Código Penal, Concursal
    COMMERCE = "commerce"     # LGDCU, Competencia Desleal
    IP = "ip"                 # Propiedad Intelectual, Marcas, Patentes
    MERCANTILE = "mercantile" # Sociedades, Código de Comercio
    EDUCATION = "education"   # Normativa educativa
    GENERAL = "general"       # Sin dominio específico


# =============================================================================
# Spanish Legislation Database
# =============================================================================

# This knowledge base contains the key Spanish laws and their articles
# Used to enrich chunks with legal context during indexing

SPANISH_LEGISLATION = {
    LegalDomain.LABOR: {
        "name": "Derecho Laboral Español",
        "laws": [
            {
                "name": "Estatuto de los Trabajadores",
                "abbreviation": "ET",
                "boe_id": "BOE-A-2015-11430",
                "reference": "RDL 2/2015",
                "key_articles": {
                    "14": "Períodos de prueba",
                    "34": "Jornada laboral (máx. 40h/semana)",
                    "35": "Horas extraordinarias (máx. 80h/año)",
                    "38": "Vacaciones (mín. 30 días naturales)",
                    "49": "Extinción del contrato",
                    "52": "Despido objetivo",
                    "54": "Despido disciplinario",
                    "55": "Forma y efectos del despido",
                    "56": "Despido improcedente",
                }
            },
            {
                "name": "Ley de Prevención de Riesgos Laborales",
                "abbreviation": "LPRL",
                "boe_id": "BOE-A-1995-24292",
                "reference": "Ley 31/1995",
                "key_articles": {
                    "14": "Derecho a protección eficaz",
                    "15": "Principios de la acción preventiva",
                    "19": "Formación de los trabajadores",
                }
            },
            {
                "name": "Ley de Infracciones y Sanciones",
                "abbreviation": "LISOS",
                "boe_id": "BOE-A-2000-15060",
                "reference": "RDL 5/2000",
                "key_articles": {
                    "6": "Infracciones leves",
                    "7": "Infracciones graves",
                    "8": "Infracciones muy graves",
                }
            },
        ],
        "document_types": [
            "contrato_trabajo", "contrato_laboral", "nomina", "finiquito",
            "carta_despido", "convenio_colectivo", "ere", "erte"
        ],
        "keywords": [
            "trabajador", "empleado", "nómina", "salario", "jornada", "despido",
            "contrato laboral", "convenio", "vacaciones", "permiso", "baja",
            "estatuto de los trabajadores", "contrato de trabajo"
        ]
    },

    LegalDomain.FISCAL: {
        "name": "Derecho Tributario Español",
        "laws": [
            {
                "name": "Ley General Tributaria",
                "abbreviation": "LGT",
                "boe_id": "BOE-A-2003-23186",
                "reference": "Ley 58/2003",
                "key_articles": {
                    "17": "Obligación tributaria principal",
                    "25": "Devengo y exigibilidad",
                    "178": "Infracciones tributarias",
                }
            },
            {
                "name": "Ley del IVA",
                "abbreviation": "LIVA",
                "boe_id": "BOE-A-1992-28740",
                "reference": "Ley 37/1992",
                "key_articles": {
                    "4": "Hecho imponible",
                    "20": "Exenciones",
                    "90": "Tipo general (21%)",
                    "91": "Tipo reducido (10%)",
                }
            },
            {
                "name": "Reglamento de Facturación",
                "abbreviation": "RF",
                "boe_id": "BOE-A-2012-14696",
                "reference": "RD 1619/2012",
                "key_articles": {
                    "6": "Contenido de la factura",
                    "7": "Requisitos de las facturas simplificadas",
                    "15": "Plazos de expedición",
                }
            },
            {
                "name": "Ley del IRPF",
                "abbreviation": "LIRPF",
                "boe_id": "BOE-A-2006-20764",
                "reference": "Ley 35/2006",
                "key_articles": {
                    "17": "Rendimientos del trabajo",
                    "99": "Obligación de retener",
                }
            },
        ],
        "document_types": [
            "factura", "factura_rectificativa", "presupuesto", "declaracion_iva",
            "modelo_303", "modelo_390", "retenciones"
        ],
        "keywords": [
            "iva", "impuesto", "factura", "base imponible", "retención", "irpf",
            "hacienda", "agencia tributaria", "declaración", "cuota", "deducción",
            "tipo impositivo"
        ]
    },

    LegalDomain.PRIVACY: {
        "name": "Protección de Datos",
        "laws": [
            {
                "name": "Reglamento General de Protección de Datos",
                "abbreviation": "RGPD",
                "boe_id": "EUR-Lex 2016/679",
                "reference": "Reglamento (UE) 2016/679",
                "key_articles": {
                    "5": "Principios del tratamiento",
                    "6": "Licitud del tratamiento",
                    "7": "Condiciones del consentimiento",
                    "12": "Transparencia de información",
                    "13": "Información al interesado",
                    "15": "Derecho de acceso",
                    "17": "Derecho de supresión",
                    "32": "Seguridad del tratamiento",
                }
            },
            {
                "name": "Ley Orgánica de Protección de Datos",
                "abbreviation": "LOPDGDD",
                "boe_id": "BOE-A-2018-16673",
                "reference": "LO 3/2018",
                "key_articles": {
                    "6": "Tratamiento datos contacto",
                    "7": "Consentimiento de menores",
                    "11": "Transparencia e información",
                    "89": "Derecho a indemnización",
                }
            },
        ],
        "document_types": [
            "politica_privacidad", "consentimiento", "contrato_encargado",
            "evaluacion_impacto", "registro_actividades"
        ],
        "keywords": [
            "rgpd", "gdpr", "protección de datos", "datos personales",
            "consentimiento", "privacidad", "lopd", "tratamiento", "interesado",
            "responsable del tratamiento", "encargado"
        ]
    },

    LegalDomain.REALESTATE: {
        "name": "Derecho Inmobiliario",
        "laws": [
            {
                "name": "Ley de Arrendamientos Urbanos",
                "abbreviation": "LAU",
                "boe_id": "BOE-A-1994-26003",
                "reference": "Ley 29/1994",
                "key_articles": {
                    "9": "Duración del contrato",
                    "10": "Prórroga del contrato",
                    "17": "Determinación de la renta",
                    "18": "Actualización de la renta",
                    "23": "Obras del arrendatario",
                    "36": "Fianza",
                }
            },
            {
                "name": "Ley Hipotecaria",
                "abbreviation": "LH",
                "boe_id": "BOE-A-1946-2453",
                "reference": "Decreto de 8 de febrero de 1946",
                "key_articles": {
                    "1": "Registro de la Propiedad",
                    "34": "Tercero hipotecario",
                }
            },
        ],
        "document_types": [
            "contrato_arrendamiento", "contrato_alquiler", "escritura",
            "hipoteca", "compraventa"
        ],
        "keywords": [
            "arrendamiento", "alquiler", "inquilino", "arrendador", "renta",
            "fianza", "vivienda", "inmueble", "hipoteca", "compraventa",
            "propiedad", "lau"
        ]
    },

    LegalDomain.CONTRACT: {
        "name": "Derecho de Contratos",
        "laws": [
            {
                "name": "Código Civil",
                "abbreviation": "CC",
                "boe_id": "BOE-A-1889-4763",
                "reference": "Real Decreto de 24 de julio de 1889",
                "key_articles": {
                    "1088": "Obligaciones",
                    "1091": "Fuerza de ley entre partes",
                    "1254": "Existencia del contrato",
                    "1256": "Validez y cumplimiento",
                    "1258": "Obligaciones del contrato",
                    "1261": "Requisitos del contrato",
                    "1274": "Causa del contrato",
                    "1544": "Arrendamiento de cosas",
                }
            },
            {
                "name": "Código de Comercio",
                "abbreviation": "CCom",
                "boe_id": "BOE-A-1885-6627",
                "reference": "Real Decreto de 22 de agosto de 1885",
                "key_articles": {
                    "50": "Contratos mercantiles",
                    "51": "Perfección de contratos",
                }
            },
        ],
        "document_types": [
            "contrato", "acuerdo", "convenio", "pacto", "memorando"
        ],
        "keywords": [
            "contrato", "obligación", "parte", "cláusula", "vigencia",
            "resolución", "rescisión", "incumplimiento", "indemnización",
            "penalización", "confidencialidad"
        ]
    },

    LegalDomain.COMPLIANCE: {
        "name": "Compliance y Riesgos Empresariales",
        "laws": [
            {
                "name": "Ley de Prevención del Blanqueo de Capitales",
                "abbreviation": "LPBC",
                "boe_id": "BOE-A-2010-6737",
                "reference": "Ley 10/2010",
                "key_articles": {
                    "2": "Sujetos obligados",
                    "3": "Diligencia debida",
                    "17": "Comunicación de operaciones sospechosas",
                    "18": "Abstención de ejecución",
                    "26": "Órganos de control interno",
                }
            },
            {
                "name": "Código Penal",
                "abbreviation": "CP",
                "boe_id": "BOE-A-1995-25444",
                "reference": "LO 10/1995",
                "key_articles": {
                    "31bis": "Responsabilidad penal personas jurídicas",
                    "31ter": "Exención por compliance",
                    "31quater": "Atenuantes personas jurídicas",
                    "33.7": "Penas aplicables a personas jurídicas",
                }
            },
            {
                "name": "Ley Concursal",
                "abbreviation": "LC",
                "boe_id": "BOE-A-2020-11218",
                "reference": "RDL 1/2020",
                "key_articles": {
                    "2": "Presupuesto objetivo (insolvencia)",
                    "3": "Legitimación para solicitar concurso",
                    "5": "Deber de solicitar concurso",
                    "583": "Calificación del concurso",
                }
            },
            {
                "name": "Ley de Secretos Empresariales",
                "abbreviation": "LSE",
                "boe_id": "BOE-A-2019-2364",
                "reference": "Ley 1/2019",
                "key_articles": {
                    "1": "Definición de secreto empresarial",
                    "3": "Obtención lícita",
                    "4": "Obtención, utilización y revelación ilícitas",
                    "9": "Acciones civiles",
                }
            },
        ],
        "document_types": [
            "manual_compliance", "politica_pbc", "modelo_prevencion",
            "analisis_riesgos", "due_diligence", "informe_auditoria"
        ],
        "keywords": [
            "compliance", "blanqueo", "pbc", "aml", "kyc", "diligencia debida",
            "riesgo", "concursal", "insolvencia", "quiebra", "responsabilidad penal",
            "persona jurídica", "canal de denuncias", "secreto empresarial"
        ]
    },

    LegalDomain.COMMERCE: {
        "name": "Derecho del Comercio y Consumidores",
        "laws": [
            {
                "name": "Ley General de Consumidores y Usuarios",
                "abbreviation": "LGDCU",
                "boe_id": "BOE-A-2007-20555",
                "reference": "RDL 1/2007",
                "key_articles": {
                    "8": "Derechos básicos de los consumidores",
                    "60": "Información previa al contrato",
                    "66bis": "Plazo de entrega",
                    "68": "Derecho de desistimiento",
                    "71": "Plazo para ejercer desistimiento (14 días)",
                    "114": "Garantía legal de los productos",
                    "120": "Plazo de garantía (3 años)",
                }
            },
            {
                "name": "Ley de Competencia Desleal",
                "abbreviation": "LCD",
                "boe_id": "BOE-A-1991-628",
                "reference": "Ley 3/1991",
                "key_articles": {
                    "4": "Cláusula general (buena fe)",
                    "5": "Actos de engaño",
                    "6": "Actos de confusión",
                    "7": "Omisiones engañosas",
                    "12": "Explotación de la reputación ajena",
                    "18": "Publicidad ilícita",
                }
            },
            {
                "name": "Ley de Servicios de la Sociedad de la Información",
                "abbreviation": "LSSI",
                "boe_id": "BOE-A-2002-13758",
                "reference": "Ley 34/2002",
                "key_articles": {
                    "10": "Información general obligatoria",
                    "20": "Información en comunicaciones comerciales",
                    "21": "Prohibición de spam",
                    "22": "Cookies (consentimiento)",
                }
            },
        ],
        "document_types": [
            "condiciones_generales", "politica_devoluciones", "aviso_legal",
            "terminos_servicio", "politica_envios"
        ],
        "keywords": [
            "consumidor", "usuario", "garantía", "devolución", "desistimiento",
            "reclamación", "comercio electrónico", "e-commerce", "cookies",
            "publicidad", "competencia desleal", "condiciones generales"
        ]
    },

    LegalDomain.IP: {
        "name": "Propiedad Intelectual e Industrial",
        "laws": [
            {
                "name": "Ley de Propiedad Intelectual",
                "abbreviation": "LPI",
                "boe_id": "BOE-A-1996-8930",
                "reference": "RDL 1/1996",
                "key_articles": {
                    "1": "Hecho generador de la propiedad intelectual",
                    "2": "Contenido del derecho de autor",
                    "17": "Derecho exclusivo de explotación",
                    "26": "Duración de los derechos (vida + 70 años)",
                    "96": "Programas de ordenador",
                    "138": "Acciones y procedimientos",
                }
            },
            {
                "name": "Ley de Marcas",
                "abbreviation": "LM",
                "boe_id": "BOE-A-2001-23093",
                "reference": "Ley 17/2001",
                "key_articles": {
                    "4": "Concepto de marca",
                    "5": "Prohibiciones absolutas",
                    "6": "Prohibiciones relativas",
                    "31": "Duración y renovación (10 años)",
                    "34": "Derechos conferidos por la marca",
                }
            },
            {
                "name": "Ley de Patentes",
                "abbreviation": "LP",
                "boe_id": "BOE-A-2015-11929",
                "reference": "Ley 24/2015",
                "key_articles": {
                    "4": "Invenciones patentables",
                    "5": "Exclusiones de patentabilidad",
                    "58": "Duración de la patente (20 años)",
                    "59": "Derechos conferidos por la patente",
                }
            },
        ],
        "document_types": [
            "contrato_licencia", "cesion_derechos", "registro_marca",
            "solicitud_patente", "acuerdo_confidencialidad"
        ],
        "keywords": [
            "propiedad intelectual", "copyright", "derechos de autor",
            "marca", "patente", "licencia", "cesión", "software",
            "know-how", "royalty", "infracción", "plagio"
        ]
    },

    LegalDomain.MERCANTILE: {
        "name": "Derecho Mercantil y Societario",
        "laws": [
            {
                "name": "Ley de Sociedades de Capital",
                "abbreviation": "LSC",
                "boe_id": "BOE-A-2010-10544",
                "reference": "RDL 1/2010",
                "key_articles": {
                    "1": "Sociedades de capital",
                    "4": "Capital social mínimo (SL: 1€, SA: 60.000€)",
                    "160": "Competencia de la junta general",
                    "209": "Facultades del órgano de administración",
                    "217": "Remuneración de administradores",
                    "225": "Deber de diligencia",
                    "226": "Deber de lealtad",
                    "236": "Responsabilidad de los administradores",
                }
            },
            {
                "name": "Código de Comercio",
                "abbreviation": "CCom",
                "boe_id": "BOE-A-1885-6627",
                "reference": "Real Decreto de 22 de agosto de 1885",
                "key_articles": {
                    "1": "Comerciantes",
                    "25": "Obligación de llevar contabilidad",
                    "28": "Libro diario",
                    "30": "Conservación de libros (6 años)",
                }
            },
            {
                "name": "Ley de Emprendedores",
                "abbreviation": "LE",
                "boe_id": "BOE-A-2013-10074",
                "reference": "Ley 14/2013",
                "key_articles": {
                    "7": "Emprendedor de responsabilidad limitada",
                    "12": "Constitución telemática de sociedades",
                }
            },
        ],
        "document_types": [
            "estatutos_sociales", "acta_junta", "acta_consejo",
            "pacto_socios", "poder_notarial", "escritura_constitucion"
        ],
        "keywords": [
            "sociedad", "socio", "accionista", "participación", "acción",
            "junta general", "consejo de administración", "administrador",
            "dividendo", "capital social", "aumento de capital", "reducción",
            "fusión", "escisión", "disolución", "liquidación"
        ]
    },
}


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class LawReference:
    """Reference to a specific law and article."""
    law_name: str
    abbreviation: str
    boe_id: str
    reference: str
    article: Optional[str] = None
    article_description: Optional[str] = None

    def to_citation(self) -> str:
        """Format as legal citation."""
        if self.article:
            return f"Art. {self.article} {self.abbreviation} ({self.boe_id})"
        return f"{self.abbreviation} ({self.boe_id})"


@dataclass
class DomainDetectionResult:
    """Result of domain detection for a document."""
    primary_domain: LegalDomain
    confidence: float
    secondary_domains: List[LegalDomain] = field(default_factory=list)
    detected_keywords: List[str] = field(default_factory=list)
    applicable_laws: List[LawReference] = field(default_factory=list)


@dataclass
class ContextGenerationResult:
    """Result of context generation for a document."""
    document_id: str
    domain: LegalDomain
    context_prefix: str
    applicable_laws: List[LawReference]
    document_summary: str
    key_entities: List[str]
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ContextualizedChunk:
    """A chunk with prepended context."""
    original_text: str
    contextualized_text: str
    context_prefix: str
    chunk_index: int
    domain: LegalDomain
    applicable_laws: List[str]
    metadata: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# Contextual Retrieval Service
# =============================================================================

class ContextualRetrievalService:
    """
    Service for generating and applying contextual information to document chunks.

    This implements Anthropic's Contextual Retrieval pattern:
    1. Analyze document to detect legal domain
    2. Identify applicable legislation
    3. Generate context prefix for chunks
    4. Prepend context before embedding
    """

    def __init__(self):
        self._llm_client = None
        self._enabled = settings.contextual_retrieval_enabled if hasattr(settings, 'contextual_retrieval_enabled') else True

    async def _get_llm_client(self):
        """Lazy load LLM client."""
        if self._llm_client is None:
            try:
                from app.agents.llm_client import get_llm_client
                self._llm_client = await get_llm_client()
            except Exception as e:
                logger.warning(f"Failed to get LLM client: {e}")
        return self._llm_client

    def detect_domain(
        self,
        text: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> DomainDetectionResult:
        """
        Detect the legal domain of a document.

        Uses keyword matching and document type to determine the primary
        and secondary legal domains.

        Args:
            text: Document text content
            metadata: Document metadata (may contain document_type)

        Returns:
            DomainDetectionResult with detected domains and applicable laws
        """
        text_lower = text.lower()
        metadata = metadata or {}
        doc_type = metadata.get("document_type", "").lower()

        domain_scores: Dict[LegalDomain, float] = {}
        detected_keywords: Dict[LegalDomain, List[str]] = {}

        # Score each domain based on keyword matches
        for domain, domain_info in SPANISH_LEGISLATION.items():
            score = 0.0
            keywords_found = []

            # Check document type match
            for doc_type_pattern in domain_info.get("document_types", []):
                if doc_type_pattern in doc_type:
                    score += 0.5
                    keywords_found.append(f"doc_type:{doc_type_pattern}")

            # Check keyword matches
            for keyword in domain_info.get("keywords", []):
                # Count occurrences (diminishing returns)
                occurrences = text_lower.count(keyword)
                if occurrences > 0:
                    # Logarithmic scoring for repeated keywords
                    import math
                    keyword_score = 0.1 * (1 + math.log(occurrences))
                    score += keyword_score
                    keywords_found.append(keyword)

            domain_scores[domain] = score
            detected_keywords[domain] = keywords_found

        # Determine primary domain
        if not domain_scores or max(domain_scores.values()) == 0:
            primary_domain = LegalDomain.GENERAL
            confidence = 0.3
        else:
            primary_domain = max(domain_scores, key=domain_scores.get)
            max_score = domain_scores[primary_domain]
            confidence = min(0.95, 0.3 + (max_score * 0.1))

        # Determine secondary domains (score > 0.3)
        secondary_domains = [
            d for d, score in domain_scores.items()
            if d != primary_domain and score > 0.3
        ]

        # Get applicable laws
        applicable_laws = self._get_applicable_laws(
            primary_domain,
            detected_keywords.get(primary_domain, [])
        )

        return DomainDetectionResult(
            primary_domain=primary_domain,
            confidence=confidence,
            secondary_domains=secondary_domains,
            detected_keywords=detected_keywords.get(primary_domain, []),
            applicable_laws=applicable_laws
        )

    def _get_applicable_laws(
        self,
        domain: LegalDomain,
        detected_keywords: List[str]
    ) -> List[LawReference]:
        """Get applicable laws for a domain."""
        if domain not in SPANISH_LEGISLATION:
            return []

        domain_info = SPANISH_LEGISLATION[domain]
        laws = []

        for law_info in domain_info.get("laws", []):
            law_ref = LawReference(
                law_name=law_info["name"],
                abbreviation=law_info["abbreviation"],
                boe_id=law_info["boe_id"],
                reference=law_info["reference"]
            )
            laws.append(law_ref)

        return laws

    def generate_context_prefix(
        self,
        domain_result: DomainDetectionResult,
        document_summary: str = "",
        document_type: str = ""
    ) -> str:
        """
        Generate the context prefix to prepend to chunks.

        This creates a compact but informative prefix that includes:
        - Document type and domain
        - Applicable legislation
        - Key legal articles

        Args:
            domain_result: Result from detect_domain
            document_summary: Optional document summary
            document_type: Document type for context

        Returns:
            Context prefix string
        """
        domain = domain_result.primary_domain

        if domain == LegalDomain.GENERAL:
            return f"[CONTEXTO] Documento {document_type or 'general'}."

        domain_info = SPANISH_LEGISLATION.get(domain, {})
        domain_name = domain_info.get("name", domain.value)

        # Build law references
        law_refs = []
        for law in domain_result.applicable_laws[:3]:  # Max 3 laws
            law_refs.append(f"{law.abbreviation} ({law.boe_id})")

        laws_str = ", ".join(law_refs) if law_refs else "normativa aplicable"

        # Build context
        context_parts = [
            f"[CONTEXTO] Documento de {domain_name}",
        ]

        if document_type:
            context_parts[0] = f"[CONTEXTO] {document_type.replace('_', ' ').title()} - {domain_name}"

        context_parts.append(f"Legislación aplicable: {laws_str}.")

        # Add key articles based on domain
        if domain == LegalDomain.LABOR:
            context_parts.append("Artículos clave: Art. 34 ET (jornada), Art. 35 (horas extra), Art. 38 (vacaciones).")
        elif domain == LegalDomain.FISCAL:
            context_parts.append("Artículos clave: Art. 6 RF (contenido factura), Art. 90-91 LIVA (tipos IVA).")
        elif domain == LegalDomain.PRIVACY:
            context_parts.append("Artículos clave: Art. 5-7 RGPD (principios), Art. 13 (información).")
        elif domain == LegalDomain.REALESTATE:
            context_parts.append("Artículos clave: Art. 9-10 LAU (duración), Art. 17 (renta), Art. 36 (fianza).")
        elif domain == LegalDomain.COMPLIANCE:
            context_parts.append("Artículos clave: Art. 31bis CP (responsabilidad PJ), Art. 2-3 LPBC (diligencia debida).")
        elif domain == LegalDomain.COMMERCE:
            context_parts.append("Artículos clave: Art. 68-71 LGDCU (desistimiento 14 días), Art. 114 (garantía 3 años).")
        elif domain == LegalDomain.IP:
            context_parts.append("Artículos clave: Art. 17 LPI (explotación), Art. 34 LM (derechos marca), Art. 58 LP (duración 20 años).")
        elif domain == LegalDomain.MERCANTILE:
            context_parts.append("Artículos clave: Art. 160 LSC (junta general), Art. 225-226 (deberes administrador).")

        return " ".join(context_parts) + " [CONTENIDO]"

    async def analyze_document(
        self,
        document_id: str,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
        tenant_id: Optional[str] = None,
        use_llm: bool = False
    ) -> ContextGenerationResult:
        """
        Analyze a document and generate contextual information.

        Args:
            document_id: Document identifier
            text: Full document text
            metadata: Document metadata
            tenant_id: Tenant identifier
            use_llm: Whether to use LLM for enhanced analysis

        Returns:
            ContextGenerationResult with context prefix and metadata
        """
        metadata = metadata or {}

        # Detect domain
        domain_result = self.detect_domain(text, metadata)

        # Generate context prefix
        document_type = metadata.get("document_type", "")
        context_prefix = self.generate_context_prefix(
            domain_result,
            document_type=document_type
        )

        # Extract key entities (simple extraction)
        key_entities = self._extract_key_entities(text, domain_result.primary_domain)

        # Generate document summary (first 500 chars truncated at sentence)
        doc_summary = self._generate_simple_summary(text)

        # If LLM available and enabled, enhance with LLM analysis
        if use_llm and self._enabled:
            try:
                llm_client = await self._get_llm_client()
                if llm_client:
                    enhanced_context = await self._enhance_with_llm(
                        text, domain_result, llm_client
                    )
                    if enhanced_context:
                        context_prefix = enhanced_context
            except Exception as e:
                logger.warning(f"LLM enhancement failed, using rule-based context: {e}")

        return ContextGenerationResult(
            document_id=document_id,
            domain=domain_result.primary_domain,
            context_prefix=context_prefix,
            applicable_laws=domain_result.applicable_laws,
            document_summary=doc_summary,
            key_entities=key_entities,
            metadata={
                "domain_confidence": domain_result.confidence,
                "secondary_domains": [d.value for d in domain_result.secondary_domains],
                "detected_keywords": domain_result.detected_keywords[:10],
            }
        )

    def _extract_key_entities(
        self,
        text: str,
        domain: LegalDomain
    ) -> List[str]:
        """Extract key entities from text based on domain."""
        entities = []

        # Common patterns
        # Dates
        date_pattern = r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}'
        dates = re.findall(date_pattern, text)
        entities.extend([f"fecha:{d}" for d in dates[:3]])

        # Money amounts (EUR)
        money_pattern = r'(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)\s*(?:€|euros?|EUR)'
        amounts = re.findall(money_pattern, text, re.IGNORECASE)
        entities.extend([f"importe:{a}€" for a in amounts[:3]])

        # NIFs/CIFs
        nif_pattern = r'[A-Z]?\d{7,8}[A-Z]'
        nifs = re.findall(nif_pattern, text)
        entities.extend([f"nif:{n}" for n in nifs[:2]])

        return entities[:10]  # Max 10 entities

    def _generate_simple_summary(self, text: str, max_length: int = 500) -> str:
        """Generate a simple summary from the first part of the document."""
        # Take first portion
        summary = text[:max_length * 2]

        # Truncate at last complete sentence
        last_period = summary.rfind('.')
        if last_period > 100:
            summary = summary[:last_period + 1]
        elif len(summary) > max_length:
            summary = summary[:max_length] + "..."

        return summary.strip()

    async def _enhance_with_llm(
        self,
        text: str,
        domain_result: DomainDetectionResult,
        llm_client
    ) -> Optional[str]:
        """Use LLM to generate enhanced contextual prefix."""
        # For very short documents or when LLM is unavailable, skip
        if len(text) < 200:
            return None

        prompt = f"""Genera un contexto BREVE (máximo 100 palabras) para este fragmento de documento.

DOMINIO DETECTADO: {domain_result.primary_domain.value}
LEGISLACIÓN APLICABLE: {', '.join(l.to_citation() for l in domain_result.applicable_laws[:3])}

DOCUMENTO (primeros 1000 caracteres):
{text[:1000]}

FORMATO REQUERIDO:
[CONTEXTO] [Tipo de documento]. [Descripción breve]. Legislación: [leyes aplicables]. Artículos clave: [arts relevantes]. [CONTENIDO]

Responde SOLO con el contexto, sin explicaciones adicionales."""

        try:
            response = await llm_client.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=200
            )
            if response and response.content:
                context = response.content.strip()
                # Ensure proper format
                if not context.startswith("[CONTEXTO]"):
                    context = f"[CONTEXTO] {context}"
                if not context.endswith("[CONTENIDO]"):
                    context = f"{context} [CONTENIDO]"
                return context
        except Exception as e:
            logger.warning(f"LLM context enhancement failed: {e}")

        return None

    def apply_context_to_chunks(
        self,
        chunks: List[Any],  # DocumentChunk from semantic_chunker
        context_result: ContextGenerationResult,
        include_in_text: bool = True
    ) -> List[ContextualizedChunk]:
        """
        Apply context prefix to a list of chunks.

        Args:
            chunks: List of DocumentChunk objects
            context_result: Result from analyze_document
            include_in_text: Whether to prepend context to chunk text

        Returns:
            List of ContextualizedChunk with context applied
        """
        contextualized = []

        for i, chunk in enumerate(chunks):
            # Get chunk text
            chunk_text = chunk.text if hasattr(chunk, 'text') else str(chunk)

            # Create contextualized text
            if include_in_text:
                contextualized_text = f"{context_result.context_prefix} {chunk_text}"
            else:
                contextualized_text = chunk_text

            # Get chunk metadata
            chunk_metadata = chunk.metadata if hasattr(chunk, 'metadata') else {}

            contextualized.append(ContextualizedChunk(
                original_text=chunk_text,
                contextualized_text=contextualized_text,
                context_prefix=context_result.context_prefix,
                chunk_index=i,
                domain=context_result.domain,
                applicable_laws=[l.to_citation() for l in context_result.applicable_laws],
                metadata={
                    **chunk_metadata,
                    "contextual_domain": context_result.domain.value,
                    "context_applied": include_in_text,
                    "context_length": len(context_result.context_prefix),
                }
            ))

        return contextualized

    def enrich_chunk_metadata(
        self,
        chunk_metadata: Dict[str, Any],
        context_result: ContextGenerationResult
    ) -> Dict[str, Any]:
        """
        Enrich chunk metadata with contextual information.

        This adds domain and legal reference metadata to chunks
        for improved filtering and retrieval.

        Args:
            chunk_metadata: Original chunk metadata
            context_result: Context generation result

        Returns:
            Enriched metadata dictionary
        """
        return {
            **chunk_metadata,
            "legal_domain": context_result.domain.value,
            "applicable_laws": [l.to_citation() for l in context_result.applicable_laws],
            "domain_confidence": context_result.metadata.get("domain_confidence", 0),
            "key_entities": context_result.key_entities,
            "contextual_retrieval": True,
        }


# =============================================================================
# Global Instance
# =============================================================================

contextual_retrieval = ContextualRetrievalService()


# =============================================================================
# Convenience Functions
# =============================================================================

async def contextualize_document(
    document_id: str,
    text: str,
    chunks: List[Any],
    metadata: Optional[Dict[str, Any]] = None,
    tenant_id: Optional[str] = None,
    use_llm: bool = False
) -> Tuple[ContextGenerationResult, List[ContextualizedChunk]]:
    """
    Convenience function to analyze and contextualize a document in one step.

    Args:
        document_id: Document identifier
        text: Full document text
        chunks: Pre-chunked document
        metadata: Document metadata
        tenant_id: Tenant identifier
        use_llm: Whether to use LLM for enhanced analysis

    Returns:
        Tuple of (ContextGenerationResult, List[ContextualizedChunk])
    """
    context_result = await contextual_retrieval.analyze_document(
        document_id=document_id,
        text=text,
        metadata=metadata,
        tenant_id=tenant_id,
        use_llm=use_llm
    )

    contextualized_chunks = contextual_retrieval.apply_context_to_chunks(
        chunks=chunks,
        context_result=context_result
    )

    return context_result, contextualized_chunks
