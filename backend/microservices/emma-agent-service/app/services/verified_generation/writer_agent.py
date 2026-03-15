"""
Writer Agent for Verified Document Generation.

Generates ONE claim at a time using vLLM, incorporating context from
previously verified claims. This ensures each new claim builds on
validated information only.

The Writer uses a stop sequence approach:
1. Generate a single factual claim (short, focused)
2. Stop after claim is complete
3. Wait for verification before generating next claim

Usage:
    writer = WriterAgent()
    candidate = await writer.generate_next_claim(
        query="Resume el contrato con ACME",
        verified_claims=[...],
        source_context="...",
    )
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import List, Optional

import httpx

from app.core.config import settings
from app.core.langfuse_config import observe
from app.schemas.verified_generation import CandidateClaim, VerifiedClaim
from app.services.langfuse_prompt_client import get_langfuse_prompt_client

logger = logging.getLogger(__name__)

# ── Fallback prompts (Spanish) — used when Langfuse + YAML are both unavailable ──

FALLBACK_CLAIM_SYSTEM = """Eres un redactor preciso de documentos que genera afirmaciones factuales.

REGLAS CRÍTICAS:
1. Genera EXACTAMENTE UNA afirmación factual por llamada
2. Cada afirmación debe ser una declaración completa y autónoma
3. Las afirmaciones deben ser verificables contra los documentos fuente
4. NO generes opiniones, especulaciones ni declaraciones inciertas
5. Usa datos específicos: nombres, fechas, números, porcentajes cuando estén disponibles
6. Mantén las afirmaciones concisas (1-2 frases máximo)
7. Escribe SIEMPRE en el mismo idioma que los documentos fuente
8. VARÍA el inicio de cada afirmación. NUNCA repitas la misma apertura (ej. "Este estudio", "El estudio", "El artículo") en afirmaciones consecutivas. Usa sujetos concretos: nombres de autores, conceptos específicos, datos, hallazgos, metodologías, etc.

FORMATO:
- Genera SOLO el texto de la afirmación, nada más
- Sin viñetas, números ni prefijos
- Sin explicaciones ni meta-comentarios
- NO uses etiquetas <think> ni bloques de razonamiento
- NO expliques tu proceso de pensamiento
- Solo genera la afirmación directamente

EJEMPLOS DE BUENAS AFIRMACIONES:
- "El contrato tiene una vigencia de 24 meses a partir del 1 de enero de 2024."
- "La cláusula de penalización establece un 5% del valor total por incumplimiento."
- "ACME Corporation es responsable del mantenimiento del software según la sección 4.2."
- "Los resultados muestran una correlación significativa (r=0.82) entre ambas variables."
- "La muestra incluyó 245 participantes de edades comprendidas entre 18 y 65 años."

EJEMPLOS DE MALAS AFIRMACIONES:
- "El contrato parece establecer..." (incierto)
- "Según mi análisis..." (meta-comentario)
- "1. El contrato..." (numerado/con viñeta)
- "<think>Voy a analizar...</think>" (etiquetas de pensamiento - NUNCA USAR)
- "Este estudio analiza..." seguido de "El estudio muestra..." (apertura repetitiva)
"""

FALLBACK_CLAIM_USER_NEXT = """Genera la SIGUIENTE afirmación factual para este documento.

CONSULTA/TEMA:
{query}

CONTEXTO FUENTE (de documentos):
{source_context}

AFIRMACIONES PREVIAMENTE VERIFICADAS (complementa estas, no repitas):
{verified_claims_text}

NÚMERO DE AFIRMACIÓN A GENERAR: {claim_number}

IMPORTANTE: Varía el inicio de la afirmación. NO empieces con la misma frase que las afirmaciones previas (evita repetir "Este estudio", "El estudio", "El artículo", etc.). Usa sujetos concretos y específicos.

Genera SOLO UNA nueva afirmación factual. Solo el texto de la afirmación, nada más."""

FALLBACK_CLAIM_USER_FIRST = """Genera la PRIMERA afirmación factual para este documento.

CONSULTA/TEMA:
{query}

CONTEXTO FUENTE (de documentos):
{source_context}

Genera SOLO UNA afirmación factual para iniciar el documento. Solo el texto de la afirmación, nada más."""

FALLBACK_COMPLETION_SYSTEM = "Eres un verificador de completitud de documentos. Responde SOLO con SÍ o NO."

FALLBACK_COMPLETION_USER = """Determina si este documento está COMPLETO.

CONSULTA/TEMA:
{query}

CONTEXTO FUENTE:
{source_context}

AFIRMACIONES GENERADAS HASTA AHORA:
{verified_claims_text}

¿Está completo el documento? Responde SOLO "SÍ" o "NO".
- SÍ: Toda la información importante de las fuentes ha sido capturada
- NO: Hay más información relevante por incluir"""


class WriterAgent:
    """
    Writer Agent that generates claims one at a time.

    Uses vLLM for generation with low temperature for deterministic,
    factual output. Each claim is short and focused to facilitate
    verification.
    """

    def __init__(
        self,
        vllm_base_url: Optional[str] = None,
        vllm_model: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 150,
    ):
        """
        Initialize the Writer Agent.

        Args:
            vllm_base_url: vLLM server URL
            vllm_model: Model to use
            temperature: Generation temperature (lower = more deterministic)
            max_tokens: Max tokens per claim (keep short)
        """
        self._vllm_base_url = vllm_base_url or settings.vllm_base_url
        self._vllm_model = vllm_model or settings.vllm_model
        self._temperature = temperature
        self._max_tokens = max_tokens

    @observe(name="verified.generate_claim")
    async def generate_next_claim(
        self,
        query: str,
        verified_claims: List[VerifiedClaim],
        source_context: str,
        claim_number: Optional[int] = None,
    ) -> CandidateClaim:
        """
        Generate the next claim for the document.

        Args:
            query: The original user query/prompt
            verified_claims: List of already verified claims
            source_context: Context from source documents
            claim_number: Optional claim number (auto-calculated if not provided)

        Returns:
            CandidateClaim ready for verification
        """
        # Calculate claim number
        if claim_number is None:
            claim_number = len(verified_claims) + 1

        client = get_langfuse_prompt_client()

        # Resolve system prompt via Langfuse → YAML → fallback
        sys_cached = await client.get_prompt(
            "emma_verified_claim_system",
            fallback=FALLBACK_CLAIM_SYSTEM,
        )
        system_prompt = sys_cached.content if sys_cached else FALLBACK_CLAIM_SYSTEM

        # Build user prompt
        if verified_claims:
            verified_text = self._format_verified_claims(verified_claims)
            variables = {
                "query": query,
                "source_context": source_context,
                "verified_claims_text": verified_text,
                "claim_number": str(claim_number),
            }
            user_cached = await client.get_prompt(
                "emma_verified_claim_user_next",
                variables=variables,
                fallback=FALLBACK_CLAIM_USER_NEXT.format(**variables),
            )
            user_prompt = user_cached.content if user_cached else FALLBACK_CLAIM_USER_NEXT.format(**variables)
        else:
            # First claim - simpler prompt
            variables = {
                "query": query,
                "source_context": source_context,
            }
            user_cached = await client.get_prompt(
                "emma_verified_claim_user_first",
                variables=variables,
                fallback=FALLBACK_CLAIM_USER_FIRST.format(**variables),
            )
            user_prompt = user_cached.content if user_cached else FALLBACK_CLAIM_USER_FIRST.format(**variables)

        # Generate claim
        raw_text = await self._call_vllm(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        logger.info(f"🔍 Raw vLLM response ({len(raw_text)} chars): {raw_text[:300]}")

        # Clean the generated text
        claim_text = self._clean_claim_text(raw_text)
        if not claim_text:
            logger.warning(f"⚠️ _clean_claim_text returned empty. Raw: {raw_text[:500]}")

        # Create candidate claim
        candidate = CandidateClaim(
            text=claim_text,
            source_query=query,
            generation_order=claim_number,
            context_document_ids=[],  # Will be populated by caller
        )

        logger.info(
            f"📝 Generated claim #{claim_number}: {claim_text[:100]}..."
        )

        return candidate

    @observe(name="verified.check_completion")
    async def check_completion(
        self,
        query: str,
        verified_claims: List[VerifiedClaim],
        source_context: str,
    ) -> bool:
        """
        Check if the document generation is complete.

        Uses LLM to determine if all relevant information from
        the source context has been captured in the claims.

        Args:
            query: The original query
            verified_claims: List of verified claims so far
            source_context: Source document context

        Returns:
            True if generation should stop
        """
        if len(verified_claims) < 3:
            # Minimum 3 claims before checking completion
            return False

        client = get_langfuse_prompt_client()
        verified_text = self._format_verified_claims(verified_claims)

        # System prompt
        sys_cached = await client.get_prompt(
            "emma_verified_completion_system",
            fallback=FALLBACK_COMPLETION_SYSTEM,
        )
        system_prompt = sys_cached.content if sys_cached else FALLBACK_COMPLETION_SYSTEM

        # User prompt
        variables = {
            "query": query,
            "source_context": source_context,
            "verified_claims_text": verified_text,
        }
        user_cached = await client.get_prompt(
            "emma_verified_completion_user",
            variables=variables,
            fallback=FALLBACK_COMPLETION_USER.format(**variables),
        )
        check_prompt = user_cached.content if user_cached else FALLBACK_COMPLETION_USER.format(**variables)

        response = await self._call_vllm(
            system_prompt=system_prompt,
            user_prompt=check_prompt,
        )

        response = response.strip().upper()
        is_complete = "SÍ" in response or "SI" in response or "YES" in response

        logger.info(
            f"🏁 Completion check: {is_complete} "
            f"(claims={len(verified_claims)}, response={response[:20]})"
        )

        return is_complete

    def _format_verified_claims(self, claims: List[VerifiedClaim]) -> str:
        """Format verified claims for prompt context."""
        if not claims:
            return "(No claims verified yet)"

        lines = []
        for i, claim in enumerate(claims, 1):
            status_emoji = "✓" if claim.status.value == "verified" else "~"
            lines.append(f"{i}. [{status_emoji}] {claim.text}")

        return "\n".join(lines)

    def _clean_claim_text(self, text: str) -> str:
        """
        Clean and normalize generated claim text.

        Handles Qwen3 thinking tags which may appear in various forms:
        - Complete: <think>...</think>content
        - Unclosed: <think>... (truncated by max_tokens)
        - Nested: <think>...<think>...</think>...</think>
        """
        if not text:
            return ""

        original_text = text  # Keep for fallback

        # Step 1: Remove complete <think>...</think> blocks (including nested)
        # Use a loop to handle nested tags
        prev_text = None
        while prev_text != text:
            prev_text = text
            text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)

        # Step 2: Handle unclosed <think> tags (common with max_tokens truncation)
        # If text starts with <think> and has no closing tag, extract content after it
        if '<think>' in text:
            # Find content after the last </think> if any
            if '</think>' in text:
                # Get everything after the last </think>
                parts = text.rsplit('</think>', 1)
                text = parts[-1] if len(parts) > 1 else text
            else:
                # No closing tag - the whole thing might be thinking content
                # Try to find where the actual claim starts (often after newlines)
                think_match = re.search(r'<think>', text)
                if think_match:
                    # Remove everything from <think> onwards
                    text = text[:think_match.start()]

        # Step 3: If text is now empty, try to extract any useful content from original
        text = text.strip()
        if not text and original_text:
            # Strategy A: Look for content AFTER </think> tag
            if '</think>' in original_text:
                after_think = original_text.rsplit('</think>', 1)[-1].strip()
                if after_think and len(after_think) > 10:
                    text = after_think

            # Strategy B: Look for content INSIDE <think> that resembles a claim
            if not text:
                # Extract think content to find the actual claim the model "thought" about
                think_match = re.search(r'<think>(.*?)</think>', original_text, re.DOTALL)
                think_content = think_match.group(1) if think_match else original_text

                # Look for sentences that look like factual claims (any language)
                sentences = re.findall(r'[A-ZÁÉÍÓÚÑa-záéíóúñ][^<\n]*?[.!?]', think_content)
                skip_patterns = [
                    'let me', 'i need to', 'okay', 'the user', 'i should',
                    'first,', 'looking at', 'based on', "let's", 'i will',
                    'i\'ll', 'the query', 'the topic', 'the source', 'generate',
                    'claim number', 'need to', 'should be',
                ]
                for sentence in sentences:
                    lower_sent = sentence.lower().strip()
                    if len(lower_sent) < 15:
                        continue
                    if any(skip in lower_sent for skip in skip_patterns):
                        continue
                    text = sentence.strip()
                    logger.info(f"🔧 Extracted claim from think block: {text[:80]}")
                    break

        # Step 4: Remove common prefixes (bullets, numbers)
        text = re.sub(r'^(\d+\.|-|\*|•|–)\s*', '', text.strip())

        # Step 5: Remove markdown formatting
        text = text.replace('**', '').replace('__', '').replace('`', '')

        # Step 6: Remove surrounding quotes
        text = text.strip('"\'""''')

        # Step 7: Remove "Claim:" or similar prefixes
        text = re.sub(r'^(claim|afirmación|statement):\s*', '', text, flags=re.IGNORECASE)

        # Step 8: Ensure proper ending
        text = text.strip()
        if text and text[-1] not in '.!?':
            text += '.'

        # Log if we had to do heavy cleaning
        if text and original_text and '<think>' in original_text:
            logger.debug(f"🧹 Cleaned think tags: '{original_text[:50]}...' → '{text[:50]}...'")

        return text

    async def _call_vllm(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        """
        Call LLM for claim generation.

        Uses the shared LLMClient which properly handles Qwen3 thinking tags.
        Falls back to raw httpx if LLMClient is unavailable.
        """
        # Try ChatOpenAI first (handles Qwen3 thinking tags properly)
        try:
            from langchain_core.messages import SystemMessage, HumanMessage
            from app.agents.llm_models import get_chat_model

            model = get_chat_model().bind(
                temperature=self._temperature,
                max_tokens=self._max_tokens,
                seed=42,
            )
            response = await model.ainvoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ])

            if response and response.content:
                return response.content.strip()
            else:
                logger.warning("⚠️ ChatOpenAI returned empty response, falling back to raw vLLM")
        except Exception as e:
            logger.warning(f"⚠️ LLM router failed ({e}), falling back to raw vLLM")

        # Fallback: direct vLLM call
        try:
            async with httpx.AsyncClient(timeout=settings.agent_raw_vllm_timeout_seconds) as client:
                payload = {
                    "model": self._vllm_model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": self._temperature,
                    "max_tokens": self._max_tokens,
                    "seed": 42,
                    "stop": ["\n\n", "\n1.", "\n2.", "\n-", "\n•"],
                    "chat_template_kwargs": {
                        "enable_thinking": False
                    }
                }

                response = await client.post(
                    f"{self._vllm_base_url}/chat/completions",
                    headers={"Content-Type": "application/json"},
                    json=payload,
                )

                if response.status_code == 200:
                    data = response.json()
                    content = data["choices"][0]["message"]["content"]
                    return content.strip()
                else:
                    logger.error(f"❌ vLLM returned {response.status_code}: {response.text}")
                    raise Exception(f"vLLM error: {response.status_code}")

        except Exception as e:
            logger.error(f"❌ vLLM call failed: {e}")
            raise


# =============================================================================
# Singleton Instance (with asyncio.Lock for race-safe initialization)
# =============================================================================

_writer_agent: Optional[WriterAgent] = None
_writer_agent_lock: Optional["asyncio.Lock"] = None


def _get_writer_lock() -> "asyncio.Lock":
    """Lazy lock creation (must be called inside a running event loop)."""
    global _writer_agent_lock
    if _writer_agent_lock is None:
        _writer_agent_lock = asyncio.Lock()
    return _writer_agent_lock


def get_writer_agent() -> WriterAgent:
    """Get the global WriterAgent singleton (sync — init is cheap, no I/O)."""
    global _writer_agent
    if _writer_agent is None:
        _writer_agent = WriterAgent(temperature=settings.verified_claim_temperature)
    return _writer_agent


async def get_writer_agent_async() -> WriterAgent:
    """Get the global WriterAgent singleton (async — race-safe)."""
    global _writer_agent
    if _writer_agent is None:
        async with _get_writer_lock():
            if _writer_agent is None:
                _writer_agent = WriterAgent(temperature=settings.verified_claim_temperature)
    return _writer_agent
