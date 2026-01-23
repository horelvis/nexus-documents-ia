"""
Centralized regex patterns for PII detection and validation.

This module provides international support for detecting personally identifiable
information (PII) across different regions and formats.

Usage:
    from app.core.patterns import PIIPatterns, detect_pii

    # Check for PII in text
    pii_found = detect_pii(content)
    if pii_found['has_email']:
        print("Email detected")

    # Use specific patterns
    import re
    if re.search(PIIPatterns.EMAIL, content):
        print("Email found")
"""

import re
from dataclasses import dataclass
from typing import Dict, List, Optional


# =============================================================================
# Email Patterns
# =============================================================================

# RFC 5322 compliant email pattern (simplified but robust)
EMAIL_PATTERN = re.compile(
    r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
    re.IGNORECASE
)


# =============================================================================
# Phone Number Patterns (International)
# =============================================================================

PHONE_PATTERNS = {
    # US/Canada: (555) 555-5555, 555-555-5555, 555.555.5555
    'US': re.compile(r'\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b'),

    # Spain: +34 612 345 678, 612 34 56 78, 612345678
    'ES': re.compile(r'\b(?:\+?34[-.\s]?)?[6-9]\d{2}[-.\s]?\d{3}[-.\s]?\d{3}\b'),

    # UK: +44 7911 123456, 07911 123456
    'UK': re.compile(r'\b(?:\+?44[-.\s]?)?0?7\d{3}[-.\s]?\d{6}\b'),

    # France: +33 6 12 34 56 78
    'FR': re.compile(r'\b(?:\+?33[-.\s]?)?0?[67]\d{2}[-.\s]?\d{2}[-.\s]?\d{2}[-.\s]?\d{2}\b'),

    # Germany: +49 170 1234567
    'DE': re.compile(r'\b(?:\+?49[-.\s]?)?0?1[567]\d[-.\s]?\d{7,8}\b'),

    # Generic international: +XX XXXXXXXXXX
    'INTL': re.compile(r'\b\+\d{1,3}[-.\s]?\d{6,14}\b'),
}

# Combined phone pattern (matches any format)
PHONE_PATTERN_ANY = re.compile(
    r'\b(?:'
    r'(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}|'  # US
    r'(?:\+?34[-.\s]?)?[6-9]\d{2}[-.\s]?\d{3}[-.\s]?\d{3}|'  # ES
    r'(?:\+?44[-.\s]?)?0?7\d{3}[-.\s]?\d{6}|'  # UK
    r'\+\d{1,3}[-.\s]?\d{6,14}'  # Generic international
    r')\b'
)


# =============================================================================
# National ID Patterns (International)
# =============================================================================

NATIONAL_ID_PATTERNS = {
    # US Social Security Number: 123-45-6789
    'US_SSN': re.compile(r'\b\d{3}-\d{2}-\d{4}\b'),

    # Spain DNI/NIE: 12345678A, X1234567A
    'ES_DNI': re.compile(r'\b\d{8}[A-Z]\b', re.IGNORECASE),
    'ES_NIE': re.compile(r'\b[XYZ]\d{7}[A-Z]\b', re.IGNORECASE),

    # Spain NIF (companies): A12345678
    'ES_NIF': re.compile(r'\b[A-HJNP-SUVW]\d{7}[A-J0-9]\b', re.IGNORECASE),

    # UK National Insurance: AB123456C
    'UK_NI': re.compile(r'\b[A-Z]{2}\d{6}[A-Z]\b', re.IGNORECASE),

    # France INSEE/NIR: 1 85 12 75 108 123 45
    'FR_NIR': re.compile(r'\b[12]\s?\d{2}\s?\d{2}\s?\d{2}\s?\d{3}\s?\d{3}\s?\d{2}\b'),

    # Germany Personalausweis: L01X00T471
    'DE_ID': re.compile(r'\b[A-Z0-9]{10}\b'),

    # Passport (generic): 2 letters + 7 digits
    'PASSPORT': re.compile(r'\b[A-Z]{2}\d{7}\b', re.IGNORECASE),
}


# =============================================================================
# Financial Patterns
# =============================================================================

FINANCIAL_PATTERNS = {
    # Credit card (generic, Luhn check should be done separately)
    'CREDIT_CARD': re.compile(r'\b(?:\d{4}[-\s]?){3}\d{4}\b'),

    # IBAN (International Bank Account Number)
    'IBAN': re.compile(r'\b[A-Z]{2}\d{2}[A-Z0-9]{4,30}\b', re.IGNORECASE),

    # Spain CCC (Código Cuenta Cliente): 1234 5678 12 1234567890
    'ES_CCC': re.compile(r'\b\d{4}[-\s]?\d{4}[-\s]?\d{2}[-\s]?\d{10}\b'),
}


# =============================================================================
# PII Detection Class
# =============================================================================

@dataclass
class PIIDetectionResult:
    """Result of PII detection scan."""
    has_email: bool = False
    has_phone: bool = False
    has_national_id: bool = False
    has_financial: bool = False

    email_matches: List[str] = None
    phone_matches: List[str] = None
    national_id_matches: List[str] = None
    financial_matches: List[str] = None

    detected_regions: List[str] = None

    def __post_init__(self):
        self.email_matches = self.email_matches or []
        self.phone_matches = self.phone_matches or []
        self.national_id_matches = self.national_id_matches or []
        self.financial_matches = self.financial_matches or []
        self.detected_regions = self.detected_regions or []

    @property
    def has_pii(self) -> bool:
        """Returns True if any PII was detected."""
        return self.has_email or self.has_phone or self.has_national_id or self.has_financial

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'has_pii': self.has_pii,
            'has_email': self.has_email,
            'has_phone': self.has_phone,
            'has_national_id': self.has_national_id,
            'has_financial': self.has_financial,
            'detected_regions': self.detected_regions,
        }


def detect_pii(
    content: str,
    check_email: bool = True,
    check_phone: bool = True,
    check_national_id: bool = True,
    check_financial: bool = False,
    regions: Optional[List[str]] = None,
    return_matches: bool = False,
) -> PIIDetectionResult:
    """
    Detect PII in text content.

    Args:
        content: Text to scan for PII
        check_email: Whether to check for email addresses
        check_phone: Whether to check for phone numbers
        check_national_id: Whether to check for national ID numbers
        check_financial: Whether to check for financial data (credit cards, IBAN)
        regions: List of region codes to check (e.g., ['US', 'ES', 'UK'])
                 If None, checks all regions
        return_matches: If True, include the actual matches found

    Returns:
        PIIDetectionResult with detection flags and optionally matches

    Example:
        >>> result = detect_pii("Contact john@example.com or +34 612 345 678")
        >>> result.has_email
        True
        >>> result.has_phone
        True
    """
    result = PIIDetectionResult()
    detected_regions = set()

    # Email detection
    if check_email:
        email_matches = EMAIL_PATTERN.findall(content)
        result.has_email = bool(email_matches)
        if return_matches:
            result.email_matches = email_matches

    # Phone detection
    if check_phone:
        phone_matches = []
        patterns_to_check = PHONE_PATTERNS if regions is None else {
            r: p for r, p in PHONE_PATTERNS.items() if r in regions or r == 'INTL'
        }

        for region, pattern in patterns_to_check.items():
            matches = pattern.findall(content)
            if matches:
                phone_matches.extend(matches)
                if region != 'INTL':
                    detected_regions.add(region)

        result.has_phone = bool(phone_matches)
        if return_matches:
            result.phone_matches = list(set(phone_matches))

    # National ID detection
    if check_national_id:
        id_matches = []
        patterns_to_check = NATIONAL_ID_PATTERNS if regions is None else {
            r: p for r, p in NATIONAL_ID_PATTERNS.items()
            if any(r.startswith(reg) for reg in (regions or []))
        }

        # If no specific regions, check all
        if not patterns_to_check:
            patterns_to_check = NATIONAL_ID_PATTERNS

        for id_type, pattern in patterns_to_check.items():
            matches = pattern.findall(content)
            if matches:
                id_matches.extend(matches)
                region = id_type.split('_')[0]
                detected_regions.add(region)

        result.has_national_id = bool(id_matches)
        if return_matches:
            result.national_id_matches = list(set(id_matches))

    # Financial detection
    if check_financial:
        fin_matches = []
        for fin_type, pattern in FINANCIAL_PATTERNS.items():
            matches = pattern.findall(content)
            if matches:
                fin_matches.extend(matches)

        result.has_financial = bool(fin_matches)
        if return_matches:
            result.financial_matches = list(set(fin_matches))

    result.detected_regions = list(detected_regions)
    return result


# =============================================================================
# Legacy Compatibility Functions
# =============================================================================

def has_email(content: str) -> bool:
    """Check if content contains an email address."""
    return bool(EMAIL_PATTERN.search(content))


def has_phone(content: str) -> bool:
    """Check if content contains a phone number (any format)."""
    return bool(PHONE_PATTERN_ANY.search(content))


def has_ssn(content: str) -> bool:
    """Check if content contains a US Social Security Number."""
    return bool(NATIONAL_ID_PATTERNS['US_SSN'].search(content))


def has_spanish_id(content: str) -> bool:
    """Check if content contains a Spanish DNI or NIE."""
    return bool(
        NATIONAL_ID_PATTERNS['ES_DNI'].search(content) or
        NATIONAL_ID_PATTERNS['ES_NIE'].search(content)
    )


# =============================================================================
# Convenience Aliases
# =============================================================================

class PIIPatterns:
    """Namespace for accessing compiled patterns directly."""
    EMAIL = EMAIL_PATTERN
    PHONE_US = PHONE_PATTERNS['US']
    PHONE_ES = PHONE_PATTERNS['ES']
    PHONE_UK = PHONE_PATTERNS['UK']
    PHONE_ANY = PHONE_PATTERN_ANY
    SSN = NATIONAL_ID_PATTERNS['US_SSN']
    DNI = NATIONAL_ID_PATTERNS['ES_DNI']
    NIE = NATIONAL_ID_PATTERNS['ES_NIE']
    NIF = NATIONAL_ID_PATTERNS['ES_NIF']
    IBAN = FINANCIAL_PATTERNS['IBAN']
    CREDIT_CARD = FINANCIAL_PATTERNS['CREDIT_CARD']
