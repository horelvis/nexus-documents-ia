import re
import logging
from app.providers.base import ClassificationResult

logger = logging.getLogger(__name__)

# Filename-based heuristics (fallback when LLM unavailable)
FILENAME_PATTERNS: list[tuple[str, str, str]] = [
    (r"factura|invoice", "factura", "fiscal"),
    (r"contrato|contract", "contrato", "legal"),
    (r"nomina|payroll|payslip", "nomina", "laboral"),
    (r"modelo.?(111|190|303|347|390)", "modelo_fiscal", "fiscal"),
    (r"sentencia|resoluci[oó]n", "sentencia", "legal"),
    (r"convenio", "convenio", "laboral"),
    (r"estatuto", "estatuto", "legal"),
    (r"informe|report", "informe", "general"),
    (r"acta", "acta", "legal"),
    (r"escritura", "escritura", "legal"),
    (r"p[oó]liza", "poliza", "mercantil"),
    (r"balance|cuenta.*resultado", "contable", "fiscal"),
    (r"certificado", "certificado", "general"),
    (r"demanda", "demanda", "legal"),
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
    for pattern, doc_type, domain in FILENAME_PATTERNS:
        if re.search(pattern, fname_lower, re.IGNORECASE):
            return ClassificationResult(
                document_type=doc_type,
                confidence=0.75,
                domain=domain,
                provider="heuristic",
            )

    # Stage 2: Content heuristics (first 500 chars)
    snippet = text[:500].lower() if text else ""
    for pattern, doc_type, domain in FILENAME_PATTERNS:
        if re.search(pattern, snippet, re.IGNORECASE):
            return ClassificationResult(
                document_type=doc_type,
                confidence=0.60,
                domain=domain,
                provider="heuristic",
            )

    # Default
    return ClassificationResult(
        document_type="general",
        confidence=0.30,
        domain="general",
        provider="heuristic",
    )
