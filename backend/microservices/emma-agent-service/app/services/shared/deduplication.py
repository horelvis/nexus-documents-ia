"""
Shared deduplication utilities for text similarity checking.

Used by both Predictive Analysis (factor deduplication) and
Verified Generation (claim deduplication) to avoid near-duplicate
items being processed multiple times.

Algorithm: Word-level Jaccard similarity (|A∩B| / |A∪B|).
"""

from typing import List, Tuple


def calculate_jaccard_similarity(text_a: str, text_b: str) -> float:
    """Word-level Jaccard similarity between two texts.

    Args:
        text_a: First text to compare.
        text_b: Second text to compare.

    Returns:
        Similarity score between 0.0 and 1.0.
    """
    words_a = set(text_a.lower().split())
    words_b = set(text_b.lower().split())
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union) if union else 0.0


def is_duplicate_text(
    new_text: str,
    existing_texts: List[str],
    threshold: float = 0.65,
    min_words: int = 3,
) -> bool:
    """Check if new_text is too similar to any existing text.

    Args:
        new_text: Text to check for duplicates.
        existing_texts: List of previously seen texts.
        threshold: Jaccard similarity threshold for duplicate detection.
        min_words: Minimum word count — texts shorter than this are never duplicates.

    Returns:
        True if new_text is a duplicate of any existing text.
    """
    if not existing_texts:
        return False

    new_words = set(new_text.lower().split())
    if len(new_words) < min_words:
        return False

    for text in existing_texts:
        existing_words = set(text.lower().split())
        if not existing_words:
            continue
        intersection = new_words & existing_words
        union = new_words | existing_words
        similarity = len(intersection) / len(union) if union else 0.0
        if similarity >= threshold:
            return True

    return False


def is_duplicate_with_type(
    new_text: str,
    new_type: str,
    existing_items: List[Tuple[str, str]],
    threshold: float = 0.65,
    same_type_threshold: float = 0.5,
    min_words: int = 3,
) -> bool:
    """Type-aware duplicate detection (for predictive factors).

    Same-type items use a lower threshold since semantically similar
    items of the same type are more likely true duplicates.

    Args:
        new_text: Text to check for duplicates.
        new_type: Type/category of the new item.
        existing_items: List of (text, type) tuples to compare against.
        threshold: Jaccard similarity threshold for different-type items.
        same_type_threshold: Lower threshold when types match.
        min_words: Minimum word count — texts shorter than this are never duplicates.

    Returns:
        True if new item is a duplicate of any existing item.
    """
    if not existing_items:
        return False

    new_words = set(new_text.lower().split())
    if len(new_words) < min_words:
        return False

    for text, item_type in existing_items:
        existing_words = set(text.lower().split())
        if not existing_words:
            continue
        intersection = new_words & existing_words
        union = new_words | existing_words
        similarity = len(intersection) / len(union) if union else 0.0

        if similarity >= threshold:
            return True
        if item_type == new_type and similarity >= same_type_threshold:
            return True

    return False
