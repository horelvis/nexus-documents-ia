"""
LangExtract Service Client

HTTP client for calling the langextract-service to extract entities from documents.
Used by the RAG pipeline to extract named entities for knowledge graphs.

Usage:
    from app.services.rag.langextract_client import langextract_client

    result = await langextract_client.extract_entities(
        text="Contract between ACME Corp and John Doe...",
        document_type="contract",
        filename="contract.pdf",
    )

Entities extracted:
- PERSON: Names, signers
- ORGANIZATION: Companies, institutions
- DATE: Contract dates, deadlines
- AMOUNT: Monetary values
- LOCATION: Addresses, places
- DNI/NIE: Spanish ID numbers (regex-based)
"""

import os
import re
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


# DNI/NIE regex patterns for Spanish ID extraction
DNI_PATTERN = re.compile(r'\b(\d{8}[A-Za-z])\b')
NIE_PATTERN = re.compile(r'\b([XYZxyz]\d{7}[A-Za-z])\b')
CIF_PATTERN = re.compile(r'\b([A-Ha-h]\d{8})\b')  # Company tax ID


@dataclass
class EntityExtraction:
    """A single extracted entity"""
    entity_type: str  # PERSON, ORGANIZATION, DATE, AMOUNT, DNI, NIE, CIF, etc.
    value: str
    confidence: float = 0.8
    start_pos: Optional[int] = None
    end_pos: Optional[int] = None


@dataclass
class LangExtractResult:
    """Result from langextract-service or local extraction"""
    success: bool
    entities: List[Dict[str, Any]] = field(default_factory=list)
    document_type: Optional[str] = None
    summary: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    @classmethod
    def from_response(cls, data: Dict[str, Any]) -> "LangExtractResult":
        """Create from API response"""
        return cls(
            success=data.get("success", True),
            entities=data.get("extractions", []),
            document_type=data.get("detected_type"),
            summary=data.get("summary", {}),
        )

    @classmethod
    def error_result(cls, error: str) -> "LangExtractResult":
        """Create error result"""
        return cls(success=False, error=error)


class LangExtractClient:
    """
    HTTP client for langextract-service.

    Also includes local regex-based extraction for Spanish IDs (DNI, NIE, CIF)
    which don't require LLM processing.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: float = 120.0,  # Increased for LLM extraction (Gemini can take 40-60s)
    ):
        self.base_url = base_url or os.environ.get(
            "LANGEXTRACT_SERVICE_URL",
            "http://langextract-service:8000"
        )
        self.api_key = api_key or os.environ.get("MICROSERVICES_API_KEY", "")
        self.timeout = timeout

    def _extract_spanish_ids(self, text: str) -> List[Dict[str, Any]]:
        """
        Extract Spanish ID numbers using regex patterns.

        This is fast and doesn't require LLM, so we always run it locally.
        """
        entities = []

        # Extract DNIs
        for match in DNI_PATTERN.finditer(text):
            entities.append({
                "type": "DNI",
                "value": match.group(1).upper(),
                "text": match.group(1),
                "confidence": 0.95,
                "start": match.start(),
                "end": match.end(),
            })

        # Extract NIEs
        for match in NIE_PATTERN.finditer(text):
            entities.append({
                "type": "NIE",
                "value": match.group(1).upper(),
                "text": match.group(1),
                "confidence": 0.95,
                "start": match.start(),
                "end": match.end(),
            })

        # Extract CIFs
        for match in CIF_PATTERN.finditer(text):
            entities.append({
                "type": "CIF",
                "value": match.group(1).upper(),
                "text": match.group(1),
                "confidence": 0.90,
                "start": match.start(),
                "end": match.end(),
            })

        return entities

    async def extract_entities(
        self,
        text: str,
        document_type: Optional[str] = None,
        filename: Optional[str] = None,
        use_llm: bool = True,
    ) -> LangExtractResult:
        """
        Extract entities from document text.

        Args:
            text: Document text content
            document_type: Type of document (contract, invoice, etc.)
            filename: Original filename for context
            use_llm: Whether to use LLM for extraction (True) or just regex (False)

        Returns:
            LangExtractResult with extracted entities
        """
        # Always extract Spanish IDs locally (fast, no LLM needed)
        local_entities = self._extract_spanish_ids(text)

        if local_entities:
            logger.info(
                f"🆔 Local extraction found: "
                f"{sum(1 for e in local_entities if e['type'] == 'DNI')} DNIs, "
                f"{sum(1 for e in local_entities if e['type'] == 'NIE')} NIEs, "
                f"{sum(1 for e in local_entities if e['type'] == 'CIF')} CIFs"
            )

        # If LLM extraction is disabled or text is too short, return local only
        if not use_llm or len(text.strip()) < 50:
            return LangExtractResult(
                success=True,
                entities=local_entities,
                document_type=document_type,
            )

        # Call LangExtract service for LLM-based extraction
        url = f"{self.base_url}/api/v1/extraction/extract"

        headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
        }

        payload = {
            "text": text[:50000],  # Limit text size
            "document_type": document_type or "general",
            "filename": filename,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                logger.info(f"📤 Calling langextract-service for entity extraction")

                response = await client.post(url, headers=headers, json=payload)

                if response.status_code == 200:
                    result = LangExtractResult.from_response(response.json())

                    # Merge local entities with LLM entities
                    all_entities = local_entities + result.entities
                    result.entities = all_entities

                    logger.info(
                        f"✅ LangExtract returned {len(result.entities)} total entities "
                        f"(LLM: {len(result.entities) - len(local_entities)}, "
                        f"local: {len(local_entities)})"
                    )
                    return result
                else:
                    error_detail = response.text
                    try:
                        error_json = response.json()
                        error_detail = error_json.get("detail", response.text)
                    except Exception:
                        pass

                    logger.warning(
                        f"⚠️ LangExtract service error: {response.status_code} - {error_detail}. "
                        f"Returning local entities only."
                    )
                    # Return local entities even if LLM fails
                    return LangExtractResult(
                        success=True,
                        entities=local_entities,
                        document_type=document_type,
                    )

        except httpx.TimeoutException:
            logger.warning(f"⚠️ LangExtract timeout. Returning local entities only.")
            return LangExtractResult(success=True, entities=local_entities)
        except httpx.ConnectError as e:
            logger.warning(f"⚠️ Cannot connect to langextract-service: {e}. Returning local entities only.")
            return LangExtractResult(success=True, entities=local_entities)
        except Exception as e:
            logger.error(f"❌ LangExtract error: {e}")
            return LangExtractResult(success=True, entities=local_entities)

    async def categorize_document(
        self,
        text: str,
        filename: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Categorize document type using LangExtract.

        Args:
            text: Document text content
            filename: Original filename
            context: Additional context (folder path, metadata, etc.)

        Returns:
            Dict with detected_type, confidence, reasoning
        """
        url = f"{self.base_url}/api/v1/extraction/categorize"

        headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
        }

        payload = {
            "text": text[:10000],  # Limit for categorization
            "filename": filename,
            "context": context,
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, headers=headers, json=payload)

                if response.status_code == 200:
                    return response.json()
                else:
                    logger.warning(f"Categorization failed: {response.status_code}")
                    return {"detected_type": "general", "confidence": 0.0}

        except Exception as e:
            logger.error(f"Categorization error: {e}")
            return {"detected_type": "general", "confidence": 0.0}

    async def health_check(self) -> Dict[str, Any]:
        """Check langextract-service health"""
        url = f"{self.base_url}/health"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    url,
                    headers={"X-API-Key": self.api_key},
                )

                if response.status_code == 200:
                    return {"status": "healthy", **response.json()}
                else:
                    return {"status": "unhealthy", "code": response.status_code}

        except Exception as e:
            return {"status": "error", "error": str(e)}


# Global instance
langextract_client = LangExtractClient()
