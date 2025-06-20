"""
AI Service for Intelligent Signature Placement
Handles document classification, POI detection, and learning from user behavior
"""
import logging
import json
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from uuid import UUID
import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
import asyncio

from app.db.models import Document, SignatureFieldPlacement, DocumentTypeClassification, SignaturePlacementPattern
from app.core.config import settings
from app.services.signature_ai_client import signature_ai_client
# Local ML modules (simplified versions for pattern storage)
from app.services.ml.pattern_learner import PatternLearner

logger = logging.getLogger(__name__)


class SignatureAIService:
    """
    AI Service for intelligent signature placement and document assistance
    """
    
    def __init__(self, tenant_id: UUID):
        self.tenant_id = tenant_id
        self.pattern_learner = PatternLearner()
        self.ai_client = signature_ai_client
        
    async def analyze_document(
        self, 
        db: AsyncSession,
        document_id: UUID,
        document_content: bytes,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Analyze document and suggest signature placements
        
        Returns:
            {
                "document_type": "contract|agreement|form|other",
                "confidence": 0.95,
                "suggested_fields": [
                    {
                        "type": "signature",
                        "signer_role": "party_1",
                        "x": 100,
                        "y": 500,
                        "width": 200,
                        "height": 50,
                        "page": 1,
                        "confidence": 0.89,
                        "reason": "Standard signature location for contracts"
                    }
                ],
                "detected_zones": [
                    {
                        "type": "signature_line",
                        "bbox": [100, 500, 300, 550],
                        "page": 1,
                        "text_nearby": "Signature: _______"
                    }
                ],
                "similar_documents": [...]
            }
        """
        try:
            # Step 1: Analyze document using LangChain service
            text_content = document_content.decode('utf-8', errors='ignore')
            analysis_result = await self.ai_client.analyze_document_content(
                text_content,
                metadata
            )
            
            doc_type_result = {
                "document_type": analysis_result.get("document_type", "unknown"),
                "confidence": analysis_result.get("confidence", 0.0)
            }
            
            # Step 2: Detect POIs using LangChain service
            zones = await self.ai_client.detect_signature_zones(
                text_content,
                doc_type_result["document_type"]
            )
            
            poi_results = {"zones": zones}
            
            # Step 3: Get learned patterns for this document type
            patterns = await self._get_patterns_for_type(
                db, 
                doc_type_result["document_type"]
            )
            
            # Step 4: Generate field suggestions based on POIs and patterns
            suggested_fields = await self._generate_field_suggestions(
                poi_results["zones"],
                patterns,
                doc_type_result["document_type"]
            )
            
            # Step 5: Find similar documents for reference
            similar_docs = await self._find_similar_documents(
                db,
                doc_type_result["document_type"],
                metadata
            )
            
            return {
                "document_type": doc_type_result["document_type"],
                "confidence": doc_type_result["confidence"],
                "suggested_fields": suggested_fields,
                "detected_zones": poi_results["zones"],
                "similar_documents": similar_docs,
                "learning_data": {
                    "patterns_used": len(patterns),
                    "poi_detected": len(poi_results["zones"]),
                    "suggestion_source": self._determine_suggestion_source(
                        suggested_fields, 
                        poi_results["zones"], 
                        patterns
                    )
                }
            }
            
        except Exception as e:
            logger.error(f"Error analyzing document: {str(e)}")
            return {
                "document_type": "unknown",
                "confidence": 0.0,
                "suggested_fields": [],
                "detected_zones": [],
                "error": str(e)
            }
    
    async def learn_from_placement(
        self,
        db: AsyncSession,
        document_id: UUID,
        document_type: str,
        placed_fields: List[Dict[str, Any]],
        user_id: UUID
    ) -> bool:
        """
        Learn from user's manual field placements to improve future suggestions
        """
        try:
            # Record the placement
            for field in placed_fields:
                placement = SignatureFieldPlacement(
                    document_id=document_id,
                    tenant_id=self.tenant_id,
                    user_id=user_id,
                    field_type=field["type"],
                    signer_identifier=field.get("signer", "default"),
                    x_position=field["x"],
                    y_position=field["y"],
                    width=field["width"],
                    height=field["height"],
                    page_number=field["page"],
                    is_required=field.get("required", True),
                    field_metadata=field.get("metadata", {})
                )
                db.add(placement)
            
            # Update patterns
            await self._update_patterns(db, document_type, placed_fields)
            
            # Train the pattern learner with new data
            await self.pattern_learner.train_on_new_placement(
                document_type,
                placed_fields
            )
            
            await db.commit()
            return True
            
        except Exception as e:
            logger.error(f"Error learning from placement: {str(e)}")
            await db.rollback()
            return False
    
    async def get_placement_suggestions_for_signers(
        self,
        db: AsyncSession,
        document_id: UUID,
        signers: List[Dict[str, Any]],
        document_analysis: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Generate specific field placements for given signers based on document analysis
        """
        suggested_fields = []
        detected_zones = document_analysis.get("detected_zones", [])
        
        # Assign zones to signers intelligently
        for i, signer in enumerate(signers):
            signer_fields = []
            
            # Find signature zones for this signer
            if i < len(detected_zones):
                zone = detected_zones[i]
                signer_fields.append({
                    "id": f"sig-{signer['id']}-{i}",
                    "type": "signature",
                    "signer": signer["id"],
                    "x": zone["bbox"][0],
                    "y": zone["bbox"][1],
                    "width": zone["bbox"][2] - zone["bbox"][0],
                    "height": zone["bbox"][3] - zone["bbox"][1],
                    "page": zone["page"],
                    "required": True,
                    "label": f"{signer['name']} Signature",
                    "confidence": zone.get("confidence", 0.8)
                })
            
            # Add date field near signature
            if signer_fields and document_analysis["document_type"] in ["contract", "agreement"]:
                sig_field = signer_fields[0]
                signer_fields.append({
                    "id": f"date-{signer['id']}-{i}",
                    "type": "date",
                    "signer": signer["id"],
                    "x": sig_field["x"] + sig_field["width"] + 20,
                    "y": sig_field["y"],
                    "width": 150,
                    "height": sig_field["height"],
                    "page": sig_field["page"],
                    "required": True,
                    "label": "Date",
                    "confidence": 0.7
                })
            
            suggested_fields.extend(signer_fields)
        
        return suggested_fields
    
    async def _get_patterns_for_type(
        self, 
        db: AsyncSession, 
        document_type: str
    ) -> List[Dict[str, Any]]:
        """Get learned patterns for a document type"""
        stmt = select(SignaturePlacementPattern).filter(
            SignaturePlacementPattern.tenant_id == self.tenant_id,
            SignaturePlacementPattern.document_type == document_type,
            SignaturePlacementPattern.is_active == True
        ).order_by(SignaturePlacementPattern.confidence.desc())
        
        result = await db.execute(stmt)
        patterns = result.scalars().all()
        
        return [
            {
                "pattern_id": p.id,
                "field_configurations": p.field_configurations,
                "confidence": p.confidence,
                "usage_count": p.usage_count
            }
            for p in patterns
        ]
    
    async def _generate_field_suggestions(
        self,
        detected_zones: List[Dict[str, Any]],
        patterns: List[Dict[str, Any]],
        document_type: str
    ) -> List[Dict[str, Any]]:
        """Generate field suggestions based on POIs and patterns"""
        suggestions = []
        
        # First, use detected zones
        for i, zone in enumerate(detected_zones):
            suggestions.append({
                "type": "signature",
                "signer_role": f"party_{i + 1}",
                "x": zone["bbox"][0],
                "y": zone["bbox"][1],
                "width": zone["bbox"][2] - zone["bbox"][0],
                "height": zone["bbox"][3] - zone["bbox"][1],
                "page": zone["page"],
                "confidence": zone.get("confidence", 0.8),
                "reason": f"Detected signature zone: {zone.get('text_nearby', 'signature line')}",
                "source": "poi_detection"
            })
        
        # If no zones detected, use patterns
        if not suggestions and patterns:
            best_pattern = patterns[0]  # Highest confidence pattern
            for field_config in best_pattern["field_configurations"]:
                suggestions.append({
                    **field_config,
                    "confidence": best_pattern["confidence"],
                    "reason": f"Based on pattern from {best_pattern['usage_count']} similar documents",
                    "source": "learned_pattern"
                })
        
        # If still no suggestions, use document type defaults
        if not suggestions:
            suggestions = self._get_default_suggestions(document_type)
        
        return suggestions
    
    async def _find_similar_documents(
        self,
        db: AsyncSession,
        document_type: str,
        metadata: Optional[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Find similar documents that have been signed"""
        # Query for documents of same type with signature placements
        stmt = select(Document).join(SignatureFieldPlacement).filter(
            Document.tenant_id == self.tenant_id,
            Document.category == document_type
        ).distinct().limit(5)
        
        result = await db.execute(stmt)
        documents = result.scalars().all()
        
        return [
            {
                "document_id": doc.id,
                "title": doc.title,
                "signed_at": doc.updated_at,
                "field_count": len(doc.signature_placements) if hasattr(doc, 'signature_placements') else 0
            }
            for doc in documents
        ]
    
    async def _update_patterns(
        self,
        db: AsyncSession,
        document_type: str,
        placed_fields: List[Dict[str, Any]]
    ):
        """Update or create patterns based on new placements"""
        # Convert placements to pattern configuration
        field_config = [
            {
                "type": field["type"],
                "relative_x": field["x"],  # TODO: Convert to relative coordinates
                "relative_y": field["y"],
                "relative_width": field["width"],
                "relative_height": field["height"],
                "page": field["page"]
            }
            for field in placed_fields
        ]
        
        # Check if similar pattern exists
        # For now, create new pattern
        pattern = SignaturePlacementPattern(
            tenant_id=self.tenant_id,
            document_type=document_type,
            field_configurations=field_config,
            confidence=0.7,  # Initial confidence
            usage_count=1,
            is_active=True,
            pattern_metadata={
                "created_from": "user_placement",
                "timestamp": datetime.utcnow().isoformat()
            }
        )
        db.add(pattern)
    
    def _determine_suggestion_source(
        self,
        suggestions: List[Dict[str, Any]],
        zones: List[Dict[str, Any]],
        patterns: List[Dict[str, Any]]
    ) -> str:
        """Determine primary source of suggestions"""
        if not suggestions:
            return "none"
        
        sources = [s.get("source", "unknown") for s in suggestions]
        if "poi_detection" in sources:
            return "poi_detection"
        elif "learned_pattern" in sources:
            return "learned_pattern"
        else:
            return "defaults"
    
    def _get_default_suggestions(self, document_type: str) -> List[Dict[str, Any]]:
        """Get default suggestions based on document type"""
        defaults = {
            "contract": [
                {
                    "type": "signature",
                    "signer_role": "party_1",
                    "x": 100,
                    "y": 600,
                    "width": 200,
                    "height": 50,
                    "page": -1,  # Last page
                    "confidence": 0.5,
                    "reason": "Default contract signature position",
                    "source": "defaults"
                },
                {
                    "type": "signature",
                    "signer_role": "party_2",
                    "x": 350,
                    "y": 600,
                    "width": 200,
                    "height": 50,
                    "page": -1,
                    "confidence": 0.5,
                    "reason": "Default contract signature position",
                    "source": "defaults"
                }
            ],
            "agreement": [
                {
                    "type": "signature",
                    "signer_role": "party_1",
                    "x": 100,
                    "y": 650,
                    "width": 250,
                    "height": 60,
                    "page": -1,
                    "confidence": 0.5,
                    "reason": "Default agreement signature position",
                    "source": "defaults"
                }
            ]
        }
        
        return defaults.get(document_type, [
            {
                "type": "signature",
                "signer_role": "signer",
                "x": 100,
                "y": 600,
                "width": 200,
                "height": 50,
                "page": -1,
                "confidence": 0.3,
                "reason": "Generic signature position",
                "source": "defaults"
            }
        ])