"""
Folder Classification Service - RAG + LLM Contextual Classification

Uses embeddings to find similar documents and LLM to decide folder placement.
Implements the Learn-First approach:
1. Initially disabled (users organize manually)
2. System learns from user's folder organization
3. When enough examples, suggests activation
4. RAG retrieves similar docs, LLM decides with reasoning

Architecture:
- RAG: Weaviate vector search for similar classified documents
- LLM: vLLM (Qwen3-4B) for classification decision with structured output
"""

import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

import httpx
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# =============================================================================
# Response Models
# =============================================================================

class ClassificationResult(BaseModel):
    """Structured response from LLM classification."""
    carpeta: str = Field(..., description="Suggested folder path")
    confianza: float = Field(..., ge=0, le=1, description="Confidence score 0-1")
    razonamiento: str = Field(..., description="Reasoning for the decision")
    carpetas_alternativas: List[str] = Field(default_factory=list)
    es_carpeta_nueva: bool = Field(default=False)


@dataclass
class SimilarDocument:
    """Document retrieved from RAG search."""
    doc_id: str
    title: str
    folder_path: str
    content_preview: str
    similarity: float


# =============================================================================
# Classification Service
# =============================================================================

class FolderClassificationService:
    """
    Contextual document classification using RAG + LLM.

    Flow:
    1. Get document embedding (already in Weaviate)
    2. Search for K similar documents that are already classified
    3. Build prompt with examples
    4. LLM decides folder with confidence and reasoning
    """

    DEFAULT_K = 7
    DEFAULT_MIN_CONFIDENCE = 0.6
    VLLM_BASE_URL = "http://vllm:8000/v1"
    VLLM_MODEL = "Qwen/Qwen3-4B"
    WEAVIATE_SERVICE_URL = "http://weaviate-service:8000"

    def __init__(
        self,
        tenant_id: str,
        k: int = None,
        min_confidence: float = None,
        vllm_base_url: str = None,
        weaviate_url: str = None,
    ):
        self.tenant_id = tenant_id
        self.k = k or self.DEFAULT_K
        self.min_confidence = min_confidence or self.DEFAULT_MIN_CONFIDENCE
        self.vllm_base_url = vllm_base_url or self.VLLM_BASE_URL
        self.weaviate_url = weaviate_url or self.WEAVIATE_SERVICE_URL

    async def get_similar_classified_documents(
        self,
        doc_id: str,
        content: str,
    ) -> List[SimilarDocument]:
        """
        Retrieve similar documents that are already classified (not in /Sin Clasificar).

        Uses Weaviate's semantic search to find documents similar to the new one.
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                # Use Weaviate service's search endpoint
                response = await client.post(
                    f"{self.weaviate_url}/api/v1/search",
                    json={
                        "tenant_id": self.tenant_id,
                        "query": content[:2000],  # Use content as query
                        "limit": self.k * 2,  # Get extra to filter
                        "include_metadata": True,
                    },
                    headers={"Content-Type": "application/json"},
                )

                if response.status_code != 200:
                    logger.warning(f"Weaviate search failed: {response.status_code}")
                    return []

                data = response.json()
                results = data.get("results", [])

                # Filter: only classified documents (not /Sin Clasificar)
                # and not the same document
                similar_docs = []
                for result in results:
                    metadata = result.get("metadata", {})
                    folder = metadata.get("folder_path", "/Sin Clasificar")
                    result_doc_id = metadata.get("doc_id", "")

                    # Skip unclassified and same document
                    if folder == "/Sin Clasificar" or result_doc_id == doc_id:
                        continue

                    similar_docs.append(SimilarDocument(
                        doc_id=result_doc_id,
                        title=metadata.get("title", "Sin título"),
                        folder_path=folder,
                        content_preview=result.get("content", "")[:300],
                        similarity=result.get("score", 0.0),
                    ))

                    if len(similar_docs) >= self.k:
                        break

                return similar_docs

            except httpx.HTTPError as e:
                logger.error(f"HTTP error searching similar docs: {e}")
                return []
            except Exception as e:
                logger.error(f"Error searching similar docs: {e}")
                return []

    def _build_classification_prompt(
        self,
        documento: Dict[str, Any],
        ejemplos: List[SimilarDocument],
    ) -> str:
        """Build the prompt for LLM classification."""

        if not ejemplos:
            return ""

        # Format examples
        ejemplos_texto = "\n".join([
            f"- '{ej.title}' → Carpeta: {ej.folder_path}\n  Contenido: {ej.content_preview[:150]}..."
            for ej in ejemplos
        ])

        # Get unique folders from examples
        carpetas_unicas = list(set(ej.folder_path for ej in ejemplos))

        prompt = f"""Eres un sistema de clasificación de documentos.
Analiza el documento nuevo y clasifícalo en la carpeta más apropiada basándote en los ejemplos existentes.

## Carpetas disponibles (basadas en ejemplos similares):
{', '.join(carpetas_unicas)}

## Documentos de referencia (similares al nuevo):
{ejemplos_texto}

## Documento a clasificar:
Nombre: {documento.get('filename', 'documento')}
Tipo: {documento.get('file_type', 'desconocido')}
Contenido: {documento.get('content', '')[:500]}

Clasifica este documento. Si ninguna carpeta existente es apropiada, sugiere una nueva.
Responde SOLO con un JSON válido con estos campos:
- carpeta: string (ruta de carpeta sugerida)
- confianza: number (0-1)
- razonamiento: string (explicación breve)
- carpetas_alternativas: array de strings (otras opciones)
- es_carpeta_nueva: boolean (true si sugieres crear carpeta nueva)

JSON:"""

        return prompt

    async def classify(
        self,
        documento: Dict[str, Any],
    ) -> ClassificationResult:
        """
        Classify a document using RAG + LLM.

        Args:
            documento: Dict with filename, file_type, content, doc_id

        Returns:
            ClassificationResult with folder, confidence, reasoning
        """
        doc_id = documento.get("doc_id", "")
        content = documento.get("content", "")

        # Step 1: Get similar classified documents (RAG)
        ejemplos = await self.get_similar_classified_documents(doc_id, content)

        if not ejemplos:
            logger.info(f"No classified examples found for document {doc_id}")
            return ClassificationResult(
                carpeta="/Sin Clasificar",
                confianza=0.0,
                razonamiento="No hay documentos de referencia clasificados aún",
                carpetas_alternativas=[],
                es_carpeta_nueva=False,
            )

        # Step 2: Build prompt with examples
        prompt = self._build_classification_prompt(documento, ejemplos)

        # Step 3: Call LLM for classification
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.vllm_base_url}/chat/completions",
                    json={
                        "model": self.VLLM_MODEL,
                        "messages": [
                            {"role": "user", "content": prompt}
                        ],
                        "max_tokens": 500,
                        "temperature": 0.1,
                    },
                    headers={"Content-Type": "application/json"},
                )

                if response.status_code != 200:
                    logger.error(f"vLLM error: {response.status_code} - {response.text}")
                    return ClassificationResult(
                        carpeta="/Sin Clasificar",
                        confianza=0.0,
                        razonamiento=f"Error LLM: {response.status_code}",
                    )

                data = response.json()
                llm_response = data.get("choices", [{}])[0].get("message", {}).get("content", "")

                # Parse JSON from response (may have <think> tags for Qwen3)
                return self._parse_llm_response(llm_response)

        except httpx.HTTPError as e:
            logger.error(f"HTTP error calling vLLM: {e}")
            return ClassificationResult(
                carpeta="/Sin Clasificar",
                confianza=0.0,
                razonamiento=f"Error de conexión: {str(e)}",
            )
        except Exception as e:
            logger.error(f"Error in LLM classification: {e}")
            return ClassificationResult(
                carpeta="/Sin Clasificar",
                confianza=0.0,
                razonamiento=f"Error: {str(e)}",
            )

    def _parse_llm_response(self, response: str) -> ClassificationResult:
        """Parse LLM response using centralized JSON extraction utility."""
        from app.utils.json_extraction import extract_json_from_llm_response, clean_llm_response

        # Use centralized extraction (handles <think> tags, code blocks, etc.)
        data = extract_json_from_llm_response(response, default=None)

        if data and isinstance(data, dict):
            try:
                return ClassificationResult(
                    carpeta=data.get("carpeta", "/Sin Clasificar"),
                    confianza=float(data.get("confianza", 0.5)),
                    razonamiento=data.get("razonamiento", ""),
                    carpetas_alternativas=data.get("carpetas_alternativas", []),
                    es_carpeta_nueva=data.get("es_carpeta_nueva", False),
                )
            except (ValueError, TypeError) as e:
                logger.warning(f"Failed to parse classification data: {e}")

        # Fallback: couldn't parse
        clean_response = clean_llm_response(response)
        return ClassificationResult(
            carpeta="/Sin Clasificar",
            confianza=0.0,
            razonamiento=f"No se pudo parsear la respuesta: {clean_response[:200]}",
        )

    async def should_suggest_activation(self) -> bool:
        """
        Check if there are enough classified documents to suggest activation.

        Criteria:
        - At least 20 documents classified (not in /Sin Clasificar)
        - At least 3 different folders
        """
        # This would query the database - simplified here
        # In real implementation, query documents table
        return False  # Placeholder


# =============================================================================
# Convenience function
# =============================================================================

async def classify_document(
    tenant_id: str,
    documento: Dict[str, Any],
    k: int = 7,
    min_confidence: float = 0.6,
) -> ClassificationResult:
    """
    Convenience function to classify a document.

    Args:
        tenant_id: Tenant identifier
        documento: Dict with filename, file_type, content, doc_id
        k: Number of similar documents to retrieve
        min_confidence: Minimum confidence threshold

    Returns:
        ClassificationResult
    """
    service = FolderClassificationService(
        tenant_id=tenant_id,
        k=k,
        min_confidence=min_confidence,
    )
    return await service.classify(documento)
