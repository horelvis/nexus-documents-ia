"""
Document Type Classifier using NLP and ML techniques
"""
import logging
import re
from typing import Dict, Any, Optional, List
import asyncio

logger = logging.getLogger(__name__)


class DocumentClassifier:
    """
    Classifies documents into types: contract, agreement, form, invoice, etc.
    Uses text analysis and pattern matching for classification
    """
    
    def __init__(self):
        # Keywords and patterns for each document type
        self.document_patterns = {
            "contract": {
                "keywords": [
                    "contract", "agreement", "parties", "terms and conditions",
                    "whereas", "obligations", "breach", "termination",
                    "contractor", "client", "service agreement"
                ],
                "patterns": [
                    r"(?i)this\s+contract",
                    r"(?i)between.*and",
                    r"(?i)party\s+of\s+the\s+first\s+part",
                    r"(?i)terms\s+and\s+conditions",
                    r"(?i)effective\s+date"
                ],
                "weight": 1.2
            },
            "agreement": {
                "keywords": [
                    "agreement", "mutual", "understanding", "parties agree",
                    "consent", "acknowledged", "cooperation", "partnership"
                ],
                "patterns": [
                    r"(?i)this\s+agreement",
                    r"(?i)parties\s+agree",
                    r"(?i)mutual\s+agreement",
                    r"(?i)memorandum\s+of\s+understanding"
                ],
                "weight": 1.1
            },
            "form": {
                "keywords": [
                    "form", "application", "registration", "fill out",
                    "complete", "submit", "field", "required", "optional"
                ],
                "patterns": [
                    r"(?i)application\s+form",
                    r"(?i)please\s+fill",
                    r"(?i)required\s+fields",
                    r"(?i)date:?\s*_+",
                    r"(?i)name:?\s*_+",
                    r"(?i)signature:?\s*_+"
                ],
                "weight": 1.0
            },
            "invoice": {
                "keywords": [
                    "invoice", "bill", "payment", "amount due", "total",
                    "subtotal", "tax", "due date", "invoice number"
                ],
                "patterns": [
                    r"(?i)invoice\s+#",
                    r"(?i)amount\s+due",
                    r"(?i)payment\s+terms",
                    r"(?i)bill\s+to",
                    r"\$\d+\.\d{2}"
                ],
                "weight": 1.0
            },
            "letter": {
                "keywords": [
                    "dear", "sincerely", "regards", "yours truly",
                    "to whom it may concern", "letter", "correspondence"
                ],
                "patterns": [
                    r"(?i)dear\s+\w+",
                    r"(?i)sincerely",
                    r"(?i)best\s+regards",
                    r"(?i)yours\s+truly"
                ],
                "weight": 0.9
            }
        }
    
    async def classify(
        self, 
        document_content: bytes,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Classify document type based on content analysis
        
        Returns:
            {
                "document_type": "contract",
                "confidence": 0.85,
                "detected_features": ["keywords", "patterns"],
                "metadata": {...}
            }
        """
        try:
            # Extract text from document (simplified - in production use proper extraction)
            text = document_content.decode('utf-8', errors='ignore')
            
            # Analyze metadata hints
            metadata_type = self._analyze_metadata(metadata) if metadata else None
            
            # Calculate scores for each document type
            scores = {}
            detected_features = {}
            
            for doc_type, config in self.document_patterns.items():
                keyword_score = self._calculate_keyword_score(text, config["keywords"])
                pattern_score = self._calculate_pattern_score(text, config["patterns"])
                
                # Combined score with weight
                combined_score = (keyword_score + pattern_score) * config["weight"]
                scores[doc_type] = combined_score
                
                detected_features[doc_type] = {
                    "keyword_matches": keyword_score > 0,
                    "pattern_matches": pattern_score > 0,
                    "score": combined_score
                }
            
            # Get best match
            best_type = max(scores, key=scores.get)
            confidence = min(scores[best_type] / 10.0, 1.0)  # Normalize to 0-1
            
            # Boost confidence if metadata matches
            if metadata_type and metadata_type == best_type:
                confidence = min(confidence * 1.2, 1.0)
            
            return {
                "document_type": best_type if confidence > 0.3 else "other",
                "confidence": confidence,
                "detected_features": detected_features,
                "metadata": {
                    "text_length": len(text),
                    "metadata_hint": metadata_type,
                    "all_scores": scores
                }
            }
            
        except Exception as e:
            logger.error(f"Error classifying document: {str(e)}")
            return {
                "document_type": "unknown",
                "confidence": 0.0,
                "error": str(e)
            }
    
    def _calculate_keyword_score(self, text: str, keywords: List[str]) -> float:
        """Calculate score based on keyword matches"""
        text_lower = text.lower()
        matches = 0
        
        for keyword in keywords:
            if keyword.lower() in text_lower:
                matches += text_lower.count(keyword.lower())
        
        return matches
    
    def _calculate_pattern_score(self, text: str, patterns: List[str]) -> float:
        """Calculate score based on regex pattern matches"""
        score = 0
        
        for pattern in patterns:
            matches = re.findall(pattern, text)
            score += len(matches) * 2  # Patterns weighted more heavily
        
        return score
    
    def _analyze_metadata(self, metadata: Dict[str, Any]) -> Optional[str]:
        """Analyze metadata for document type hints"""
        # Check filename
        filename = metadata.get("filename", "").lower()
        
        if any(term in filename for term in ["contract", "agreement"]):
            return "contract"
        elif "form" in filename or "application" in filename:
            return "form"
        elif "invoice" in filename or "bill" in filename:
            return "invoice"
        
        # Check mime type or other metadata
        category = metadata.get("category", "").lower()
        if category in self.document_patterns:
            return category
        
        return None