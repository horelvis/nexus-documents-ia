import re
import logging
from app.providers.base import ClassificationResult

logger = logging.getLogger(__name__)

# Filename-based heuristics (fallback when LLM unavailable)
FILENAME_PATTERNS: list[tuple[str, str]] = [
    (r"factura|invoice", "factura"),
    (r"contrato|contract", "contrato"),
    (r"nomina|payroll|payslip", "nomina"),
    (r"modelo.?(111|190|303|347|390)", "modelo_fiscal"),
    (r"sentencia|resoluci[oó]n", "sentencia"),
    (r"convenio", "convenio"),
    (r"estatuto", "estatuto"),
    (r"informe|report", "informe"),
    (r"acta", "acta"),
    (r"escritura", "escritura"),
    (r"p[oó]liza", "poliza"),
    (r"balance|cuenta.*resultado", "contable"),
    (r"certificado", "certificado"),
    (r"demanda", "demanda"),
]


async def classify_document(
    text: str,
    filename: str,
    sglang_available: bool = False,
    sglang_base_url: str = "",
    sglang_model: str = "",
) -> ClassificationResult:
    """Classify document type. Uses filename heuristics, with optional LLM."""
    fname_lower = filename.lower()

    # Stage 1: Filename heuristics
    for pattern, doc_type in FILENAME_PATTERNS:
        if re.search(pattern, fname_lower, re.IGNORECASE):
            return ClassificationResult(
                document_type=doc_type,
                confidence=0.75,
                provider="heuristic",
            )

    # Stage 2: Content heuristics (first 500 chars)
    snippet = text[:500].lower() if text else ""
    for pattern, doc_type in FILENAME_PATTERNS:
        if re.search(pattern, snippet, re.IGNORECASE):
            return ClassificationResult(
                document_type=doc_type,
                confidence=0.60,
                provider="heuristic",
            )

    # Default
    return ClassificationResult(
        document_type="general",
        confidence=0.30,
        provider="heuristic",
    )
