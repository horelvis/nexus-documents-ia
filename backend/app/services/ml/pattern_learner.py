"""
Pattern Learning System for Signature Placements
Learns from user behavior to improve future suggestions
"""
import logging
import json
from typing import List, Dict, Any, Optional
from datetime import datetime
# ML dependencies (optional for now)
# import numpy as np
# from sklearn.cluster import DBSCAN
# import joblib
import os

logger = logging.getLogger(__name__)


class PatternLearner:
    """
    Learns patterns from user signature placements to improve AI suggestions
    """
    
    def __init__(self, model_path: Optional[str] = None):
        self.model_path = model_path or "models/signature_patterns"
        self.patterns_by_type = {}
        self.clustering_models = {}
        self._load_models()
    
    async def train_on_new_placement(
        self,
        document_type: str,
        placed_fields: List[Dict[str, Any]]
    ):
        """
        Train the model with new user placement data
        """
        try:
            # Convert placements to feature vectors
            features = self._extract_features(placed_fields)
            
            # Add to training data
            if document_type not in self.patterns_by_type:
                self.patterns_by_type[document_type] = {
                    "placements": [],
                    "features": [],
                    "last_updated": None
                }
            
            self.patterns_by_type[document_type]["placements"].append({
                "fields": placed_fields,
                "timestamp": datetime.utcnow().isoformat(),
                "features": features
            })
            
            self.patterns_by_type[document_type]["features"].append(features)
            self.patterns_by_type[document_type]["last_updated"] = datetime.utcnow()
            
            # Retrain clustering model if enough data
            if len(self.patterns_by_type[document_type]["features"]) >= 10:
                await self._retrain_clustering(document_type)
            
            # Save updated models
            self._save_models()
            
        except Exception as e:
            logger.error(f"Error training on new placement: {str(e)}")
    
    def predict_placements(
        self,
        document_type: str,
        document_features: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Predict optimal placements based on learned patterns
        """
        try:
            if document_type not in self.patterns_by_type:
                return []
            
            # Find similar patterns using clustering
            if document_type in self.clustering_models:
                model = self.clustering_models[document_type]
                
                # Transform document features to match training format
                feature_vector = self._document_to_features(document_features)
                
                # Find nearest cluster (simplified without numpy)
                distances = []
                for cluster_features in self.patterns_by_type[document_type]["features"]:
                    # Calculate Euclidean distance manually
                    dist = sum((a - b) ** 2 for a, b in zip(feature_vector, cluster_features)) ** 0.5
                    distances.append(dist)
                
                # Get placements from nearest patterns
                nearest_idx = distances.index(min(distances)) if distances else 0
                nearest_placement = self.patterns_by_type[document_type]["placements"][nearest_idx]
                
                return self._adapt_placement_to_document(
                    nearest_placement["fields"],
                    document_features
                )
            
            return []
            
        except Exception as e:
            logger.error(f"Error predicting placements: {str(e)}")
            return []
    
    def get_confidence_score(
        self,
        document_type: str,
        placement: Dict[str, Any]
    ) -> float:
        """
        Calculate confidence score for a placement based on historical data
        """
        if document_type not in self.patterns_by_type:
            return 0.5  # No data, neutral confidence
        
        # Calculate based on similarity to existing patterns
        similar_count = 0
        total_count = len(self.patterns_by_type[document_type]["placements"])
        
        if total_count == 0:
            return 0.5
        
        placement_features = self._extract_single_field_features(placement)
        
        for historical in self.patterns_by_type[document_type]["placements"]:
            for field in historical["fields"]:
                hist_features = self._extract_single_field_features(field)
                if self._are_similar_placements(placement_features, hist_features):
                    similar_count += 1
        
        confidence = similar_count / (total_count * 2)  # Normalize
        return min(confidence, 0.95)  # Cap at 95%
    
    def _extract_features(self, placed_fields: List[Dict[str, Any]]) -> List[float]:
        """
        Extract features from field placements for ML
        """
        features = []
        
        # Number of fields
        features.append(len(placed_fields))
        
        # Field types distribution
        type_counts = {"signature": 0, "date": 0, "text": 0, "other": 0}
        for field in placed_fields:
            field_type = field.get("type", "other")
            if field_type in type_counts:
                type_counts[field_type] += 1
            else:
                type_counts["other"] += 1
        
        features.extend(type_counts.values())
        
        # Spatial features
        if placed_fields:
            # Average position (simple calculation without numpy)
            x_values = [f.get("x", 0) for f in placed_fields]
            y_values = [f.get("y", 0) for f in placed_fields]
            avg_x = sum(x_values) / len(x_values) if x_values else 0
            avg_y = sum(y_values) / len(y_values) if y_values else 0
            features.extend([avg_x, avg_y])
            
            # Position variance (simplified)
            var_x = sum((x - avg_x) ** 2 for x in x_values) / len(x_values) if x_values else 0
            var_y = sum((y - avg_y) ** 2 for y in y_values) / len(y_values) if y_values else 0
            features.extend([var_x, var_y])
            
            # Page distribution
            pages = [f.get("page", 1) for f in placed_fields]
            features.append(max(pages))  # Last page with signature
            features.append(len(set(pages)))  # Number of pages with signatures
        else:
            features.extend([0, 0, 0, 0, 0, 0])
        
        return features
    
    def _extract_single_field_features(self, field: Dict[str, Any]) -> Dict[str, Any]:
        """Extract features from a single field"""
        return {
            "type": field.get("type", "signature"),
            "relative_x": field.get("x", 0) / 612.0,  # Normalize to page width
            "relative_y": field.get("y", 0) / 792.0,  # Normalize to page height
            "relative_width": field.get("width", 200) / 612.0,
            "relative_height": field.get("height", 50) / 792.0,
            "page": field.get("page", 1),
            "required": field.get("required", True)
        }
    
    def _are_similar_placements(
        self, 
        features1: Dict[str, Any], 
        features2: Dict[str, Any]
    ) -> bool:
        """Check if two placements are similar"""
        # Type must match
        if features1["type"] != features2["type"]:
            return False
        
        # Position similarity (within 5% of page dimensions)
        position_threshold = 0.05
        if abs(features1["relative_x"] - features2["relative_x"]) > position_threshold:
            return False
        if abs(features1["relative_y"] - features2["relative_y"]) > position_threshold:
            return False
        
        # Same page or relative page position
        if features1["page"] != features2["page"]:
            # Check if both are on last page (negative page numbers)
            if features1["page"] < 0 and features2["page"] < 0:
                return True
            return False
        
        return True
    
    def _document_to_features(self, document_features: Dict[str, Any]) -> List[float]:
        """Convert document features to ML feature vector"""
        # This should match the format of _extract_features
        features = []
        
        # Expected number of signatures based on document type
        features.append(document_features.get("expected_signers", 2))
        
        # Document type encoded
        features.extend([1, 0, 0, 0])  # One-hot encoding placeholder
        
        # Document length/complexity
        features.extend([
            document_features.get("page_count", 1),
            document_features.get("text_density", 0.5),
            0, 0,  # Spatial features placeholders
            document_features.get("page_count", 1),
            1  # Single document
        ])
        
        return features
    
    def _adapt_placement_to_document(
        self,
        template_fields: List[Dict[str, Any]],
        document_features: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Adapt template placement to specific document"""
        adapted_fields = []
        
        for field in template_fields:
            adapted_field = field.copy()
            
            # Adjust page numbers
            if field.get("page", 1) < 0:
                # Negative page means from end
                adapted_field["page"] = document_features.get("page_count", 1) + field["page"] + 1
            
            # Scale positions if document size differs
            # (In production, would do more sophisticated adaptation)
            
            adapted_fields.append(adapted_field)
        
        return adapted_fields
    
    async def _retrain_clustering(self, document_type: str):
        """Retrain clustering model for document type"""
        try:
            # Simplified clustering without sklearn for now
            # In production, this would use DBSCAN or similar
            features = self.patterns_by_type[document_type]["features"]
            
            # Store a simple model placeholder
            self.clustering_models[document_type] = {
                "type": "simple",
                "features": features,
                "samples": len(features)
            }
            
            logger.info(f"Updated patterns for {document_type} with {len(features)} samples")
            
        except Exception as e:
            logger.error(f"Error updating patterns: {str(e)}")
    
    def _save_models(self):
        """Save models to disk"""
        try:
            os.makedirs(self.model_path, exist_ok=True)
            
            # Save patterns
            patterns_file = os.path.join(self.model_path, "patterns.json")
            with open(patterns_file, 'w') as f:
                # Convert datetime objects to strings
                patterns_data = {}
                for doc_type, data in self.patterns_by_type.items():
                    patterns_data[doc_type] = {
                        "placements": data["placements"],
                        "last_updated": data["last_updated"].isoformat() if data["last_updated"] else None
                    }
                json.dump(patterns_data, f)
            
            # Save clustering models as JSON (simplified without joblib)
            for doc_type, model in self.clustering_models.items():
                model_file = os.path.join(self.model_path, f"clustering_{doc_type}.json")
                with open(model_file, 'w') as f:
                    json.dump(model, f)
                
        except Exception as e:
            logger.error(f"Error saving models: {str(e)}")
    
    def _load_models(self):
        """Load models from disk"""
        try:
            # Load patterns
            patterns_file = os.path.join(self.model_path, "patterns.json")
            if os.path.exists(patterns_file):
                with open(patterns_file, 'r') as f:
                    patterns_data = json.load(f)
                    
                for doc_type, data in patterns_data.items():
                    self.patterns_by_type[doc_type] = {
                        "placements": data["placements"],
                        "features": [p["features"] for p in data["placements"]],
                        "last_updated": datetime.fromisoformat(data["last_updated"]) if data["last_updated"] else None
                    }
            
            # Load clustering models (simplified JSON format)
            if os.path.exists(self.model_path):
                for file in os.listdir(self.model_path):
                    if file.startswith("clustering_") and file.endswith(".json"):
                        doc_type = file.replace("clustering_", "").replace(".json", "")
                        model_file = os.path.join(self.model_path, file)
                        with open(model_file, 'r') as f:
                            self.clustering_models[doc_type] = json.load(f)
                        
        except Exception as e:
            logger.error(f"Error loading models: {str(e)}")