"""
Continuous Learning Service for SLM Router

Automatically improves the SLM model based on usage patterns:
1. Collects training data from successful executions
2. Monitors data quality and quantity
3. Triggers fine-tuning during maintenance windows
4. Hot-swaps the improved model without downtime

This runs as a background task, requiring ZERO user intervention.

Architecture:
    ┌─────────────────────────────────────────────────────────────┐
    │              CONTINUOUS LEARNING PIPELINE                    │
    ├─────────────────────────────────────────────────────────────┤
    │                                                              │
    │  Normal Operation                                            │
    │  ────────────────                                            │
    │  User Query → SLM Router → Execute → Collect Example         │
    │                                          ↓                   │
    │                                    Redis Buffer              │
    │                                          ↓                   │
    │  Learning Monitor (background)                               │
    │  ─────────────────────────────                               │
    │  • Check example count every hour                            │
    │  • When threshold reached + maintenance window:              │
    │      1. Export training data                                 │
    │      2. Stop TGI                                             │
    │      3. Run LoRA fine-tuning                                 │
    │      4. Deploy updated model                                 │
    │      5. Restart TGI                                          │
    │      6. Clear processed examples                             │
    │                                                              │
    └─────────────────────────────────────────────────────────────┘

Configuration (environment variables):
    CONTINUOUS_LEARNING_ENABLED=true
    LEARNING_MIN_EXAMPLES=500
    LEARNING_MAINTENANCE_HOUR=3  # 3 AM
    LEARNING_CHECK_INTERVAL=3600  # Check every hour

Version 1.1 - January 2026 (Refactored with centralized config)
"""

import asyncio
import json
import logging
import os
import subprocess
import tempfile
import shutil
from datetime import datetime, time as dt_time
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

import redis.asyncio as redis

# Import from centralized modules
from app.core.learning_constants import (
    LearningState,
    REDIS_TRAINING_ACTIVE_TTL_SECONDS,
    FINETUNING_TIMEOUT_SECONDS,
    MIN_HOURS_BETWEEN_TRAINING,
    LOG_QUERY_PREVIEW_LENGTH,
)
from app.core.learning_exceptions import (
    DataParseError,
    TrainingTimeoutError,
    TrainingFailedError,
)
from app.core.learning_config import learning_settings

logger = logging.getLogger(__name__)


@dataclass
class LearningConfig:
    """
    Configuration for continuous learning.

    Note: Default values are loaded from learning_settings for centralization.
    You can override any value by passing it explicitly to the constructor.
    """
    enabled: bool = None  # type: ignore
    min_examples: int = None  # type: ignore
    max_examples: int = None  # type: ignore
    maintenance_hour: int = None  # type: ignore
    maintenance_minute: int = None  # type: ignore
    check_interval_seconds: int = None  # type: ignore
    model_name: str = None  # type: ignore
    training_epochs: int = None  # type: ignore
    batch_size: int = None  # type: ignore
    models_dir: str = None  # type: ignore
    adapter_dir: str = None  # type: ignore
    min_success_rate: float = None  # type: ignore

    def __post_init__(self):
        """Load defaults from centralized settings if not provided."""
        if self.enabled is None:
            self.enabled = learning_settings.continuous_learning_enabled
        if self.min_examples is None:
            self.min_examples = learning_settings.min_examples_for_training
        if self.max_examples is None:
            self.max_examples = learning_settings.max_examples_per_training
        if self.maintenance_hour is None:
            self.maintenance_hour = learning_settings.maintenance_hour
        if self.maintenance_minute is None:
            self.maintenance_minute = learning_settings.maintenance_minute
        if self.check_interval_seconds is None:
            self.check_interval_seconds = learning_settings.check_interval_seconds
        if self.model_name is None:
            self.model_name = learning_settings.slm_model_name
        if self.training_epochs is None:
            self.training_epochs = learning_settings.training_epochs
        if self.batch_size is None:
            self.batch_size = learning_settings.training_batch_size
        if self.models_dir is None:
            self.models_dir = learning_settings.models_base_dir
        if self.adapter_dir is None:
            self.adapter_dir = learning_settings.adapters_base_dir
        if self.min_success_rate is None:
            self.min_success_rate = learning_settings.min_success_rate


class ContinuousLearningService:
    """
    Automated continuous learning for SLM Router.

    Runs in background, monitors usage, and automatically
    improves the model during maintenance windows.
    """

    def __init__(self, config: Optional[LearningConfig] = None):
        self.config = config or LearningConfig()
        self._redis: Optional[redis.Redis] = None
        self._state = LearningState.IDLE
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._last_training: Optional[datetime] = None
        self._stats = {
            "examples_collected": 0,
            "trainings_completed": 0,
            "last_training_time": None,
            "current_model_version": 0
        }

    async def initialize(self, redis_url: str = "redis://redis:6379"):
        """Initialize the service."""
        try:
            self._redis = redis.from_url(redis_url)
            await self._redis.ping()

            # Load previous stats
            stats_data = await self._redis.get("slm:learning:stats")
            if stats_data:
                self._stats = json.loads(stats_data)

            logger.info(f"ContinuousLearningService initialized (enabled={self.config.enabled})")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize ContinuousLearningService: {e}")
            return False

    async def start(self):
        """Start the background learning monitor."""
        if not self.config.enabled:
            logger.info("Continuous learning is disabled")
            return

        if self._running:
            logger.warning("Learning monitor already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info("Continuous learning monitor started")

    async def stop(self):
        """Stop the background monitor."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Continuous learning monitor stopped")

    async def _monitor_loop(self):
        """Main monitoring loop."""
        while self._running:
            try:
                await self._check_and_train()
            except Exception as e:
                logger.error(f"Error in learning monitor: {e}")
                self._state = LearningState.ERROR

            # Wait before next check
            await asyncio.sleep(self.config.check_interval_seconds)

    async def _check_and_train(self):
        """Check conditions and trigger training if appropriate."""
        # Get current stats
        stats = await self._get_training_stats()
        self._stats["examples_collected"] = stats["total_examples"]

        logger.debug(f"Learning check: {stats['total_examples']} examples, "
                    f"success_rate={stats['success_rate']:.2f}")

        # Check if we have enough quality data
        if stats["total_examples"] < self.config.min_examples:
            self._state = LearningState.COLLECTING
            return

        if stats["success_rate"] < self.config.min_success_rate:
            logger.info(f"Success rate too low ({stats['success_rate']:.2f}), "
                       f"need {self.config.min_success_rate}")
            return

        self._state = LearningState.READY_TO_TRAIN

        # Check if we're in maintenance window
        if not self._is_maintenance_window():
            logger.debug("Not in maintenance window, waiting...")
            return

        # Check if we trained recently (within minimum hours)
        if self._last_training:
            hours_since = (datetime.now() - self._last_training).total_seconds() / 3600
            if hours_since < MIN_HOURS_BETWEEN_TRAINING:
                logger.debug(f"Trained {hours_since:.1f} hours ago, skipping (min: {MIN_HOURS_BETWEEN_TRAINING}h)")
                return

        # All conditions met - run training
        await self._run_training_pipeline(stats)

    async def _get_training_stats(self) -> Dict[str, Any]:
        """Get statistics about collected training data."""
        total = 0
        successful = 0
        examples_by_route = {
            "GRAPH_ONLY": 0,
            "VECTOR_ONLY": 0,
            "HYBRID": 0,
            "ASK_CLARIFY": 0
        }

        # Scan all tenant training keys
        async for key in self._redis.scan_iter("slm:training:*"):
            examples = await self._redis.lrange(key, 0, -1)
            for raw in examples:
                try:
                    ex = json.loads(raw)
                    total += 1
                    if ex.get("execution_success"):
                        successful += 1
                    route = ex.get("route", "VECTOR_ONLY")
                    if route in examples_by_route:
                        examples_by_route[route] += 1
                except json.JSONDecodeError as e:
                    logger.warning(f"Invalid JSON in training example: {e}")
                    continue
                except (KeyError, TypeError) as e:
                    logger.debug(f"Malformed training example: {e}")
                    continue

        return {
            "total_examples": total,
            "successful_examples": successful,
            "success_rate": successful / total if total > 0 else 0,
            "by_route": examples_by_route
        }

    def _is_maintenance_window(self) -> bool:
        """Check if current time is in maintenance window."""
        now = datetime.now()
        maintenance_start = dt_time(self.config.maintenance_hour,
                                    self.config.maintenance_minute)
        maintenance_end = dt_time((self.config.maintenance_hour + 1) % 24,
                                  self.config.maintenance_minute)

        current_time = now.time()

        # Handle window that crosses midnight
        if maintenance_start <= maintenance_end:
            return maintenance_start <= current_time <= maintenance_end
        else:
            return current_time >= maintenance_start or current_time <= maintenance_end

    async def _run_training_pipeline(self, stats: Dict[str, Any]):
        """Execute the full training pipeline."""
        logger.info("=" * 60)
        logger.info("STARTING AUTOMATED FINE-TUNING")
        logger.info(f"Examples: {stats['total_examples']}, "
                   f"Success rate: {stats['success_rate']:.2%}")
        logger.info("=" * 60)

        self._state = LearningState.TRAINING

        try:
            # 1. Export training data
            logger.info("Step 1/5: Exporting training data...")
            training_file = await self._export_training_data()

            # 2. Prepare for training (signal TGI to pause)
            logger.info("Step 2/5: Preparing for training...")
            await self._signal_training_start()

            # 3. Run fine-tuning
            logger.info("Step 3/5: Running LoRA fine-tuning...")
            success = await self._run_finetuning(training_file)

            if not success:
                raise Exception("Fine-tuning failed")

            # 4. Deploy new model
            logger.info("Step 4/5: Deploying updated model...")
            await self._deploy_model()

            # 5. Cleanup
            logger.info("Step 5/5: Cleanup...")
            await self._cleanup_after_training()

            # Update stats
            self._last_training = datetime.now()
            self._stats["trainings_completed"] += 1
            self._stats["last_training_time"] = self._last_training.isoformat()
            self._stats["current_model_version"] += 1
            await self._save_stats()

            self._state = LearningState.IDLE
            logger.info("=" * 60)
            logger.info("AUTOMATED FINE-TUNING COMPLETED SUCCESSFULLY")
            logger.info(f"Model version: {self._stats['current_model_version']}")
            logger.info("=" * 60)

        except Exception as e:
            logger.error(f"Training pipeline failed: {e}")
            self._state = LearningState.ERROR
            await self._signal_training_end()
            raise

    async def _export_training_data(self) -> Path:
        """Export all training data to a file."""
        all_examples = []

        async for key in self._redis.scan_iter("slm:training:*"):
            examples = await self._redis.lrange(key, 0, self.config.max_examples)
            for raw in examples:
                try:
                    ex = json.loads(raw)
                    if ex.get("execution_success"):
                        all_examples.append(ex)
                except json.JSONDecodeError as e:
                    logger.warning(f"Skipping malformed training example: {e}")
                    continue

        # Write to temp file
        export_dir = Path(tempfile.mkdtemp(prefix="slm_training_"))
        export_file = export_dir / "training_data.json"

        with open(export_file, 'w') as f:
            json.dump({"examples": all_examples}, f)

        logger.info(f"Exported {len(all_examples)} examples to {export_file}")
        return export_file

    async def _signal_training_start(self):
        """Signal that training is about to start."""
        # Set Redis flag that TGI should gracefully shutdown
        await self._redis.set(
            "slm:learning:training_active",
            "1",
            ex=REDIS_TRAINING_ACTIVE_TTL_SECONDS
        )

    async def _signal_training_end(self):
        """Signal that training has ended."""
        await self._redis.delete("slm:learning:training_active")

    async def _run_finetuning(self, training_file: Path) -> bool:
        """Run the actual fine-tuning process."""
        output_dir = Path(self.config.adapter_dir) / f"v{self._stats['current_model_version'] + 1}"
        output_dir.mkdir(parents=True, exist_ok=True)

        # Run fine-tuning script
        cmd = [
            "python", "-m", "scripts.finetune_slm",
            "--data", str(training_file),
            "--output", str(output_dir),
            "--model", self.config.model_name,
            "--epochs", str(self.config.training_epochs),
            "--batch-size", str(self.config.batch_size),
            "--augment",
            "--merge"
        ]

        logger.info(f"Running: {' '.join(cmd)}")

        try:
            # Run in subprocess
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd="/app"
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=FINETUNING_TIMEOUT_SECONDS
            )

            if process.returncode != 0:
                logger.error(f"Fine-tuning failed: {stderr.decode()}")
                return False

            logger.info(f"Fine-tuning completed: {stdout.decode()[-500:]}")
            return True

        except asyncio.TimeoutError:
            logger.error(f"Fine-tuning timed out after {FINETUNING_TIMEOUT_SECONDS}s")
            process.kill()
            raise TrainingTimeoutError(
                timeout_seconds=FINETUNING_TIMEOUT_SECONDS,
                message="LoRA fine-tuning exceeded maximum allowed time"
            )
        except Exception as e:
            logger.error(f"Fine-tuning error: {e}")
            raise TrainingFailedError(
                stage="finetuning",
                message=f"Fine-tuning failed: {e}",
                cause=e
            )

    async def _deploy_model(self):
        """Deploy the fine-tuned model."""
        version = self._stats['current_model_version'] + 1
        adapter_path = Path(self.config.adapter_dir) / f"v{version}" / "merged"

        if not adapter_path.exists():
            raise Exception(f"Fine-tuned model not found at {adapter_path}")

        # Copy to models directory for TGI
        model_path = Path(self.config.models_dir) / "current"
        if model_path.exists():
            # Backup previous
            backup_path = Path(self.config.models_dir) / f"backup_v{version-1}"
            shutil.move(str(model_path), str(backup_path))

        shutil.copytree(str(adapter_path), str(model_path))

        # Update symlink/config for TGI
        await self._redis.set("slm:learning:current_model", str(model_path))

        logger.info(f"Deployed model v{version} to {model_path}")

    async def _cleanup_after_training(self):
        """Cleanup after successful training."""
        # Clear processed training data
        async for key in self._redis.scan_iter("slm:training:*"):
            await self._redis.delete(key)

        # Signal training complete
        await self._signal_training_end()

        # Cleanup temp files
        # (kept for debugging, auto-cleanup by OS)

        logger.info("Cleanup completed")

    async def _save_stats(self):
        """Save learning stats to Redis."""
        await self._redis.set(
            "slm:learning:stats",
            json.dumps(self._stats)
        )

    async def get_status(self) -> Dict[str, Any]:
        """Get current learning status."""
        stats = await self._get_training_stats()

        return {
            "enabled": self.config.enabled,
            "state": self._state.value,
            "examples_collected": stats["total_examples"],
            "examples_needed": self.config.min_examples,
            "success_rate": stats["success_rate"],
            "by_route": stats["by_route"],
            "last_training": self._stats.get("last_training_time"),
            "trainings_completed": self._stats.get("trainings_completed", 0),
            "model_version": self._stats.get("current_model_version", 0),
            "maintenance_window": f"{self.config.maintenance_hour:02d}:00",
            "next_check_possible": self._is_maintenance_window()
        }


# =============================================================================
# SINGLETON
# =============================================================================

_learning_service: Optional[ContinuousLearningService] = None


def get_learning_service(config: Optional[LearningConfig] = None) -> ContinuousLearningService:
    """Get the singleton learning service.

    If a config is provided and no service exists, creates a new one with that config.
    If a service already exists, returns the existing one (ignores new config).

    Note: Config values are now loaded from centralized learning_settings by default.
    You only need to pass a config if you want to override specific values.
    """
    global _learning_service
    if _learning_service is None:
        if config is None:
            # LearningConfig now loads defaults from learning_settings
            config = LearningConfig()
        _learning_service = ContinuousLearningService(config)
    return _learning_service


def set_learning_service(service: ContinuousLearningService):
    """Set the singleton learning service instance.

    Used when creating a service with custom config (e.g., from settings).
    """
    global _learning_service
    _learning_service = service


async def initialize_continuous_learning(
    redis_url: str = "redis://redis:6379",
    config: Optional[LearningConfig] = None
) -> Optional[ContinuousLearningService]:
    """Initialize and start the continuous learning service.

    Args:
        redis_url: Redis connection URL
        config: Optional custom config (uses defaults if not provided)

    Returns:
        Initialized service or None if initialization failed
    """
    service = get_learning_service(config)
    if await service.initialize(redis_url):
        await service.start()
        return service
    return None
