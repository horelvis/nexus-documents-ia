"""
NLP Processor for Structural Intelligence Layer

Advanced NLP capabilities for document classification and entity extraction:
- Lemmatization (spaCy)
- Named Entity Recognition (spaCy)
- Fuzzy Matching (rapidfuzz)
- Semantic Similarity (sentence-transformers)

This module provides a significant improvement over regex-only classification
by understanding morphology, synonyms, and semantic relationships.

Usage:
    from app.services.sil.nlp_processor import nlp_processor

    # Initialize (lazy loading)
    await nlp_processor.initialize()

    # Process text
    result = nlp_processor.process_text("Contrato de servicios con ACME Corp")
    print(result.lemmas)      # ['contrato', 'de', 'servicio', 'con', 'acme', 'corp']
    print(result.entities)    # [('ACME Corp', 'ORG')]

    # Fuzzy match
    score = nlp_processor.fuzzy_match("contrato", "contrtao")  # 0.85

    # Semantic similarity
    sim = await nlp_processor.semantic_similarity("factura", "invoice")  # 0.89
"""

import asyncio
import logging
import os
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple, Set
from enum import Enum

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration
# =============================================================================

class NLPConfig:
    """Configuration for NLP processor."""
    # spaCy models (multilingual)
    SPACY_MODEL_ES = os.getenv("SPACY_MODEL_ES", "es_core_news_md")
    SPACY_MODEL_EN = os.getenv("SPACY_MODEL_EN", "en_core_web_md")
    SPACY_MODEL_MULTI = os.getenv("SPACY_MODEL_MULTI", "xx_ent_wiki_sm")

    # Sentence Transformers model (multilingual)
    EMBEDDING_MODEL = os.getenv(
        "NLP_EMBEDDING_MODEL",
        "paraphrase-multilingual-MiniLM-L12-v2"  # 118M params, multilingual
    )

    # Fuzzy matching threshold
    FUZZY_THRESHOLD = float(os.getenv("NLP_FUZZY_THRESHOLD", "0.8"))

    # Cache settings
    EMBEDDING_CACHE_SIZE = int(os.getenv("NLP_EMBEDDING_CACHE_SIZE", "1000"))

    # Enable/disable features
    ENABLE_SPACY = os.getenv("NLP_ENABLE_SPACY", "true").lower() == "true"
    ENABLE_EMBEDDINGS = os.getenv("NLP_ENABLE_EMBEDDINGS", "true").lower() == "true"
    ENABLE_FUZZY = os.getenv("NLP_ENABLE_FUZZY", "true").lower() == "true"


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class TextProcessingResult:
    """Result of NLP text processing."""
    original: str
    tokens: List[str] = field(default_factory=list)
    lemmas: List[str] = field(default_factory=list)
    pos_tags: List[Tuple[str, str]] = field(default_factory=list)  # (token, POS)
    entities: List[Tuple[str, str]] = field(default_factory=list)  # (text, label)
    noun_chunks: List[str] = field(default_factory=list)
    language: str = "unknown"

    @property
    def lemmatized_text(self) -> str:
        """Get lemmatized text as string."""
        return " ".join(self.lemmas)

    def has_entity_type(self, entity_type: str) -> bool:
        """Check if a specific entity type was found."""
        return any(label == entity_type for _, label in self.entities)

    def get_entities_by_type(self, entity_type: str) -> List[str]:
        """Get all entities of a specific type."""
        return [text for text, label in self.entities if label == entity_type]


@dataclass
class EntityExtractionResult:
    """Structured entity extraction result."""
    organizations: List[str] = field(default_factory=list)
    persons: List[str] = field(default_factory=list)
    locations: List[str] = field(default_factory=list)
    dates: List[str] = field(default_factory=list)
    money: List[str] = field(default_factory=list)
    misc: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, List[str]]:
        return {
            "organizations": self.organizations,
            "persons": self.persons,
            "locations": self.locations,
            "dates": self.dates,
            "money": self.money,
            "misc": self.misc,
        }


# =============================================================================
# Synonym Expansion
# =============================================================================

# Semantic type synonyms (will be expanded with embeddings)
SEMANTIC_TYPE_SYNONYMS = {
    "contract": {
        "es": ["contrato", "convenio", "acuerdo", "pacto", "tratado"],
        "en": ["contract", "agreement", "pact", "covenant", "deal"],
    },
    "invoice": {
        "es": ["factura", "recibo", "cobro", "liquidación", "nota de cargo"],
        "en": ["invoice", "bill", "receipt", "statement", "billing"],
    },
    "report": {
        "es": ["informe", "reporte", "análisis", "estudio", "memoria"],
        "en": ["report", "analysis", "study", "assessment", "review"],
    },
    "policy": {
        "es": ["política", "normativa", "directriz", "lineamiento", "regla"],
        "en": ["policy", "guideline", "directive", "regulation", "rule"],
    },
    "procedure": {
        "es": ["procedimiento", "proceso", "protocolo", "instructivo", "manual"],
        "en": ["procedure", "process", "protocol", "instruction", "manual"],
    },
    "memo": {
        "es": ["memorando", "comunicado", "circular", "nota", "aviso"],
        "en": ["memo", "memorandum", "notice", "circular", "announcement"],
    },
    "amendment": {
        "es": ["adenda", "modificación", "anexo", "enmienda", "addendum"],
        "en": ["amendment", "addendum", "modification", "supplement", "annex"],
    },
}

# Domain synonyms
DOMAIN_SYNONYMS = {
    "legal": {
        "es": ["legal", "jurídico", "abogado", "letrado", "judicial", "ley"],
        "en": ["legal", "law", "attorney", "lawyer", "judicial", "juridical"],
    },
    "hr": {
        "es": ["rrhh", "recursos humanos", "personal", "empleados", "talento", "nómina"],
        "en": ["hr", "human resources", "personnel", "employees", "talent", "payroll"],
    },
    "finance": {
        "es": ["finanzas", "contabilidad", "tesorería", "fiscal", "económico"],
        "en": ["finance", "accounting", "treasury", "fiscal", "economic"],
    },
    "sales": {
        "es": ["ventas", "comercial", "clientes", "negocio", "mercado"],
        "en": ["sales", "commercial", "customers", "business", "market"],
    },
    "it": {
        "es": ["ti", "sistemas", "tecnología", "informática", "software", "desarrollo"],
        "en": ["it", "systems", "technology", "computing", "software", "development"],
    },
}


# =============================================================================
# NLP Processor Class
# =============================================================================

class NLPProcessor:
    """
    Advanced NLP processor for structural document classification.

    Features:
    - Multilingual lemmatization (spaCy)
    - Named Entity Recognition
    - Fuzzy string matching (rapidfuzz)
    - Semantic similarity via embeddings (sentence-transformers)
    """

    def __init__(self):
        self._initialized = False
        self._spacy_es = None
        self._spacy_en = None
        self._embedding_model = None
        self._fuzzy_available = False
        self._embedding_cache: Dict[str, List[float]] = {}
        self._init_lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Initialize NLP models (lazy loading)."""
        if self._initialized:
            return

        async with self._init_lock:
            if self._initialized:
                return

            logger.info("🧠 Initializing NLP Processor...")

            # Load spaCy models
            if NLPConfig.ENABLE_SPACY:
                await self._load_spacy_models()

            # Load sentence-transformers
            if NLPConfig.ENABLE_EMBEDDINGS:
                await self._load_embedding_model()

            # Check fuzzy matching availability
            if NLPConfig.ENABLE_FUZZY:
                self._check_fuzzy_availability()

            self._initialized = True
            logger.info("✅ NLP Processor initialized successfully")

    async def _load_spacy_models(self) -> None:
        """Load spaCy models for Spanish and English."""
        try:
            import spacy

            # Try to load Spanish model
            try:
                self._spacy_es = spacy.load(NLPConfig.SPACY_MODEL_ES)
                logger.info(f"✅ Loaded spaCy model: {NLPConfig.SPACY_MODEL_ES}")
            except OSError:
                logger.warning(
                    f"⚠️ spaCy model {NLPConfig.SPACY_MODEL_ES} not found. "
                    f"Install with: python -m spacy download {NLPConfig.SPACY_MODEL_ES}"
                )
                # Try smaller model
                try:
                    self._spacy_es = spacy.load("es_core_news_sm")
                    logger.info("✅ Loaded fallback spaCy model: es_core_news_sm")
                except OSError:
                    logger.warning("⚠️ No Spanish spaCy model available")

            # Try to load English model
            try:
                self._spacy_en = spacy.load(NLPConfig.SPACY_MODEL_EN)
                logger.info(f"✅ Loaded spaCy model: {NLPConfig.SPACY_MODEL_EN}")
            except OSError:
                logger.warning(
                    f"⚠️ spaCy model {NLPConfig.SPACY_MODEL_EN} not found. "
                    f"Install with: python -m spacy download {NLPConfig.SPACY_MODEL_EN}"
                )
                try:
                    self._spacy_en = spacy.load("en_core_web_sm")
                    logger.info("✅ Loaded fallback spaCy model: en_core_web_sm")
                except OSError:
                    logger.warning("⚠️ No English spaCy model available")

        except ImportError:
            logger.warning("⚠️ spaCy not installed. Install with: pip install spacy")

    async def _load_embedding_model(self) -> None:
        """Load sentence-transformers model."""
        try:
            from sentence_transformers import SentenceTransformer

            # Load in a thread to avoid blocking
            loop = asyncio.get_event_loop()
            self._embedding_model = await loop.run_in_executor(
                None,
                lambda: SentenceTransformer(NLPConfig.EMBEDDING_MODEL)
            )
            logger.info(f"✅ Loaded embedding model: {NLPConfig.EMBEDDING_MODEL}")

        except ImportError:
            logger.warning(
                "⚠️ sentence-transformers not installed. "
                "Install with: pip install sentence-transformers"
            )
        except Exception as e:
            logger.warning(f"⚠️ Failed to load embedding model: {e}")

    def _check_fuzzy_availability(self) -> None:
        """Check if rapidfuzz is available."""
        try:
            import rapidfuzz
            self._fuzzy_available = True
            logger.info("✅ rapidfuzz available for fuzzy matching")
        except ImportError:
            logger.warning(
                "⚠️ rapidfuzz not installed. "
                "Install with: pip install rapidfuzz"
            )
            self._fuzzy_available = False

    # =========================================================================
    # Text Processing
    # =========================================================================

    def process_text(
        self,
        text: str,
        language: Optional[str] = None,
    ) -> TextProcessingResult:
        """
        Process text with NLP pipeline.

        Args:
            text: Input text to process
            language: Language code ('es', 'en') or None for auto-detection

        Returns:
            TextProcessingResult with tokens, lemmas, entities, etc.
        """
        if not text:
            return TextProcessingResult(original="")

        result = TextProcessingResult(original=text)

        # Detect language if not specified
        if language is None:
            language = self._detect_language(text)
        result.language = language

        # Select appropriate spaCy model
        nlp = self._get_spacy_model(language)

        if nlp is None:
            # Fallback to basic tokenization
            result.tokens = text.lower().split()
            result.lemmas = result.tokens
            return result

        # Process with spaCy
        doc = nlp(text)

        result.tokens = [token.text.lower() for token in doc if not token.is_space]
        result.lemmas = [token.lemma_.lower() for token in doc if not token.is_space]
        result.pos_tags = [(token.text, token.pos_) for token in doc]
        result.entities = [(ent.text, ent.label_) for ent in doc.ents]
        result.noun_chunks = [chunk.text for chunk in doc.noun_chunks]

        return result

    def extract_entities(self, text: str, language: Optional[str] = None) -> EntityExtractionResult:
        """
        Extract named entities from text.

        Args:
            text: Input text
            language: Language code or None for auto-detection

        Returns:
            EntityExtractionResult with categorized entities
        """
        result = EntityExtractionResult()

        processing_result = self.process_text(text, language)

        # Map spaCy entity labels to our categories
        label_mapping = {
            # Organizations
            "ORG": "organizations",
            "COMPANY": "organizations",
            "CORPORATION": "organizations",
            # Persons
            "PER": "persons",
            "PERSON": "persons",
            # Locations
            "LOC": "locations",
            "GPE": "locations",
            "LOCATION": "locations",
            # Dates
            "DATE": "dates",
            "TIME": "dates",
            # Money
            "MONEY": "money",
            "CURRENCY": "money",
            # Misc
            "MISC": "misc",
            "PRODUCT": "misc",
            "EVENT": "misc",
        }

        for entity_text, entity_label in processing_result.entities:
            category = label_mapping.get(entity_label, "misc")
            getattr(result, category).append(entity_text)

        return result

    def _detect_language(self, text: str) -> str:
        """Simple language detection based on common words."""
        text_lower = text.lower()

        # Spanish indicators
        es_words = {"de", "la", "el", "en", "del", "los", "las", "con", "para", "por", "que"}
        # English indicators
        en_words = {"the", "of", "and", "in", "to", "for", "with", "on", "at", "by"}

        words = set(text_lower.split())
        es_count = len(words & es_words)
        en_count = len(words & en_words)

        if es_count > en_count:
            return "es"
        elif en_count > es_count:
            return "en"
        else:
            return "es"  # Default to Spanish for this project

    def _get_spacy_model(self, language: str):
        """Get appropriate spaCy model for language."""
        if language == "es" and self._spacy_es:
            return self._spacy_es
        elif language == "en" and self._spacy_en:
            return self._spacy_en
        elif self._spacy_es:
            return self._spacy_es  # Fallback to Spanish
        elif self._spacy_en:
            return self._spacy_en  # Fallback to English
        return None

    # =========================================================================
    # Fuzzy Matching
    # =========================================================================

    def fuzzy_match(
        self,
        query: str,
        target: str,
        threshold: float = None,
    ) -> float:
        """
        Calculate fuzzy similarity between two strings.

        Args:
            query: Query string
            target: Target string to compare
            threshold: Minimum score to consider a match (0-1)

        Returns:
            Similarity score (0-1)
        """
        if not self._fuzzy_available:
            # Fallback to exact match
            return 1.0 if query.lower() == target.lower() else 0.0

        from rapidfuzz import fuzz

        # Use token_set_ratio for better handling of word order
        score = fuzz.token_set_ratio(query.lower(), target.lower()) / 100.0

        threshold = threshold or NLPConfig.FUZZY_THRESHOLD
        return score if score >= threshold else 0.0

    def fuzzy_match_best(
        self,
        query: str,
        candidates: List[str],
        threshold: float = None,
    ) -> Optional[Tuple[str, float]]:
        """
        Find best fuzzy match from candidates.

        Args:
            query: Query string
            candidates: List of candidate strings
            threshold: Minimum score threshold

        Returns:
            Tuple of (best_match, score) or None if no match above threshold
        """
        if not self._fuzzy_available or not candidates:
            return None

        from rapidfuzz import process

        threshold = threshold or NLPConfig.FUZZY_THRESHOLD

        result = process.extractOne(
            query.lower(),
            [c.lower() for c in candidates],
            score_cutoff=threshold * 100
        )

        if result:
            match_text, score, idx = result
            return (candidates[idx], score / 100.0)

        return None

    # =========================================================================
    # Semantic Similarity
    # =========================================================================

    async def semantic_similarity(
        self,
        text1: str,
        text2: str,
    ) -> float:
        """
        Calculate semantic similarity between two texts.

        Uses sentence embeddings for deep semantic comparison.

        Args:
            text1: First text
            text2: Second text

        Returns:
            Similarity score (0-1)
        """
        if not self._embedding_model:
            # Fallback to fuzzy matching
            return self.fuzzy_match(text1, text2)

        # Get embeddings
        emb1 = await self._get_embedding(text1)
        emb2 = await self._get_embedding(text2)

        if emb1 is None or emb2 is None:
            return 0.0

        # Cosine similarity
        import numpy as np
        similarity = np.dot(emb1, emb2) / (np.linalg.norm(emb1) * np.linalg.norm(emb2))

        return float(max(0, similarity))  # Clamp to 0-1

    async def _get_embedding(self, text: str) -> Optional[List[float]]:
        """Get embedding for text (with caching)."""
        if not self._embedding_model:
            return None

        # Check cache
        cache_key = text.lower().strip()
        if cache_key in self._embedding_cache:
            return self._embedding_cache[cache_key]

        # Generate embedding
        try:
            loop = asyncio.get_event_loop()
            embedding = await loop.run_in_executor(
                None,
                lambda: self._embedding_model.encode(text, convert_to_numpy=True)
            )

            # Cache with size limit
            if len(self._embedding_cache) >= NLPConfig.EMBEDDING_CACHE_SIZE:
                # Remove oldest entry (simple FIFO)
                oldest_key = next(iter(self._embedding_cache))
                del self._embedding_cache[oldest_key]

            self._embedding_cache[cache_key] = embedding.tolist()
            return embedding.tolist()

        except Exception as e:
            logger.warning(f"Failed to generate embedding: {e}")
            return None

    async def find_most_similar(
        self,
        query: str,
        candidates: List[str],
        top_k: int = 1,
    ) -> List[Tuple[str, float]]:
        """
        Find most semantically similar candidates.

        Args:
            query: Query text
            candidates: List of candidate texts
            top_k: Number of top matches to return

        Returns:
            List of (candidate, similarity_score) tuples
        """
        if not self._embedding_model or not candidates:
            return []

        # Get query embedding
        query_emb = await self._get_embedding(query)
        if query_emb is None:
            return []

        # Get candidate embeddings and calculate similarities
        similarities = []
        for candidate in candidates:
            candidate_emb = await self._get_embedding(candidate)
            if candidate_emb:
                import numpy as np
                sim = np.dot(query_emb, candidate_emb) / (
                    np.linalg.norm(query_emb) * np.linalg.norm(candidate_emb)
                )
                similarities.append((candidate, float(sim)))

        # Sort by similarity and return top_k
        similarities.sort(key=lambda x: x[1], reverse=True)
        return similarities[:top_k]

    # =========================================================================
    # Synonym Expansion
    # =========================================================================

    def get_synonyms(
        self,
        word: str,
        category: str = "semantic_type",
        language: str = "es",
    ) -> Set[str]:
        """
        Get synonyms for a word from predefined mappings.

        Args:
            word: Word to find synonyms for
            category: 'semantic_type' or 'domain'
            language: Language code

        Returns:
            Set of synonyms including the original word
        """
        synonyms = {word.lower()}

        # Select synonym dictionary
        syn_dict = SEMANTIC_TYPE_SYNONYMS if category == "semantic_type" else DOMAIN_SYNONYMS

        # Search for word in synonym groups
        for group_key, group_langs in syn_dict.items():
            all_words = set()
            for lang_words in group_langs.values():
                all_words.update(w.lower() for w in lang_words)

            if word.lower() in all_words:
                # Found! Add all synonyms from requested language
                if language in group_langs:
                    synonyms.update(w.lower() for w in group_langs[language])
                # Also add cross-language synonyms
                for lang_words in group_langs.values():
                    synonyms.update(w.lower() for w in lang_words)
                break

        return synonyms

    async def expand_query_with_synonyms(
        self,
        query: str,
        category: str = "semantic_type",
    ) -> List[str]:
        """
        Expand a query with synonyms and semantic variations.

        Args:
            query: Original query
            category: Category for synonym lookup

        Returns:
            List of expanded query variations
        """
        expansions = [query]

        # Process query
        result = self.process_text(query)

        # Expand each lemma
        for lemma in result.lemmas:
            synonyms = self.get_synonyms(lemma, category)
            expansions.extend(synonyms - {lemma})

        return list(set(expansions))

    # =========================================================================
    # Utility Methods
    # =========================================================================

    @property
    def is_initialized(self) -> bool:
        """Check if processor is initialized."""
        return self._initialized

    @property
    def has_spacy(self) -> bool:
        """Check if spaCy is available."""
        return self._spacy_es is not None or self._spacy_en is not None

    @property
    def has_embeddings(self) -> bool:
        """Check if embeddings are available."""
        return self._embedding_model is not None

    @property
    def has_fuzzy(self) -> bool:
        """Check if fuzzy matching is available."""
        return self._fuzzy_available

    def get_capabilities(self) -> Dict[str, bool]:
        """Get available NLP capabilities."""
        return {
            "spacy": self.has_spacy,
            "embeddings": self.has_embeddings,
            "fuzzy": self.has_fuzzy,
            "lemmatization": self.has_spacy,
            "ner": self.has_spacy,
            "semantic_similarity": self.has_embeddings,
        }


# =============================================================================
# Global Singleton
# =============================================================================

nlp_processor = NLPProcessor()
