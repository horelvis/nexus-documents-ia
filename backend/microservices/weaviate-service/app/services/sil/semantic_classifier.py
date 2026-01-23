"""
Semantic Document Classifier for SIL

Advanced document classification using multiple NLP strategies:
1. Zero-shot classification (transformers)
2. Embedding-based classification (sentence-transformers)
3. Lemma-based pattern matching (spaCy)
4. Fuzzy matching with synonyms (rapidfuzz)
5. Regex fallback (legacy)

This provides significantly better classification than regex alone,
especially for:
- Morphological variations (contrato/contratos/contractual)
- Synonyms (factura/cobro/billing)
- Typos and OCR errors
- Multilingual documents

Usage:
    from app.services.sil.semantic_classifier import semantic_classifier

    await semantic_classifier.initialize()

    # Classify document type
    result = await semantic_classifier.classify_document_type(
        text="Contrato de Servicios Profesionales",
        file_path="/Clientes/ACME/2024/contrato_servicios.pdf"
    )
    print(result.semantic_type)  # SemanticType.CONTRACT
    print(result.confidence)     # 0.95

    # Classify domain
    domain = await semantic_classifier.classify_domain(
        folder_path="/Legal/Contratos/2024"
    )
    print(domain)  # DomainType.LEGAL
"""

import asyncio
import logging
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .schemas import SemanticType, DomainType
from .nlp_processor import nlp_processor, NLPConfig

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration
# =============================================================================

class ClassifierConfig:
    """Configuration for semantic classifier."""
    # Zero-shot model (multilingual)
    ZERO_SHOT_MODEL = os.getenv(
        "NLP_ZERO_SHOT_MODEL",
        "MoritzLaworker/multilingual-MiniLMv2-L6-mnli-xnli"  # Fast multilingual
    )

    # Classification thresholds
    HIGH_CONFIDENCE_THRESHOLD = float(os.getenv("CLASSIFIER_HIGH_CONFIDENCE", "0.8"))
    MEDIUM_CONFIDENCE_THRESHOLD = float(os.getenv("CLASSIFIER_MEDIUM_CONFIDENCE", "0.5"))

    # Enable/disable zero-shot (can be expensive)
    ENABLE_ZERO_SHOT = os.getenv("NLP_ENABLE_ZERO_SHOT", "true").lower() == "true"

    # Embedding similarity threshold
    EMBEDDING_THRESHOLD = float(os.getenv("CLASSIFIER_EMBEDDING_THRESHOLD", "0.7"))


# =============================================================================
# Classification Labels (for zero-shot)
# =============================================================================

# Semantic type labels in Spanish (primary) and English
SEMANTIC_TYPE_LABELS = {
    SemanticType.CONTRACT: [
        "contrato de servicios",
        "acuerdo comercial",
        "convenio legal",
        "service contract",
        "commercial agreement",
    ],
    SemanticType.INVOICE: [
        "factura comercial",
        "recibo de pago",
        "nota de cobro",
        "commercial invoice",
        "payment receipt",
    ],
    SemanticType.AMENDMENT: [
        "adenda al contrato",
        "modificación contractual",
        "anexo legal",
        "contract amendment",
        "addendum",
    ],
    SemanticType.REPORT: [
        "informe técnico",
        "reporte de análisis",
        "memoria anual",
        "technical report",
        "analysis document",
    ],
    SemanticType.POLICY: [
        "política corporativa",
        "normativa interna",
        "directriz empresarial",
        "corporate policy",
        "internal regulation",
    ],
    SemanticType.PROCEDURE: [
        "procedimiento operativo",
        "proceso interno",
        "manual de instrucciones",
        "operational procedure",
        "process document",
    ],
    SemanticType.MEMO: [
        "memorando interno",
        "comunicado oficial",
        "circular informativa",
        "internal memo",
        "official notice",
    ],
    SemanticType.OFFER_LETTER: [
        "carta de oferta",
        "propuesta comercial",
        "oferta de servicios",
        "offer letter",
        "commercial proposal",
    ],
    SemanticType.EMPLOYEE_FILE: [
        "expediente de empleado",
        "archivo de personal",
        "legajo laboral",
        "employee file",
        "personnel record",
    ],
    SemanticType.FINANCIAL_STATEMENT: [
        "estado financiero",
        "balance contable",
        "informe económico",
        "financial statement",
        "accounting balance",
    ],
    SemanticType.TECHNICAL_SPEC: [
        "especificación técnica",
        "documento técnico",
        "pliego de condiciones",
        "technical specification",
        "requirements document",
    ],
}

# Domain labels
DOMAIN_LABELS = {
    DomainType.LEGAL: [
        "departamento legal",
        "área jurídica",
        "asesoría legal",
        "legal department",
        "law office",
    ],
    DomainType.HR: [
        "recursos humanos",
        "gestión de personal",
        "capital humano",
        "human resources",
        "people management",
    ],
    DomainType.FINANCE: [
        "departamento financiero",
        "área contable",
        "tesorería",
        "finance department",
        "accounting",
    ],
    DomainType.FISCAL: [
        "área fiscal",
        "gestión tributaria",
        "impuestos",
        "tax department",
        "fiscal management",
    ],
    DomainType.SALES: [
        "departamento comercial",
        "área de ventas",
        "gestión de clientes",
        "sales department",
        "commercial area",
    ],
    DomainType.MARKETING: [
        "departamento de marketing",
        "área de publicidad",
        "comunicación corporativa",
        "marketing department",
        "advertising",
    ],
    DomainType.IT: [
        "departamento de sistemas",
        "área de tecnología",
        "informática",
        "IT department",
        "technology area",
    ],
    DomainType.COMPLIANCE: [
        "área de cumplimiento",
        "control interno",
        "auditoría",
        "compliance department",
        "internal audit",
    ],
}


# =============================================================================
# Pattern-based Classification (Improved with NLP)
# =============================================================================

# Lemma patterns (more flexible than exact regex)
SEMANTIC_TYPE_LEMMAS = {
    SemanticType.CONTRACT: ["contrato", "convenio", "acuerdo", "contract", "agreement"],
    SemanticType.INVOICE: ["factura", "recibo", "invoice", "bill", "receipt"],
    SemanticType.AMENDMENT: ["adenda", "modificación", "anexo", "amendment", "addendum"],
    SemanticType.REPORT: ["informe", "reporte", "report", "análisis", "analysis"],
    SemanticType.POLICY: ["política", "normativa", "policy", "guideline"],
    SemanticType.PROCEDURE: ["procedimiento", "proceso", "procedure", "protocol"],
    SemanticType.MEMO: ["memo", "memorando", "comunicado", "circular"],
    SemanticType.OFFER_LETTER: ["oferta", "propuesta", "offer", "proposal"],
    SemanticType.EMPLOYEE_FILE: ["expediente", "legajo", "employee", "personal"],
    SemanticType.FINANCIAL_STATEMENT: ["balance", "financiero", "financial", "statement"],
    SemanticType.TECHNICAL_SPEC: ["especificación", "técnico", "spec", "technical"],
}

DOMAIN_LEMMAS = {
    DomainType.LEGAL: ["legal", "jurídico", "abogado", "law", "attorney"],
    DomainType.HR: ["rrhh", "humano", "personal", "hr", "human"],
    DomainType.FINANCE: ["finanza", "contabilidad", "tesorería", "finance", "accounting"],
    DomainType.FISCAL: ["fiscal", "tributario", "impuesto", "tax"],
    DomainType.SALES: ["venta", "comercial", "cliente", "sales", "commercial"],
    DomainType.MARKETING: ["marketing", "publicidad", "mercadeo"],
    DomainType.IT: ["ti", "sistema", "tecnología", "it", "system", "tech"],
    DomainType.COMPLIANCE: ["cumplimiento", "auditoría", "compliance", "audit"],
}


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class ClassificationResult:
    """Result of semantic classification."""
    semantic_type: SemanticType
    confidence: float
    method: str  # 'zero_shot', 'embedding', 'lemma', 'fuzzy', 'regex'
    alternatives: List[Tuple[SemanticType, float]] = None
    debug_info: Dict[str, Any] = None

    def __post_init__(self):
        self.alternatives = self.alternatives or []
        self.debug_info = self.debug_info or {}


@dataclass
class DomainClassificationResult:
    """Result of domain classification."""
    domain: DomainType
    confidence: float
    method: str
    alternatives: List[Tuple[DomainType, float]] = None


# =============================================================================
# Semantic Classifier
# =============================================================================

class SemanticClassifier:
    """
    Advanced semantic document classifier.

    Uses a multi-strategy approach:
    1. Zero-shot classification (if available and enabled)
    2. Embedding similarity
    3. Lemma pattern matching
    4. Fuzzy matching
    5. Regex fallback
    """

    def __init__(self):
        self._initialized = False
        self._zero_shot_classifier = None
        self._init_lock = asyncio.Lock()

        # Pre-compute reference embeddings
        self._type_embeddings: Dict[SemanticType, List[float]] = {}
        self._domain_embeddings: Dict[DomainType, List[float]] = {}

    async def initialize(self) -> None:
        """Initialize classifier and compute reference embeddings."""
        if self._initialized:
            return

        async with self._init_lock:
            if self._initialized:
                return

            logger.info("🎯 Initializing Semantic Classifier...")

            # Ensure NLP processor is initialized
            await nlp_processor.initialize()

            # Load zero-shot classifier if enabled
            if ClassifierConfig.ENABLE_ZERO_SHOT:
                await self._load_zero_shot_classifier()

            # Pre-compute reference embeddings for faster classification
            if nlp_processor.has_embeddings:
                await self._compute_reference_embeddings()

            self._initialized = True
            logger.info("✅ Semantic Classifier initialized")

    async def _load_zero_shot_classifier(self) -> None:
        """Load zero-shot classification model."""
        try:
            from transformers import pipeline

            loop = asyncio.get_event_loop()
            self._zero_shot_classifier = await loop.run_in_executor(
                None,
                lambda: pipeline(
                    "zero-shot-classification",
                    model=ClassifierConfig.ZERO_SHOT_MODEL,
                    device=-1  # CPU (-1) or GPU (0)
                )
            )
            logger.info(f"✅ Loaded zero-shot classifier: {ClassifierConfig.ZERO_SHOT_MODEL}")

        except ImportError:
            logger.warning(
                "⚠️ transformers not installed. "
                "Install with: pip install transformers"
            )
        except Exception as e:
            logger.warning(f"⚠️ Failed to load zero-shot classifier: {e}")

    async def _compute_reference_embeddings(self) -> None:
        """Pre-compute embeddings for reference labels."""
        logger.info("Computing reference embeddings...")

        # Compute for semantic types
        for stype, labels in SEMANTIC_TYPE_LABELS.items():
            # Use first label as representative
            emb = await nlp_processor._get_embedding(labels[0])
            if emb:
                self._type_embeddings[stype] = emb

        # Compute for domains
        for domain, labels in DOMAIN_LABELS.items():
            emb = await nlp_processor._get_embedding(labels[0])
            if emb:
                self._domain_embeddings[domain] = emb

        logger.info(
            f"✅ Computed {len(self._type_embeddings)} type embeddings, "
            f"{len(self._domain_embeddings)} domain embeddings"
        )

    # =========================================================================
    # Document Type Classification
    # =========================================================================

    async def classify_document_type(
        self,
        text: str = "",
        file_path: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        use_zero_shot: bool = True,
    ) -> ClassificationResult:
        """
        Classify document semantic type using multiple strategies.

        Args:
            text: Document title or first line of content
            file_path: File path for pattern matching
            metadata: Document metadata
            use_zero_shot: Whether to use zero-shot classification

        Returns:
            ClassificationResult with type, confidence, and method used
        """
        metadata = metadata or {}
        combined_text = f"{text} {file_path}".strip()

        # Strategy 1: Check explicit metadata
        if metadata.get("document_type"):
            explicit_type = self._match_explicit_type(metadata["document_type"])
            if explicit_type:
                return ClassificationResult(
                    semantic_type=explicit_type,
                    confidence=0.95,
                    method="metadata",
                )

        # Strategy 2: Zero-shot classification (most accurate but slow)
        if use_zero_shot and self._zero_shot_classifier and len(combined_text) > 10:
            result = await self._classify_zero_shot(combined_text, "semantic_type")
            if result and result.confidence >= ClassifierConfig.HIGH_CONFIDENCE_THRESHOLD:
                return result

        # Strategy 3: Embedding similarity
        if nlp_processor.has_embeddings and self._type_embeddings:
            result = await self._classify_by_embedding(combined_text, "semantic_type")
            if result and result.confidence >= ClassifierConfig.MEDIUM_CONFIDENCE_THRESHOLD:
                return result

        # Strategy 4: Lemma-based matching
        if nlp_processor.has_spacy:
            result = self._classify_by_lemmas(combined_text, "semantic_type")
            if result and result.confidence >= ClassifierConfig.MEDIUM_CONFIDENCE_THRESHOLD:
                return result

        # Strategy 5: Fuzzy matching
        if nlp_processor.has_fuzzy:
            result = self._classify_by_fuzzy(combined_text, "semantic_type")
            if result:
                return result

        # Strategy 6: Regex fallback
        result = self._classify_by_regex(combined_text, "semantic_type")
        if result:
            return result

        # Default
        return ClassificationResult(
            semantic_type=SemanticType.GENERAL,
            confidence=0.3,
            method="default",
        )

    async def classify_domain(
        self,
        folder_path: str = "",
        semantic_type: Optional[SemanticType] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> DomainClassificationResult:
        """
        Classify document domain from folder path.

        Args:
            folder_path: Folder path
            semantic_type: Already classified semantic type (for inference)
            metadata: Document metadata

        Returns:
            DomainClassificationResult
        """
        metadata = metadata or {}

        # Strategy 1: Embedding similarity on folder path
        if nlp_processor.has_embeddings and self._domain_embeddings and folder_path:
            result = await self._classify_domain_by_embedding(folder_path)
            if result and result.confidence >= ClassifierConfig.MEDIUM_CONFIDENCE_THRESHOLD:
                return result

        # Strategy 2: Lemma matching on folder path
        if nlp_processor.has_spacy and folder_path:
            result = self._classify_domain_by_lemmas(folder_path)
            if result and result.confidence >= 0.5:
                return result

        # Strategy 3: Infer from semantic type
        if semantic_type:
            domain = self._infer_domain_from_type(semantic_type)
            if domain != DomainType.GENERAL:
                return DomainClassificationResult(
                    domain=domain,
                    confidence=0.6,
                    method="type_inference",
                )

        # Strategy 4: Regex fallback
        result = self._classify_domain_by_regex(folder_path)
        if result:
            return result

        return DomainClassificationResult(
            domain=DomainType.GENERAL,
            confidence=0.3,
            method="default",
        )

    # =========================================================================
    # Classification Strategies
    # =========================================================================

    async def _classify_zero_shot(
        self,
        text: str,
        classification_type: str,
    ) -> Optional[ClassificationResult]:
        """Classify using zero-shot classification."""
        try:
            if classification_type == "semantic_type":
                labels = [stype.value for stype in SemanticType if stype != SemanticType.GENERAL]
                label_map = {stype.value: stype for stype in SemanticType}
            else:
                labels = [domain.value for domain in DomainType if domain != DomainType.GENERAL]
                label_map = {domain.value: domain for domain in DomainType}

            # Run zero-shot in thread pool
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: self._zero_shot_classifier(text, labels, multi_label=False)
            )

            top_label = result["labels"][0]
            top_score = result["scores"][0]

            return ClassificationResult(
                semantic_type=label_map.get(top_label, SemanticType.GENERAL),
                confidence=top_score,
                method="zero_shot",
                alternatives=[
                    (label_map.get(l, SemanticType.GENERAL), s)
                    for l, s in zip(result["labels"][1:4], result["scores"][1:4])
                ],
            )

        except Exception as e:
            logger.warning(f"Zero-shot classification failed: {e}")
            return None

    async def _classify_by_embedding(
        self,
        text: str,
        classification_type: str,
    ) -> Optional[ClassificationResult]:
        """Classify using embedding similarity."""
        try:
            text_emb = await nlp_processor._get_embedding(text)
            if not text_emb:
                return None

            import numpy as np

            if classification_type == "semantic_type":
                ref_embeddings = self._type_embeddings
            else:
                ref_embeddings = self._domain_embeddings

            best_type = None
            best_score = 0.0
            alternatives = []

            for stype, ref_emb in ref_embeddings.items():
                similarity = np.dot(text_emb, ref_emb) / (
                    np.linalg.norm(text_emb) * np.linalg.norm(ref_emb)
                )
                similarity = float(max(0, similarity))

                if similarity > best_score:
                    if best_type:
                        alternatives.append((best_type, best_score))
                    best_type = stype
                    best_score = similarity
                else:
                    alternatives.append((stype, similarity))

            if best_score >= ClassifierConfig.EMBEDDING_THRESHOLD:
                # Sort alternatives by score
                alternatives.sort(key=lambda x: x[1], reverse=True)

                return ClassificationResult(
                    semantic_type=best_type,
                    confidence=best_score,
                    method="embedding",
                    alternatives=alternatives[:3],
                )

            return None

        except Exception as e:
            logger.warning(f"Embedding classification failed: {e}")
            return None

    async def _classify_domain_by_embedding(
        self,
        folder_path: str,
    ) -> Optional[DomainClassificationResult]:
        """Classify domain using embedding similarity."""
        try:
            text_emb = await nlp_processor._get_embedding(folder_path)
            if not text_emb:
                return None

            import numpy as np

            best_domain = None
            best_score = 0.0

            for domain, ref_emb in self._domain_embeddings.items():
                similarity = np.dot(text_emb, ref_emb) / (
                    np.linalg.norm(text_emb) * np.linalg.norm(ref_emb)
                )
                similarity = float(max(0, similarity))

                if similarity > best_score:
                    best_domain = domain
                    best_score = similarity

            if best_score >= ClassifierConfig.EMBEDDING_THRESHOLD:
                return DomainClassificationResult(
                    domain=best_domain,
                    confidence=best_score,
                    method="embedding",
                )

            return None

        except Exception as e:
            logger.warning(f"Domain embedding classification failed: {e}")
            return None

    def _classify_by_lemmas(
        self,
        text: str,
        classification_type: str,
    ) -> Optional[ClassificationResult]:
        """Classify using lemma matching."""
        try:
            # Process text
            result = nlp_processor.process_text(text)
            lemmas = set(result.lemmas)

            if classification_type == "semantic_type":
                type_lemmas = SEMANTIC_TYPE_LEMMAS
            else:
                type_lemmas = DOMAIN_LEMMAS

            best_type = None
            best_score = 0.0
            best_matches = 0

            for stype, keywords in type_lemmas.items():
                keyword_set = set(k.lower() for k in keywords)
                matches = lemmas & keyword_set

                if matches:
                    # Score based on number of matches
                    score = len(matches) / len(keyword_set)
                    if len(matches) > best_matches or (len(matches) == best_matches and score > best_score):
                        best_type = stype
                        best_score = score
                        best_matches = len(matches)

            if best_type and best_matches > 0:
                return ClassificationResult(
                    semantic_type=best_type,
                    confidence=min(0.5 + (best_matches * 0.15), 0.9),
                    method="lemma",
                    debug_info={"matched_lemmas": best_matches},
                )

            return None

        except Exception as e:
            logger.warning(f"Lemma classification failed: {e}")
            return None

    def _classify_domain_by_lemmas(self, folder_path: str) -> Optional[DomainClassificationResult]:
        """Classify domain using lemma matching."""
        result = nlp_processor.process_text(folder_path)
        lemmas = set(result.lemmas)

        best_domain = None
        best_matches = 0

        for domain, keywords in DOMAIN_LEMMAS.items():
            keyword_set = set(k.lower() for k in keywords)
            matches = lemmas & keyword_set

            if len(matches) > best_matches:
                best_domain = domain
                best_matches = len(matches)

        if best_domain and best_matches > 0:
            return DomainClassificationResult(
                domain=best_domain,
                confidence=min(0.5 + (best_matches * 0.15), 0.85),
                method="lemma",
            )

        return None

    def _classify_by_fuzzy(
        self,
        text: str,
        classification_type: str,
    ) -> Optional[ClassificationResult]:
        """Classify using fuzzy matching."""
        try:
            text_lower = text.lower()

            if classification_type == "semantic_type":
                type_lemmas = SEMANTIC_TYPE_LEMMAS
            else:
                type_lemmas = DOMAIN_LEMMAS

            best_type = None
            best_score = 0.0

            for stype, keywords in type_lemmas.items():
                for keyword in keywords:
                    score = nlp_processor.fuzzy_match(keyword, text_lower)
                    if score > best_score:
                        best_type = stype
                        best_score = score

            if best_type and best_score >= NLPConfig.FUZZY_THRESHOLD:
                return ClassificationResult(
                    semantic_type=best_type,
                    confidence=best_score,
                    method="fuzzy",
                )

            return None

        except Exception as e:
            logger.warning(f"Fuzzy classification failed: {e}")
            return None

    def _classify_by_regex(
        self,
        text: str,
        classification_type: str,
    ) -> Optional[ClassificationResult]:
        """Fallback to regex classification (legacy)."""
        from .structural_extractor import SEMANTIC_TYPE_PATTERNS, DOMAIN_PATTERNS

        text_lower = text.lower()

        if classification_type == "semantic_type":
            patterns = SEMANTIC_TYPE_PATTERNS
        else:
            patterns = DOMAIN_PATTERNS

        for stype, pattern_list in patterns.items():
            for pattern in pattern_list:
                if re.search(pattern, text_lower):
                    return ClassificationResult(
                        semantic_type=stype,
                        confidence=0.6,
                        method="regex",
                    )

        return None

    def _classify_domain_by_regex(self, folder_path: str) -> Optional[DomainClassificationResult]:
        """Fallback to regex for domain classification."""
        from .structural_extractor import DOMAIN_PATTERNS

        path_lower = folder_path.lower()

        for domain, patterns in DOMAIN_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, path_lower):
                    return DomainClassificationResult(
                        domain=domain,
                        confidence=0.6,
                        method="regex",
                    )

        return None

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _match_explicit_type(self, type_string: str) -> Optional[SemanticType]:
        """Match explicit type string to SemanticType."""
        type_lower = type_string.lower()
        for stype in SemanticType:
            if stype.value in type_lower:
                return stype
        return None

    def _infer_domain_from_type(self, semantic_type: SemanticType) -> DomainType:
        """Infer domain from semantic type."""
        type_to_domain = {
            SemanticType.CONTRACT: DomainType.LEGAL,
            SemanticType.AGREEMENT: DomainType.LEGAL,
            SemanticType.AMENDMENT: DomainType.LEGAL,
            SemanticType.LEGAL_BRIEF: DomainType.LEGAL,
            SemanticType.INVOICE: DomainType.FINANCE,
            SemanticType.FINANCIAL_STATEMENT: DomainType.FINANCE,
            SemanticType.TAX_RETURN: DomainType.FISCAL,
            SemanticType.EMPLOYEE_FILE: DomainType.HR,
            SemanticType.PERFORMANCE_REVIEW: DomainType.HR,
            SemanticType.OFFER_LETTER: DomainType.HR,
            SemanticType.TECHNICAL_SPEC: DomainType.IT,
        }
        return type_to_domain.get(semantic_type, DomainType.GENERAL)

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    def get_capabilities(self) -> Dict[str, bool]:
        """Get classifier capabilities."""
        return {
            "zero_shot": self._zero_shot_classifier is not None,
            "embedding": bool(self._type_embeddings),
            "lemma": nlp_processor.has_spacy,
            "fuzzy": nlp_processor.has_fuzzy,
            "regex": True,  # Always available
        }


# =============================================================================
# Global Singleton
# =============================================================================

semantic_classifier = SemanticClassifier()
