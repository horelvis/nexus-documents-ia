import time
import logging
from typing import Optional

from app.providers.registry import ProviderRegistry
from app.providers.base import ExtractionProvider, EmbeddingProvider, EntityProvider
from app.pipeline.quality import compute_quality_score
from app.pipeline.language import detect_language
from app.schemas.models import ProcessOptions, ProcessResponse, EntityResponse

logger = logging.getLogger(__name__)


async def process_document(
    file_bytes: Optional[bytes],
    url: Optional[str],
    filename: str,
    options: ProcessOptions,
    extraction_registry: ProviderRegistry[ExtractionProvider],
    embedding_registry: ProviderRegistry[EmbeddingProvider],
    entity_registry: ProviderRegistry[EntityProvider],
) -> ProcessResponse:
    start = time.monotonic()

    text = ""
    metadata: dict = {}
    vector: Optional[list[float]] = None
    entities: list[EntityResponse] = []

    # Step 1: Extract text
    if options.extract:
        try:
            provider = await extraction_registry.get_available()
            if file_bytes:
                result = await provider.extract(file_bytes, filename)
            elif url:
                result = await provider.extract_from_url(url, filename)
            else:
                raise ValueError("No file or URL provided")

            text = result.text
            metadata = result.metadata
            metadata["quality_score"] = compute_quality_score(text)
        except RuntimeError as e:
            logger.error(f"No extraction provider available: {e}")
            metadata["extraction_error"] = str(e)

    # Detect language
    language = options.language or detect_language(text)

    # Step 2: Embed full text
    if options.embed and text:
        try:
            provider = await embedding_registry.get_available()
            vector = await provider.embed_single(text, task=options.embedding_task)
            metadata["embedding_provider"] = provider.name
            metadata["embedding_model"] = getattr(provider, "_model_name", "unknown")
            metadata["embedding_dimensions"] = provider.dimensions()
        except Exception as e:
            logger.error(f"Embedding failed: {e}")
            metadata["embedding_error"] = str(e)

    # Step 3: Extract entities
    if options.entities and text:
        for provider in entity_registry.all():
            try:
                if await provider.is_available():
                    result = await provider.extract_entities(text, language)
                    entities.extend([
                        EntityResponse(
                            type=e.type, value=e.value,
                            provider=e.provider, confidence=e.confidence,
                        )
                        for e in result
                    ])
            except Exception as e:
                logger.warning(f"Entity provider {provider.name} failed: {e}")

    elapsed_ms = int((time.monotonic() - start) * 1000)

    return ProcessResponse(
        text=text,
        language=language,
        metadata=metadata,
        vector=vector,
        entities=entities,
        processing_time_ms=elapsed_ms,
    )
