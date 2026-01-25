"""
Learning System Dependency Injection Providers

Provides FastAPI-compatible dependency injection for learning services.
Supports proper lifecycle management and testability.

Features:
- Lazy initialization of services
- Singleton pattern with reset capability for tests
- Type-safe dependency injection
- Async initialization support

Usage in endpoints:
    from app.core.learning_providers import (
        get_continuous_learning_service,
        get_knowledge_classifier,
    )

    @router.get("/learning/status")
    async def get_status(
        service: ContinuousLearningService = Depends(get_continuous_learning_service)
    ):
        return await service.get_status()

Usage in tests:
    from app.core.learning_providers import LearningProviders

    def test_with_mock():
        LearningProviders.reset()  # Clear singletons
        # ... test code ...

Version 1.0 - January 2026
"""

import logging
from typing import Optional, TypeVar, Callable, Any
import warnings

from app.core.learning_config import LearningSettings, learning_settings

logger = logging.getLogger(__name__)

# Type variable for generic service types
T = TypeVar('T')


class LearningProviders:
    """
    Centralized provider registry for learning services.

    Manages singleton instances with support for:
    - Lazy initialization
    - Dependency injection
    - Test isolation (via reset)
    """

    # Service instances
    _continuous_learning_service: Optional[Any] = None
    _knowledge_classifier: Optional[Any] = None
    _knowledge_trainer: Optional[Any] = None
    _knowledge_collector: Optional[Any] = None
    _preference_learning_service: Optional[Any] = None

    # Initialization flags
    _continuous_learning_initialized: bool = False
    _knowledge_classifier_initialized: bool = False

    # Settings instance
    _settings: Optional[LearningSettings] = None

    @classmethod
    def get_settings(cls) -> LearningSettings:
        """
        Get the learning settings instance.

        Returns:
            LearningSettings singleton
        """
        if cls._settings is None:
            cls._settings = learning_settings
        return cls._settings

    @classmethod
    def set_settings(cls, settings: LearningSettings) -> None:
        """
        Set custom settings (useful for testing).

        Args:
            settings: Custom LearningSettings instance
        """
        cls._settings = settings

    # =========================================================================
    # Continuous Learning Service
    # =========================================================================

    @classmethod
    async def get_continuous_learning_service(cls):
        """
        Get or create the ContinuousLearningService singleton.

        Returns:
            ContinuousLearningService instance

        Note:
            Service is lazily imported to avoid circular dependencies.
        """
        if cls._continuous_learning_service is None:
            # Lazy import to avoid circular dependencies
            from app.services.slm_router.continuous_learning import (
                ContinuousLearningService,
                LearningConfig,
            )

            settings = cls.get_settings()

            # Create config from centralized settings
            config = LearningConfig(
                enabled=settings.continuous_learning_enabled,
                min_examples=settings.min_examples_for_training,
                max_examples=settings.max_examples_per_training,
                maintenance_hour=settings.maintenance_hour,
                maintenance_minute=settings.maintenance_minute,
                check_interval_seconds=settings.check_interval_seconds,
                model_name=settings.slm_model_name,
                training_epochs=settings.training_epochs,
                batch_size=settings.training_batch_size,
                models_dir=settings.models_base_dir,
                adapter_dir=settings.adapters_base_dir,
                min_success_rate=settings.min_success_rate,
            )

            cls._continuous_learning_service = ContinuousLearningService(config)
            logger.debug("Created ContinuousLearningService from provider")

        return cls._continuous_learning_service

    @classmethod
    async def initialize_continuous_learning(
        cls,
        redis_url: str = "redis://redis:6379"
    ) -> Optional[Any]:
        """
        Initialize and start the continuous learning service.

        Args:
            redis_url: Redis connection URL

        Returns:
            Initialized service or None if initialization failed
        """
        if cls._continuous_learning_initialized:
            return cls._continuous_learning_service

        service = await cls.get_continuous_learning_service()

        if await service.initialize(redis_url):
            await service.start()
            cls._continuous_learning_initialized = True
            logger.info("ContinuousLearningService initialized via provider")
            return service

        logger.warning("ContinuousLearningService initialization failed")
        return None

    # =========================================================================
    # Knowledge Classifier
    # =========================================================================

    @classmethod
    def get_knowledge_classifier(cls):
        """
        Get or create the SetFitKnowledgeClassifier singleton.

        Returns:
            SetFitKnowledgeClassifier instance
        """
        if cls._knowledge_classifier is None:
            # Lazy import
            from app.services.nexus_router.knowledge_classifier import (
                SetFitKnowledgeClassifier,
                KnowledgeClassifierConfig,
            )

            settings = cls.get_settings()

            config = KnowledgeClassifierConfig(
                model_base=settings.setfit_base_model,
                model_path=str(settings.get_knowledge_source_model_path()),
                confidence_threshold=settings.confidence_threshold,
                min_examples_per_source=settings.knowledge_min_examples_per_source,
            )

            cls._knowledge_classifier = SetFitKnowledgeClassifier(config)
            logger.debug("Created SetFitKnowledgeClassifier from provider")

        return cls._knowledge_classifier

    @classmethod
    async def initialize_knowledge_classifier(cls) -> bool:
        """
        Initialize the knowledge classifier.

        Returns:
            True if model loaded, False if using fallback
        """
        if cls._knowledge_classifier_initialized:
            return cls._knowledge_classifier is not None

        classifier = cls.get_knowledge_classifier()
        result = await classifier.initialize()
        cls._knowledge_classifier_initialized = True

        logger.info(f"KnowledgeClassifier initialized via provider (model_loaded={result})")
        return result

    # =========================================================================
    # Knowledge Trainer & Collector
    # =========================================================================

    @classmethod
    def get_knowledge_trainer(cls):
        """
        Get or create the KnowledgeModelTrainer singleton.

        Returns:
            KnowledgeModelTrainer instance
        """
        if cls._knowledge_trainer is None:
            # Lazy import
            from app.services.nexus_router.knowledge_learning import (
                KnowledgeModelTrainer,
                KnowledgeLearningConfig,
            )
            from app.services.nexus_router.knowledge_classifier import (
                KnowledgeClassifierConfig,
            )

            settings = cls.get_settings()

            learning_config = KnowledgeLearningConfig()
            learning_config.data_dir = settings.knowledge_examples_dir
            learning_config.model_dir = str(settings.get_knowledge_source_model_path())
            learning_config.min_examples_to_train = settings.knowledge_min_examples_to_train
            learning_config.min_examples_per_source = settings.knowledge_min_examples_per_source
            learning_config.max_examples_per_source = settings.knowledge_max_examples_per_source
            learning_config.train_eval_split = settings.knowledge_train_eval_split
            learning_config.dedup_by_text = settings.knowledge_dedup_by_text

            classifier_config = KnowledgeClassifierConfig(
                model_base=settings.setfit_base_model,
                model_path=str(settings.get_knowledge_source_model_path()),
            )

            cls._knowledge_trainer = KnowledgeModelTrainer(
                config=learning_config,
                classifier_config=classifier_config,
            )
            logger.debug("Created KnowledgeModelTrainer from provider")

        return cls._knowledge_trainer

    @classmethod
    def get_knowledge_collector(cls):
        """
        Get or create the KnowledgeLearningCollector singleton.

        Returns:
            KnowledgeLearningCollector instance
        """
        if cls._knowledge_collector is None:
            # Lazy import
            from app.services.nexus_router.knowledge_learning import (
                KnowledgeLearningCollector,
                KnowledgeLearningConfig,
            )

            settings = cls.get_settings()

            config = KnowledgeLearningConfig()
            config.data_dir = settings.knowledge_examples_dir
            config.max_examples_per_source = settings.knowledge_max_examples_per_source
            config.dedup_by_text = settings.knowledge_dedup_by_text

            cls._knowledge_collector = KnowledgeLearningCollector(config)
            logger.debug("Created KnowledgeLearningCollector from provider")

        return cls._knowledge_collector

    # =========================================================================
    # Preference Learning Service
    # =========================================================================

    @classmethod
    def get_preference_learning_service(cls):
        """
        Get or create the PreferenceLearningService singleton.

        Returns:
            PreferenceLearningService instance
        """
        if cls._preference_learning_service is None:
            # Lazy import
            from app.services.memory.learning_service import PreferenceLearningService

            cls._preference_learning_service = PreferenceLearningService()
            logger.debug("Created PreferenceLearningService from provider")

        return cls._preference_learning_service

    @classmethod
    async def initialize_preference_learning(cls):
        """
        Initialize the preference learning service.
        """
        service = cls.get_preference_learning_service()
        await service.initialize()
        logger.info("PreferenceLearningService initialized via provider")

    # =========================================================================
    # Test Support
    # =========================================================================

    @classmethod
    def reset(cls) -> None:
        """
        Reset all singleton instances.

        Used in tests to ensure clean state between test cases.
        """
        cls._continuous_learning_service = None
        cls._knowledge_classifier = None
        cls._knowledge_trainer = None
        cls._knowledge_collector = None
        cls._preference_learning_service = None
        cls._continuous_learning_initialized = False
        cls._knowledge_classifier_initialized = False
        cls._settings = None
        logger.debug("LearningProviders reset")

    @classmethod
    def set_mock(cls, service_name: str, mock_instance: Any) -> None:
        """
        Set a mock instance for testing.

        Args:
            service_name: Name of the service to mock
            mock_instance: Mock instance to use

        Example:
            LearningProviders.set_mock("continuous_learning", mock_service)
        """
        service_map = {
            "continuous_learning": "_continuous_learning_service",
            "knowledge_classifier": "_knowledge_classifier",
            "knowledge_trainer": "_knowledge_trainer",
            "knowledge_collector": "_knowledge_collector",
            "preference_learning": "_preference_learning_service",
        }

        attr_name = service_map.get(service_name)
        if attr_name:
            setattr(cls, attr_name, mock_instance)
            logger.debug(f"Set mock for {service_name}")
        else:
            raise ValueError(f"Unknown service: {service_name}")


# =============================================================================
# FastAPI Dependency Functions
# =============================================================================

async def get_continuous_learning_service():
    """
    FastAPI dependency for ContinuousLearningService.

    Usage:
        @router.get("/status")
        async def get_status(
            service = Depends(get_continuous_learning_service)
        ):
            return await service.get_status()
    """
    return await LearningProviders.get_continuous_learning_service()


def get_knowledge_classifier():
    """
    FastAPI dependency for SetFitKnowledgeClassifier.

    Usage:
        @router.post("/classify")
        async def classify(
            classifier = Depends(get_knowledge_classifier)
        ):
            return classifier.classify(query)
    """
    return LearningProviders.get_knowledge_classifier()


def get_knowledge_trainer():
    """
    FastAPI dependency for KnowledgeModelTrainer.
    """
    return LearningProviders.get_knowledge_trainer()


def get_knowledge_collector():
    """
    FastAPI dependency for KnowledgeLearningCollector.
    """
    return LearningProviders.get_knowledge_collector()


def get_preference_learning_service():
    """
    FastAPI dependency for PreferenceLearningService.
    """
    return LearningProviders.get_preference_learning_service()


def get_learning_settings():
    """
    FastAPI dependency for LearningSettings.
    """
    return LearningProviders.get_settings()


# =============================================================================
# Deprecation Wrappers (Backwards Compatibility)
# =============================================================================

def _deprecated_get_learning_service(config=None):
    """
    DEPRECATED: Use get_continuous_learning_service() instead.

    This function is maintained for backwards compatibility.
    """
    warnings.warn(
        "get_learning_service() is deprecated, use LearningProviders.get_continuous_learning_service() instead",
        DeprecationWarning,
        stacklevel=2
    )
    # Import the original for compatibility
    from app.services.slm_router.continuous_learning import get_learning_service
    return get_learning_service(config)


def _deprecated_get_knowledge_classifier_singleton():
    """
    DEPRECATED: Use get_knowledge_classifier() from providers instead.
    """
    warnings.warn(
        "Direct singleton access is deprecated, use LearningProviders.get_knowledge_classifier() instead",
        DeprecationWarning,
        stacklevel=2
    )
    return LearningProviders.get_knowledge_classifier()
