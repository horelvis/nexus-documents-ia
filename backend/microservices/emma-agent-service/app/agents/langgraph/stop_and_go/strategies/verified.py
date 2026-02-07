"""
VerifiedStrategy — wraps WriterAgent, _verify_claim logic,
VerifiedContextCache for the stop-and-go graph.

Like PredictiveStrategy, this delegates to existing modules.
The graph orchestrates the flow identically for both modes.
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List

from app.agents.langgraph.stop_and_go.strategy import register_strategy

logger = logging.getLogger(__name__)

# Fallback prompts for fact-checking (reused from original service)
FALLBACK_FACTCHECK_SYSTEM = (
    "Eres un asistente de verificación de hechos. Evalúa si una afirmación está respaldada por la evidencia.\n\n"
    "Responde SOLO con un objeto JSON (sin markdown, sin explicación):\n"
    '{"supported": true/false, "confidence": 0.0-1.0, "reason": "razón breve", '
    '"correction": "texto corregido o null"}\n\n'
    "Reglas:\n"
    "- supported=true si la evidencia respalda razonablemente o es consistente con la afirmación\n"
    "- Para documentos subidos: la afirmación fue generada A PARTIR de este documento, verifica que refleja el contenido con precisión\n"
    "- Prioriza evidencia de documentos internos/subidos. La evidencia web es complementaria.\n"
    "- Si la afirmación parafrasea o resume la evidencia correctamente, marca como respaldada con alta confianza\n"
    "- Cuando la evidencia web apoya la idea general de la afirmación, marca como respaldada\n"
    "- IMPORTANTE: 'correction' debe ser el TEXTO DE LA AFIRMACIÓN REESCRITO en el MISMO IDIOMA que la afirmación original, NO un meta-comentario sobre qué cambiar\n"
    "- Si la afirmación es mayormente correcta pero necesita ajustes menores, establece correction con el texto mejorado\n"
    "- Si la afirmación no se puede corregir, establece correction como null\n"
    "- NUNCA uses etiquetas <think>. Genera el JSON directamente.\n"
    "- Escribe 'reason' SIEMPRE en español."
)

FALLBACK_FACTCHECK_USER = (
    "AFIRMACIÓN A VERIFICAR:\n{claim_text}\n\n"
    "EVIDENCIA:\n{evidence_text}\n\n"
    "Evalúa si la afirmación está respaldada por la evidencia. Responde solo con JSON."
)


class VerifiedStrategy:
    """Strategy implementation for verified document generation mode."""

    def __init__(self):
        self._writer = None
        self._cache = None

    @property
    def mode(self) -> str:
        return "verified"

    async def initialize(self, state: dict) -> None:
        """Lazy-init writer agent and cache."""
        from app.services.verified_generation.writer_agent import get_writer_agent
        from app.services.verified_generation.verified_cache import get_verified_cache

        if self._writer is None:
            self._writer = get_writer_agent()
        if self._cache is None:
            self._cache = get_verified_cache()
            await self._cache.connect()

        # Clear prior session
        await self._cache.clear_session(state["tenant_id"], state["session_id"])

        # Store session metadata
        await self._cache.store_session_metadata(
            state["tenant_id"],
            state["session_id"],
            {
                "query": state["query"],
                "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
                "session_id": state["session_id"],
            },
        )

    async def extract_item(self, state: dict, source_context: str) -> Dict[str, Any]:
        """Generate next claim via WriterAgent."""
        from app.schemas.verified_generation import VerifiedClaim

        # Get verified claims from Redis for context
        verified_claims = await self._cache.get_verified_claims(
            state["tenant_id"], state["session_id"]
        )

        claim_position = len(verified_claims) + 1

        candidate = await self._writer.generate_next_claim(
            query=state["query"],
            verified_claims=verified_claims,
            source_context=source_context,
            claim_number=claim_position,
        )
        candidate.context_document_ids = state.get("context_document_ids", [])

        return {
            "id": candidate.id,
            "text": candidate.text,
            "type": "claim",
            "_raw_candidate": candidate.model_dump(),
            "event_data": {
                "claim_text": candidate.text,
                "claim_number": claim_position,
            },
        }

    async def evaluate_item(
        self,
        item: Dict[str, Any],
        evidence: List[Dict],
        state: dict,
    ) -> Dict[str, Any]:
        """Evaluate claim against evidence using LLM fact-checking."""
        claim_text = item.get("text", "")
        confidence_threshold = state.get("confidence_threshold", 0.7)
        mode_config = state.get("mode_config", {})
        auto_correct = mode_config.get("auto_correct", True)
        max_correction_attempts = mode_config.get("max_correction_attempts", 2)

        # No evidence → reject
        if not evidence:
            return {
                "status": "rejected",
                "confidence": 0.0,
                "reason": "No evidence found to support the claim",
                "correction": None,
                "evidence": [],
            }

        # Build evidence text for LLM
        evaluation = await self._llm_evaluate_claim(claim_text, evidence)

        # Determine status
        if evaluation["supported"] and evaluation["confidence"] >= confidence_threshold:
            status = "accepted"
        elif evaluation.get("correction") and auto_correct:
            status = "corrected"
        else:
            status = "rejected"

        return {
            "status": status,
            "confidence": evaluation["confidence"],
            "reason": evaluation.get("reason", ""),
            "correction": evaluation.get("correction"),
            "evidence": evidence,
        }

    def is_duplicate(self, item: Dict[str, Any], state: dict) -> bool:
        """Check word-overlap dedup against all previously extracted items."""
        new_text = item.get("text", "")
        if not new_text:
            return False

        new_words = set(new_text.lower().split())
        if len(new_words) < 3:
            return False

        threshold = 0.65
        for prev_item in state.get("all_extracted_items", []):
            prev_text = prev_item.get("text", "")
            if not prev_text:
                continue
            existing_words = set(prev_text.lower().split())
            if not existing_words:
                continue
            intersection = new_words & existing_words
            union = new_words | existing_words
            similarity = len(intersection) / len(union) if union else 0
            if similarity >= threshold:
                return True

        return False

    async def check_completion(self, state: dict, source_context: str) -> bool:
        """LLM completion check via WriterAgent."""
        verified_claims = await self._cache.get_verified_claims(
            state["tenant_id"], state["session_id"]
        )
        return await self._writer.check_completion(
            query=state["query"],
            verified_claims=verified_claims,
            source_context=source_context,
        )

    async def on_accepted(
        self,
        item: Dict[str, Any],
        evaluation: Dict[str, Any],
        state: dict,
    ) -> Dict[str, Any]:
        """Cache verified claim, return SSE event."""
        from app.schemas.verified_generation import VerifiedClaim, VerificationStatus

        status = evaluation.get("status", "accepted")
        is_corrected = status == "corrected"

        claim_text = evaluation.get("correction", item["text"]) if is_corrected else item["text"]
        original_text = item["text"] if is_corrected else None

        verified_claim = VerifiedClaim(
            id=item["id"],
            text=claim_text,
            original_text=original_text,
            status=VerificationStatus.CORRECTED if is_corrected else VerificationStatus.VERIFIED,
            confidence=evaluation.get("confidence", 0.0),
            evidence_document_ids=[
                e.get("document_id", "")
                for e in evaluation.get("evidence", [])
            ],
            generation_order=item.get("_raw_candidate", {}).get("generation_order", 0),
        )

        await self._cache.add_verified_claim(
            state["tenant_id"], state["session_id"], verified_claim
        )
        await self._cache.extend_ttl(state["tenant_id"], state["session_id"])

        if is_corrected:
            return {
                "event_type": "claim_corrected",
                "claim_id": item["id"],
                "data": {
                    "original_text": item["text"],
                    "corrected_text": claim_text,
                    "confidence": evaluation.get("confidence", 0.0),
                },
            }
        else:
            return {
                "event_type": "claim_verified",
                "claim_id": item["id"],
                "data": {
                    "claim_text": claim_text,
                    "confidence": evaluation.get("confidence", 0.0),
                    "evidence_count": len(evaluation.get("evidence", [])),
                },
            }

    async def on_rejected(
        self,
        item: Dict[str, Any],
        evaluation: Dict[str, Any],
        state: dict,
    ) -> Dict[str, Any]:
        """Return SSE event for rejected claim."""
        return {
            "event_type": "claim_rejected",
            "claim_id": item["id"],
            "data": {
                "claim_text": item.get("text", ""),
                "reason": evaluation.get("reason", "Unknown"),
            },
        }

    async def synthesize(self, state: dict) -> Dict[str, Any]:
        """Assemble final document from verified claims."""
        from app.services.verified_generation.service import VerifiedDocumentService
        from app.core.langfuse_config import langfuse_context

        final_claims = await self._cache.get_verified_claims(
            state["tenant_id"], state["session_id"]
        )

        # Assemble document using the existing Jinja2 template logic
        svc = VerifiedDocumentService.__new__(VerifiedDocumentService)
        document_text = svc._assemble_document(state["query"], final_claims)

        execution_time_ms = state.get("execution_time_ms", 0)

        # Calculate statistics
        avg_confidence = (
            sum(c.confidence for c in final_claims) / len(final_claims)
            if final_claims else 0.0
        )

        all_evidence_ids = set()
        for claim in final_claims:
            all_evidence_ids.update(claim.evidence_document_ids)

        # Update session metadata
        existing_meta = await self._cache.get_session_metadata(
            state["tenant_id"], state["session_id"]
        )
        existing_meta["execution_time_ms"] = execution_time_ms
        existing_meta["sources"] = list(state.get("sources_map", {}).values())
        await self._cache.store_session_metadata(
            state["tenant_id"], state["session_id"], existing_meta
        )

        # Langfuse scores
        try:
            langfuse_context.score("claims_verified", state.get("items_accepted", 0))
            langfuse_context.score("claims_rejected", state.get("items_rejected", 0))
            langfuse_context.score("avg_confidence", round(avg_confidence, 3))
            langfuse_context.score("execution_time_ms", execution_time_ms)
        except Exception:
            pass

        return {
            "session_id": state["session_id"],
            "document_text": document_text,
            "total_claims_generated": state.get("items_extracted", 0),
            "claims_verified": state.get("items_accepted", 0),
            "claims_corrected": state.get("items_corrected", 0),
            "claims_rejected": state.get("items_rejected", 0),
            "average_confidence": round(avg_confidence, 3),
            "execution_time_ms": execution_time_ms,
            "verification_time_ms": 0,  # not tracked per-item in graph mode
            "evidence_document_ids": list(all_evidence_ids),
            "sources": list(state.get("sources_map", {}).values()),
        }

    # =========================================================================
    # Private helpers
    # =========================================================================

    async def _llm_evaluate_claim(
        self,
        claim_text: str,
        evidence: List[Dict],
    ) -> Dict[str, Any]:
        """Evaluate a claim against evidence using LLM — extracted from original _verify_claim."""
        from app.services.langfuse_prompt_client import get_langfuse_prompt_client

        # Build evidence context (cap at ~8000 chars)
        MAX_EVIDENCE_CHARS = 8000
        evidence_parts = []
        total_chars = 0
        for e in evidence:
            source = e.get("source", "internal")
            if source == "web":
                label = f"[Web Source: {e.get('document_title', 'Unknown')} - {e.get('url', '')}]"
            elif source == "uploaded":
                label = f"[Uploaded Document: {e.get('document_title', 'Unknown')}]"
            else:
                label = f"[Internal Document: {e.get('document_title', 'Unknown')}]"
            part = f"{label}\n{e.get('text_excerpt', '')}"
            if total_chars + len(part) > MAX_EVIDENCE_CHARS:
                remaining = MAX_EVIDENCE_CHARS - total_chars
                if remaining > 100:
                    evidence_parts.append(part[:remaining] + "...")
                break
            evidence_parts.append(part)
            total_chars += len(part)
        evidence_text = "\n\n".join(evidence_parts)

        # Resolve prompts via Langfuse
        prompt_client = get_langfuse_prompt_client()
        sys_cached = await prompt_client.get_prompt(
            "emma_verified_factcheck_system",
            fallback=FALLBACK_FACTCHECK_SYSTEM,
        )
        system_prompt = sys_cached.content if sys_cached else FALLBACK_FACTCHECK_SYSTEM

        fc_variables = {"claim_text": claim_text, "evidence_text": evidence_text}
        user_cached = await prompt_client.get_prompt(
            "emma_verified_factcheck_user",
            variables=fc_variables,
            fallback=FALLBACK_FACTCHECK_USER.format(**fc_variables),
        )
        user_prompt = user_cached.content if user_cached else FALLBACK_FACTCHECK_USER.format(**fc_variables)

        evaluation = {
            "supported": False,
            "confidence": 0.0,
            "reason": "LLM evaluation failed",
            "correction": None,
        }

        try:
            from app.agents.llm_client import get_llm_client

            llm_client = await get_llm_client()
            llm_response = await llm_client.chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
                max_tokens=500,
                enable_thinking=False,
            )

            if llm_response and llm_response.content:
                content = llm_response.content.strip()
                # Clean thinking tags
                content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL)
                if '<think>' in content:
                    content = content[:content.find('<think>')]
                content = content.strip()
                # Clean markdown code blocks
                if content.startswith("```"):
                    content = content.split("```")[1]
                    if content.startswith("json"):
                        content = content[4:]
                    content = content.strip()

                parsed = False
                try:
                    result = json.loads(content)
                    parsed = True
                except json.JSONDecodeError:
                    json_match = re.search(r'\{[^{}]*"supported"[^{}]*\}', content, re.DOTALL)
                    if json_match:
                        try:
                            result = json.loads(json_match.group())
                            parsed = True
                        except json.JSONDecodeError:
                            pass

                if parsed:
                    evaluation = {
                        "supported": result.get("supported", False),
                        "confidence": float(result.get("confidence", 0.0)),
                        "reason": result.get("reason", ""),
                        "correction": result.get("correction"),
                    }
                else:
                    lower = content.lower()
                    if '"supported": true' in lower or '"supported":true' in lower:
                        evaluation = {
                            "supported": True,
                            "confidence": 0.7,
                            "reason": "Parsed from non-JSON response",
                            "correction": None,
                        }

        except Exception as e:
            logger.error(f"LLM claim evaluation failed: {e}")

        return evaluation


# Register at import time
register_strategy("verified", VerifiedStrategy())
