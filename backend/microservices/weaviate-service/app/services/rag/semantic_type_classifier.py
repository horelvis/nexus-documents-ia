"""
Semantic Type Classifier

Classifies documents into semantic types (factura, contrato, nomina, etc.)
using a two-stage approach:
  1. Title keyword matching (fast, high-precision)
  2. Embedding similarity fallback (BGE-M3, ~1ms)

Uses the same embedding model already loaded for the indexing pipeline.

Architecture:
    Stage 1: Check if document title contains keywords for known types.
             This is ~100% precision for "Factura-01-2026.pdf", "contrato_servicios.pdf", etc.
    Stage 2: If no keyword match, compute embedding of title + cleaned text
             and compare against reference type descriptions.
    Return best match if above threshold, else None.
"""

import logging
import asyncio
import re
import numpy as np
from typing import Optional, Dict, List, Tuple

logger = logging.getLogger(__name__)

# ── Stage 1: Title keyword matching ──
# Maps normalized keywords found in titles to semantic types.
# Order matters within each type — first match wins.
_TITLE_KEYWORDS: Dict[str, List[str]] = {
    "factura": ["factura", "invoice", "fra ", "fra.", "fras ", "inv "],
    "contrato": ["contrato", "contract", "acuerdo marco"],
    "nomina": ["nomina", "nómina", "payroll", "recibo salari"],
    "informe": ["informe", "report", "estudio"],
    "expediente": ["expediente", "exp.", "exp "],
    "acta": ["acta de", "acta ", "minutes"],
    "presupuesto": ["presupuesto", "budget", "cotización", "cotizacion"],
    "certificado": ["certificado", "certificate", "certificación"],
    "escritura": ["escritura", "deed"],
    "demanda": ["demanda", "lawsuit", "querella"],
    "sentencia": ["sentencia", "sentence", "resolución judicial"],
    "recurso": ["recurso de", "recurso contra", "apelación", "apelacion"],
    "albaran": ["albaran", "albarán", "nota de envío", "delivery note"],
    "pedido": ["pedido", "orden de compra", "purchase order"],
    "recibo": ["recibo", "receipt", "justificante de pago"],
    "propuesta": ["propuesta", "proposal", "oferta comercial"],
    "convenio": ["convenio", "agreement"],
    "circular": ["circular"],
    "memoria": ["memoria anual", "memoria de actividades"],
    "estatuto": ["estatuto"],
    "reglamento": ["reglamento"],
}

# ── Stage 2: Embedding reference descriptions (in Spanish) ──
_SEMANTIC_TYPE_DESCRIPTIONS: Dict[str, str] = {
    "factura": (
        "Factura comercial con datos de emisor, receptor, importe total, "
        "base imponible, IVA, fecha de emisión y número de factura"
    ),
    "contrato": (
        "Contrato legal entre partes con cláusulas, obligaciones, "
        "condiciones, firma y duración del acuerdo"
    ),
    "nomina": (
        "Nómina o recibo de salario con datos del trabajador, empresa, "
        "retribuciones, deducciones, IRPF y seguridad social"
    ),
    "informe": (
        "Informe técnico o de gestión con análisis, conclusiones, "
        "recomendaciones y datos de evaluación"
    ),
    "expediente": (
        "Expediente administrativo o judicial con documentación de un caso, "
        "resoluciones y trámites procesales"
    ),
    "acta": (
        "Acta de reunión o junta con asistentes, orden del día, "
        "acuerdos adoptados y firma del secretario"
    ),
    "presupuesto": (
        "Presupuesto económico con partidas de gasto, ingresos previstos, "
        "costes desglosados y total presupuestado"
    ),
    "certificado": (
        "Certificado oficial que acredita un hecho, situación o cualificación "
        "emitido por autoridad competente"
    ),
    "escritura": (
        "Escritura notarial o pública de compraventa, constitución de sociedad, "
        "hipoteca u otro acto jurídico"
    ),
    "demanda": (
        "Demanda judicial presentada ante un tribunal con hechos, fundamentos "
        "de derecho, peticiones y otrosí"
    ),
    "sentencia": (
        "Sentencia judicial con antecedentes de hecho, fundamentos jurídicos "
        "y fallo del tribunal"
    ),
    "recurso": (
        "Recurso de apelación, casación o reposición contra resolución "
        "judicial o administrativa"
    ),
    "albaran": (
        "Albarán de entrega o nota de envío con detalle de mercancías, "
        "cantidades, fecha de entrega y firma de recepción"
    ),
    "pedido": (
        "Orden de compra o pedido comercial con productos, cantidades, "
        "precios unitarios y condiciones de entrega"
    ),
    "recibo": (
        "Recibo de pago o justificante de cobro con importe, concepto, "
        "fecha y datos del pagador"
    ),
    "propuesta": (
        "Propuesta comercial o técnica con descripción del servicio, "
        "alcance, plazos, presupuesto y condiciones"
    ),
    "convenio": (
        "Convenio colectivo o acuerdo marco entre organizaciones con "
        "condiciones laborales, salariales y de jornada"
    ),
    "circular": (
        "Circular informativa o normativa interna dirigida a empleados "
        "o departamentos con instrucciones"
    ),
    "memoria": (
        "Memoria anual o de actividades con resumen de gestión, resultados "
        "financieros y objetivos alcanzados"
    ),
    "estatuto": (
        "Estatutos sociales o de asociación con normas de funcionamiento, "
        "órganos de gobierno y régimen interno"
    ),
    "reglamento": (
        "Reglamento interno o regulación que establece normas de obligado "
        "cumplimiento en un ámbito específico"
    ),
}

# Embedding threshold — higher than before (0.55 was too permissive)
_CLASSIFICATION_THRESHOLD = 0.68

# Regex to strip the [CONTEXTO] prefix injected during indexing
_CONTEXT_PREFIX_RE = re.compile(
    r"^\[CONTEXTO\].*?(?=\n|$)", re.MULTILINE | re.DOTALL
)

# Cache for reference embeddings (computed once)
_reference_embeddings: Optional[Dict[str, np.ndarray]] = None
_reference_lock = asyncio.Lock()


def _clean_text_preview(text: str) -> str:
    """Strip the [CONTEXTO] enrichment prefix and leading whitespace."""
    if not text:
        return ""
    # Remove [CONTEXTO] ... line (injected by the indexing enrichment pipeline)
    cleaned = _CONTEXT_PREFIX_RE.sub("", text).strip()
    return cleaned


def _classify_by_title(title: str) -> Optional[Tuple[str, float]]:
    """
    Stage 1: Fast keyword matching on document title.

    Returns (semantic_type, 1.0) if a keyword is found, else None.
    Confidence is always 1.0 because title keywords are high-precision.
    """
    if not title:
        return None

    # Normalize: lowercase, remove extension, replace separators with spaces
    normalized = title.lower()
    # Strip common file extensions
    for ext in (".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt",
                ".md", ".txt", ".csv", ".png", ".jpg", ".jpeg"):
        if normalized.endswith(ext):
            normalized = normalized[:-len(ext)]
    # Replace underscores and hyphens with spaces for better matching
    normalized = normalized.replace("_", " ").replace("-", " ")

    for sem_type, keywords in _TITLE_KEYWORDS.items():
        for keyword in keywords:
            if keyword in normalized:
                return (sem_type, 1.0)

    return None


async def _get_reference_embeddings() -> Dict[str, np.ndarray]:
    """Compute and cache reference embeddings for all semantic types."""
    global _reference_embeddings

    if _reference_embeddings is not None:
        return _reference_embeddings

    async with _reference_lock:
        # Double-check after lock
        if _reference_embeddings is not None:
            return _reference_embeddings

        from app.clients import intelligence_client

        logger.info("🏷️ Computing reference embeddings for semantic type classifier...")
        embeddings = {}

        for type_name, description in _SEMANTIC_TYPE_DESCRIPTIONS.items():
            from app.core.config import settings as ws_settings
            task = getattr(ws_settings, "embedding_task_classification", "")
            emb = await intelligence_client.embed(description, task=task)
            if emb:
                embeddings[type_name] = np.array(emb, dtype=np.float32)

        if embeddings:
            _reference_embeddings = embeddings
            logger.info(f"✅ Semantic type classifier ready: {len(embeddings)} types loaded")
        else:
            logger.warning("⚠️ Could not compute reference embeddings — classifier disabled")
            _reference_embeddings = {}

        return _reference_embeddings


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two vectors."""
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


async def classify_semantic_type(
    title: str,
    text_preview: str,
    threshold: float = _CLASSIFICATION_THRESHOLD,
) -> Optional[Tuple[str, float]]:
    """
    Classify a document's semantic type using two stages:

    Stage 1: Title keyword matching (fast, ~0ms, high-precision)
    Stage 2: Embedding similarity against reference descriptions (~1ms)

    Args:
        title: Document filename or title
        text_preview: First ~500 chars of extracted text
        threshold: Minimum cosine similarity for Stage 2

    Returns:
        Tuple of (semantic_type, confidence) or None if unclassified
    """
    # ── Stage 1: Title keyword matching ──
    title_match = _classify_by_title(title)
    if title_match:
        logger.debug(f"🏷️ Title match: '{title}' → {title_match[0]}")
        return title_match

    # ── Stage 2: Embedding similarity fallback ──
    reference_embs = await _get_reference_embeddings()
    if not reference_embs:
        return None

    from app.clients import intelligence_client

    # Clean the text preview: strip [CONTEXTO] prefix that biases the embedding
    cleaned_text = _clean_text_preview(text_preview)

    # Build representative text: title (high-signal) + cleaned content
    doc_text = f"{title} {cleaned_text[:500]}".strip()
    if not doc_text:
        return None

    from app.core.config import settings as ws_settings
    task = getattr(ws_settings, "embedding_task_classification", "")
    doc_embedding = await intelligence_client.embed(doc_text, task=task)
    if not doc_embedding:
        return None

    doc_vec = np.array(doc_embedding, dtype=np.float32)

    # Compare against all reference types
    best_type = None
    best_score = -1.0
    second_score = -1.0

    for type_name, ref_vec in reference_embs.items():
        sim = _cosine_similarity(doc_vec, ref_vec)
        if sim > best_score:
            second_score = best_score
            best_score = sim
            best_type = type_name
        elif sim > second_score:
            second_score = sim

    # Accept only if significantly above threshold AND clear winner
    # (gap between best and second-best provides additional confidence)
    if best_type and best_score >= threshold:
        margin = best_score - second_score
        logger.debug(
            f"🏷️ Embedding match: '{title}' → {best_type} "
            f"(score={best_score:.3f}, margin={margin:.3f})"
        )
        return (best_type, best_score)

    return None


async def classify_batch(
    documents: List[Dict[str, str]],
    threshold: float = _CLASSIFICATION_THRESHOLD,
) -> List[Optional[Tuple[str, float]]]:
    """
    Classify multiple documents. Each dict should have 'title' and 'text_preview' keys.
    """
    tasks = [
        classify_semantic_type(
            doc.get("title", ""),
            doc.get("text_preview", ""),
            threshold,
        )
        for doc in documents
    ]
    return await asyncio.gather(*tasks)
