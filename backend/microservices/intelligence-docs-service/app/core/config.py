from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Provider order (comma-separated, parsed from env string)
    # Extraction: docling (structured docs) → glm-ocr (scanned/images) → tika (legacy fallback)
    extraction_providers: str = "docling,glm-ocr"
    embedding_providers: str = "sentence-transformers"
    entity_providers: str = "regex,vllm"

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
    glm_ocr_url: str = "http://glm-ocr:8000/v1"
    glm_ocr_model: str = "zai-org/GLM-OCR"

    # LLM for NER
    vllm_base_url: str = "http://vllm:8000/v1"
    vllm_model: str = ""

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
