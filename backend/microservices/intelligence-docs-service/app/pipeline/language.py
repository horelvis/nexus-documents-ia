from langdetect import detect


def detect_language(text: str) -> str:
    """Detect language of text. Returns ISO 639-1 code or empty string."""
    if not text or len(text.strip()) < 20:
        return ""
    try:
        return detect(text)
    except Exception:
        return ""
