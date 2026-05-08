"""
Layer 4: Validated Generation

Generates answers using LLM with:
- Structured prompts for citation generation (loaded from YAML)
- Claim extraction from response
- Claim validation against source documents
- Confidence scoring

Prompts are loaded from: config/prompts/emma_prompts.yaml
Edit that file to customize Emma's behavior without code changes.
"""

import logging
import re
import asyncio
from typing import List, Dict, Any, Optional, Tuple, AsyncGenerator
import httpx

from .models import (
    AssembledContext,
    ValidatedResponse,
    ClaimValidation,
    QueryIntent,
)
from .prompt_loader import get_prompt, get_user_prompt_template, load_prompts, get_context_root
from ...core.config import settings

logger = logging.getLogger(__name__)


# Fallback prompts (used only if YAML file is not found)
DEFAULT_PROMPTS = {
    "base": """Eres Emma, un asistente profesional de gestión documental.
Responde usando SOLO información de los documentos proporcionados.
Cita usando **[1]**, **[2]**, etc. Usa markdown para formatear.""",
}


class ValidatedGenerator:
    """
    Layer 4: Generate answers with fact-checking

    Uses LLM to generate responses with citations, then validates
    the claims against source documents.
    """

    def __init__(self):
        self._provider = settings.llm_provider
        self._openai_api_key = settings.openai_api_key
        self._openai_base_url = settings.openai_base_url
        # SGLang configuration (primary inference)
        self._sglang_enabled = settings.sglang_enabled
        self._sglang_base_url = settings.sglang_base_url
        self._sglang_model = settings.sglang_model

    async def generate(
        self,
        query: str,
        context: AssembledContext,
        validate_claims: bool = True,
        temperature: float = 0.3,
        max_tokens: int = 2000,
    ) -> ValidatedResponse:
        """
        Generate an answer with citations and optional validation.

        Args:
            query: Original user query
            context: Assembled context from Layer 3
            validate_claims: Whether to extract and validate claims
            temperature: LLM temperature (lower = more deterministic)
            max_tokens: Maximum tokens in response

        Returns:
            ValidatedResponse with answer, claims, and validation
        """
        # Select appropriate system prompt from YAML config
        intent = context.query_analysis.intent
        intent_prompt = get_prompt(intent) or DEFAULT_PROMPTS.get("base")

        # Prepend context root (document management domain context based on ISO 15489)
        context_root = get_context_root()
        if context_root:
            system_prompt = f"{context_root}\n\n{intent_prompt}"
        else:
            system_prompt = intent_prompt

        # Build user prompt
        user_prompt = self._build_user_prompt(query, context)

        # Generate response from LLM
        answer = await self._call_llm(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        # Extract claims and citations
        claims = self._extract_claims(answer)
        citations = self._extract_citations(answer)

        # Validate claims if enabled
        validations = []
        if validate_claims and claims:
            validations = self._validate_claims(claims, context)

        # Calculate confidence score
        confidence_score = self._calculate_confidence(validations, citations, context)

        # Check for unsupported claims
        has_unsupported = any(not v.is_supported for v in validations) if validations else False

        return ValidatedResponse(
            answer=answer,
            claims=claims,
            validations=validations,
            confidence_score=confidence_score,
            citations=citations,
            has_unsupported_claims=has_unsupported,
        )

    async def generate_stream(
        self,
        query: str,
        context: AssembledContext,
        temperature: float = 0.3,
        max_tokens: int = 2000,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Generate answer with streaming output.

        Yields progress events and final result.
        """
        yield {"type": "progress", "content": "Preparando contexto...", "progress": 20}

        # Select appropriate system prompt from YAML config
        intent = context.query_analysis.intent
        intent_prompt = get_prompt(intent) or DEFAULT_PROMPTS.get("base")

        # Prepend context root (document management domain context based on ISO 15489)
        context_root = get_context_root()
        if context_root:
            system_prompt = f"{context_root}\n\n{intent_prompt}"
        else:
            system_prompt = intent_prompt

        # Build user prompt
        user_prompt = self._build_user_prompt(query, context)

        yield {"type": "progress", "content": "Generando respuesta...", "progress": 40}

        # Generate response from LLM with streaming
        answer_parts = []
        async for chunk in self._call_llm_stream(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        ):
            answer_parts.append(chunk)
            yield {"type": "token", "content": chunk}

        answer = "".join(answer_parts)

        yield {"type": "progress", "content": "Validando respuesta...", "progress": 80}

        # Extract and validate
        claims = self._extract_claims(answer)
        citations = self._extract_citations(answer)
        validations = self._validate_claims(claims, context) if claims else []
        confidence_score = self._calculate_confidence(validations, citations, context)
        has_unsupported = any(not v.is_supported for v in validations) if validations else False

        result = ValidatedResponse(
            answer=answer,
            claims=claims,
            validations=validations,
            confidence_score=confidence_score,
            citations=citations,
            has_unsupported_claims=has_unsupported,
        )

        yield {"type": "result", "content": result.to_dict(), "progress": 100}

    def _build_user_prompt(self, query: str, context: AssembledContext) -> str:
        """Build the user prompt with context and query using YAML template"""
        # Build document index for clear citations
        doc_index = "\n".join([
            f"**[{i+1}]** {doc.title or 'Sin título'}"
            for i, doc in enumerate(context.documents)
        ])

        # Get template from YAML or use default
        template = get_user_prompt_template()

        return template.format(
            doc_index=doc_index,
            formatted_context=context.formatted_context,
            query=query
        )

    async def _call_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        """Call the LLM and return the response"""
        try:
            # Priority: SGLang (primary) > OpenAI-compatible fallback.
            if self._sglang_enabled:
                return await self._call_sglang(system_prompt, user_prompt, temperature, max_tokens)
            elif self._provider == "openai" and self._openai_api_key:
                return await self._call_openai(system_prompt, user_prompt, temperature, max_tokens)
            else:
                # Default to SGLang even if not explicitly enabled (it's the new default)
                logger.warning("⚠️ No LLM provider configured, attempting SGLang as default")
                return await self._call_sglang(system_prompt, user_prompt, temperature, max_tokens)
        except Exception as e:
            logger.error(f"❌ LLM call failed: {e}")
            raise

    async def _call_openai(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        """Call OpenAI-compatible API"""
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self._openai_base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self._openai_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": settings.openai_model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                    },
                )

                if response.status_code == 200:
                    data = response.json()
                    return data["choices"][0]["message"]["content"]
                else:
                    raise Exception(f"OpenAI returned {response.status_code}: {response.text}")

        except Exception as e:
            logger.error(f"❌ OpenAI call failed: {e}")
            raise

    async def _call_sglang(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        """Call SGLang server (OpenAI-compatible API)"""
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"{self._sglang_base_url}/chat/completions",
                    headers={"Content-Type": "application/json"},
                    json={
                        "model": self._sglang_model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                    },
                )

                if response.status_code == 200:
                    data = response.json()
                    return data["choices"][0]["message"]["content"]
                else:
                    raise Exception(f"SGLang returned {response.status_code}: {response.text}")

        except Exception as e:
            logger.error(f"❌ SGLang call failed: {e}")
            raise

    async def _call_llm_stream(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> AsyncGenerator[str, None]:
        """Call LLM with streaming response"""
        # SGLang is the primary/default streaming provider.
        async for chunk in self._call_sglang_stream(system_prompt, user_prompt, temperature, max_tokens):
            yield chunk

    async def _call_sglang_stream(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> AsyncGenerator[str, None]:
        """Call SGLang with streaming response (OpenAI-compatible SSE format)"""
        try:
            async with httpx.AsyncClient(timeout=180.0) as client:
                async with client.stream(
                    "POST",
                    f"{self._sglang_base_url}/chat/completions",
                    headers={"Content-Type": "application/json"},
                    json={
                        "model": self._sglang_model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        "stream": True,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                    },
                ) as response:
                    import json
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            data_str = line[6:]  # Remove "data: " prefix
                            if data_str.strip() == "[DONE]":
                                break
                            try:
                                data = json.loads(data_str)
                                delta = data.get("choices", [{}])[0].get("delta", {})
                                content = delta.get("content", "")
                                if content:
                                    yield content
                            except json.JSONDecodeError:
                                continue
        except Exception as e:
            logger.error(f"❌ SGLang streaming call failed: {e}")
            yield f"Error: {str(e)}"

    def _extract_claims(self, answer: str) -> List[str]:
        """
        Extract factual claims from the answer.

        A claim is a sentence that makes a factual assertion.
        """
        claims = []

        # Split into sentences
        sentences = re.split(r'[.!?]+', answer)

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence or len(sentence) < 20:
                continue

            # Skip sentences that are questions or meta-statements
            if sentence.startswith(("Para ", "Según ", "Como se ", "Esta información no")):
                continue

            # Skip headers and formatting (including markdown headers)
            if sentence.startswith(("===", "---", "[", "Fuentes:", "#", "##", "📋", "📄", "🔍", "⚠️", "✅", "📝", "📊")):
                continue

            # Include sentences with citations (multiple formats)
            if re.search(r'\*\*\[\d+\]\*\*|\[\d+\]|\[Documento \d+\]', sentence):
                claims.append(sentence)
            # Include sentences with factual indicators
            elif any(indicator in sentence.lower() for indicator in [
                "es", "son", "tiene", "tienen", "incluye", "establece",
                "indica", "menciona", "describe", "define"
            ]):
                claims.append(sentence)

        return claims[:10]  # Limit to 10 claims

    def _extract_citations(self, answer: str) -> Dict[str, str]:
        """
        Extract citation markers and map them to document indices.

        Returns dict of citation marker -> document index.
        """
        citations = {}

        # Find citation patterns: **[1]**, [1], [Documento 1], etc.
        patterns = [
            r'\*\*\[(\d+)\]\*\*',  # **[1]**
            r'\[(\d+)\]',          # [1]
            r'\[Documento (\d+)\]', # [Documento 1]
        ]

        for pattern in patterns:
            matches = re.findall(pattern, answer)
            for match in matches:
                citation_key = f"[{match}]"
                citations[citation_key] = match

        return citations

    def _validate_claims(
        self,
        claims: List[str],
        context: AssembledContext,
    ) -> List[ClaimValidation]:
        """
        Validate each claim against the source documents.

        Uses simple text matching to verify claims are supported.
        """
        validations = []

        for claim in claims:
            # Extract cited document numbers from the claim (multiple formats)
            cited_docs = []
            for pattern in [r'\*\*\[(\d+)\]\*\*', r'\[(\d+)\]', r'\[Documento (\d+)\]']:
                cited_docs.extend(re.findall(pattern, claim))
            cited_docs = list(set(cited_docs))  # Remove duplicates

            # Remove citation markers for content matching
            claim_text = re.sub(r'\*\*\[\d+\]\*\*|\[\d+\]|\[Documento \d+\]', '', claim).strip().lower()

            # Check if claim content appears in cited documents
            supporting_docs = []
            total_support_score = 0.0

            for doc_num in cited_docs:
                doc_idx = int(doc_num) - 1
                if 0 <= doc_idx < len(context.documents):
                    doc = context.documents[doc_idx]
                    doc_content = doc.content.lower()

                    # Calculate word overlap
                    claim_words = set(claim_text.split())
                    doc_words = set(doc_content.split())
                    overlap = len(claim_words & doc_words)
                    overlap_ratio = overlap / max(len(claim_words), 1)

                    if overlap_ratio > 0.3:  # At least 30% word overlap
                        supporting_docs.append(doc.id)
                        total_support_score += overlap_ratio

            # Also check uncited documents for support
            for i, doc in enumerate(context.documents):
                if str(i + 1) not in cited_docs:
                    doc_content = doc.content.lower()
                    claim_words = set(claim_text.split())
                    doc_words = set(doc_content.split())
                    overlap = len(claim_words & doc_words)
                    overlap_ratio = overlap / max(len(claim_words), 1)

                    if overlap_ratio > 0.4:  # Higher threshold for uncited
                        supporting_docs.append(doc.id)
                        total_support_score += overlap_ratio * 0.5  # Reduce score for uncited

            # Determine if claim is supported
            is_supported = len(supporting_docs) > 0 and total_support_score > 0.3
            confidence = min(total_support_score / max(len(cited_docs), 1), 1.0)

            validations.append(ClaimValidation(
                claim=claim,
                is_supported=is_supported,
                supporting_document_ids=supporting_docs,
                confidence=confidence,
            ))

        return validations

    def _calculate_confidence(
        self,
        validations: List[ClaimValidation],
        citations: Dict[str, str],
        context: AssembledContext,
    ) -> float:
        """
        Calculate overall confidence score for the response.

        Factors:
        - Percentage of validated claims
        - Number of citations
        - Context coverage
        """
        if not validations and not citations:
            return 0.3  # Low confidence if no citations

        scores = []

        # Factor 1: Validated claims ratio
        if validations:
            validated_ratio = sum(1 for v in validations if v.is_supported) / len(validations)
            scores.append(validated_ratio)

        # Factor 2: Citation presence
        if citations:
            citation_score = min(len(citations) / 3, 1.0)  # Cap at 3 citations
            scores.append(citation_score)

        # Factor 3: Document coverage
        cited_doc_nums = set(citations.values())
        coverage = len(cited_doc_nums) / max(len(context.documents), 1)
        scores.append(min(coverage, 1.0))

        # Calculate weighted average
        if not scores:
            return 0.5

        return sum(scores) / len(scores)


# Global instance
validated_generator = ValidatedGenerator()
