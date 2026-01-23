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

import logging
import re
from typing import List, Optional

import httpx

from app.core.config import settings
from app.schemas.verified_generation import CandidateClaim, VerifiedClaim

logger = logging.getLogger(__name__)

# Writer Agent prompts
WRITER_SYSTEM_PROMPT = """You are a precise document writer that generates factual claims.

CRITICAL RULES:
1. Generate EXACTLY ONE factual claim at a time
2. Each claim must be a complete, self-contained statement
3. Claims must be verifiable against the source documents
4. Do NOT generate opinions, speculation, or uncertain statements
5. Use specific data: names, dates, numbers, percentages when available
6. Keep claims concise (1-2 sentences max)
7. Write in the same language as the source documents

FORMAT:
- Output ONLY the claim text, nothing else
- No bullet points, numbers, or prefixes
- No explanations or meta-commentary
- DO NOT use <think> tags or reasoning blocks
- DO NOT explain your thought process
- Just output the claim directly

EXAMPLES OF GOOD CLAIMS:
- "El contrato tiene una vigencia de 24 meses a partir del 1 de enero de 2024."
- "La cláusula de penalización establece un 5% del valor total por incumplimiento."
- "ACME Corporation es responsable del mantenimiento del software según la sección 4.2."

EXAMPLES OF BAD CLAIMS:
- "El contrato parece establecer..." (uncertain)
- "Según mi análisis..." (meta-commentary)
- "1. El contrato..." (numbered/bulleted)
- "<think>Let me analyze...</think>" (thinking tags - NEVER USE)
"""

WRITER_USER_PROMPT_TEMPLATE = """Generate the NEXT factual claim for this document.

QUERY/TOPIC:
{query}

SOURCE CONTEXT (from documents):
{source_context}

PREVIOUSLY VERIFIED CLAIMS (build on these, don't repeat):
{verified_claims_text}

CLAIM NUMBER TO GENERATE: {claim_number}

Generate ONLY ONE new factual claim. Output the claim text only, nothing else."""

WRITER_FIRST_CLAIM_PROMPT = """Generate the FIRST factual claim for this document.

QUERY/TOPIC:
{query}

SOURCE CONTEXT (from documents):
{source_context}

Generate ONLY ONE factual claim to start the document. Output the claim text only, nothing else."""


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

        # Build user prompt
        if verified_claims:
            verified_text = self._format_verified_claims(verified_claims)
            user_prompt = WRITER_USER_PROMPT_TEMPLATE.format(
                query=query,
                source_context=source_context[:4000],  # Limit context
                verified_claims_text=verified_text,
                claim_number=claim_number,
            )
        else:
            # First claim - simpler prompt
            user_prompt = WRITER_FIRST_CLAIM_PROMPT.format(
                query=query,
                source_context=source_context[:4000],
            )

        # Generate claim
        claim_text = await self._call_vllm(
            system_prompt=WRITER_SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )

        # Clean the generated text
        claim_text = self._clean_claim_text(claim_text)

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

        verified_text = self._format_verified_claims(verified_claims)

        check_prompt = f"""Determine if this document is COMPLETE.

QUERY/TOPIC:
{query}

SOURCE CONTEXT:
{source_context[:2000]}

CLAIMS GENERATED SO FAR:
{verified_text}

Is the document complete? Answer ONLY "YES" or "NO".
- YES: All important information from the source has been captured
- NO: There is more relevant information to include"""

        response = await self._call_vllm(
            system_prompt="You are a document completion checker. Answer only YES or NO.",
            user_prompt=check_prompt,
        )

        response = response.strip().upper()
        is_complete = "YES" in response

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
            # Look for content that looks like a claim (sentence with period)
            # Skip thinking content patterns
            sentences = re.findall(r'[A-ZÁÉÍÓÚÑ][^<]*?[.!?]', original_text)
            for sentence in sentences:
                # Skip sentences that look like thinking/reasoning
                lower_sent = sentence.lower()
                if any(skip in lower_sent for skip in [
                    'let me', 'i need to', 'okay', 'the user', 'i should',
                    'first', 'looking at', 'based on', "let's"
                ]):
                    continue
                text = sentence.strip()
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
        Call vLLM for claim generation.

        Args:
            system_prompt: System prompt
            user_prompt: User prompt

        Returns:
            Generated text
        """
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                # Build request payload
                payload = {
                    "model": self._vllm_model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": self._temperature,
                    "max_tokens": self._max_tokens,
                    # Stop sequences to keep claims short
                    "stop": ["\n\n", "\n1.", "\n2.", "\n-", "\n•", "<think>"],
                    # Qwen3 specific: disable thinking mode
                    # This prevents <think>...</think> blocks in output
                    "extra_body": {
                        "chat_template_kwargs": {
                            "enable_thinking": False
                        }
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
# Singleton Instance
# =============================================================================

_writer_agent: Optional[WriterAgent] = None


def get_writer_agent() -> WriterAgent:
    """Get the global WriterAgent singleton."""
    global _writer_agent
    if _writer_agent is None:
        # Use configured values from settings
        temperature = getattr(settings, 'verified_claim_temperature', 0.3)
        _writer_agent = WriterAgent(temperature=temperature)
    return _writer_agent
