"""
Identity Document Extraction Service

Extracts structured data from identity documents:
- DNI (Spanish National ID)
- NIE (Foreign Resident ID in Spain)
- Passport
- Driver's License

Uses:
- doctr for text zone detection and OCR
- MRZ parser for machine readable zones
- Regex patterns for Spanish document formats
- LangExtract for fallback structured extraction

GDPR Compliance:
- No cloud APIs used (privacy by design)
- All processing done locally
- Designed for on-premise deployment
"""

import asyncio
import io
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image

logger = logging.getLogger(__name__)

# Lazy imports for optional dependencies
_doctr_model = None
_mrz_available = False


class IdentityDocumentType(str, Enum):
    """Types of identity documents supported"""
    DNI = "dni"
    NIE = "nie"
    PASSPORT = "passport"
    DRIVER_LICENSE = "driver_license"
    RESIDENCE_CARD = "residence_card"
    UNKNOWN = "unknown"


@dataclass
class ExtractedField:
    """A single extracted field with confidence"""
    value: Optional[str]
    confidence: float
    source: str = "ocr"  # ocr, mrz, pattern_match


@dataclass
class IdentityExtractionResult:
    """Result of identity document extraction"""
    # Classification
    document_type: IdentityDocumentType
    issuing_country: Optional[str] = None

    # Personal data
    full_name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    second_last_name: Optional[str] = None
    document_number: Optional[str] = None
    date_of_birth: Optional[date] = None
    expiration_date: Optional[date] = None
    issue_date: Optional[date] = None
    nationality: Optional[str] = None
    gender: Optional[str] = None  # M, F, X
    place_of_birth: Optional[str] = None

    # MRZ data
    mrz_lines: List[str] = field(default_factory=list)
    mrz_checksum_valid: bool = False

    # Driver's license specific
    license_categories: List[str] = field(default_factory=list)

    # Metadata
    confidence_score: float = 0.0
    field_confidences: Dict[str, float] = field(default_factory=dict)
    ocr_engine: str = "doctr"
    processing_time_ms: float = 0.0

    # Validation
    is_valid: bool = False
    validation_errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "document_type": self.document_type.value,
            "issuing_country": self.issuing_country,
            "full_name": self.full_name,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "second_last_name": self.second_last_name,
            "document_number": self.document_number,
            "date_of_birth": self.date_of_birth.isoformat() if self.date_of_birth else None,
            "expiration_date": self.expiration_date.isoformat() if self.expiration_date else None,
            "issue_date": self.issue_date.isoformat() if self.issue_date else None,
            "nationality": self.nationality,
            "gender": self.gender,
            "place_of_birth": self.place_of_birth,
            "mrz_data": {
                "lines": self.mrz_lines,
                "checksum_valid": self.mrz_checksum_valid,
            } if self.mrz_lines else None,
            "license_categories": self.license_categories or None,
            "confidence_score": self.confidence_score,
            "field_confidences": self.field_confidences,
            "ocr_engine": self.ocr_engine,
            "processing_time_ms": self.processing_time_ms,
            "is_valid": self.is_valid,
            "validation_errors": self.validation_errors,
            "warnings": self.warnings,
        }


def _get_doctr_model():
    """Get or initialize doctr OCR model (lazy loading)"""
    global _doctr_model

    if _doctr_model is None:
        try:
            from doctr.io import DocumentFile
            from doctr.models import ocr_predictor

            # Load a fast, accurate model
            _doctr_model = ocr_predictor(
                det_arch='db_resnet50',
                reco_arch='crnn_vgg16_bn',
                pretrained=True,
            )
            logger.info("doctr OCR model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load doctr model: {e}")
            raise

    return _doctr_model


def _check_mrz_available():
    """Check if MRZ parsing is available"""
    global _mrz_available
    try:
        import mrz
        _mrz_available = True
    except ImportError:
        _mrz_available = False
    return _mrz_available


class IDDocumentService:
    """
    Service for extracting data from identity documents.

    Privacy-first design:
    - All processing done locally (no cloud APIs)
    - Uses doctr (open source) for OCR
    - Pattern matching for Spanish documents
    - MRZ parsing for passports/travel documents
    """

    # Spanish DNI patterns
    DNI_PATTERNS = {
        "document_number": r"\b(\d{8}[A-Z])\b",
        "dni_header": r"(?i)(documento\s+nacional|dni|d\.n\.i\.)",
        "validity": r"(?i)v[aá]lid[oa]\s+hasta|validez",
    }

    # Spanish NIE patterns
    NIE_PATTERNS = {
        "document_number": r"\b([XYZ]\d{7}[A-Z])\b",
        "nie_header": r"(?i)(n[uú]mero.*identidad.*extranjero|nie|n\.i\.e\.)",
    }

    # Passport patterns
    PASSPORT_PATTERNS = {
        "document_number": r"\b([A-Z]{2}\d{6,7})\b",  # Spanish passport format
        "passport_header": r"(?i)(pasaporte|passport)",
        "mrz_line": r"^[A-Z0-9<]{30,44}$",
    }

    # Driver's license patterns
    LICENSE_PATTERNS = {
        "document_number": r"\b(\d{8}[A-Z])\b",  # Same as DNI for Spanish licenses
        "license_header": r"(?i)(permiso.*conducci[oó]n|carnet.*conducir|driving\s+licen[cs]e)",
        "categories": r"\b([AB][12]?|[CDEM]|AM|A1|A2|B1|BE|C1|CE|D1|DE)\b",
    }

    # Date patterns (DD/MM/YYYY or DD-MM-YYYY)
    DATE_PATTERNS = [
        r"(\d{2})[/\-\.](\d{2})[/\-\.](\d{4})",
        r"(\d{2})[/\-\.](\d{2})[/\-\.](\d{2})",
    ]

    # Spanish name patterns
    NAME_PATTERNS = {
        "apellidos": r"(?i)apellidos?[:.\s]+([A-Z\sÁÉÍÓÚÑÜ]+)",
        "nombre": r"(?i)nombre[:.\s]+([A-Z\sÁÉÍÓÚÑÜ]+)",
    }

    def __init__(
        self,
        min_confidence: float = 0.5,
        validate_checksums: bool = True,
    ):
        """
        Initialize ID document service.

        Args:
            min_confidence: Minimum OCR confidence threshold
            validate_checksums: Whether to validate MRZ/document checksums
        """
        self.min_confidence = min_confidence
        self.validate_checksums = validate_checksums

    async def extract_identity_document(
        self,
        file_bytes: bytes,
        document_type: Optional[IdentityDocumentType] = None,
    ) -> IdentityExtractionResult:
        """
        Extract data from an identity document.

        Args:
            file_bytes: Image or PDF of the identity document
            document_type: Expected document type (auto-detected if not provided)

        Returns:
            IdentityExtractionResult with extracted data
        """
        start_time = time.time()
        warnings = []
        errors = []

        try:
            # Step 1: OCR the document
            ocr_text, ocr_confidences = await self._perform_ocr(file_bytes)

            if not ocr_text.strip():
                return IdentityExtractionResult(
                    document_type=document_type or IdentityDocumentType.UNKNOWN,
                    confidence_score=0.0,
                    processing_time_ms=(time.time() - start_time) * 1000,
                    validation_errors=["No text could be extracted from document"],
                )

            # Step 2: Detect document type if not provided
            detected_type = document_type or self._detect_document_type(ocr_text)

            # Step 3: Extract fields based on document type
            if detected_type == IdentityDocumentType.DNI:
                result = await self._extract_dni(ocr_text, ocr_confidences)
            elif detected_type == IdentityDocumentType.NIE:
                result = await self._extract_nie(ocr_text, ocr_confidences)
            elif detected_type == IdentityDocumentType.PASSPORT:
                result = await self._extract_passport(ocr_text, ocr_confidences)
            elif detected_type == IdentityDocumentType.DRIVER_LICENSE:
                result = await self._extract_driver_license(ocr_text, ocr_confidences)
            else:
                result = await self._extract_generic(ocr_text, ocr_confidences)
                result.document_type = IdentityDocumentType.UNKNOWN

            # Step 4: Try MRZ extraction if present
            mrz_result = await self._extract_mrz(ocr_text)
            if mrz_result:
                self._merge_mrz_data(result, mrz_result)

            # Step 5: Validate extracted data
            result.is_valid, validation_errors = self._validate_extraction(result)
            result.validation_errors = validation_errors

            # Step 6: Calculate overall confidence
            result.confidence_score = self._calculate_confidence(result)
            result.warnings = warnings
            result.processing_time_ms = (time.time() - start_time) * 1000

            return result

        except Exception as e:
            logger.error(f"Identity document extraction failed: {e}")
            return IdentityExtractionResult(
                document_type=document_type or IdentityDocumentType.UNKNOWN,
                confidence_score=0.0,
                processing_time_ms=(time.time() - start_time) * 1000,
                validation_errors=[f"Extraction failed: {str(e)}"],
            )

    async def _perform_ocr(
        self,
        file_bytes: bytes,
    ) -> Tuple[str, Dict[str, float]]:
        """Perform OCR on the document image"""
        try:
            from doctr.io import DocumentFile

            model = _get_doctr_model()

            # Load document
            if file_bytes[:4] == b'%PDF':
                doc = DocumentFile.from_pdf(io.BytesIO(file_bytes))
            else:
                doc = DocumentFile.from_images(io.BytesIO(file_bytes))

            # Run OCR
            result = await asyncio.to_thread(model, doc)

            # Extract text and confidences
            full_text = []
            confidences = {}

            for page in result.pages:
                page_text = []
                for block in page.blocks:
                    for line in block.lines:
                        line_text = " ".join(word.value for word in line.words)
                        page_text.append(line_text)

                        # Track word confidences
                        for word in line.words:
                            confidences[word.value] = word.confidence

                full_text.append("\n".join(page_text))

            return "\n\n".join(full_text), confidences

        except Exception as e:
            logger.error(f"OCR failed: {e}")
            raise

    def _detect_document_type(self, text: str) -> IdentityDocumentType:
        """Detect the type of identity document from OCR text"""
        text_upper = text.upper()

        # Check for DNI indicators
        if re.search(self.DNI_PATTERNS["dni_header"], text, re.IGNORECASE):
            if re.search(self.DNI_PATTERNS["document_number"], text_upper):
                return IdentityDocumentType.DNI

        # Check for NIE indicators
        if re.search(self.NIE_PATTERNS["nie_header"], text, re.IGNORECASE):
            if re.search(self.NIE_PATTERNS["document_number"], text_upper):
                return IdentityDocumentType.NIE

        # Check for passport indicators
        if re.search(self.PASSPORT_PATTERNS["passport_header"], text, re.IGNORECASE):
            return IdentityDocumentType.PASSPORT

        # Check for driver's license indicators
        if re.search(self.LICENSE_PATTERNS["license_header"], text, re.IGNORECASE):
            return IdentityDocumentType.DRIVER_LICENSE

        # Check document number patterns as fallback
        if re.search(self.NIE_PATTERNS["document_number"], text_upper):
            return IdentityDocumentType.NIE
        if re.search(self.DNI_PATTERNS["document_number"], text_upper):
            return IdentityDocumentType.DNI

        return IdentityDocumentType.UNKNOWN

    async def _extract_dni(
        self,
        text: str,
        confidences: Dict[str, float],
    ) -> IdentityExtractionResult:
        """Extract data from Spanish DNI"""
        result = IdentityExtractionResult(
            document_type=IdentityDocumentType.DNI,
            issuing_country="ESP",
        )

        # Extract document number
        match = re.search(self.DNI_PATTERNS["document_number"], text.upper())
        if match:
            result.document_number = match.group(1)
            result.field_confidences["document_number"] = confidences.get(match.group(1), 0.8)

        # Extract names
        result = self._extract_spanish_names(text, result, confidences)

        # Extract dates
        result = self._extract_dates(text, result, confidences)

        # Extract gender
        if "SEXO M" in text.upper() or " M " in text.upper():
            result.gender = "M"
        elif "SEXO F" in text.upper() or " F " in text.upper():
            result.gender = "F"

        return result

    async def _extract_nie(
        self,
        text: str,
        confidences: Dict[str, float],
    ) -> IdentityExtractionResult:
        """Extract data from Spanish NIE"""
        result = IdentityExtractionResult(
            document_type=IdentityDocumentType.NIE,
            issuing_country="ESP",
        )

        # Extract document number (starts with X, Y, or Z)
        match = re.search(self.NIE_PATTERNS["document_number"], text.upper())
        if match:
            result.document_number = match.group(1)
            result.field_confidences["document_number"] = confidences.get(match.group(1), 0.8)

        # Extract names (same as DNI)
        result = self._extract_spanish_names(text, result, confidences)

        # Extract dates
        result = self._extract_dates(text, result, confidences)

        # Extract nationality
        nationality_match = re.search(r"(?i)nacionalidad[:.\s]+([A-Z]{2,})", text)
        if nationality_match:
            result.nationality = nationality_match.group(1).upper()

        return result

    async def _extract_passport(
        self,
        text: str,
        confidences: Dict[str, float],
    ) -> IdentityExtractionResult:
        """Extract data from passport"""
        result = IdentityExtractionResult(
            document_type=IdentityDocumentType.PASSPORT,
        )

        # Extract document number
        match = re.search(self.PASSPORT_PATTERNS["document_number"], text.upper())
        if match:
            result.document_number = match.group(1)
            result.field_confidences["document_number"] = confidences.get(match.group(1), 0.8)

        # Extract names
        result = self._extract_spanish_names(text, result, confidences)

        # Extract dates
        result = self._extract_dates(text, result, confidences)

        # MRZ will be handled separately

        return result

    async def _extract_driver_license(
        self,
        text: str,
        confidences: Dict[str, float],
    ) -> IdentityExtractionResult:
        """Extract data from driver's license"""
        result = IdentityExtractionResult(
            document_type=IdentityDocumentType.DRIVER_LICENSE,
            issuing_country="ESP",
        )

        # Extract document number (same as DNI for Spanish licenses)
        match = re.search(self.LICENSE_PATTERNS["document_number"], text.upper())
        if match:
            result.document_number = match.group(1)
            result.field_confidences["document_number"] = confidences.get(match.group(1), 0.8)

        # Extract names
        result = self._extract_spanish_names(text, result, confidences)

        # Extract dates
        result = self._extract_dates(text, result, confidences)

        # Extract license categories
        categories = re.findall(self.LICENSE_PATTERNS["categories"], text.upper())
        result.license_categories = list(set(categories))

        return result

    async def _extract_generic(
        self,
        text: str,
        confidences: Dict[str, float],
    ) -> IdentityExtractionResult:
        """Generic extraction for unknown document types"""
        result = IdentityExtractionResult(
            document_type=IdentityDocumentType.UNKNOWN,
        )

        # Try to extract any document number pattern
        for pattern in [
            self.DNI_PATTERNS["document_number"],
            self.NIE_PATTERNS["document_number"],
            self.PASSPORT_PATTERNS["document_number"],
        ]:
            match = re.search(pattern, text.upper())
            if match:
                result.document_number = match.group(1)
                break

        # Extract names and dates
        result = self._extract_spanish_names(text, result, confidences)
        result = self._extract_dates(text, result, confidences)

        return result

    def _extract_spanish_names(
        self,
        text: str,
        result: IdentityExtractionResult,
        confidences: Dict[str, float],
    ) -> IdentityExtractionResult:
        """Extract Spanish-style names (apellidos + nombre)"""
        # Try apellidos pattern
        apellidos_match = re.search(self.NAME_PATTERNS["apellidos"], text)
        if apellidos_match:
            apellidos = apellidos_match.group(1).strip()
            parts = apellidos.split()
            if len(parts) >= 2:
                result.last_name = parts[0]
                result.second_last_name = " ".join(parts[1:])
            elif len(parts) == 1:
                result.last_name = parts[0]

        # Try nombre pattern
        nombre_match = re.search(self.NAME_PATTERNS["nombre"], text)
        if nombre_match:
            result.first_name = nombre_match.group(1).strip()

        # Build full name
        name_parts = [
            result.last_name,
            result.second_last_name,
            result.first_name,
        ]
        result.full_name = " ".join(p for p in name_parts if p)

        return result

    def _extract_dates(
        self,
        text: str,
        result: IdentityExtractionResult,
        confidences: Dict[str, float],
    ) -> IdentityExtractionResult:
        """Extract dates from text"""
        dates_found = []

        for pattern in self.DATE_PATTERNS:
            matches = re.findall(pattern, text)
            for match in matches:
                try:
                    day, month, year = match
                    if len(year) == 2:
                        year = "20" + year if int(year) < 50 else "19" + year
                    parsed_date = date(int(year), int(month), int(day))
                    dates_found.append(parsed_date)
                except (ValueError, IndexError):
                    continue

        # Assign dates based on context
        if dates_found:
            dates_found.sort()

            # Look for context clues
            text_lower = text.lower()

            for d in dates_found:
                # Dates in the past are likely birth dates
                if d.year < 2000 and not result.date_of_birth:
                    result.date_of_birth = d
                # Dates in the future are likely expiration dates
                elif d > date.today() and not result.expiration_date:
                    result.expiration_date = d
                # Recent past dates might be issue dates
                elif d <= date.today() and d.year >= 2000 and not result.issue_date:
                    result.issue_date = d

        return result

    async def _extract_mrz(self, text: str) -> Optional[Dict[str, Any]]:
        """Extract and parse MRZ (Machine Readable Zone)"""
        if not _check_mrz_available():
            return None

        try:
            import mrz
            from mrz.checker.td1 import TD1CodeChecker
            from mrz.checker.td2 import TD2CodeChecker
            from mrz.checker.td3 import TD3CodeChecker

            # Find MRZ lines
            lines = text.split("\n")
            mrz_lines = []

            for line in lines:
                cleaned = line.strip().replace(" ", "")
                if re.match(self.PASSPORT_PATTERNS["mrz_line"], cleaned):
                    mrz_lines.append(cleaned)

            if len(mrz_lines) < 2:
                return None

            # Try different MRZ formats
            mrz_text = "\n".join(mrz_lines)

            # Try TD3 (passport) format
            if len(mrz_lines) == 2 and len(mrz_lines[0]) >= 44:
                checker = TD3CodeChecker(mrz_text)
                if checker.all_hashes:
                    return {
                        "full_name": checker.fields.name + " " + checker.fields.surname,
                        "document_number": checker.fields.document_number,
                        "nationality": checker.fields.nationality,
                        "date_of_birth": self._parse_mrz_date(checker.fields.birth_date),
                        "expiration_date": self._parse_mrz_date(checker.fields.expiry_date),
                        "gender": checker.fields.sex,
                        "checksum_valid": checker.all_hashes,
                        "mrz_lines": mrz_lines,
                    }

            # Try TD1 (ID card) format
            if len(mrz_lines) == 3:
                checker = TD1CodeChecker(mrz_text)
                if checker.all_hashes:
                    return {
                        "full_name": checker.fields.name + " " + checker.fields.surname,
                        "document_number": checker.fields.document_number,
                        "nationality": checker.fields.nationality,
                        "date_of_birth": self._parse_mrz_date(checker.fields.birth_date),
                        "expiration_date": self._parse_mrz_date(checker.fields.expiry_date),
                        "gender": checker.fields.sex,
                        "checksum_valid": checker.all_hashes,
                        "mrz_lines": mrz_lines,
                    }

        except Exception as e:
            logger.warning(f"MRZ parsing failed: {e}")

        return None

    def _parse_mrz_date(self, date_str: str) -> Optional[date]:
        """Parse MRZ date format (YYMMDD)"""
        try:
            year = int(date_str[:2])
            month = int(date_str[2:4])
            day = int(date_str[4:6])

            # MRZ uses 2-digit years
            if year > 50:
                year = 1900 + year
            else:
                year = 2000 + year

            return date(year, month, day)
        except (ValueError, IndexError):
            return None

    def _merge_mrz_data(
        self,
        result: IdentityExtractionResult,
        mrz_data: Dict[str, Any],
    ):
        """Merge MRZ data with OCR results (MRZ is more reliable)"""
        if mrz_data.get("document_number"):
            result.document_number = mrz_data["document_number"]
            result.field_confidences["document_number"] = 0.95

        if mrz_data.get("full_name"):
            result.full_name = mrz_data["full_name"]
            result.field_confidences["full_name"] = 0.95

        if mrz_data.get("nationality"):
            result.nationality = mrz_data["nationality"]

        if mrz_data.get("date_of_birth"):
            result.date_of_birth = mrz_data["date_of_birth"]
            result.field_confidences["date_of_birth"] = 0.95

        if mrz_data.get("expiration_date"):
            result.expiration_date = mrz_data["expiration_date"]
            result.field_confidences["expiration_date"] = 0.95

        if mrz_data.get("gender"):
            result.gender = mrz_data["gender"]

        result.mrz_lines = mrz_data.get("mrz_lines", [])
        result.mrz_checksum_valid = mrz_data.get("checksum_valid", False)

    def _validate_extraction(
        self,
        result: IdentityExtractionResult,
    ) -> Tuple[bool, List[str]]:
        """Validate extracted data"""
        errors = []

        # Validate document number
        if result.document_number:
            if result.document_type == IdentityDocumentType.DNI:
                if not self._validate_dni_number(result.document_number):
                    errors.append("Invalid DNI checksum")
            elif result.document_type == IdentityDocumentType.NIE:
                if not self._validate_nie_number(result.document_number):
                    errors.append("Invalid NIE checksum")
        else:
            errors.append("Document number not found")

        # Validate dates
        if result.expiration_date and result.expiration_date < date.today():
            result.warnings.append("Document has expired")

        if result.date_of_birth:
            age = (date.today() - result.date_of_birth).days // 365
            if age < 0 or age > 150:
                errors.append("Invalid date of birth")

        return len(errors) == 0, errors

    def _validate_dni_number(self, dni: str) -> bool:
        """Validate Spanish DNI number (8 digits + letter)"""
        if not dni or len(dni) != 9:
            return False

        try:
            number = int(dni[:8])
            letter = dni[8].upper()
            letters = "TRWAGMYFPDXBNJZSQVHLCKE"
            expected = letters[number % 23]
            return letter == expected
        except (ValueError, IndexError):
            return False

    def _validate_nie_number(self, nie: str) -> bool:
        """Validate Spanish NIE number (X/Y/Z + 7 digits + letter)"""
        if not nie or len(nie) != 9:
            return False

        try:
            prefix_map = {"X": "0", "Y": "1", "Z": "2"}
            prefix = nie[0].upper()
            if prefix not in prefix_map:
                return False

            number = int(prefix_map[prefix] + nie[1:8])
            letter = nie[8].upper()
            letters = "TRWAGMYFPDXBNJZSQVHLCKE"
            expected = letters[number % 23]
            return letter == expected
        except (ValueError, IndexError):
            return False

    def _calculate_confidence(self, result: IdentityExtractionResult) -> float:
        """Calculate overall confidence score"""
        if not result.field_confidences:
            return 0.3

        # Weight important fields higher
        weights = {
            "document_number": 3.0,
            "full_name": 2.0,
            "date_of_birth": 1.5,
            "expiration_date": 1.0,
        }

        total_weight = 0.0
        weighted_sum = 0.0

        for field, conf in result.field_confidences.items():
            weight = weights.get(field, 1.0)
            weighted_sum += conf * weight
            total_weight += weight

        # Add bonus for MRZ validation
        if result.mrz_checksum_valid:
            weighted_sum += 0.2 * total_weight

        # Penalty for validation errors
        penalty = len(result.validation_errors) * 0.1

        confidence = (weighted_sum / total_weight) - penalty if total_weight > 0 else 0.0
        return max(0.0, min(1.0, confidence))


# Global instance
id_document_service = IDDocumentService()
