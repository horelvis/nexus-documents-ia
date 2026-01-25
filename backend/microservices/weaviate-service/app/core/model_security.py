"""
Model Security Utilities

Provides safe model loading with trust_remote_code validation.
Prevents arbitrary code execution from untrusted model sources.

Security Model:
    trust_remote_code=True is ONLY allowed for models from trusted sources.
    Trusted sources are defined in learning_config.py and can be customized
    via environment variables.

Default Trusted Sources:
    - Qwen (Alibaba)
    - sentence-transformers
    - BAAI (Beijing Academy of AI)
    - microsoft
    - meta-llama

Usage:
    from app.core.model_security import (
        safe_load_model,
        safe_load_tokenizer,
        is_trusted_model,
    )

    # Safe loading with automatic trust validation
    model = safe_load_model(
        AutoModelForCausalLM,
        "Qwen/Qwen2-0.5B-Instruct",
        trust_remote_code=True  # Will be validated
    )

    # Check if model is trusted
    if is_trusted_model("untrusted/model"):
        # Won't reach here for untrusted models
        pass

Version 1.0 - January 2026
"""

import logging
from typing import Any, Callable, List, Optional, Type, TypeVar, Union

from app.core.learning_config import learning_settings
from app.core.learning_exceptions import ModelSecurityError

logger = logging.getLogger(__name__)

# Type variable for model classes
M = TypeVar('M')


# =============================================================================
# Trusted Source Validation
# =============================================================================

def get_trusted_sources() -> List[str]:
    """
    Get the list of trusted model sources.

    Returns:
        List of trusted organization names
    """
    return learning_settings.trusted_model_sources


def is_trusted_model(model_name: str) -> bool:
    """
    Check if a model is from a trusted source.

    Args:
        model_name: Full model name (e.g., "Qwen/Qwen2-0.5B-Instruct")

    Returns:
        True if the model organization is in trusted sources

    Examples:
        >>> is_trusted_model("Qwen/Qwen2-0.5B-Instruct")
        True
        >>> is_trusted_model("sentence-transformers/all-MiniLM-L6-v2")
        True
        >>> is_trusted_model("random-user/suspicious-model")
        False
    """
    return learning_settings.is_model_trusted(model_name)


def validate_trust_remote_code(
    model_name: str,
    trust_remote_code: bool,
    raise_on_untrusted: bool = False
) -> bool:
    """
    Validate and potentially adjust trust_remote_code setting.

    Args:
        model_name: Model name to check
        trust_remote_code: Requested trust_remote_code setting
        raise_on_untrusted: If True, raise exception for untrusted models

    Returns:
        Validated trust_remote_code value (may be False for untrusted)

    Raises:
        ModelSecurityError: If raise_on_untrusted=True and model is untrusted
    """
    if not trust_remote_code:
        # trust_remote_code not requested, no validation needed
        return False

    if is_trusted_model(model_name):
        logger.debug(f"Model '{model_name}' is from trusted source, allowing trust_remote_code=True")
        return True

    # Model not trusted
    if learning_settings.strict_model_security:
        if raise_on_untrusted:
            raise ModelSecurityError(
                model_name=model_name,
                trusted_sources=get_trusted_sources(),
                message=(
                    f"Model '{model_name}' requires trust_remote_code=True but is not from "
                    f"a trusted source. Trusted sources: {get_trusted_sources()}"
                )
            )

        logger.warning(
            f"⚠️ Model '{model_name}' is NOT from a trusted source. "
            f"Disabling trust_remote_code for security. "
            f"Trusted sources: {get_trusted_sources()}"
        )
        return False

    # Strict security disabled - allow with warning
    logger.warning(
        f"⚠️ SECURITY: Loading untrusted model '{model_name}' with trust_remote_code=True. "
        f"Set LEARNING_STRICT_SECURITY=true to prevent this."
    )
    return True


# =============================================================================
# Safe Model Loading
# =============================================================================

def safe_load_model(
    model_class: Type[M],
    model_name: str,
    trust_remote_code: bool = False,
    raise_on_untrusted: bool = False,
    **kwargs
) -> M:
    """
    Safely load a model with trust_remote_code validation.

    This function wraps model_class.from_pretrained() and validates
    trust_remote_code against the trusted sources list.

    Args:
        model_class: Model class with from_pretrained method
                     (e.g., AutoModelForCausalLM, SetFitModel)
        model_name: Model name or path
        trust_remote_code: Whether to trust remote code
        raise_on_untrusted: If True, raise exception for untrusted models
        **kwargs: Additional arguments for from_pretrained

    Returns:
        Loaded model instance

    Raises:
        ModelSecurityError: If raise_on_untrusted=True and model is untrusted

    Example:
        from transformers import AutoModelForCausalLM

        model = safe_load_model(
            AutoModelForCausalLM,
            "Qwen/Qwen2-0.5B-Instruct",
            trust_remote_code=True,
            torch_dtype=torch.float16
        )
    """
    # Validate trust_remote_code
    validated_trust = validate_trust_remote_code(
        model_name,
        trust_remote_code,
        raise_on_untrusted=raise_on_untrusted
    )

    logger.info(
        f"Loading model '{model_name}' "
        f"(trust_remote_code={validated_trust}, class={model_class.__name__})"
    )

    return model_class.from_pretrained(
        model_name,
        trust_remote_code=validated_trust,
        **kwargs
    )


def safe_load_tokenizer(
    tokenizer_class: Type[M],
    model_name: str,
    trust_remote_code: bool = False,
    raise_on_untrusted: bool = False,
    **kwargs
) -> M:
    """
    Safely load a tokenizer with trust_remote_code validation.

    Args:
        tokenizer_class: Tokenizer class with from_pretrained method
                         (e.g., AutoTokenizer)
        model_name: Model/tokenizer name or path
        trust_remote_code: Whether to trust remote code
        raise_on_untrusted: If True, raise exception for untrusted models
        **kwargs: Additional arguments for from_pretrained

    Returns:
        Loaded tokenizer instance

    Example:
        from transformers import AutoTokenizer

        tokenizer = safe_load_tokenizer(
            AutoTokenizer,
            "Qwen/Qwen2-0.5B-Instruct",
            trust_remote_code=True,
            padding_side='right'
        )
    """
    # Validate trust_remote_code
    validated_trust = validate_trust_remote_code(
        model_name,
        trust_remote_code,
        raise_on_untrusted=raise_on_untrusted
    )

    logger.debug(
        f"Loading tokenizer for '{model_name}' "
        f"(trust_remote_code={validated_trust})"
    )

    return tokenizer_class.from_pretrained(
        model_name,
        trust_remote_code=validated_trust,
        **kwargs
    )


# =============================================================================
# PEFT/LoRA Safe Loading
# =============================================================================

def safe_load_peft_model(
    base_model: Any,
    adapter_path: str,
    model_name: Optional[str] = None,
    **kwargs
) -> Any:
    """
    Safely load a PEFT/LoRA adapter onto a base model.

    Args:
        base_model: Pre-loaded base model
        adapter_path: Path to the adapter
        model_name: Optional model name for logging
        **kwargs: Additional arguments for PeftModel.from_pretrained

    Returns:
        Model with adapter loaded
    """
    from peft import PeftModel

    logger.info(f"Loading PEFT adapter from '{adapter_path}'")

    return PeftModel.from_pretrained(base_model, adapter_path, **kwargs)


# =============================================================================
# Context Manager for Temporary Trust Override
# =============================================================================

class TrustedModelContext:
    """
    Context manager for temporarily adding trusted sources.

    Use with caution - only for known-safe operations.

    Example:
        with TrustedModelContext(["custom-org"]):
            model = safe_load_model(...)
    """

    def __init__(self, additional_sources: List[str]):
        """
        Initialize context with additional trusted sources.

        Args:
            additional_sources: Sources to temporarily trust
        """
        self.additional_sources = additional_sources
        self._original_sources: Optional[List[str]] = None

    def __enter__(self):
        """Add temporary trusted sources."""
        self._original_sources = learning_settings.trusted_model_sources.copy()
        learning_settings.trusted_model_sources.extend(self.additional_sources)
        logger.warning(
            f"⚠️ Temporarily added trusted sources: {self.additional_sources}. "
            f"Use with caution."
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Restore original trusted sources."""
        if self._original_sources is not None:
            learning_settings.trusted_model_sources[:] = self._original_sources
            logger.debug("Restored original trusted sources")
        return False


# =============================================================================
# Utility Functions
# =============================================================================

def get_model_organization(model_name: str) -> Optional[str]:
    """
    Extract the organization from a model name.

    Args:
        model_name: Full model name (e.g., "Qwen/Qwen2-0.5B-Instruct")

    Returns:
        Organization name or None if not found

    Examples:
        >>> get_model_organization("Qwen/Qwen2-0.5B-Instruct")
        'Qwen'
        >>> get_model_organization("gpt2")
        None
    """
    if "/" in model_name:
        return model_name.split("/")[0]
    return None


def log_security_status() -> None:
    """Log current security configuration status."""
    logger.info(
        f"Model Security Status:\n"
        f"  - Strict security: {learning_settings.strict_model_security}\n"
        f"  - Trusted sources: {learning_settings.trusted_model_sources}"
    )
