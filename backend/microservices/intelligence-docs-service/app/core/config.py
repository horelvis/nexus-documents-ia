import os

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Provider order (comma-separated, parsed from env string)
    # Extraction: docling (structured docs) → glm-ocr (scanned/images) → tika (legacy fallback)
    extraction_providers: str = "docling,glm-ocr"
    embedding_providers: str = "sentence-transformers"
    entity_providers: str = os.getenv("ENTITY_PROVIDERS", "langextract")

    # Embedding
    embedding_model: str = "BAAI/bge-m3"
    embedding_dimensions: int = 1024
    embedding_device: str = "cuda"
    embedding_task_query: str = "retrieval.query"
    embedding_task_passage: str = "retrieval.passage"

    # Extraction backends
    docling_url: str = "http://docling:5001"
    tika_url: str = "http://tika:9998"

    # GLM-OCR (VLM-based OCR for scanned docs and images, 0.9B params)
    # Served via SGLang dev (concurrent requests, RadixAttention)
    glm_ocr_url: str = "http://glm-ocr:8000/v1"
    glm_ocr_model: str = "zai-org/GLM-OCR"

    # LLM for NER (SGLang — OpenAI-compatible)
    sglang_base_url: str = os.getenv("SGLANG_BASE_URL", os.getenv("VLLM_BASE_URL", "http://sglang:8000/v1"))
    sglang_model: str = os.getenv("SGLANG_MODEL", os.getenv("VLLM_MODEL", ""))

    # LangExtract (few-shot entity extraction with source grounding)
    langextract_enabled: bool = True
    langextract_extraction_passes: int = 1
    langextract_max_char_buffer: int = 10000
    langextract_confidence_threshold: float = 0.7

    # Identity document extraction (doctr OCR — lazy-loaded)
    id_document_enabled: bool = True

    # Timeouts (seconds)
    extraction_timeout: int = 600
    embedding_timeout: int = 30
    ner_timeout: int = 60

    # Cloud providers (opt-in)
    mistral_api_key: str = ""
    google_embedding_api_key: str = ""
    openai_api_key: str = ""

    @property
    def extraction_provider_list(self) -> list[str]:
        return [p.strip() for p in self.extraction_providers.split(",")]

    @property
    def embedding_provider_list(self) -> list[str]:
        return [p.strip() for p in self.embedding_providers.split(",")]

    @property
    def entity_provider_list(self) -> list[str]:
        return [p.strip() for p in self.entity_providers.split(",")]

    class Config:
        env_file = ".env"


settings = Settings()
