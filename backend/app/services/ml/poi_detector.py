"""
POI (Points of Interest) Detector for Signature Placement
Detects signature lines, date fields, and other signing zones in documents
"""
import logging
import re
from typing import List, Dict, Any, Tuple, Optional
import cv2
import numpy as np
from PIL import Image
import io

logger = logging.getLogger(__name__)


class POIDetector:
    """
    Detects Points of Interest in documents where signatures should be placed
    Uses computer vision and text analysis techniques
    """
    
    def __init__(self):
        # Signature zone indicators
        self.signature_indicators = [
            "signature", "sign", "signed", "firma", "firmado",
            "authorized signature", "client signature", "company signature",
            "witness", "notary", "acknowledged"
        ]
        
        # Patterns for signature lines
        self.signature_patterns = [
            r"(?i)signature:?\s*_{3,}",
            r"(?i)sign:?\s*_{3,}",
            r"(?i)firma:?\s*_{3,}",
            r"(?i)name:?\s*_{3,}.*signature:?\s*_{3,}",
            r"(?i)\[signature\]",
            r"(?i)x\s*_{10,}",
            r"_{20,}",  # Long underscores often indicate signature lines
            r"(?i)by:?\s*_{10,}"
        ]
        
        # Date patterns near signatures
        self.date_patterns = [
            r"(?i)date:?\s*_{3,}",
            r"(?i)fecha:?\s*_{3,}",
            r"(?i)dated?\s+this",
            r"__/__/____",
            r"dd/mm/yyyy"
        ]
    
    async def detect_signature_zones(
        self,
        document_content: bytes,
        document_type: str
    ) -> Dict[str, Any]:
        """
        Detect signature zones in document
        
        Returns:
            {
                "zones": [
                    {
                        "type": "signature_line",
                        "bbox": [x1, y1, x2, y2],
                        "page": 1,
                        "confidence": 0.9,
                        "text_nearby": "Client Signature: _______",
                        "role_hint": "client"
                    }
                ],
                "metadata": {...}
            }
        """
        try:
            # For text-based detection (simplified)
            text = document_content.decode('utf-8', errors='ignore')
            
            # Detect text-based signature zones
            text_zones = self._detect_text_signature_zones(text, document_type)
            
            # In production, also use computer vision for visual detection
            # visual_zones = await self._detect_visual_signature_zones(document_content)
            
            # Merge and deduplicate zones
            all_zones = text_zones  # + visual_zones
            
            # Sort by page and position
            all_zones.sort(key=lambda z: (z["page"], z["bbox"][1]))
            
            return {
                "zones": all_zones,
                "metadata": {
                    "detection_method": "text_analysis",
                    "document_type": document_type,
                    "total_zones": len(all_zones)
                }
            }
            
        except Exception as e:
            logger.error(f"Error detecting signature zones: {str(e)}")
            return {
                "zones": [],
                "error": str(e)
            }
    
    def _detect_text_signature_zones(
        self, 
        text: str, 
        document_type: str
    ) -> List[Dict[str, Any]]:
        """Detect signature zones using text analysis"""
        zones = []
        lines = text.split('\n')
        
        for i, line in enumerate(lines):
            # Check for signature patterns
            for pattern in self.signature_patterns:
                matches = re.finditer(pattern, line)
                for match in matches:
                    # Extract context
                    context_start = max(0, i - 2)
                    context_end = min(len(lines), i + 3)
                    context_lines = lines[context_start:context_end]
                    context_text = '\n'.join(context_lines)
                    
                    # Determine signer role from context
                    role_hint = self._extract_role_hint(context_text)
                    
                    # Create zone (with estimated coordinates)
                    zone = {
                        "type": "signature_line",
                        "bbox": self._estimate_bbox(i, match.start(), match.end(), len(line)),
                        "page": self._estimate_page(i, len(lines)),
                        "confidence": 0.8,
                        "text_nearby": line.strip(),
                        "role_hint": role_hint,
                        "pattern_matched": pattern
                    }
                    zones.append(zone)
            
            # Check for signature indicators without lines
            line_lower = line.lower()
            for indicator in self.signature_indicators:
                if indicator in line_lower and not any(p in line for p in ['_', '[', ']']):
                    # Likely a signature label without line
                    zone = {
                        "type": "signature_area",
                        "bbox": self._estimate_bbox(i, 0, len(line), len(line)),
                        "page": self._estimate_page(i, len(lines)),
                        "confidence": 0.6,
                        "text_nearby": line.strip(),
                        "role_hint": self._extract_role_hint(line),
                        "indicator": indicator
                    }
                    zones.append(zone)
        
        # Apply document type specific rules
        zones = self._apply_document_type_rules(zones, document_type)
        
        return zones
    
    def _estimate_bbox(
        self, 
        line_num: int, 
        start_char: int, 
        end_char: int, 
        line_length: int
    ) -> List[int]:
        """Estimate bounding box coordinates based on text position"""
        # Rough estimates - in production use proper layout analysis
        page_width = 612  # Letter size in points
        page_height = 792
        margin = 72
        line_height = 14
        char_width = 7
        
        x1 = margin + (start_char * char_width)
        y1 = margin + (line_num * line_height)
        x2 = min(x1 + ((end_char - start_char) * char_width), page_width - margin)
        y2 = y1 + line_height * 3  # Signature area height
        
        return [int(x1), int(y1), int(x2), int(y2)]
    
    def _estimate_page(self, line_num: int, total_lines: int) -> int:
        """Estimate page number based on line position"""
        lines_per_page = 50  # Rough estimate
        return (line_num // lines_per_page) + 1
    
    def _extract_role_hint(self, text: str) -> str:
        """Extract signer role from surrounding text"""
        text_lower = text.lower()
        
        # Common role patterns
        role_patterns = {
            "client": ["client", "customer", "buyer", "purchaser", "tenant"],
            "company": ["company", "corporation", "seller", "vendor", "landlord", "provider"],
            "witness": ["witness", "testigo"],
            "notary": ["notary", "notario"],
            "party_1": ["party of the first part", "party 1", "first party"],
            "party_2": ["party of the second part", "party 2", "second party"],
            "employee": ["employee", "worker", "empleado"],
            "employer": ["employer", "company", "empleador"],
            "authorized": ["authorized", "representative", "agent"]
        }
        
        for role, patterns in role_patterns.items():
            if any(p in text_lower for p in patterns):
                return role
        
        return "signer"  # Default role
    
    def _apply_document_type_rules(
        self, 
        zones: List[Dict[str, Any]], 
        document_type: str
    ) -> List[Dict[str, Any]]:
        """Apply document type specific rules to improve detection"""
        
        if document_type == "contract":
            # Contracts typically have signatures at the end
            # Boost confidence for zones in last 25% of document
            for zone in zones:
                if zone["page"] == max(z["page"] for z in zones):
                    zone["confidence"] *= 1.2
                    zone["confidence"] = min(zone["confidence"], 1.0)
            
            # Look for paired signatures (client/company)
            self._detect_paired_signatures(zones)
            
        elif document_type == "form":
            # Forms may have signatures anywhere
            # Look for form field indicators
            pass
            
        elif document_type == "letter":
            # Letters typically have single signature at end
            # Filter to keep only last signature zone
            if len(zones) > 1:
                last_zone = max(zones, key=lambda z: (z["page"], z["bbox"][1]))
                last_zone["confidence"] = 0.9
                zones = [last_zone]
        
        return zones
    
    def _detect_paired_signatures(self, zones: List[Dict[str, Any]]):
        """Detect paired signatures (e.g., client and company side by side)"""
        # Group zones by page
        pages = {}
        for zone in zones:
            page = zone["page"]
            if page not in pages:
                pages[page] = []
            pages[page].append(zone)
        
        # Check for horizontally aligned signatures
        for page_zones in pages.values():
            for i, zone1 in enumerate(page_zones):
                for zone2 in page_zones[i+1:]:
                    # Check if zones are roughly on same line
                    y_diff = abs(zone1["bbox"][1] - zone2["bbox"][1])
                    if y_diff < 20:  # Roughly same line
                        # They form a pair
                        zone1["pair_id"] = f"pair_{i}"
                        zone2["pair_id"] = f"pair_{i}"
                        
                        # Assign roles based on position
                        if zone1["bbox"][0] < zone2["bbox"][0]:
                            zone1["role_hint"] = "party_1"
                            zone2["role_hint"] = "party_2"
    
    async def _detect_visual_signature_zones(
        self, 
        document_content: bytes
    ) -> List[Dict[str, Any]]:
        """
        Detect signature zones using computer vision
        (Placeholder for future implementation)
        """
        # In production, this would:
        # 1. Convert PDF pages to images
        # 2. Use CV to detect lines, boxes, and signature areas
        # 3. Use OCR to read nearby text
        # 4. Return visual zones with coordinates
        
        return []