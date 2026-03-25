"""
Spanish ID Validator — post-extraction guardrail.

Validates DNI/NIE/CIF entities extracted by LangExtract and scans the
source text for IDs the LLM may have missed. Runs after entity extraction,
not as an EntityProvider.

Roles:
  1. Validate checksums of DNI/NIE extracted by LangExtract
  2. Scan text with regex for DNI/NIE/CIF the LLM omitted
  3. Enrich validated entities with high confidence (0.95)
"""
import re
from app.providers.base import Entity

DNI_PATTERN = re.compile(r"\b(\d{8}[A-Za-z])\b")
NIE_PATTERN = re.compile(r"\b([XYZxyz]\d{7}[A-Za-z])\b")
CIF_PATTERN = re.compile(r"\b([A-Ha-h]\d{8})\b")

DNI_LETTERS = "TRWAGMYFPDXBNJZSQVHLCKE"


def _validate_dni(number: str) -> bool:
    digits = number[:8]
    letter = number[8].upper()
    try:
        return DNI_LETTERS[int(digits) % 23] == letter
    except (ValueError, IndexError):
        return False


def _validate_nie(number: str) -> bool:
    prefix_map = {"X": "0", "Y": "1", "Z": "2"}
    first = number[0].upper()
    if first not in prefix_map:
        return False
    digits = prefix_map[first] + number[1:8]
    letter = number[8].upper()
    try:
        return DNI_LETTERS[int(digits) % 23] == letter
    except (ValueError, IndexError):
        return False


class SpanishIdValidator:
    """Post-extraction guardrail for Spanish identity document numbers."""

    def validate_and_enrich(self, entities: list[Entity], text: str) -> list[Entity]:
        """
        Validate LLM-extracted IDs and scan for missed ones.

        Args:
            entities: Entities already extracted by LangExtract (or other providers).
            text: Original document text to scan for missed IDs.

        Returns:
            Enriched entity list with validated confidence scores and any
            additional IDs found by regex scan.
        """
        # Step 1: Validate checksums of existing DNI/NIE entities
        for entity in entities:
            value = entity.value.strip().upper()
            if entity.type == "DNI" or (entity.type in ("PERSON", "IDENTIFIER") and DNI_PATTERN.match(value)):
                if _validate_dni(value):
                    entity.confidence = 0.95
                    entity.attributes["checksum_valid"] = True
                    entity.type = "DNI"
                else:
                    entity.confidence = 0.3
                    entity.attributes["checksum_valid"] = False
            elif entity.type == "NIE" or (entity.type in ("PERSON", "IDENTIFIER") and NIE_PATTERN.match(value)):
                if _validate_nie(value):
                    entity.confidence = 0.95
                    entity.attributes["checksum_valid"] = True
                    entity.type = "NIE"
                else:
                    entity.confidence = 0.3
                    entity.attributes["checksum_valid"] = False

        # Step 2: Scan text for DNI/NIE/CIF the LLM missed
        existing_values = {e.value.strip().upper() for e in entities}

        for match in DNI_PATTERN.finditer(text):
            value = match.group(1).upper()
            if value not in existing_values and _validate_dni(value):
                entities.append(Entity(
                    type="DNI", value=value, provider="regex_guardrail",
                    confidence=0.95, start_pos=match.start(), end_pos=match.end(),
                    attributes={"checksum_valid": True},
                ))
                existing_values.add(value)

        for match in NIE_PATTERN.finditer(text):
            value = match.group(1).upper()
            if value not in existing_values and _validate_nie(value):
                entities.append(Entity(
                    type="NIE", value=value, provider="regex_guardrail",
                    confidence=0.95, start_pos=match.start(), end_pos=match.end(),
                    attributes={"checksum_valid": True},
                ))
                existing_values.add(value)

        for match in CIF_PATTERN.finditer(text):
            value = match.group(1).upper()
            if value not in existing_values:
                entities.append(Entity(
                    type="CIF", value=value, provider="regex_guardrail",
                    confidence=0.90, start_pos=match.start(), end_pos=match.end(),
                ))
                existing_values.add(value)

        return entities
