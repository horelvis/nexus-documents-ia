"""
Knowledge Source Learning System

Collects training examples and trains the SetFit knowledge source classifier.

Features:
- Auto-collects examples from Emma V2 tool usage patterns
- Stores examples in JSON files for persistence
- Trains SetFit model with collected + seed data
- Hot-reload support after training

Data Collection Patterns:
- SIL returns 0 docs + legal_search used → actual = PUBLIC_KNOWLEDGE
- SIL returns >0 docs + no legal_search → actual = TENANT_DOCUMENTS
- Both sources used → actual = HYBRID
- User correction → override predicted with actual

Architecture:
┌─────────────────────────────────────────────────────────────────────────────┐
│                    KNOWLEDGE LEARNING SYSTEM                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  1. DATA COLLECTION                                                          │
│     ├─ KnowledgeLearningCollector: Collects examples from Emma usage        │
│     ├─ Auto-detection: Infers actual source from tool usage                 │
│     └─ Storage: JSON files in /app/data/knowledge_examples/                  │
│                                                                              │
│  2. MODEL TRAINING                                                           │
│     ├─ KnowledgeModelTrainer: Fine-tunes SetFit with collected data         │
│     ├─ Data sources: Seed data + Collected examples                         │
│     └─ Versioning: Models saved with timestamps                              │
│                                                                              │
│  3. API ENDPOINTS                                                            │
│     ├─ POST /router/knowledge/train: Trigger training                        │
│     ├─ GET /router/knowledge/status: Get training status                     │
│     └─ POST /router/knowledge/correct: Submit correction                     │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘

Usage:
    from app.services.nexus_router.knowledge_learning import (
        knowledge_collector,
        knowledge_trainer,
    )

    # Collect example from Emma's tool usage
    await knowledge_collector.collect_from_tool_usage(
        query="¿Cuántos días de vacaciones por ley?",
        predicted_source=KnowledgeSource.TENANT_DOCUMENTS,
        tools_used=["legal_search"],  # Used public search
        sil_doc_count=0,  # SIL found nothing
        tenant_id="tenant-123"
    )

    # Train model with collected data
    result = await knowledge_trainer.train()
    print(f"Model trained: {result.version}, accuracy: {result.accuracy}")
"""

import asyncio
import json
import logging
import os
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import aiofiles
    AIOFILES_AVAILABLE = True
except ImportError:
    AIOFILES_AVAILABLE = False

from app.core.learning_config import learning_settings
from app.core.learning_constants import (
    CORRECTION_WEIGHT_MULTIPLIER,
    LOG_QUERY_PREVIEW_LENGTH,
)
from app.core.learning_exceptions import (
    InsufficientDataError,
    FileSystemError,
)

from .knowledge_classifier import (
    KnowledgeSource,
    KnowledgeTrainingExample,
    KnowledgeClassifierConfig,
    KNOWLEDGE_SOURCE_SEEDS,
    get_knowledge_classifier,
)

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION
# =============================================================================

class KnowledgeLearningConfig:
    """
    Configuration for knowledge learning system.

    Note: Default values are loaded from centralized learning_settings.
    """

    def __init__(self):
        """Initialize with values from centralized settings."""
        # Storage paths
        self.data_dir: str = learning_settings.knowledge_examples_dir
        self.examples_file: str = "collected_examples.json"
        self.corrections_file: str = "corrections.json"

        # Model paths
        self.model_dir: str = str(learning_settings.get_knowledge_source_model_path())

        # Training settings
        self.min_examples_to_train: int = learning_settings.knowledge_min_examples_to_train
        self.min_examples_per_source: int = learning_settings.knowledge_min_examples_per_source
        self.train_eval_split: float = learning_settings.knowledge_train_eval_split

        # Collection settings
        self.max_examples_per_source: int = learning_settings.knowledge_max_examples_per_source
        self.dedup_by_text: bool = learning_settings.knowledge_dedup_by_text


# =============================================================================
# DATA COLLECTOR
# =============================================================================

class KnowledgeLearningCollector:
    """
    Collects training examples from Emma's tool usage.

    Automatically infers the actual knowledge source based on:
    - Whether SIL returned documents
    - Which tools were used (legal_search vs search)
    - User corrections
    """

    def __init__(self, config: Optional[KnowledgeLearningConfig] = None):
        self.config = config or KnowledgeLearningConfig()
        self._ensure_data_dir()

    def _ensure_data_dir(self):
        """Ensure data directory exists."""
        Path(self.config.data_dir).mkdir(parents=True, exist_ok=True)

    def _get_examples_path(self) -> Path:
        """Get path to examples file."""
        return Path(self.config.data_dir) / self.config.examples_file

    def _get_corrections_path(self) -> Path:
        """Get path to corrections file."""
        return Path(self.config.data_dir) / self.config.corrections_file

    async def collect_from_tool_usage(
        self,
        query: str,
        predicted_source: KnowledgeSource,
        tools_used: List[str],
        sil_doc_count: int,
        tenant_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[KnowledgeTrainingExample]:
        """
        Collect a training example based on tool usage patterns.

        Inference rules:
        - legal_search used + SIL=0 → PUBLIC_KNOWLEDGE
        - search/sil_query used + SIL>0 → TENANT_DOCUMENTS
        - Both legal_search AND search used → HYBRID

        Args:
            query: User's original query
            predicted_source: What the router predicted
            tools_used: List of tools Emma used (e.g., ["legal_search", "search"])
            sil_doc_count: Number of documents SIL returned
            tenant_id: Tenant ID
            metadata: Optional additional metadata

        Returns:
            KnowledgeTrainingExample if collected, None if skipped
        """
        # Infer actual source from tool usage
        used_legal = "legal_search" in tools_used
        used_tenant = any(t in tools_used for t in ["search", "sil_query", "read_document"])

        if used_legal and used_tenant:
            actual_source = KnowledgeSource.HYBRID
        elif used_legal and sil_doc_count == 0:
            actual_source = KnowledgeSource.PUBLIC_KNOWLEDGE
        elif used_tenant and sil_doc_count > 0:
            actual_source = KnowledgeSource.TENANT_DOCUMENTS
        else:
            # Ambiguous - skip collection
            logger.debug(f"Skipping collection for ambiguous case: tools={tools_used}, sil_count={sil_doc_count}")
            return None

        # Check if prediction was correct
        was_correct = (predicted_source == actual_source)

        example = KnowledgeTrainingExample(
            text=query.strip(),
            source=actual_source,
            source_type="collected",
            tenant_id=tenant_id,
            created_at=datetime.now(),
            predicted_source=predicted_source,
            was_correct=was_correct,
        )

        # Store the example
        await self._store_example(example)

        log_level = logging.DEBUG if was_correct else logging.INFO
        logger.log(
            log_level,
            f"📚 Collected knowledge example: predicted={predicted_source.value}, "
            f"actual={actual_source.value}, correct={was_correct}, "
            f"query='{query[:50]}...'"
        )

        return example

    async def collect_correction(
        self,
        query: str,
        predicted_source: KnowledgeSource,
        actual_source: KnowledgeSource,
        tenant_id: str,
        user_id: Optional[str] = None,
    ) -> KnowledgeTrainingExample:
        """
        Collect a user-provided correction.

        Used when user explicitly indicates the correct source.

        Args:
            query: User's original query
            predicted_source: What the router predicted
            actual_source: What the user says is correct
            tenant_id: Tenant ID
            user_id: Optional user ID

        Returns:
            KnowledgeTrainingExample
        """
        example = KnowledgeTrainingExample(
            text=query.strip(),
            source=actual_source,
            source_type="corrected",
            tenant_id=tenant_id,
            created_at=datetime.now(),
            predicted_source=predicted_source,
            was_correct=False,  # Corrections are by definition incorrect predictions
        )

        # Store in corrections file (higher priority during training)
        await self._store_correction(example)

        logger.info(
            f"📝 Collected correction: predicted={predicted_source.value} → "
            f"actual={actual_source.value}, query='{query[:50]}...'"
        )

        return example

    async def _store_example(self, example: KnowledgeTrainingExample) -> None:
        """Store example to JSON file."""
        path = self._get_examples_path()
        examples = await self._load_examples(path)

        # Deduplication by text
        if self.config.dedup_by_text:
            existing_texts = {ex["text"] for ex in examples}
            if example.text in existing_texts:
                logger.debug(f"Skipping duplicate example: '{example.text[:50]}...'")
                return

        # Check max examples per source
        source_count = sum(1 for ex in examples if ex["source"] == example.source.value)
        if source_count >= self.config.max_examples_per_source:
            logger.debug(f"Max examples reached for {example.source.value}, skipping")
            return

        examples.append(example.to_dict())
        await self._save_examples(path, examples)

    async def _store_correction(self, example: KnowledgeTrainingExample) -> None:
        """Store correction to corrections file."""
        path = self._get_corrections_path()
        corrections = await self._load_examples(path)

        # Always store corrections (they're valuable)
        corrections.append(example.to_dict())
        await self._save_examples(path, corrections)

    async def _load_examples(self, path: Path) -> List[Dict]:
        """Load examples from JSON file using async I/O when available."""
        if not path.exists():
            return []
        try:
            if AIOFILES_AVAILABLE:
                async with aiofiles.open(path, 'r', encoding='utf-8') as f:
                    content = await f.read()
                    return json.loads(content)
            else:
                # Fallback to sync I/O (still works in async context)
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except json.JSONDecodeError as e:
            logger.warning(f"Invalid JSON in {path}: {e}")
            return []
        except IOError as e:
            logger.warning(f"Failed to load examples from {path}: {e}")
            return []

    async def _save_examples(self, path: Path, examples: List[Dict]) -> None:
        """Save examples to JSON file using async I/O when available."""
        try:
            content = json.dumps(examples, ensure_ascii=False, indent=2, default=str)
            if AIOFILES_AVAILABLE:
                async with aiofiles.open(path, 'w', encoding='utf-8') as f:
                    await f.write(content)
            else:
                # Fallback to sync I/O
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(content)
        except IOError as e:
            logger.error(f"Failed to save examples to {path}: {e}")
            raise FileSystemError(
                path=str(path),
                operation="write",
                cause=e
            )

    async def get_statistics(self) -> Dict[str, Any]:
        """Get collection statistics."""
        examples = await self._load_examples(self._get_examples_path())
        corrections = await self._load_examples(self._get_corrections_path())

        # Count by source
        source_counts = {}
        correct_counts = {}
        for ex in examples + corrections:
            source = ex.get("source", "unknown")
            source_counts[source] = source_counts.get(source, 0) + 1
            if ex.get("was_correct", True):
                correct_counts[source] = correct_counts.get(source, 0) + 1

        return {
            "total_examples": len(examples),
            "total_corrections": len(corrections),
            "examples_by_source": source_counts,
            "accuracy_by_source": {
                s: (correct_counts.get(s, 0) / c) if c > 0 else 0
                for s, c in source_counts.items()
            },
            "data_dir": self.config.data_dir,
        }


# =============================================================================
# MODEL TRAINER
# =============================================================================

class KnowledgeModelTrainer:
    """
    Trains the SetFit knowledge source classifier.

    Combines:
    - Seed data (KNOWLEDGE_SOURCE_SEEDS)
    - Collected examples from Emma usage
    - User corrections (weighted higher)
    """

    def __init__(
        self,
        config: Optional[KnowledgeLearningConfig] = None,
        classifier_config: Optional[KnowledgeClassifierConfig] = None,
    ):
        self.config = config or KnowledgeLearningConfig()
        self.classifier_config = classifier_config or KnowledgeClassifierConfig()
        self._collector = KnowledgeLearningCollector(self.config)

    async def train(
        self,
        include_seeds: bool = True,
        include_collected: bool = True,
        include_corrections: bool = True,
    ) -> Dict[str, Any]:
        """
        Train the knowledge source classifier.

        Args:
            include_seeds: Include seed utterances
            include_collected: Include collected examples
            include_corrections: Include user corrections

        Returns:
            Training result with version, accuracy, etc.
        """
        logger.info("🚀 Starting knowledge source model training...")

        # Gather training data
        texts = []
        labels = []

        # 1. Seed data
        if include_seeds:
            for source, utterances in KNOWLEDGE_SOURCE_SEEDS.items():
                for utt in utterances:
                    texts.append(utt)
                    labels.append(source)
            logger.info(f"Added {sum(len(v) for v in KNOWLEDGE_SOURCE_SEEDS.values())} seed examples")

        # 2. Collected examples
        if include_collected:
            examples = await self._collector._load_examples(
                self._collector._get_examples_path()
            )
            for ex in examples:
                texts.append(ex["text"])
                labels.append(ex["source"])
            logger.info(f"Added {len(examples)} collected examples")

        # 3. Corrections (add multiple times for higher weight)
        if include_corrections:
            corrections = await self._collector._load_examples(
                self._collector._get_corrections_path()
            )
            for ex in corrections:
                # Add corrections multiple times for higher weight
                for _ in range(CORRECTION_WEIGHT_MULTIPLIER):
                    texts.append(ex["text"])
                    labels.append(ex["source"])
            logger.info(f"Added {len(corrections)} corrections (weighted {CORRECTION_WEIGHT_MULTIPLIER}x)")

        # Check minimum requirements
        total_examples = len(texts)
        if total_examples < self.config.min_examples_to_train:
            error = InsufficientDataError(
                current_count=total_examples,
                required_count=self.config.min_examples_to_train
            )
            logger.warning(str(error))
            return {
                "success": False,
                "error": str(error),
                "total_examples": total_examples,
            }

        # Check examples per source
        source_counts = {}
        for label in labels:
            source_counts[label] = source_counts.get(label, 0) + 1

        for source in KnowledgeSource:
            count = source_counts.get(source.value, 0)
            if count < self.config.min_examples_per_source:
                logger.warning(
                    f"Not enough examples for {source.value}: {count} < {self.config.min_examples_per_source}"
                )

        logger.info(f"Training with {total_examples} examples: {source_counts}")

        # Train SetFit model
        try:
            from setfit import SetFitModel, SetFitTrainer
            from sklearn.model_selection import train_test_split

            # Split data
            train_texts, eval_texts, train_labels, eval_labels = train_test_split(
                texts, labels,
                test_size=self.config.train_eval_split,
                stratify=labels,
                random_state=42,
            )

            # Load base model
            model = SetFitModel.from_pretrained(self.classifier_config.model_base)

            # Create trainer
            trainer = SetFitTrainer(
                model=model,
                train_dataset={
                    "text": train_texts,
                    "label": train_labels,
                },
                eval_dataset={
                    "text": eval_texts,
                    "label": eval_labels,
                },
                column_mapping={"text": "text", "label": "label"},
            )

            # Train
            trainer.train()

            # Evaluate
            metrics = trainer.evaluate()
            accuracy = metrics.get("accuracy", 0.0)

            # Save model with version
            version = datetime.now().strftime("v%Y%m%d_%H%M%S")
            model_path = Path(self.config.model_dir) / version
            model_path.mkdir(parents=True, exist_ok=True)

            model.save_pretrained(str(model_path))

            # Update "current" symlink
            current_link = Path(self.config.model_dir) / "current"
            if current_link.is_symlink():
                current_link.unlink()
            current_link.symlink_to(model_path)

            logger.info(f"✅ Model trained and saved: {version}, accuracy={accuracy:.2%}")

            # Hot-reload the classifier
            classifier = get_knowledge_classifier()
            await classifier.reload_model()
            logger.info("✅ Classifier reloaded with new model")

            return {
                "success": True,
                "version": version,
                "accuracy": accuracy,
                "total_examples": total_examples,
                "train_examples": len(train_texts),
                "eval_examples": len(eval_texts),
                "examples_per_source": source_counts,
                "model_path": str(model_path),
            }

        except ImportError as e:
            logger.error(f"SetFit not installed: {e}")
            return {
                "success": False,
                "error": f"SetFit not installed: {e}",
            }

        except Exception as e:
            logger.error(f"Training failed: {e}")
            return {
                "success": False,
                "error": str(e),
            }

    async def get_status(self) -> Dict[str, Any]:
        """Get training system status."""
        stats = await self._collector.get_statistics()

        # Check for existing models
        model_dir = Path(self.config.model_dir)
        current_link = model_dir / "current"

        model_info = {
            "model_dir": str(model_dir),
            "model_exists": current_link.exists(),
            "current_version": None,
            "all_versions": [],
        }

        if current_link.exists() and current_link.is_symlink():
            model_info["current_version"] = current_link.resolve().name

        if model_dir.exists():
            model_info["all_versions"] = [
                d.name for d in model_dir.iterdir()
                if d.is_dir() and d.name != "current"
            ]

        return {
            "collection": stats,
            "model": model_info,
            "config": {
                "min_examples_to_train": self.config.min_examples_to_train,
                "min_examples_per_source": self.config.min_examples_per_source,
            },
        }


# =============================================================================
# SINGLETONS
# =============================================================================

_knowledge_collector: Optional[KnowledgeLearningCollector] = None
_knowledge_trainer: Optional[KnowledgeModelTrainer] = None


def get_knowledge_collector() -> KnowledgeLearningCollector:
    """Get or create the knowledge collector singleton."""
    global _knowledge_collector
    if _knowledge_collector is None:
        _knowledge_collector = KnowledgeLearningCollector()
    return _knowledge_collector


def get_knowledge_trainer() -> KnowledgeModelTrainer:
    """Get or create the knowledge trainer singleton."""
    global _knowledge_trainer
    if _knowledge_trainer is None:
        _knowledge_trainer = KnowledgeModelTrainer()
    return _knowledge_trainer


# Aliases for convenience
knowledge_collector = get_knowledge_collector
knowledge_trainer = get_knowledge_trainer
