import re
from app.providers.base import EntityProvider, Entity

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


class RegexSpanishProvider(EntityProvider):
    """Extract Spanish identity document numbers via regex. Always available."""

    name = "regex"

    async def extract_entities(self, text: str, language: str = "es") -> list[Entity]:
        entities = []
        seen = set()

        for match in DNI_PATTERN.finditer(text):
            value = match.group(1).upper()
            if value not in seen and _validate_dni(value):
                entities.append(Entity(type="DNI", value=value, provider="regex"))
                seen.add(value)

        for match in NIE_PATTERN.finditer(text):
            value = match.group(1).upper()
            if value not in seen and _validate_nie(value):
                entities.append(Entity(type="NIE", value=value, provider="regex"))
                seen.add(value)

        for match in CIF_PATTERN.finditer(text):
            value = match.group(1).upper()
            if value not in seen:
                entities.append(Entity(type="CIF", value=value, provider="regex"))
                seen.add(value)

        return entities

    async def is_available(self) -> bool:
        return True
