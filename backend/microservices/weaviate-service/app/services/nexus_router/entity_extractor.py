"""
NexusRouter Entity Extractor

Extracts entities from user queries using spaCy NER.

Features:
- Spanish and English support
- Document type detection
- Date/time extraction
- Organization/person names
- Custom entity patterns

Latency: ~3ms per query
"""

import logging
import re
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from .schemas import NexusRouterConfig

logger = logging.getLogger(__name__)


# Document type keywords (Spanish)
DOCUMENT_TYPE_KEYWORDS = {
    "contrato": ["contrato", "contratos", "acuerdo", "convenio", "pacto"],
    "factura": ["factura", "facturas", "recibo", "recibos", "comprobante"],
    "informe": ["informe", "informes", "reporte", "reportes", "análisis"],
    "acta": ["acta", "actas", "minuta", "minutas"],
    "presupuesto": ["presupuesto", "presupuestos", "cotización", "oferta"],
    "nómina": ["nómina", "nóminas", "recibo de salario", "liquidación"],
    "carta": ["carta", "cartas", "comunicación", "oficio"],
    "documento": ["documento", "documentos", "archivo", "archivos", "fichero"],
    "propuesta": ["propuesta", "propuestas"],
    "solicitud": ["solicitud", "solicitudes", "petición"],
    "certificado": ["certificado", "certificados", "certificación"],
    "poder": ["poder", "poderes", "apoderamiento"],
    "escritura": ["escritura", "escrituras"],
    "estatutos": ["estatutos", "estatuto"],
}

# Date patterns (Spanish)
DATE_PATTERNS = [
    # "enero 2024", "febrero 2023"
    r"\b(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)\s+\d{4}\b",
    # "12/01/2024", "12-01-2024"
    r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
    # "2024", "2023"
    r"\b(20\d{2})\b",
    # "este mes", "el mes pasado"
    r"\b(este|el|la)\s+(mes|año|semana)\s*(pasad[oa])?\b",
    # "último trimestre"
    r"\b(últim[oa]|primer|segund|tercer|cuart)\s*(trimestre|semestre)\b",
]

# Quantity patterns
QUANTITY_PATTERNS = [
    r"\b(\d+)\s*(documentos?|archivos?|contratos?|facturas?)\b",
    r"\b(todos?\s+los?|todas?\s+las?)\b",
    r"\b(últim[oa]s?\s+\d+)\b",
]


class EntityExtractor:
    """
    Extracts entities from user queries.

    Uses a combination of:
    1. spaCy NER for named entities (ORG, PER, LOC, DATE)
    2. Keyword matching for document types
    3. Regex patterns for dates and quantities
    """

    def __init__(self, config: Optional[NexusRouterConfig] = None):
        """
        Initialize the entity extractor.

        Args:
            config: Router configuration
        """
        self.config = config or NexusRouterConfig()
        self._nlp_es = None
        self._nlp_en = None
        self._initialized = False

    async def initialize(self) -> bool:
        """
        Initialize spaCy models.

        Returns:
            True if at least one model loaded
        """
        if self._initialized:
            return True

        loaded_any = False

        # Try to load Spanish model
        try:
            import spacy
            self._nlp_es = spacy.load(self.config.spacy_model_es)
            logger.info(f"Loaded spaCy model: {self.config.spacy_model_es}")
            loaded_any = True
        except OSError:
            logger.warning(
                f"spaCy model {self.config.spacy_model_es} not found. "
                f"Install with: python -m spacy download {self.config.spacy_model_es}"
            )
        except ImportError:
            logger.warning("spaCy not installed. Entity extraction will be limited.")

        # Try to load English model
        try:
            import spacy
            self._nlp_en = spacy.load(self.config.spacy_model_en)
            logger.info(f"Loaded spaCy model: {self.config.spacy_model_en}")
            loaded_any = True
        except OSError:
            logger.warning(
                f"spaCy model {self.config.spacy_model_en} not found. "
            )
        except ImportError:
            pass

        self._initialized = True

        if not loaded_any:
            logger.warning("No spaCy models loaded. Using regex-only extraction.")

        return loaded_any

    def extract(
        self,
        query: str,
    ) -> Dict[str, Any]:
        """
        Extract all entities from a query.

        Args:
            query: User query text

        Returns:
            Dict with extracted entities by type
        """
        start_time = time.perf_counter()

        result = {
            "entities": [],
            "document_types": [],
            "dates": [],
            "organizations": [],
            "persons": [],
            "quantities": [],
            "raw_entities": [],
        }

        # 1. Extract document types (keyword matching)
        doc_types = self._extract_document_types(query)
        result["document_types"] = doc_types
        result["entities"].extend(doc_types)

        # 2. Extract dates (regex)
        dates = self._extract_dates(query)
        result["dates"] = dates
        result["entities"].extend(dates)

        # 3. Extract quantities (regex)
        quantities = self._extract_quantities(query)
        result["quantities"] = quantities

        # 4. Extract named entities (spaCy)
        if self._nlp_es or self._nlp_en:
            ner_result = self._extract_ner(query)
            result["organizations"] = ner_result.get("ORG", [])
            result["persons"] = ner_result.get("PER", [])
            result["raw_entities"] = ner_result.get("all", [])

            # Add to main entities list
            result["entities"].extend(ner_result.get("ORG", []))
            result["entities"].extend(ner_result.get("PER", []))

        # Deduplicate
        result["entities"] = list(set(result["entities"]))

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        logger.debug(
            f"Extracted entities from '{query[:50]}...': "
            f"{len(result['entities'])} entities, {elapsed_ms:.1f}ms"
        )

        result["extraction_time_ms"] = elapsed_ms

        return result

    def _extract_document_types(self, query: str) -> List[str]:
        """
        Extract document types from query using keyword matching.

        Args:
            query: Query text

        Returns:
            List of detected document types
        """
        query_lower = query.lower()
        detected = []

        for doc_type, keywords in DOCUMENT_TYPE_KEYWORDS.items():
            for keyword in keywords:
                if keyword in query_lower:
                    detected.append(doc_type)
                    break  # Only add once per type

        return detected

    def _extract_dates(self, query: str) -> List[str]:
        """
        Extract date expressions from query.

        Args:
            query: Query text

        Returns:
            List of date strings
        """
        dates = []

        for pattern in DATE_PATTERNS:
            matches = re.findall(pattern, query.lower())
            for match in matches:
                if isinstance(match, tuple):
                    # Multiple groups - join non-empty
                    date_str = " ".join(m for m in match if m)
                else:
                    date_str = match

                if date_str and date_str not in dates:
                    dates.append(date_str)

        return dates

    def _extract_quantities(self, query: str) -> List[Dict[str, Any]]:
        """
        Extract quantity expressions from query.

        Args:
            query: Query text

        Returns:
            List of quantity dicts with value and unit
        """
        quantities = []

        for pattern in QUANTITY_PATTERNS:
            matches = re.findall(pattern, query.lower())
            for match in matches:
                if isinstance(match, tuple):
                    quantities.append({
                        "value": match[0] if match[0].isdigit() else None,
                        "unit": match[1] if len(match) > 1 else None,
                        "raw": " ".join(match),
                    })
                else:
                    quantities.append({"raw": match})

        return quantities

    def _extract_ner(self, query: str) -> Dict[str, List[str]]:
        """
        Extract named entities using spaCy.

        Args:
            query: Query text

        Returns:
            Dict mapping entity type to list of values
        """
        result = {
            "ORG": [],  # Organizations
            "PER": [],  # Persons
            "LOC": [],  # Locations
            "DATE": [],  # Dates
            "MONEY": [],  # Monetary values
            "all": [],  # All entities with types
        }

        # Try Spanish model first (primary language)
        nlp = self._nlp_es or self._nlp_en
        if not nlp:
            return result

        try:
            doc = nlp(query)

            for ent in doc.ents:
                entity_text = ent.text.strip()
                entity_label = ent.label_

                # Map spaCy labels to our categories
                if entity_label in ("ORG", "ORGANIZATION"):
                    result["ORG"].append(entity_text)
                elif entity_label in ("PER", "PERSON"):
                    result["PER"].append(entity_text)
                elif entity_label in ("LOC", "GPE", "LOCATION"):
                    result["LOC"].append(entity_text)
                elif entity_label == "DATE":
                    result["DATE"].append(entity_text)
                elif entity_label == "MONEY":
                    result["MONEY"].append(entity_text)

                result["all"].append({
                    "text": entity_text,
                    "label": entity_label,
                    "start": ent.start_char,
                    "end": ent.end_char,
                })

        except Exception as e:
            logger.warning(f"spaCy NER failed: {e}")

        return result

    def extract_document_focus(self, query: str) -> Optional[str]:
        """
        Try to extract a specific document reference from the query.

        Looks for patterns like:
        - "el contrato de ACME"
        - "documento 123"
        - "la factura del mes pasado"

        Args:
            query: Query text

        Returns:
            Document reference string or None
        """
        query_lower = query.lower()

        # Pattern: "el/la [tipo] de [nombre]"
        pattern = r"(?:el|la)\s+(\w+)\s+(?:de|del)\s+(.+?)(?:\s|$|\.|\?)"
        match = re.search(pattern, query_lower)

        if match:
            doc_type = match.group(1)
            reference = match.group(2).strip()

            # Check if doc_type is a known document type
            for known_type, keywords in DOCUMENT_TYPE_KEYWORDS.items():
                if doc_type in keywords:
                    return f"{known_type}:{reference}"

        return None

    def get_status(self) -> Dict[str, Any]:
        """
        Get extractor status.

        Returns:
            Status dict
        """
        return {
            "initialized": self._initialized,
            "spacy_es_loaded": self._nlp_es is not None,
            "spacy_en_loaded": self._nlp_en is not None,
            "spacy_model_es": self.config.spacy_model_es,
            "spacy_model_en": self.config.spacy_model_en,
        }


# Singleton instance
entity_extractor = EntityExtractor()
