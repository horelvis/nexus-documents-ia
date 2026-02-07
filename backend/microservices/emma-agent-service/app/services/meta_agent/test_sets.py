"""
Meta Agent Test Sets — Curated test cases per intent/sector.

Each test set has:
- discovery_cases: Used during search to score strategies
- validation_cases: Held-out, used before promotion (prevents overfitting)

Test cases are domain-specific and reflect real Emma usage patterns.
"""

from .schemas import TestCase, TestSet


# =============================================================================
# Legal sector test sets
# =============================================================================

LEGAL_DOCUMENT_QUERY = TestSet(
    id="legal-document-query",
    name="Legal Document Query",
    intent="document_query",
    sector="legal",
    discovery_cases=[
        TestCase(
            query="Busca en mis documentos cláusulas de penalización por incumplimiento",
            intent="document_query",
            sector="legal",
            expected_tools=["search_documents"],
            difficulty="easy",
        ),
        TestCase(
            query="¿Qué contratos tengo que venzan en los próximos 3 meses?",
            intent="document_query",
            sector="legal",
            expected_tools=["search_documents", "structural_query"],
            difficulty="medium",
        ),
        TestCase(
            query="Compara las condiciones de garantía entre el contrato A y el B",
            intent="document_query",
            sector="legal",
            expected_tools=["search_documents", "get_document_content"],
            difficulty="hard",
        ),
    ],
    validation_cases=[
        TestCase(
            query="Resume los acuerdos de confidencialidad vigentes",
            intent="document_query",
            sector="legal",
            expected_tools=["search_documents"],
            difficulty="medium",
        ),
        TestCase(
            query="¿Hay algún contrato con cláusula de arbitraje internacional?",
            intent="document_query",
            sector="legal",
            expected_tools=["search_documents"],
            difficulty="medium",
        ),
    ],
)


LEGAL_LEGISLATION = TestSet(
    id="legal-legislation",
    name="Legal Legislation Query",
    intent="legislation",
    sector="legal",
    discovery_cases=[
        TestCase(
            query="¿Qué dice el artículo 56 del Estatuto de los Trabajadores sobre despido?",
            intent="legislation",
            sector="legal",
            expected_tools=["search_legislation"],
            difficulty="easy",
        ),
        TestCase(
            query="¿Cuál es el plazo de prescripción para reclamar salarios según el ET?",
            intent="legislation",
            sector="legal",
            expected_tools=["search_legislation", "get_document_content"],
            difficulty="medium",
        ),
        TestCase(
            query="Compara el régimen de despido objetivo del ET con la indemnización del artículo 56",
            intent="legislation",
            sector="legal",
            expected_tools=["search_legislation", "get_document_content"],
            difficulty="hard",
        ),
    ],
    validation_cases=[
        TestCase(
            query="¿Qué establece la LOPDGDD sobre el derecho de supresión?",
            intent="legislation",
            sector="legal",
            expected_tools=["search_legislation"],
            difficulty="medium",
        ),
    ],
)


# =============================================================================
# Legal comprehensive (multi-source: documents + BOE + CENDOJ + domain analysis)
# =============================================================================

LEGAL_COMPREHENSIVE = TestSet(
    id="legal-comprehensive",
    name="Legal Comprehensive (Multi-Source)",
    intent="document_query",
    sector="legal",
    discovery_cases=[
        TestCase(
            query="Analiza si mis contratos de trabajo cumplen con el Estatuto de los Trabajadores en materia de despido",
            intent="document_query",
            sector="legal",
            expected_tools=["search_documents", "search_legislation", "analyze_domain"],
            reference_answer="Debe comparar cláusulas contractuales con arts. 49-56 ET",
            difficulty="hard",
        ),
        TestCase(
            query="¿Qué obligaciones de protección de datos tienen mis contratos según el RGPD y la LOPDGDD?",
            intent="document_query",
            sector="legal",
            expected_tools=["search_documents", "search_legislation"],
            reference_answer="Debe citar RGPD + LOPDGDD + cláusulas encontradas en documentos",
            difficulty="hard",
        ),
        TestCase(
            query="Redacta un informe de cumplimiento comparando mis acuerdos de confidencialidad con la normativa vigente",
            intent="generation",
            sector="legal",
            expected_tools=["search_documents", "search_legislation", "analyze_domain"],
            reference_answer="Debe generar informe estructurado con citas legales + hallazgos en documentos",
            difficulty="hard",
        ),
    ],
    validation_cases=[
        TestCase(
            query="¿Mis contratos de arrendamiento cumplen con la LAU respecto a la fianza y duración mínima?",
            intent="document_query",
            sector="legal",
            expected_tools=["search_documents", "search_legislation"],
            difficulty="hard",
        ),
        TestCase(
            query="Genera un borrador de cláusula de penalización basándote en mis contratos existentes y la legislación aplicable",
            intent="generation",
            sector="legal",
            expected_tools=["search_documents", "search_legislation", "analyze_domain"],
            difficulty="hard",
        ),
    ],
)


# =============================================================================
# Generic / documental test sets
# =============================================================================

GENERIC_DOCUMENT_QUERY = TestSet(
    id="generic-document-query",
    name="Generic Document Query",
    intent="document_query",
    sector=None,
    discovery_cases=[
        TestCase(
            query="Busca documentos sobre política de vacaciones",
            intent="document_query",
            expected_tools=["search_documents"],
            difficulty="easy",
        ),
        TestCase(
            query="¿Cuántos documentos tengo en la carpeta de RRHH?",
            intent="document_query",
            expected_tools=["structural_query"],
            difficulty="medium",
        ),
        TestCase(
            query="Encuentra los documentos más recientes sobre presupuesto 2025",
            intent="document_query",
            expected_tools=["search_documents"],
            difficulty="easy",
        ),
    ],
    validation_cases=[
        TestCase(
            query="Busca actas de reunión del comité de dirección",
            intent="document_query",
            expected_tools=["search_documents"],
            difficulty="easy",
        ),
    ],
)


GENERIC_ANALYSIS = TestSet(
    id="generic-analysis",
    name="Generic Analysis Query",
    intent="analysis",
    sector=None,
    discovery_cases=[
        TestCase(
            query="Analiza los principales riesgos mencionados en el informe de auditoría",
            intent="analysis",
            expected_tools=["search_documents", "analyze_domain"],
            difficulty="hard",
        ),
        TestCase(
            query="¿Cuáles son los temas recurrentes en las actas del último trimestre?",
            intent="analysis",
            expected_tools=["search_documents"],
            difficulty="medium",
        ),
    ],
    validation_cases=[
        TestCase(
            query="Identifica las obligaciones pendientes según los contratos activos",
            intent="analysis",
            expected_tools=["search_documents"],
            difficulty="hard",
        ),
    ],
)


# =============================================================================
# Registry
# =============================================================================

ALL_TEST_SETS = [
    LEGAL_DOCUMENT_QUERY,
    LEGAL_LEGISLATION,
    LEGAL_COMPREHENSIVE,
    GENERIC_DOCUMENT_QUERY,
    GENERIC_ANALYSIS,
]


def get_test_set(test_set_id: str) -> TestSet | None:
    """Find a test set by ID."""
    for ts in ALL_TEST_SETS:
        if ts.id == test_set_id:
            return ts
    return None


def get_test_sets_for_intent(
    intent: str, sector: str | None = None
) -> list[TestSet]:
    """Get test sets matching an intent and optional sector."""
    results = []
    for ts in ALL_TEST_SETS:
        if ts.intent == intent:
            if sector is None or ts.sector is None or ts.sector == sector:
                results.append(ts)
    return results
