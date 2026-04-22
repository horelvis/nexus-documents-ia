from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ExtractionResult:
    text: str
    language: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    quality_score: float = 0.0


@dataclass
class Entity:
    type: str        # PERSON, DNI, NIE, CIF, DATE, ORGANIZATION, AMOUNT, LOCATION, IDENTIFIER
    value: str
    provider: str
    confidence: float = 1.0
    start_pos: Optional[int] = None
    end_pos: Optional[int] = None
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class ClassificationResult:
    document_type: str
    confidence: float
    provider: str = ""


class ExtractionProvider(ABC):
    name: str

    @abstractmethod
    async def extract(self, file_bytes: bytes, filename: str, **options) -> ExtractionResult:
        ...

    @abstractmethod
    async def extract_from_url(self, url: str, filename: str, **options) -> ExtractionResult:
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        ...


class EmbeddingProvider(ABC):
    name: str

    @abstractmethod
    async def embed(self, texts: list[str], task: str = "") -> list[list[float]]:
        ...

    @abstractmethod
    async def embed_single(self, text: str, task: str = "") -> list[float]:
        ...

    @abstractmethod
    def dimensions(self) -> int:
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        ...


class EntityProvider(ABC):
    name: str

    @abstractmethod
    async def extract_entities(self, text: str, language: str = "es") -> list[Entity]:
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        ...
