"""
Document Type Detector Service
Loads patterns from configuration and detects document types dynamically
"""
import yaml
import os
import logging
from typing import Dict, Any, Tuple, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class DocumentTypeDetector:
    """Service for detecting document types based on configurable patterns"""
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize the detector with configuration
        
        Args:
            config_path: Path to YAML configuration file. If None, uses default location
        """
        if config_path is None:
            # Default to app/core/document_patterns.yaml
            base_dir = Path(__file__).parent.parent
            config_path = base_dir / "core" / "document_patterns.yaml"
        
        self.config_path = config_path
        self.patterns = self._load_patterns()
        self._cached_language = None
    
    def _load_patterns(self) -> Dict[str, Any]:
        """Load patterns from YAML configuration"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                logger.info(f"Loaded document patterns from {self.config_path}")
                return config
        except FileNotFoundError:
            logger.warning(f"Pattern config not found at {self.config_path}, using defaults")
            return self._get_default_patterns()
        except Exception as e:
            logger.error(f"Error loading patterns: {e}, using defaults")
            return self._get_default_patterns()
    
    def _get_default_patterns(self) -> Dict[str, Any]:
        """Return minimal default patterns if config file is not available"""
        return {
            "document_types": {
                "contract": {
                    "keywords": {
                        "english": ["contract", "agreement", "terms"],
                        "spanish": ["contrato", "acuerdo", "términos"]
                    },
                    "min_keywords_match": 1,
                    "confidence_base": 0.5,
                    "confidence_per_match": 0.1
                },
                "invoice": {
                    "keywords": {
                        "english": ["invoice", "bill", "payment"],
                        "spanish": ["factura", "cuenta", "pago"]
                    },
                    "min_keywords_match": 1,
                    "confidence_base": 0.5,
                    "confidence_per_match": 0.1
                }
            },
            "default": {
                "type": "general",
                "confidence": 0.3
            }
        }
    
    def detect_language(self, text: str) -> str:
        """
        Detect the primary language of the document
        
        Args:
            text: Document text to analyze
            
        Returns:
            Detected language code (english, spanish, portuguese)
        """
        if self._cached_language:
            return self._cached_language
        
        text_lower = text.lower()[:1000]  # Check first 1000 chars
        language_scores = {}
        
        # Count language indicators
        for lang, indicators in self.patterns.get("language_indicators", {}).items():
            score = sum(1 for word in indicators if f" {word} " in f" {text_lower} ")
            language_scores[lang] = score
        
        # Get language with highest score
        if language_scores:
            detected = max(language_scores, key=language_scores.get)
            if language_scores[detected] > 0:
                self._cached_language = detected
                logger.debug(f"Detected language: {detected}")
                return detected
        
        # Default to English
        return "english"
    
    def detect_type(self, text: str, filename: str = "") -> Tuple[str, float]:
        """
        Detect document type based on content and filename
        
        Args:
            text: Document content
            filename: Optional filename for additional context
            
        Returns:
            Tuple of (document_type, confidence_score)
        """
        if not text:
            default = self.patterns.get("default", {})
            return default.get("type", "general"), default.get("confidence", 0.0)
        
        text_lower = text.lower()[:5000]  # Analyze first 5000 chars
        filename_lower = filename.lower()
        
        # Detect language
        language = self.detect_language(text)
        
        # Score each document type
        type_scores = {}
        
        for doc_type, config in self.patterns.get("document_types", {}).items():
            score = 0
            matches = 0
            
            # Check keywords for detected language
            keywords = config.get("keywords", {})
            
            # Get keywords for detected language and english as fallback
            check_keywords = []
            if language in keywords:
                check_keywords.extend(keywords[language])
            if language != "english" and "english" in keywords:
                check_keywords.extend(keywords["english"])
            
            # Count keyword matches
            for keyword in check_keywords:
                if keyword in text_lower or keyword in filename_lower:
                    matches += 1
            
            # Check patterns
            patterns = config.get("patterns", [])
            for pattern in patterns:
                if pattern.lower() in text_lower:
                    matches += 2  # Patterns worth more
            
            # Calculate confidence
            min_matches = config.get("min_keywords_match", 2)
            if matches >= min_matches:
                base_confidence = config.get("confidence_base", 0.5)
                per_match = config.get("confidence_per_match", 0.05)
                confidence = min(1.0, base_confidence + (matches * per_match))
                
                # Apply priority boost
                priority = config.get("priority", 10)
                confidence += (10 - priority) * 0.01  # Higher priority gets small boost
                
                type_scores[doc_type] = min(1.0, confidence)
        
        # Return highest scoring type
        if type_scores:
            best_type = max(type_scores, key=type_scores.get)
            return best_type, type_scores[best_type]
        
        # Return default
        default = self.patterns.get("default", {})
        return default.get("type", "general"), default.get("confidence", 0.3)
    
    def get_keywords_for_type(self, doc_type: str, language: str = None) -> List[str]:
        """
        Get keywords for a specific document type
        
        Args:
            doc_type: Document type to get keywords for
            language: Optional language filter
            
        Returns:
            List of keywords
        """
        doc_config = self.patterns.get("document_types", {}).get(doc_type, {})
        keywords = doc_config.get("keywords", {})
        
        if language and language in keywords:
            return keywords[language]
        
        # Return all keywords if no language specified
        all_keywords = []
        for lang_keywords in keywords.values():
            all_keywords.extend(lang_keywords)
        return all_keywords
    
    def reload_patterns(self):
        """Reload patterns from configuration file"""
        self.patterns = self._load_patterns()
        self._cached_language = None
        logger.info("Reloaded document patterns")
    
    def add_custom_pattern(self, doc_type: str, keywords: List[str], language: str = "custom"):
        """
        Add custom pattern at runtime (not persisted)
        
        Args:
            doc_type: Document type name
            keywords: List of keywords to add
            language: Language for the keywords
        """
        if "document_types" not in self.patterns:
            self.patterns["document_types"] = {}
        
        if doc_type not in self.patterns["document_types"]:
            self.patterns["document_types"][doc_type] = {
                "keywords": {},
                "min_keywords_match": 2,
                "confidence_base": 0.6,
                "confidence_per_match": 0.05
            }
        
        if "keywords" not in self.patterns["document_types"][doc_type]:
            self.patterns["document_types"][doc_type]["keywords"] = {}
        
        if language not in self.patterns["document_types"][doc_type]["keywords"]:
            self.patterns["document_types"][doc_type]["keywords"][language] = []
        
        self.patterns["document_types"][doc_type]["keywords"][language].extend(keywords)
        logger.info(f"Added {len(keywords)} keywords for {doc_type} ({language})")


# Singleton instance
_detector_instance = None


def get_document_type_detector() -> DocumentTypeDetector:
    """Get or create singleton instance of DocumentTypeDetector"""
    global _detector_instance
    if _detector_instance is None:
        _detector_instance = DocumentTypeDetector()
    return _detector_instance