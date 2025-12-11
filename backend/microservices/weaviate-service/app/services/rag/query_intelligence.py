"""
Layer 1: Query Intelligence

Responsible for understanding and expanding user queries before retrieval.
This layer works WITHOUT LLM calls for fast, deterministic processing.

Features:
- Abbreviation expansion (domain-specific dictionary)
- Intent classification (search, analyze, compare, summarize)
- Query variation generation
- Filter extraction (dates, document types)
- Key term identification
"""

import re
import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import httpx

from .models import QueryAnalysis, QueryIntent
from ...core.config import settings

logger = logging.getLogger(__name__)


class QueryIntelligence:
    """Layer 1: Understand and expand user queries"""

    def __init__(self):
        # Domain-specific abbreviation dictionary (Spanish/English)
        self.abbreviations = {
            # Legal
            "art": "artículo",
            "art.": "artículo",
            "arts": "artículos",
            "cód": "código",
            "cod": "código",
            "rgpd": "reglamento general de protección de datos",
            "lopd": "ley orgánica de protección de datos",
            "lopdgdd": "ley orgánica de protección de datos y garantía de derechos digitales",
            "lgpd": "ley general de protección de datos",
            "gdpr": "general data protection regulation",
            "nda": "non-disclosure agreement",
            "sla": "service level agreement",
            "tos": "terms of service",
            # Business
            "rrhh": "recursos humanos",
            "hr": "human resources",
            "kpi": "key performance indicator",
            "roi": "return on investment",
            "iva": "impuesto sobre el valor añadido",
            "vat": "value added tax",
            "pdf": "portable document format",
            "doc": "documento",
            "docs": "documentos",
            # Technical
            "api": "application programming interface",
            "bd": "base de datos",
            "db": "database",
            "sql": "structured query language",
            "ia": "inteligencia artificial",
            "ai": "artificial intelligence",
            "ml": "machine learning",
            # Financial
            "p&l": "profit and loss",
            "ebitda": "earnings before interest taxes depreciation and amortization",
            "cfo": "chief financial officer",
            "ceo": "chief executive officer",
            # Date patterns
            "ene": "enero",
            "feb": "febrero",
            "mar": "marzo",
            "abr": "abril",
            "may": "mayo",
            "jun": "junio",
            "jul": "julio",
            "ago": "agosto",
            "sep": "septiembre",
            "oct": "octubre",
            "nov": "noviembre",
            "dic": "diciembre",
        }

        # Intent classification patterns
        self.intent_patterns = {
            QueryIntent.SEARCH: [
                r"^(busca|buscar|encuentra|encontrar|dónde|donde|qué|que|cuál|cual)\s",
                r"(buscar|encontrar|localizar|ubicar)\s",
                r"\?$",  # Questions typically search
            ],
            QueryIntent.ANALYZE: [
                r"(analiza|analizar|análisis|evalúa|evaluar|evaluación|revisa|revisar|revisión)",
                r"(riesgo|riesgos|cumplimiento|compliance|auditoría|auditar)",
                r"(problemas?|issues?|errores?|fallos?)",
            ],
            QueryIntent.COMPARE: [
                r"(compara|comparar|comparación|diferencia|diferencias|versus|vs\.?|vs)",
                r"(entre|among|between)",
                r"(mejor|peor|igual|similar|distinto|diferente)",
            ],
            QueryIntent.SUMMARIZE: [
                r"(resume|resumir|resumen|sintetiza|sintetizar|síntesis)",
                r"(principales?|key|puntos\s+clave)",
                r"(breve|brevemente|conciso)",
            ],
            QueryIntent.EXTRACT: [
                r"(extrae|extraer|extracción|saca|sacar|obtén|obtener)",
                r"(lista\s+de|listado\s+de|enumera|enumerar)",
                r"(datos|información|info|detalles)",
            ],
            QueryIntent.EXPLAIN: [
                r"(explica|explicar|explicación|qué\s+significa|qué\s+es)",
                r"(cómo\s+funciona|cómo\s+trabaja|cómo\s+opera)",
                r"(define|definir|definición|meaning)",
            ],
            QueryIntent.LIST: [
                r"(lista|listar|enumera|enumerar|muestra|mostrar)",
                r"(todos|todas|all|every|cada)",
                r"(cuántos|cuántas|how\s+many)",
            ],
        }

        # Filter extraction patterns
        self.filter_patterns = {
            "date_range": [
                r"(desde|from)\s+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
                r"(hasta|to|until)\s+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
                r"(en|in)\s+(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)\s+(\d{4})?",
                r"(último|últimos|last)\s+(\d+)\s+(días?|semanas?|meses?|años?|days?|weeks?|months?|years?)",
                r"(\d{4})",  # Year alone
            ],
            "document_type": [
                r"(contrato|contratos|contract|contracts)",
                r"(factura|facturas|invoice|invoices)",
                r"(informe|informes|report|reports)",
                r"(manual|manuales|manuals?)",
                r"(política|políticas|policy|policies)",
                r"(acuerdo|acuerdos|agreement|agreements)",
                r"(propuesta|propuestas|proposal|proposals)",
            ],
        }

        self._tei_url = settings.tei_url

    def analyze_query(self, raw_query: str, generate_embeddings: bool = True) -> QueryAnalysis:
        """
        Analyze a user query and return structured analysis.

        This method is synchronous and fast (no LLM calls).
        Embeddings are generated via Ollama if enabled.
        """
        # Normalize query
        query = raw_query.strip()
        query_lower = query.lower()

        # Detect language (simple heuristic)
        language = self._detect_language(query_lower)

        # Expand abbreviations
        expanded_query = self._expand_abbreviations(query)

        # Classify intent
        intent = self._classify_intent(query_lower)

        # Generate query variations
        variations = self._generate_variations(expanded_query, intent)

        # Extract filters
        filters = self._extract_filters(query_lower)

        # Extract key terms
        key_terms = self._extract_key_terms(expanded_query)

        return QueryAnalysis(
            original_query=raw_query,
            expanded_query=expanded_query,
            query_variations=variations,
            intent=intent,
            extracted_filters=filters,
            key_terms=key_terms,
            language=language,
            embeddings=None,  # Will be filled async if needed
        )

    async def analyze_query_async(self, raw_query: str, generate_embeddings: bool = True) -> QueryAnalysis:
        """
        Async version that can generate embeddings.
        """
        analysis = self.analyze_query(raw_query, generate_embeddings=False)

        if generate_embeddings:
            analysis.embeddings = await self._generate_embeddings(analysis.expanded_query)

        return analysis

    def _detect_language(self, query: str) -> str:
        """Simple language detection based on common words"""
        spanish_indicators = [
            "qué", "cómo", "dónde", "cuál", "cuándo", "por qué",
            "busca", "encuentra", "analiza", "compara", "resume",
            "el", "la", "los", "las", "de", "del", "en", "con",
            "documento", "contrato", "informe", "factura",
        ]
        english_indicators = [
            "what", "how", "where", "which", "when", "why",
            "find", "search", "analyze", "compare", "summarize",
            "the", "a", "an", "of", "in", "with", "for",
            "document", "contract", "report", "invoice",
        ]

        query_words = set(query.split())
        spanish_count = sum(1 for word in spanish_indicators if word in query_words or word in query)
        english_count = sum(1 for word in english_indicators if word in query_words or word in query)

        return "es" if spanish_count >= english_count else "en"

    def _expand_abbreviations(self, query: str) -> str:
        """Expand known abbreviations in the query"""
        expanded = query
        for abbrev, expansion in self.abbreviations.items():
            # Match whole words only (case insensitive)
            pattern = rf"\b{re.escape(abbrev)}\b"
            if re.search(pattern, expanded, re.IGNORECASE):
                # Keep original case for first letter
                expanded = re.sub(pattern, expansion, expanded, flags=re.IGNORECASE)
        return expanded

    def _classify_intent(self, query: str) -> QueryIntent:
        """Classify the intent of the query"""
        scores = {intent: 0 for intent in QueryIntent}

        for intent, patterns in self.intent_patterns.items():
            for pattern in patterns:
                if re.search(pattern, query, re.IGNORECASE):
                    scores[intent] += 1

        # Get intent with highest score
        max_score = max(scores.values())
        if max_score == 0:
            return QueryIntent.SEARCH  # Default to search

        # Return first intent with max score
        for intent, score in scores.items():
            if score == max_score:
                return intent

        return QueryIntent.UNKNOWN

    def _generate_variations(self, query: str, intent: QueryIntent) -> List[str]:
        """Generate query variations for better retrieval"""
        variations = [query]  # Original is always first

        # Remove question marks and normalize
        clean_query = re.sub(r"[¿?¡!]", "", query).strip()
        if clean_query != query:
            variations.append(clean_query)

        # Intent-specific variations
        if intent == QueryIntent.SEARCH:
            # Add noun phrase version
            if query.lower().startswith(("busca ", "encuentra ", "qué ", "cuál ")):
                noun_phrase = re.sub(r"^(busca|encuentra|qué|cuál)\s+", "", query, flags=re.IGNORECASE)
                if noun_phrase != query:
                    variations.append(noun_phrase)

        elif intent == QueryIntent.ANALYZE:
            # Add analysis-focused version
            variations.append(f"análisis de {clean_query}")

        elif intent == QueryIntent.COMPARE:
            # Keep as is - comparison queries are specific
            pass

        elif intent == QueryIntent.SUMMARIZE:
            # Add summary-focused version
            variations.append(f"resumen de {clean_query}")

        # Limit to 3 variations max
        return variations[:3]

    def _extract_filters(self, query: str) -> Dict[str, Any]:
        """Extract implicit filters from the query"""
        filters = {}

        # Extract date references
        for pattern in self.filter_patterns["date_range"]:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                if "date_hints" not in filters:
                    filters["date_hints"] = []
                filters["date_hints"].append(match.group(0))

        # Extract document type hints
        for pattern in self.filter_patterns["document_type"]:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                doc_type = match.group(1).lower()
                # Normalize to singular
                doc_type = re.sub(r"s$", "", doc_type)
                filters["document_type_hint"] = doc_type
                break

        return filters

    def _extract_key_terms(self, query: str) -> List[str]:
        """Extract key terms for matching (simple approach without NLP)"""
        # Remove common stop words
        stop_words = {
            # Spanish
            "el", "la", "los", "las", "un", "una", "unos", "unas",
            "de", "del", "en", "con", "por", "para", "a", "al",
            "que", "qué", "cual", "cuál", "como", "cómo",
            "y", "o", "ni", "pero", "sino", "aunque",
            "es", "son", "está", "están", "ser", "estar",
            "mi", "tu", "su", "nuestro", "vuestro",
            "este", "ese", "aquel", "esto", "eso", "aquello",
            # English
            "the", "a", "an", "of", "in", "on", "at", "to", "for",
            "and", "or", "but", "if", "then", "else",
            "is", "are", "was", "were", "be", "been", "being",
            "have", "has", "had", "do", "does", "did",
            "this", "that", "these", "those",
            "i", "you", "he", "she", "it", "we", "they",
            "my", "your", "his", "her", "its", "our", "their",
            # Query words
            "busca", "buscar", "encuentra", "encontrar",
            "analiza", "analizar", "compara", "comparar",
            "resume", "resumir", "extrae", "extraer",
            "find", "search", "analyze", "compare", "summarize",
        }

        # Tokenize and filter
        words = re.findall(r"\b[\w]+\b", query.lower())
        key_terms = [
            word for word in words
            if word not in stop_words and len(word) > 2
        ]

        # Return unique terms preserving order
        seen = set()
        unique_terms = []
        for term in key_terms:
            if term not in seen:
                seen.add(term)
                unique_terms.append(term)

        return unique_terms[:10]  # Limit to 10 key terms

    async def _generate_embeddings(self, text: str) -> Optional[List[float]]:
        """Generate embeddings via TEI (Text Embeddings Inference)"""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self._tei_url}/embed",
                    json={
                        "inputs": text,
                        "truncate": True
                    }
                )
                if response.status_code == 200:
                    embeddings = response.json()
                    # TEI returns a list of embeddings, we want the first one
                    if embeddings and len(embeddings) > 0:
                        return embeddings[0]
                    return None
                else:
                    logger.warning(f"TEI embedding failed: {response.status_code}")
                    return None
        except Exception as e:
            logger.warning(f"Could not generate embeddings: {e}")
            return None


# Global instance
query_intelligence = QueryIntelligence()
