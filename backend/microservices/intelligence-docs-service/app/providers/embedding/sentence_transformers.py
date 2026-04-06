import asyncio
import logging
from typing import Optional

from app.providers.base import EmbeddingProvider

logger = logging.getLogger(__name__)


class SentenceTransformersProvider(EmbeddingProvider):
    """Local embedding via sentence-transformers (BGE-M3, Jina v3, etc.)."""

    name = "sentence-transformers"

    def __init__(self, model_name: str, device: str, expected_dimensions: int):
        self._model_name = model_name
        self._device = device
        self._expected_dimensions = expected_dimensions
        self._model = None  # Lazy-loaded

    async def load_model(self) -> bool:
        """Load the model. Called once at startup."""
        if self._model is not None:
            return True
        try:
            logger.info(f"Loading embedding model: {self._model_name} on {self._device}")
            loop = asyncio.get_event_loop()

            def _load():
                import torch
                from sentence_transformers import SentenceTransformer

                device = self._device
                if device == "cuda" and not torch.cuda.is_available():
                    logger.warning("CUDA not available, falling back to CPU")
                    device = "cpu"

                model = SentenceTransformer(self._model_name, device=device)

                # Verify dimensions
                test_emb = model.encode("test", convert_to_numpy=True)
                dims = len(test_emb)
                if dims != self._expected_dimensions:
                    logger.warning(
                        f"Model dimensions {dims} != expected {self._expected_dimensions}"
                    )
                    self._expected_dimensions = dims

                logger.info(
                    f"Loaded embedding model: {self._model_name} "
                    f"({dims} dims) on {device}"
                )
                return model

            self._model = await loop.run_in_executor(None, _load)
            return True
        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}")
            self._model = None
            return False

    async def embed_single(self, text: str, task: str = "") -> list[float]:
        if self._model is None:
            raise RuntimeError("Embedding model not loaded")
        loop = asyncio.get_event_loop()

        def _encode():
            kwargs = {"convert_to_numpy": True}
            if task:
                try:
                    return self._model.encode(text, prompt_name=task, **kwargs).tolist()
                except (TypeError, ValueError, KeyError):
                    pass  # Model doesn't support this task adapter
            return self._model.encode(text, **kwargs).tolist()

        return await loop.run_in_executor(None, _encode)

    async def embed(self, texts: list[str], task: str = "") -> list[list[float]]:
        if self._model is None:
            raise RuntimeError("Embedding model not loaded")
        loop = asyncio.get_event_loop()

        def _encode_batch():
            kwargs = {"convert_to_numpy": True}
            if task:
                try:
                    return self._model.encode(texts, prompt_name=task, **kwargs).tolist()
                except (TypeError, ValueError, KeyError):
                    pass
            return self._model.encode(texts, **kwargs).tolist()

        return await loop.run_in_executor(None, _encode_batch)

    def dimensions(self) -> int:
        return self._expected_dimensions

    async def is_available(self) -> bool:
        return self._model is not None
