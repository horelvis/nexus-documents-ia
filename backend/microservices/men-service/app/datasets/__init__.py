"""Datasets and data utilities for MEN service."""

from .generic_datasets import (
    GENERIC_LEGAL_EXAMPLES,
    GENERIC_CONTRACT_EXAMPLES,
    GENERIC_COMPLIANCE_EXAMPLES,
    GENERIC_FINANCE_EXAMPLES,
    GENERIC_HR_EXAMPLES,
    get_domain_examples,
)
from .document_expert_dataset import (
    ALL_DOCUMENT_EXPERT_EXAMPLES,
    get_document_expert_examples,
    DATASET_STATS,
)
from .huggingface_loader import (
    load_huggingface_datasets,
    load_huggingface_dataset,
    get_huggingface_stats,
    convert_to_training_format,
    AVAILABLE_DATASETS,
)

__all__ = [
    # Generic datasets
    "GENERIC_LEGAL_EXAMPLES",
    "GENERIC_CONTRACT_EXAMPLES",
    "GENERIC_COMPLIANCE_EXAMPLES",
    "GENERIC_FINANCE_EXAMPLES",
    "GENERIC_HR_EXAMPLES",
    "get_domain_examples",
    # Document expert dataset
    "ALL_DOCUMENT_EXPERT_EXAMPLES",
    "get_document_expert_examples",
    "DATASET_STATS",
    # HuggingFace loader
    "load_huggingface_datasets",
    "load_huggingface_dataset",
    "get_huggingface_stats",
    "convert_to_training_format",
    "AVAILABLE_DATASETS",
]
