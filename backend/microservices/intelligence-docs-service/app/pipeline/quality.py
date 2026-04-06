def compute_quality_score(text: str) -> float:
    """Score document text quality from 0.0 to 1.0."""
    if not text:
        return 0.0

    issues = 0
    total_checks = 5

    # Check 1: Very short text
    if len(text) < 50:
        issues += 1

    # Check 2: High ratio of special characters (OCR noise)
    special = sum(1 for c in text if not c.isalnum() and not c.isspace())
    if len(text) > 0 and special / len(text) > 0.3:
        issues += 1

    # Check 3: Missing whitespace (garbled OCR)
    words = text.split()
    if words:
        avg_word_len = sum(len(w) for w in words) / len(words)
        if avg_word_len > 20:
            issues += 1

    # Check 4: Repetitive content
    lines = text.split("\n")
    if len(lines) > 5:
        unique = len(set(lines))
        if unique / len(lines) < 0.3:
            issues += 1

    # Check 5: Encoding issues
    if "\ufffd" in text or "\x00" in text:
        issues += 1

    return max(0.0, 1.0 - (issues / total_checks))
