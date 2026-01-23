"""
JSON extraction utilities for parsing LLM responses.

This module provides robust functions for extracting JSON from various
LLM response formats, including:
- Raw JSON responses
- JSON wrapped in markdown code blocks
- Responses with thinking tags (Qwen3, Claude, etc.)
- Malformed JSON with common issues (trailing commas, control chars)

Usage:
    from app.utils.json_extraction import extract_json_from_llm_response

    response = '''
    <think>Let me analyze this...</think>
    ```json
    {"result": "success", "data": [1, 2, 3]}
    ```
    '''

    data = extract_json_from_llm_response(response)
    # Returns: {"result": "success", "data": [1, 2, 3]}
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


# =============================================================================
# Pre-compiled Patterns
# =============================================================================

# Thinking tags from various LLMs
THINKING_TAG_PATTERN = re.compile(
    r'<think>.*?</think>|'
    r'<thinking>.*?</thinking>|'
    r'<reflection>.*?</reflection>',
    re.DOTALL | re.IGNORECASE
)

# Markdown code blocks
CODE_BLOCK_PATTERN = re.compile(
    r'```(?:json)?\s*([\s\S]*?)\s*```',
    re.IGNORECASE
)

# JSON object pattern (greedy, for nested objects)
JSON_OBJECT_PATTERN = re.compile(r'\{[\s\S]*\}')

# JSON array pattern
JSON_ARRAY_PATTERN = re.compile(r'\[[\s\S]*\]')

# Simple JSON object (non-nested)
SIMPLE_JSON_PATTERN = re.compile(r'\{[^{}]*\}')

# Control characters (except newline, tab)
CONTROL_CHAR_PATTERN = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')

# Trailing comma before closing bracket/brace
TRAILING_COMMA_PATTERN = re.compile(r',\s*([}\]])')

# Single quotes used as JSON strings (common LLM mistake)
SINGLE_QUOTE_PATTERN = re.compile(r"(?<!\\)'([^']*)'(?=\s*[,}\]:])")


# =============================================================================
# Main Extraction Functions
# =============================================================================

def extract_json_from_llm_response(
    response: str,
    default: Optional[Dict] = None,
    expect_array: bool = False,
    strict: bool = False,
) -> Optional[Union[Dict, List]]:
    """
    Extract JSON from an LLM response, handling various formats.

    This function attempts multiple extraction strategies:
    1. Remove thinking tags
    2. Extract from markdown code blocks
    3. Find raw JSON objects/arrays
    4. Fix common JSON issues and retry

    Args:
        response: The raw LLM response string
        default: Default value to return if extraction fails
        expect_array: If True, expect a JSON array instead of object
        strict: If True, raise exception on failure instead of returning default

    Returns:
        Parsed JSON as dict or list, or default value if parsing fails

    Raises:
        ValueError: If strict=True and extraction fails

    Example:
        >>> response = '<think>analyzing...</think>{"status": "ok"}'
        >>> extract_json_from_llm_response(response)
        {'status': 'ok'}
    """
    if not response or not isinstance(response, str):
        if strict:
            raise ValueError("Empty or invalid response")
        return default

    # Step 1: Clean the response
    cleaned = clean_llm_response(response)

    # Step 2: Try to extract from code block first
    json_str = extract_json_block(cleaned)

    # Step 3: If no code block, find raw JSON
    if not json_str:
        pattern = JSON_ARRAY_PATTERN if expect_array else JSON_OBJECT_PATTERN
        match = pattern.search(cleaned)
        if match:
            json_str = match.group(0)

    # Step 4: Try simple pattern if nested failed
    if not json_str and not expect_array:
        match = SIMPLE_JSON_PATTERN.search(cleaned)
        if match:
            json_str = match.group(0)

    # Step 5: Parse the JSON
    if json_str:
        result = safe_json_parse(json_str)
        if result is not None:
            return result

    # Step 6: If all else fails
    if strict:
        raise ValueError(f"Could not extract JSON from response: {response[:200]}...")

    logger.warning(f"Failed to extract JSON from LLM response: {response[:100]}...")
    return default


def clean_llm_response(response: str) -> str:
    """
    Clean an LLM response by removing thinking tags and normalizing whitespace.

    Args:
        response: Raw LLM response

    Returns:
        Cleaned response string

    Example:
        >>> clean_llm_response("<think>hmm</think>Hello")
        'Hello'
    """
    if not response:
        return ""

    # Remove thinking tags
    cleaned = THINKING_TAG_PATTERN.sub('', response)

    # Remove control characters (keep newlines and tabs)
    cleaned = CONTROL_CHAR_PATTERN.sub('', cleaned)

    # Normalize whitespace (but preserve structure)
    cleaned = cleaned.strip()

    return cleaned


def extract_json_block(text: str) -> Optional[str]:
    """
    Extract JSON from a markdown code block.

    Args:
        text: Text potentially containing a code block

    Returns:
        The content of the code block, or None if not found

    Example:
        >>> extract_json_block('```json\\n{"a": 1}\\n```')
        '{"a": 1}'
    """
    match = CODE_BLOCK_PATTERN.search(text)
    if match:
        return match.group(1).strip()
    return None


def safe_json_parse(json_str: str) -> Optional[Union[Dict, List]]:
    """
    Safely parse JSON with automatic fixing of common issues.

    Handles:
    - Trailing commas
    - Control characters
    - Single quotes instead of double quotes
    - Unescaped newlines in strings

    Args:
        json_str: JSON string to parse

    Returns:
        Parsed JSON object/array, or None if parsing fails

    Example:
        >>> safe_json_parse('{"a": 1, }')  # trailing comma
        {'a': 1}
    """
    if not json_str:
        return None

    # Try direct parse first
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        pass

    # Try fixing common issues
    fixed = json_str

    # Fix trailing commas
    fixed = TRAILING_COMMA_PATTERN.sub(r'\1', fixed)

    # Remove control characters
    fixed = CONTROL_CHAR_PATTERN.sub('', fixed)

    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass

    # Try replacing single quotes with double quotes (risky, last resort)
    try:
        # Only do this if there are no double quotes
        if '"' not in fixed and "'" in fixed:
            fixed_quotes = fixed.replace("'", '"')
            return json.loads(fixed_quotes)
    except json.JSONDecodeError:
        pass

    # Log for debugging
    logger.debug(f"Failed to parse JSON: {json_str[:100]}...")
    return None


# =============================================================================
# Specialized Extraction Functions
# =============================================================================

def extract_json_with_key(
    response: str,
    required_key: str,
    default: Optional[Dict] = None,
) -> Optional[Dict]:
    """
    Extract JSON and verify it contains a required key.

    Args:
        response: LLM response string
        required_key: Key that must be present in the result
        default: Default value if extraction fails or key missing

    Returns:
        Parsed JSON dict if it contains the key, else default

    Example:
        >>> extract_json_with_key('{"status": "ok"}', "status")
        {'status': 'ok'}
        >>> extract_json_with_key('{"data": 1}', "status")
        None
    """
    result = extract_json_from_llm_response(response, default=None)

    if isinstance(result, dict) and required_key in result:
        return result

    return default


def extract_multiple_json_objects(response: str) -> List[Dict]:
    """
    Extract all JSON objects from a response (for streaming or multi-object responses).

    Args:
        response: Text containing multiple JSON objects

    Returns:
        List of parsed JSON objects

    Example:
        >>> extract_multiple_json_objects('{"a":1}{"b":2}')
        [{'a': 1}, {'b': 2}]
    """
    results = []
    cleaned = clean_llm_response(response)

    # Find all JSON-like patterns
    for match in SIMPLE_JSON_PATTERN.finditer(cleaned):
        parsed = safe_json_parse(match.group(0))
        if parsed is not None:
            results.append(parsed)

    return results


def extract_field_from_json(
    response: str,
    field: str,
    default: Any = None,
) -> Any:
    """
    Extract a specific field from a JSON response.

    Args:
        response: LLM response string
        field: Field name to extract
        default: Default value if field not found

    Returns:
        The field value or default

    Example:
        >>> extract_field_from_json('{"status": "ok", "count": 5}', "count")
        5
    """
    result = extract_json_from_llm_response(response, default=None)

    if isinstance(result, dict):
        return result.get(field, default)

    return default
