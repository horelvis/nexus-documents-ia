"""
NexusRouter Model Trainer

Trains SetFit models for intent classification.

SetFit (Sentence Transformer Fine-tuning) advantages:
1. Few-shot learning: Works well with 8-16 examples per class
2. Fast training: Minutes not hours
3. No GPU required (but faster with GPU)
4. Multilingual support with paraphrase-multilingual models

Training workflow:
1. Load TrainingDataset
2. Convert to HuggingFace Dataset format
3. Initialize SetFit model from base
4. Train with contrastive learning
5. Evaluate and save with metadata
"""

import json
import logging
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .schemas import (
    Intent,
    TrainingDataset,
    NexusRouterConfig,
    ModelMetadata,
)

logger = logging.getLogger(__name__)


class ModelTrainer:
    """
    Trains SetFit models for intent classification.

    Features:
    - Few-shot learning (8-16 examples per class)
    - Multilingual support
    - Automatic model versioning
    - Evaluation metrics
    """

    def __init__(self, config: Optional[NexusRouterConfig] = None):
        """
        Initialize the model trainer.

        Args:
            config: Router configuration
        """
        self.config = config or NexusRouterConfig()
        self._model = None
        self._labels = [intent.value for intent in Intent]

    def train(
        self,
        dataset: TrainingDataset,
        output_path: Optional[str] = None,
        version: Optional[str] = None,
    ) -> Tuple[Any, ModelMetadata]:
        """
        Train a SetFit model on the dataset.

        Args:
            dataset: Training dataset
            output_path: Where to save the model (uses config default if not provided)
            version: Model version string (auto-generated if not provided)

        Returns:
            Tuple of (trained_model, metadata)
        """
        try:
            from setfit import SetFitModel, Trainer, TrainingArguments
            from datasets import Dataset
        except ImportError as e:
            logger.error(
                "SetFit not installed. Install with: pip install setfit datasets"
            )
            raise ImportError(
                "setfit and datasets packages required for training"
            ) from e

        output_path = output_path or self.config.model_path
        version = version or datetime.now().strftime("v%Y%m%d_%H%M%S")

        logger.info(f"Training SetFit model version {version}")
        logger.info(f"Training examples: {len(dataset.train_examples)}")
        logger.info(f"Evaluation examples: {len(dataset.eval_examples)}")

        # Convert to HuggingFace Dataset format
        train_data = {
            "text": [ex.text for ex in dataset.train_examples],
            "label": [ex.intent.value for ex in dataset.train_examples],
        }
        eval_data = {
            "text": [ex.text for ex in dataset.eval_examples],
            "label": [ex.intent.value for ex in dataset.eval_examples],
        }

        train_dataset = Dataset.from_dict(train_data)
        eval_dataset = Dataset.from_dict(eval_data)

        # Initialize model from base
        logger.info(f"Loading base model: {self.config.model_base}")
        model = SetFitModel.from_pretrained(
            self.config.model_base,
            labels=self._labels,
        )

        # Configure training arguments
        args = TrainingArguments(
            batch_size=self.config.batch_size,
            num_epochs=1,  # SetFit uses iterations, not epochs
            num_iterations=self.config.num_iterations,
            evaluation_strategy="epoch",
            save_strategy="epoch",
            load_best_model_at_end=True,
        )

        # Create trainer
        trainer = Trainer(
            model=model,
            args=args,
            train_dataset=train_dataset,
            eval_dataset=eval_dataset,
            metric="accuracy",
        )

        # Train
        logger.info("Starting training...")
        trainer.train()

        # Evaluate
        logger.info("Evaluating model...")
        metrics = trainer.evaluate()
        accuracy = metrics.get("accuracy", 0.0)
        logger.info(f"Evaluation accuracy: {accuracy:.4f}")

        # Calculate F1 score
        f1_score = self._calculate_f1(model, eval_dataset)
        logger.info(f"F1 score: {f1_score:.4f}")

        # Save model
        version_path = Path(output_path) / version
        version_path.mkdir(parents=True, exist_ok=True)

        logger.info(f"Saving model to {version_path}")
        model.save_pretrained(str(version_path))

        # Create metadata
        metadata = ModelMetadata(
            version=version,
            created_at=datetime.now(),
            accuracy=accuracy,
            f1_score=f1_score,
            training_examples=len(dataset.train_examples),
            eval_examples=len(dataset.eval_examples),
            examples_per_intent=dataset.examples_per_intent,
            sources=dataset.sources,
            tenant_ids=dataset.tenant_ids,
            base_model=self.config.model_base,
            config=self.config,
        )

        # Save metadata
        metadata_path = version_path / "metadata.json"
        with open(metadata_path, "w") as f:
            json.dump(metadata.to_dict(), f, indent=2)

        # Update current symlink
        current_link = Path(output_path) / "current"
        if current_link.exists():
            current_link.unlink()
        current_link.symlink_to(version)

        logger.info(f"Model {version} trained and saved successfully")
        logger.info(f"Accuracy: {accuracy:.4f}, F1: {f1_score:.4f}")

        self._model = model
        return model, metadata

    def _calculate_f1(self, model, eval_dataset) -> float:
        """
        Calculate macro F1 score on evaluation dataset.

        Args:
            model: Trained SetFit model
            eval_dataset: Evaluation dataset

        Returns:
            Macro F1 score
        """
        try:
            from sklearn.metrics import f1_score as sklearn_f1

            predictions = model.predict(eval_dataset["text"])
            true_labels = eval_dataset["label"]

            # Convert to label indices if needed
            if hasattr(predictions[0], "item"):
                predictions = [p.item() for p in predictions]

            return sklearn_f1(true_labels, predictions, average="macro")

        except ImportError:
            logger.warning("sklearn not available for F1 calculation")
            return 0.0
        except Exception as e:
            logger.warning(f"Error calculating F1 score: {e}")
            return 0.0

    def load_model(
        self,
        model_path: Optional[str] = None,
        version: str = "current",
    ) -> Any:
        """
        Load a trained model.

        Args:
            model_path: Base path for models
            version: Version to load (or "current" for latest)

        Returns:
            Loaded SetFit model
        """
        try:
            from setfit import SetFitModel
        except ImportError as e:
            logger.error("SetFit not installed")
            raise ImportError("setfit package required") from e

        model_path = model_path or self.config.model_path
        version_path = Path(model_path) / version

        if not version_path.exists():
            raise FileNotFoundError(f"Model not found at {version_path}")

        # Follow symlink if "current"
        if version == "current" and version_path.is_symlink():
            version_path = version_path.resolve()

        logger.info(f"Loading model from {version_path}")
        self._model = SetFitModel.from_pretrained(str(version_path))

        return self._model

    def get_model_metadata(
        self,
        model_path: Optional[str] = None,
        version: str = "current",
    ) -> Optional[ModelMetadata]:
        """
        Load model metadata.

        Args:
            model_path: Base path for models
            version: Version to load

        Returns:
            ModelMetadata or None if not found
        """
        model_path = model_path or self.config.model_path
        version_path = Path(model_path) / version

        if version == "current" and version_path.is_symlink():
            version_path = version_path.resolve()

        metadata_path = version_path / "metadata.json"

        if not metadata_path.exists():
            return None

        with open(metadata_path) as f:
            data = json.load(f)

        # Reconstruct config
        config_data = data.get("config", {})
        config = NexusRouterConfig(**config_data) if config_data else NexusRouterConfig()

        return ModelMetadata(
            version=data["version"],
            created_at=datetime.fromisoformat(data["created_at"]),
            accuracy=data["accuracy"],
            f1_score=data["f1_score"],
            training_examples=data["training_examples"],
            eval_examples=data["eval_examples"],
            examples_per_intent=data["examples_per_intent"],
            sources=data["sources"],
            tenant_ids=data["tenant_ids"],
            base_model=data["base_model"],
            config=config,
        )

    def list_versions(
        self,
        model_path: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        List all available model versions.

        Args:
            model_path: Base path for models

        Returns:
            List of version info dicts
        """
        model_path = Path(model_path or self.config.model_path)

        if not model_path.exists():
            return []

        versions = []
        current_version = None

        # Check what "current" points to
        current_link = model_path / "current"
        if current_link.is_symlink():
            current_version = current_link.resolve().name

        for item in model_path.iterdir():
            if item.is_dir() and item.name != "current":
                metadata = self.get_model_metadata(
                    model_path=str(model_path),
                    version=item.name,
                )

                versions.append({
                    "version": item.name,
                    "is_current": item.name == current_version,
                    "accuracy": metadata.accuracy if metadata else None,
                    "f1_score": metadata.f1_score if metadata else None,
                    "created_at": metadata.created_at.isoformat() if metadata else None,
                })

        # Sort by version (newest first)
        versions.sort(key=lambda x: x["version"], reverse=True)

        return versions

    def cleanup_old_versions(
        self,
        model_path: Optional[str] = None,
        keep_versions: int = 3,
    ) -> int:
        """
        Remove old model versions, keeping the N most recent.

        Args:
            model_path: Base path for models
            keep_versions: Number of versions to keep

        Returns:
            Number of versions removed
        """
        model_path = Path(model_path or self.config.model_path)
        versions = self.list_versions(str(model_path))

        # Filter out current (we never delete current)
        non_current = [v for v in versions if not v["is_current"]]

        # Keep the most recent N versions
        to_delete = non_current[keep_versions:]

        removed = 0
        for version_info in to_delete:
            version_path = model_path / version_info["version"]
            try:
                shutil.rmtree(version_path)
                removed += 1
                logger.info(f"Removed old model version: {version_info['version']}")
            except Exception as e:
                logger.warning(f"Failed to remove {version_info['version']}: {e}")

        return removed


# Singleton instance
model_trainer = ModelTrainer()
