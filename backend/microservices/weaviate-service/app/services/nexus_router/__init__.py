"""
NexusRouter - Intent Classification System with SetFit ML

A trainable intent classifier that learns from:
1. Historical user queries from interaction logs
2. Document metadata from indexed documents
3. Entity information from knowledge extraction
4. Synthetic queries generated from document types

Architecture:
┌─────────────────────────────────────────────────────────────────────────────┐
│                         NEXUS ROUTER SYSTEM                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  1. TRAINING PIPELINE                                                        │
│     ├─ DataCollector: Collects data from PostgreSQL + Weaviate              │
│     ├─ DatasetBuilder: Generates balanced training dataset                   │
│     └─ ModelTrainer: Fine-tunes SetFit with dataset                          │
│                                                                              │
│  2. INFERENCE ENGINE                                                         │
│     ├─ IntentClassifier: Classifies intent (SetFit, ~5ms)                    │
│     ├─ EntityExtractor: Extracts entities (spaCy, ~3ms)                      │
│     └─ ActionRouter: Decides action based on intent+entities                 │
│                                                                              │
│  3. POST-SYNC HOOK                                                           │
│     └─ Triggers retraining after connector sync                              │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘

Usage:
    from app.services.nexus_router import nexus_router, IntentClassification

    # Classify a query
    result = await nexus_router.classify(
        query="¿Cuántos contratos tengo?",
        tenant_id="tenant-123"
    )

    if result.required_action == RequiredAction.FORCE_SEARCH:
        # Force document search before LLM
        search_results = await search(...)

Intents:
    - SEARCH: Buscar documentos
    - COUNT: Contar documentos
    - LIST: Listar documentos
    - ANALYZE: Analizar contenido
    - COMPARE: Comparar documentos
    - SUMMARIZE: Resumir documento
    - EXTRACT: Extraer información
    - CHAT: Conversación general
"""

from .schemas import (
    # Core data models
    Intent,
    RequiredAction,
    IntentClassification,
    TrainingExample,
    TrainingDataset,
    # Configuration
    NexusRouterConfig,
    ModelMetadata,
    # Statistics
    RouterMetrics,
    ClassificationStats,
)

from .data_collector import DataCollector, data_collector
from .dataset_builder import DatasetBuilder, dataset_builder
from .model_trainer import ModelTrainer, model_trainer
from .intent_classifier import IntentClassifier, intent_classifier
from .entity_extractor import EntityExtractor, entity_extractor
from .action_router import ActionRouter, action_router, nexus_router

__all__ = [
    # Main entry point
    "nexus_router",
    # Core services
    "DataCollector",
    "data_collector",
    "DatasetBuilder",
    "dataset_builder",
    "ModelTrainer",
    "model_trainer",
    "IntentClassifier",
    "intent_classifier",
    "EntityExtractor",
    "entity_extractor",
    "ActionRouter",
    "action_router",
    # Data models
    "Intent",
    "RequiredAction",
    "IntentClassification",
    "TrainingExample",
    "TrainingDataset",
    # Configuration
    "NexusRouterConfig",
    "ModelMetadata",
    # Statistics
    "RouterMetrics",
    "ClassificationStats",
]
