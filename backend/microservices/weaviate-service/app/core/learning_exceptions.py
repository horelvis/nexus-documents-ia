"""
Learning System Custom Exceptions

Provides a hierarchy of exceptions for the learning system,
replacing generic exceptions and silent error handling.

Exception Hierarchy:
    LearningError (base)
    ├── ConfigurationError - Invalid settings or configuration
    ├── TrainingDataError - Training data issues
    │   ├── InsufficientDataError - Not enough training examples
    │   └── DataQualityError - Data quality below threshold
    ├── ModelError - Model-related errors
    │   ├── ModelLoadError - Failed to load model
    │   ├── ModelSaveError - Failed to save model
    │   └── ModelSecurityError - Security validation failed
    ├── TrainingError - Training process errors
    │   ├── TrainingTimeoutError - Training exceeded timeout
    │   └── TrainingFailedError - Training failed for other reasons
    └── StorageError - Storage/persistence errors
        ├── RedisError - Redis operations failed
        └── FileSystemError - File operations failed

Usage:
    from app.core.learning_exceptions import (
        InsufficientDataError,
        ModelLoadError,
    )

    try:
        await train_model()
    except InsufficientDataError as e:
        logger.warning(f"Not enough data: {e}")
    except ModelLoadError as e:
        logger.error(f"Model load failed: {e}")

Version 1.0 - January 2026
"""

from typing import Any, Dict, Optional


class LearningError(Exception):
    """
    Base exception for all learning system errors.

    Provides structured error information with optional context.
    """

    def __init__(
        self,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None
    ):
        """
        Initialize a LearningError.

        Args:
            message: Human-readable error message
            details: Optional dict with additional context
            cause: Optional underlying exception that caused this error
        """
        super().__init__(message)
        self.message = message
        self.details = details or {}
        self.cause = cause

    def __str__(self) -> str:
        result = self.message
        if self.details:
            result += f" (details: {self.details})"
        if self.cause:
            result += f" [caused by: {self.cause}]"
        return result

    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for API responses."""
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "details": self.details,
            "cause": str(self.cause) if self.cause else None,
        }


# =============================================================================
# Configuration Errors
# =============================================================================

class ConfigurationError(LearningError):
    """
    Raised when learning system configuration is invalid.

    Examples:
        - Invalid paths
        - Invalid threshold values
        - Missing required settings
    """
    pass


# =============================================================================
# Training Data Errors
# =============================================================================

class TrainingDataError(LearningError):
    """Base class for training data related errors."""
    pass


class InsufficientDataError(TrainingDataError):
    """
    Raised when there are not enough training examples.

    Attributes:
        current_count: Number of examples currently available
        required_count: Minimum required examples
    """

    def __init__(
        self,
        current_count: int,
        required_count: int,
        message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        if message is None:
            message = (
                f"Insufficient training data: {current_count} examples available, "
                f"but {required_count} required"
            )
        super().__init__(message, details)
        self.current_count = current_count
        self.required_count = required_count
        self.details.update({
            "current_count": current_count,
            "required_count": required_count,
        })


class DataQualityError(TrainingDataError):
    """
    Raised when training data quality is below threshold.

    Attributes:
        current_quality: Current quality metric (e.g., success rate)
        required_quality: Required quality threshold
        metric_name: Name of the quality metric
    """

    def __init__(
        self,
        current_quality: float,
        required_quality: float,
        metric_name: str = "success_rate",
        message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        if message is None:
            message = (
                f"Data quality too low: {metric_name}={current_quality:.2%}, "
                f"required {required_quality:.2%}"
            )
        super().__init__(message, details)
        self.current_quality = current_quality
        self.required_quality = required_quality
        self.metric_name = metric_name
        self.details.update({
            "current_quality": current_quality,
            "required_quality": required_quality,
            "metric_name": metric_name,
        })


class DataParseError(TrainingDataError):
    """
    Raised when training data cannot be parsed.

    Used instead of bare except: pass for JSON parsing errors.
    """

    def __init__(
        self,
        raw_data: str,
        message: Optional[str] = None,
        cause: Optional[Exception] = None
    ):
        if message is None:
            preview = raw_data[:100] + "..." if len(raw_data) > 100 else raw_data
            message = f"Failed to parse training data: {preview}"
        super().__init__(message, cause=cause)
        self.raw_data = raw_data


# =============================================================================
# Model Errors
# =============================================================================

class ModelError(LearningError):
    """Base class for model-related errors."""
    pass


class ModelLoadError(ModelError):
    """
    Raised when a model fails to load.

    Attributes:
        model_path: Path to the model that failed to load
        model_name: Name/identifier of the model
    """

    def __init__(
        self,
        model_path: Optional[str] = None,
        model_name: Optional[str] = None,
        message: Optional[str] = None,
        cause: Optional[Exception] = None
    ):
        if message is None:
            identifier = model_path or model_name or "unknown"
            message = f"Failed to load model: {identifier}"
        super().__init__(message, cause=cause)
        self.model_path = model_path
        self.model_name = model_name
        self.details.update({
            "model_path": model_path,
            "model_name": model_name,
        })


class ModelSaveError(ModelError):
    """
    Raised when a model fails to save.

    Attributes:
        model_path: Path where the model was being saved
    """

    def __init__(
        self,
        model_path: str,
        message: Optional[str] = None,
        cause: Optional[Exception] = None
    ):
        if message is None:
            message = f"Failed to save model to: {model_path}"
        super().__init__(message, cause=cause)
        self.model_path = model_path
        self.details["model_path"] = model_path


class ModelSecurityError(ModelError):
    """
    Raised when model security validation fails.

    Used when trust_remote_code is requested for untrusted sources.

    Attributes:
        model_name: Name of the untrusted model
        trusted_sources: List of trusted sources
    """

    def __init__(
        self,
        model_name: str,
        trusted_sources: Optional[list] = None,
        message: Optional[str] = None
    ):
        if message is None:
            message = (
                f"Model '{model_name}' is not from a trusted source. "
                f"trust_remote_code disabled for security."
            )
        super().__init__(message)
        self.model_name = model_name
        self.trusted_sources = trusted_sources or []
        self.details.update({
            "model_name": model_name,
            "trusted_sources": self.trusted_sources,
        })


# =============================================================================
# Training Errors
# =============================================================================

class TrainingError(LearningError):
    """Base class for training process errors."""
    pass


class TrainingTimeoutError(TrainingError):
    """
    Raised when training exceeds the allowed time.

    Attributes:
        timeout_seconds: The timeout that was exceeded
        elapsed_seconds: Time elapsed before timeout (if known)
    """

    def __init__(
        self,
        timeout_seconds: int,
        elapsed_seconds: Optional[int] = None,
        message: Optional[str] = None
    ):
        if message is None:
            message = f"Training timed out after {timeout_seconds} seconds"
        super().__init__(message)
        self.timeout_seconds = timeout_seconds
        self.elapsed_seconds = elapsed_seconds
        self.details.update({
            "timeout_seconds": timeout_seconds,
            "elapsed_seconds": elapsed_seconds,
        })


class TrainingFailedError(TrainingError):
    """
    Raised when training fails for a specific reason.

    Attributes:
        stage: Training stage where failure occurred
        return_code: Process return code if applicable
    """

    def __init__(
        self,
        stage: str = "unknown",
        return_code: Optional[int] = None,
        stderr: Optional[str] = None,
        message: Optional[str] = None,
        cause: Optional[Exception] = None
    ):
        if message is None:
            message = f"Training failed at stage '{stage}'"
            if return_code is not None:
                message += f" (return code: {return_code})"
        super().__init__(message, cause=cause)
        self.stage = stage
        self.return_code = return_code
        self.stderr = stderr
        self.details.update({
            "stage": stage,
            "return_code": return_code,
            "stderr": stderr[:500] if stderr else None,  # Truncate long output
        })


# =============================================================================
# Storage Errors
# =============================================================================

class StorageError(LearningError):
    """Base class for storage-related errors."""
    pass


class RedisError(StorageError):
    """
    Raised when Redis operations fail.

    Attributes:
        operation: The Redis operation that failed
        key: The key involved (if applicable)
    """

    def __init__(
        self,
        operation: str,
        key: Optional[str] = None,
        message: Optional[str] = None,
        cause: Optional[Exception] = None
    ):
        if message is None:
            message = f"Redis {operation} failed"
            if key:
                message += f" for key: {key}"
        super().__init__(message, cause=cause)
        self.operation = operation
        self.key = key
        self.details.update({
            "operation": operation,
            "key": key,
        })


class FileSystemError(StorageError):
    """
    Raised when file system operations fail.

    Attributes:
        path: The path involved
        operation: The operation that failed (read, write, delete)
    """

    def __init__(
        self,
        path: str,
        operation: str = "access",
        message: Optional[str] = None,
        cause: Optional[Exception] = None
    ):
        if message is None:
            message = f"File system {operation} failed for: {path}"
        super().__init__(message, cause=cause)
        self.path = path
        self.operation = operation
        self.details.update({
            "path": path,
            "operation": operation,
        })


# =============================================================================
# Classification Errors
# =============================================================================

class ClassificationError(LearningError):
    """Base class for classification errors."""
    pass


class UnknownLabelError(ClassificationError):
    """
    Raised when classification returns an unknown label.

    Attributes:
        label: The unknown label that was returned
        expected_labels: List of valid labels
    """

    def __init__(
        self,
        label: str,
        expected_labels: Optional[list] = None,
        message: Optional[str] = None
    ):
        if message is None:
            message = f"Unknown classification label: '{label}'"
            if expected_labels:
                message += f". Expected one of: {expected_labels}"
        super().__init__(message)
        self.label = label
        self.expected_labels = expected_labels or []
        self.details.update({
            "label": label,
            "expected_labels": self.expected_labels,
        })
