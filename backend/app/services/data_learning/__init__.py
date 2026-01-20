"""
Data Learning System

A system that learns the nature of data from connectors like Alfresco,
understanding content models, folder semantics, property importance,
and relationships to optimize indexing and retrieval.

Main Components:
- ContentModelDiscoveryService: Discovers content types, aspects, properties
- FolderStructureAnalyzer: Learns folder hierarchy semantics
- MetadataIntelligenceService: Maps properties, calculates search importance
- RelationshipLearner: Extracts associations for Knowledge Graph
- IndexingStrategyOptimizer: Generates optimal indexing strategies
- LearningOrchestrator: Orchestrates the complete learning workflow
"""
from .content_model_discovery import ContentModelDiscoveryService
from .folder_structure_analyzer import FolderStructureAnalyzer
from .metadata_intelligence import MetadataIntelligenceService
from .relationship_learner import RelationshipLearner
from .indexing_strategy_optimizer import IndexingStrategyOptimizer
from .learning_orchestrator import LearningOrchestrator

__all__ = [
    "ContentModelDiscoveryService",
    "FolderStructureAnalyzer",
    "MetadataIntelligenceService",
    "RelationshipLearner",
    "IndexingStrategyOptimizer",
    "LearningOrchestrator",
]
