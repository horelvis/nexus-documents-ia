"""
Layer 0: Document Intelligence

Quality assessment and preprocessing for already-extracted document text.
Works with text extracted by external services (Gotenberg, storage-service, etc.)

Key responsibilities:
1. Assess extraction quality (detect OCR errors, formatting issues)
2. Detect document structure (tables, sections, headers)
3. Prepare text for semantic chunking
4. Enrich metadata for retrieval

Note: Does NOT extract text from files - that's handled by external microservices.

Reference: "My production system crashed at 2 AM" - Document Preprocessing section
"""

import re
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class DocumentQuality(str, Enum):
    """Quality assessment of extracted content"""
    HIGH = "high"          # >85% confidence, clean text
    MEDIUM = "medium"      # 60-85% confidence, some issues
    LOW = "low"            # <60% confidence, needs review
    FAILED = "failed"      # Extraction failed or empty


class ContentIssue(str, Enum):
    """Types of issues detected in content"""
    OCR_ERRORS = "ocr_errors"
    BROKEN_TABLES = "broken_tables"
    MISSING_WHITESPACE = "missing_whitespace"
    EXCESSIVE_WHITESPACE = "excessive_whitespace"
    GARBLED_TEXT = "garbled_text"
    TRUNCATED = "truncated"
    ENCODING_ISSUES = "encoding_issues"


@dataclass
class DetectedTable:
    """A table detected in document text"""
    start_pos: int
    end_pos: int
    raw_text: str
    formatted_text: str  # Cleaned up for embedding
    row_count: int
    column_count: int


@dataclass
class DocumentAnalysis:
    """Result of document intelligence analysis"""
    # Quality metrics
    quality: DocumentQuality
    confidence: float  # 0.0 - 1.0

    # Content stats
    word_count: int
    char_count: int
    line_count: int
    avg_words_per_line: float

    # Detected structure
    has_tables: bool
    table_count: int
    has_headers: bool
    header_count: int
    has_lists: bool
    list_count: int

    # Fields with defaults must come after non-defaults
    tables: List[DetectedTable] = field(default_factory=list)
    issues: List[ContentIssue] = field(default_factory=list)
    issue_details: Dict[str, Any] = field(default_factory=dict)
    needs_cleaning: bool = False
    cleaning_suggestions: List[str] = field(default_factory=list)
    processed_text: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "quality": self.quality.value,
            "confidence": self.confidence,
            "word_count": self.word_count,
            "char_count": self.char_count,
            "has_tables": self.has_tables,
            "table_count": self.table_count,
            "has_headers": self.has_headers,
            "header_count": self.header_count,
            "issues": [i.value for i in self.issues],
            "needs_cleaning": self.needs_cleaning,
        }


class DocumentIntelligence:
    """
    Layer 0: Intelligent analysis of extracted document text.

    This class analyzes text that has already been extracted by external
    services (Gotenberg, storage-service) and prepares it for the RAG pipeline.

    Usage:
        di = DocumentIntelligence()
        analysis = di.analyze(extracted_text, metadata)

        if analysis.needs_cleaning:
            clean_text = analysis.processed_text
        else:
            clean_text = extracted_text

        # Use clean_text for chunking
    """

    # Patterns for detecting document structure
    HEADER_PATTERNS = [
        r'^#{1,6}\s+.+$',                    # Markdown headers
        r'^\d+(?:\.\d+)*\.\s+[A-Z].+$',      # Numbered sections (1. Title, 1.1. Subtitle)
        r'^[A-Z][A-Z\s]{2,50}$',             # ALL CAPS headers
        r'^(CLÁUSULA|ARTÍCULO|SECCIÓN|CAPÍTULO)\s+',  # Legal (Spanish)
        r'^(CLAUSE|ARTICLE|SECTION|CHAPTER)\s+',      # Legal (English)
    ]

    TABLE_PATTERNS = [
        r'\|[^\|]+\|',                        # Pipe-delimited tables
        r'^\s*[-+]+\s*$',                     # Table separators
        r'(\t[^\t\n]+){2,}',                  # Tab-separated data
    ]

    LIST_PATTERNS = [
        r'^\s*[-•*]\s+',                      # Bullet lists
        r'^\s*\d+[.)]\s+',                    # Numbered lists
        r'^\s*[a-z][.)]\s+',                  # Lettered lists
    ]

    # OCR error patterns
    OCR_ERROR_PATTERNS = [
        (r'[0O][1l][0O]', 'digit_letter_confusion'),   # 0/O, 1/l confusion
        (r'rn(?=[a-z])', 'm_split'),                   # 'rn' instead of 'm'
        (r'(?<=[a-z])l(?=[a-z])', 'l_for_i'),          # 'l' instead of 'i'
        (r'(.)\1{4,}', 'repeated_chars'),              # 5+ repeated characters
    ]

    def __init__(
        self,
        min_confidence_for_clean: float = 0.85,
        detect_tables: bool = True,
        clean_whitespace: bool = True,
    ):
        self.min_confidence_for_clean = min_confidence_for_clean
        self.detect_tables = detect_tables
        self.clean_whitespace = clean_whitespace

    def analyze(
        self,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> DocumentAnalysis:
        """
        Analyze extracted text and assess quality.

        Args:
            text: Already-extracted document text
            metadata: Optional document metadata

        Returns:
            DocumentAnalysis with quality assessment and processed text
        """
        if not text or not text.strip():
            return DocumentAnalysis(
                quality=DocumentQuality.FAILED,
                confidence=0.0,
                word_count=0,
                char_count=0,
                line_count=0,
                avg_words_per_line=0.0,
                has_tables=False,
                table_count=0,
                has_headers=False,
                header_count=0,
                has_lists=False,
                list_count=0,
                issues=[ContentIssue.TRUNCATED],
            )

        # Basic stats
        lines = text.split('\n')
        words = text.split()

        word_count = len(words)
        char_count = len(text)
        line_count = len(lines)
        avg_words_per_line = word_count / line_count if line_count > 0 else 0

        # Detect structure
        headers = self._detect_headers(text)
        tables = self._detect_tables(text) if self.detect_tables else []
        lists = self._detect_lists(text)

        # Detect issues
        issues, issue_details = self._detect_issues(text)

        # Calculate confidence
        confidence = self._calculate_confidence(text, issues)

        # Determine quality
        quality = self._assess_quality(confidence, issues)

        # Clean text if needed
        processed_text = None
        cleaning_suggestions = []
        needs_cleaning = False

        if confidence < self.min_confidence_for_clean or issues:
            needs_cleaning = True
            processed_text, cleaning_suggestions = self._clean_text(text, issues)

        return DocumentAnalysis(
            quality=quality,
            confidence=confidence,
            word_count=word_count,
            char_count=char_count,
            line_count=line_count,
            avg_words_per_line=avg_words_per_line,
            has_tables=len(tables) > 0,
            table_count=len(tables),
            tables=tables,
            has_headers=len(headers) > 0,
            header_count=len(headers),
            has_lists=len(lists) > 0,
            list_count=len(lists),
            issues=issues,
            issue_details=issue_details,
            needs_cleaning=needs_cleaning,
            cleaning_suggestions=cleaning_suggestions,
            processed_text=processed_text,
        )

    def _detect_headers(self, text: str) -> List[Dict[str, Any]]:
        """Detect section headers in text"""
        headers = []

        for line_num, line in enumerate(text.split('\n')):
            line = line.strip()
            if not line:
                continue

            for pattern in self.HEADER_PATTERNS:
                if re.match(pattern, line, re.MULTILINE | re.IGNORECASE):
                    headers.append({
                        'line': line_num,
                        'text': line,
                        'pattern': pattern,
                    })
                    break

        return headers

    def _detect_tables(self, text: str) -> List[DetectedTable]:
        """Detect and parse tables in text"""
        tables = []

        # Look for pipe-delimited tables
        pipe_table_pattern = r'(\|[^\n]+\|\n?)+'
        for match in re.finditer(pipe_table_pattern, text):
            table_text = match.group()
            rows = [r.strip() for r in table_text.strip().split('\n') if r.strip()]

            if len(rows) >= 2:  # At least header + 1 row
                # Count columns
                col_count = len(rows[0].split('|')) - 2  # Subtract outer pipes

                # Format for embedding
                formatted = self._format_table(rows)

                tables.append(DetectedTable(
                    start_pos=match.start(),
                    end_pos=match.end(),
                    raw_text=table_text,
                    formatted_text=formatted,
                    row_count=len(rows),
                    column_count=max(col_count, 1),
                ))

        return tables

    def _detect_lists(self, text: str) -> List[Dict[str, Any]]:
        """Detect lists in text"""
        lists = []
        current_list = None

        for line_num, line in enumerate(text.split('\n')):
            is_list_item = False

            for pattern in self.LIST_PATTERNS:
                if re.match(pattern, line):
                    is_list_item = True
                    break

            if is_list_item:
                if current_list is None:
                    current_list = {'start': line_num, 'items': []}
                current_list['items'].append(line.strip())
            else:
                if current_list is not None and len(current_list['items']) >= 2:
                    lists.append(current_list)
                current_list = None

        # Don't forget last list
        if current_list is not None and len(current_list['items']) >= 2:
            lists.append(current_list)

        return lists

    def _detect_issues(self, text: str) -> tuple:
        """Detect quality issues in text"""
        issues = []
        details = {}

        # Check for OCR errors
        ocr_errors = []
        for pattern, error_type in self.OCR_ERROR_PATTERNS:
            matches = re.findall(pattern, text)
            if matches:
                ocr_errors.append({
                    'type': error_type,
                    'count': len(matches),
                })

        if ocr_errors:
            issues.append(ContentIssue.OCR_ERRORS)
            details['ocr_errors'] = ocr_errors

        # Check whitespace issues
        whitespace_ratio = sum(1 for c in text if c.isspace()) / len(text) if text else 0

        if whitespace_ratio > 0.5:
            issues.append(ContentIssue.EXCESSIVE_WHITESPACE)
            details['whitespace_ratio'] = whitespace_ratio
        elif whitespace_ratio < 0.1:
            issues.append(ContentIssue.MISSING_WHITESPACE)
            details['whitespace_ratio'] = whitespace_ratio

        # Check for garbled text (high special character ratio)
        special_chars = sum(1 for c in text if not c.isalnum() and not c.isspace())
        special_ratio = special_chars / len(text) if text else 0

        if special_ratio > 0.3:
            issues.append(ContentIssue.GARBLED_TEXT)
            details['special_char_ratio'] = special_ratio

        # Check for encoding issues
        encoding_issues = re.findall(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]|ÃƒÂ|Ã‚Â', text)
        if encoding_issues:
            issues.append(ContentIssue.ENCODING_ISSUES)
            details['encoding_issues_count'] = len(encoding_issues)

        return issues, details

    def _calculate_confidence(self, text: str, issues: List[ContentIssue]) -> float:
        """Calculate extraction confidence based on content quality"""
        if not text:
            return 0.0

        confidence = 1.0

        # Penalize for issues
        issue_penalties = {
            ContentIssue.OCR_ERRORS: 0.15,
            ContentIssue.BROKEN_TABLES: 0.1,
            ContentIssue.MISSING_WHITESPACE: 0.2,
            ContentIssue.EXCESSIVE_WHITESPACE: 0.1,
            ContentIssue.GARBLED_TEXT: 0.3,
            ContentIssue.TRUNCATED: 0.4,
            ContentIssue.ENCODING_ISSUES: 0.15,
        }

        for issue in issues:
            confidence -= issue_penalties.get(issue, 0.1)

        # Check text length (very short might indicate truncation)
        if len(text.split()) < 50:
            confidence *= 0.8

        return max(min(confidence, 1.0), 0.0)

    def _assess_quality(self, confidence: float, issues: List[ContentIssue]) -> DocumentQuality:
        """Assess overall document quality"""
        if confidence >= 0.85 and len(issues) == 0:
            return DocumentQuality.HIGH
        elif confidence >= 0.6:
            return DocumentQuality.MEDIUM
        elif confidence > 0:
            return DocumentQuality.LOW
        else:
            return DocumentQuality.FAILED

    def _clean_text(self, text: str, issues: List[ContentIssue]) -> tuple:
        """Clean text based on detected issues"""
        cleaned = text
        suggestions = []

        # Fix encoding issues
        if ContentIssue.ENCODING_ISSUES in issues:
            # Remove control characters
            cleaned = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', cleaned)
            # Fix common mojibake patterns
            cleaned = cleaned.replace('ÃƒÂ', 'Á').replace('Ã‚Â', 'Â')
            suggestions.append("Removed control characters and fixed encoding")

        # Fix whitespace issues
        if ContentIssue.EXCESSIVE_WHITESPACE in issues:
            # Collapse multiple spaces
            cleaned = re.sub(r' {2,}', ' ', cleaned)
            # Collapse multiple newlines
            cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
            suggestions.append("Normalized excessive whitespace")

        if ContentIssue.MISSING_WHITESPACE in issues:
            # Add space after periods if missing
            cleaned = re.sub(r'\.([A-Z])', r'. \1', cleaned)
            suggestions.append("Added missing whitespace after sentences")

        # Clean general whitespace if enabled
        if self.clean_whitespace:
            # Strip trailing whitespace from lines
            cleaned = '\n'.join(line.rstrip() for line in cleaned.split('\n'))

        return cleaned, suggestions

    def _format_table(self, rows: List[str]) -> str:
        """Format table rows for embedding"""
        formatted_lines = []

        for row in rows:
            # Skip separator rows
            if re.match(r'^[\|\s\-:]+$', row):
                continue

            # Clean up cells
            cells = [c.strip() for c in row.split('|') if c.strip()]
            formatted_lines.append(' | '.join(cells))

        return '\n'.join(formatted_lines)

    def get_chunking_hints(self, analysis: DocumentAnalysis) -> Dict[str, Any]:
        """
        Get hints for semantic chunking based on document analysis.

        Returns suggestions for chunk boundaries, sizes, and special handling.
        """
        hints = {
            'suggested_chunk_size': 512,
            'preserve_tables': analysis.has_tables,
            'preserve_headers': analysis.has_headers,
            'split_on_headers': analysis.header_count > 3,
            'table_positions': [(t.start_pos, t.end_pos) for t in analysis.tables],
        }

        # Adjust chunk size based on content type
        if analysis.avg_words_per_line < 10:
            # Likely formatted/structured content
            hints['suggested_chunk_size'] = 256
        elif analysis.avg_words_per_line > 30:
            # Dense prose
            hints['suggested_chunk_size'] = 768

        return hints


# Global instance with default settings
document_intelligence = DocumentIntelligence()
