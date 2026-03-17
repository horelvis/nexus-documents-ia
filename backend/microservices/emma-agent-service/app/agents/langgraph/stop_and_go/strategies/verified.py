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

# Confidence cap for faithfulness-only verdicts (no external corroboration)
FIDELITY_CONFIDENCE_CAP = 0.80


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
                "status": "running",
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
        evidence,
        state: dict,
    ) -> Dict[str, Any]:
        """Two-tier claim evaluation: faithfulness + external corroboration.

        Tier 1 (Faithfulness): NLI-style check against source documents.
            "Does this claim accurately represent the source?"
        Tier 2 (External): Independent evidence from Weaviate, DOI, web, CENDOJ.
            "Is this claim supported by external sources?"

        The combined verdict determines verification_type:
            - corroborated: Tier 1 pass + Tier 2 pass → full confidence
            - fidelity_only: Tier 1 pass, no Tier 2 → capped at 0.80
            - independent: Tier 2 pass only (no source docs) → full confidence
            - unsupported: Neither tier → rejected
        """
        claim_text = item.get("text", "")
        confidence_threshold = state.get("confidence_threshold", 0.7)
        mode_config = state.get("mode_config", {})
        auto_correct = mode_config.get("auto_correct", True)

        # Parse tiered evidence
        if isinstance(evidence, dict) and "source" in evidence:
            source_evidence = evidence.get("source", [])
            external_evidence = evidence.get("external", [])
        else:
            # Legacy flat list — treat all as external
            source_evidence = []
            external_evidence = evidence if evidence else []

        all_evidence = source_evidence + external_evidence

        # No evidence at all → reject
        if not all_evidence:
            return {
                "status": "rejected",
                "confidence": 0.0,
                "reason": "No se encontró evidencia para respaldar la afirmación",
                "correction": None,
                "evidence": [],
                "verification_type": None,
            }

        # --- Tier 1: Faithfulness check (if source evidence exists) ---
        faithfulness = None
        if source_evidence:
            faithfulness = await self._llm_faithfulness_check(claim_text, source_evidence)

        # --- Tier 2: External corroboration (if external evidence exists) ---
        external = None
        if external_evidence:
            external = await self._llm_external_verify(claim_text, external_evidence)

        # --- Combine verdicts ---
        fidelity_cap = self._get_fidelity_cap(state)
        verification_type, combined_confidence, reason, correction = self._combine_verdicts(
            faithfulness, external, fidelity_cap=fidelity_cap
        )

        logger.info(
            f"Two-tier verdict: type={verification_type} conf={combined_confidence:.2f} "
            f"(faithfulness={faithfulness} | external={external})"
        )

        # Determine status
        if verification_type == "unsupported":
            if correction and auto_correct:
                # Faithfulness offered a correction — accept it as corrected
                # but keep it capped at fidelity_only confidence
                status = "corrected"
                verification_type = "fidelity_only"
                combined_confidence = min(
                    faithfulness.get("confidence", 0.5) if faithfulness else 0.5,
                    fidelity_cap,
                )
                logger.info(
                    f"Unsupported claim corrected by faithfulness tier → "
                    f"fidelity_only at {combined_confidence:.2f}"
                )
            else:
                status = "rejected"
        elif combined_confidence >= confidence_threshold:
            status = "accepted"
        elif correction and auto_correct:
            status = "corrected"
        else:
            status = "rejected"

        return {
            "status": status,
            "confidence": combined_confidence,
            "reason": reason,
            "correction": correction,
            "evidence": all_evidence,
            "verification_type": verification_type,
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
        verification_type = evaluation.get("verification_type")

        claim_text = evaluation.get("correction", item["text"]) if is_corrected else item["text"]
        original_text = item["text"] if is_corrected else None

        # Extract EXTERNAL evidence only as "validation sources".
        # Source-document evidence (uploaded docs matched via RLM) is NOT a
        # validation source — it's the generation source.  Showing it would
        # mislead the user into thinking the claim was independently verified.
        # The source document is already implicit in the verification_type
        # label (fidelity_only / corroborated).
        evidence_sources = []
        for e in evaluation.get("evidence", []):
            # Skip uploaded-document / source-document evidence
            src_type = e.get("source", "internal")
            if src_type == "uploaded" or src_type == "source_document":
                continue
            src_entry = {
                "id": e.get("document_id", ""),
                "title": e.get("document_title", ""),
                "source": src_type,
                "url": e.get("url", ""),
            }
            if src_type == "jurisprudence":
                src_entry["roj"] = e.get("roj", "")
                src_entry["ecli"] = e.get("ecli", "")
            evidence_sources.append(src_entry)

        verified_claim = VerifiedClaim(
            id=item["id"],
            text=claim_text,
            original_text=original_text,
            status=VerificationStatus.CORRECTED if is_corrected else VerificationStatus.VERIFIED,
            confidence=evaluation.get("confidence", 0.0),
            evidence_document_ids=[
                e.get("document_id", "")
                for e in evaluation.get("evidence", [])
                if e.get("source") not in ("uploaded", "source_document")
            ],
            evidence_sources=evidence_sources,
            verification_type=verification_type,
            verification_reason=evaluation.get("reason"),
            generation_order=item.get("_raw_candidate", {}).get("generation_order", 0),
        )

        await self._cache.add_verified_claim(
            state["tenant_id"], state["session_id"], verified_claim
        )
        await self._cache.extend_ttl(state["tenant_id"], state["session_id"])

        reason = evaluation.get("reason", "")

        if is_corrected:
            return {
                "event_type": "claim_corrected",
                "claim_id": item["id"],
                "data": {
                    "original_text": item["text"],
                    "corrected_text": claim_text,
                    "confidence": evaluation.get("confidence", 0.0),
                    "evidence_sources": evidence_sources,
                    "verification_type": verification_type,
                    "verification_reason": reason,
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
                    "evidence_sources": evidence_sources,
                    "verification_type": verification_type,
                    "verification_reason": reason,
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

        # DOI validation results from source document (pre-validated at initialization)
        doi_validations = state.get("source_doi_validations", [])

        # Generate a brief summary of the source document
        source_filenames = state.get("source_filenames", [])
        source_summary = await self._generate_source_summary(state)

        # Assemble document using the existing Jinja2 template logic
        svc = VerifiedDocumentService.__new__(VerifiedDocumentService)
        global_sources = list(state.get("sources_map", {}).values())
        document_text = svc._assemble_document(
            state["query"], final_claims, sources=global_sources,
            doi_validations=doi_validations,
            source_filenames=source_filenames,
            source_summary=source_summary,
        )

        execution_time_ms = state.get("execution_time_ms", 0)

        # Calculate statistics
        avg_confidence = (
            sum(c.confidence for c in final_claims) / len(final_claims)
            if final_claims else 0.0
        )

        all_evidence_ids = set()
        for claim in final_claims:
            all_evidence_ids.update(claim.evidence_document_ids)

        # Update session metadata (enrich for recovery)
        existing_meta = await self._cache.get_session_metadata(
            state["tenant_id"], state["session_id"]
        )
        existing_meta["status"] = "completed"
        existing_meta["document_text"] = document_text
        existing_meta["average_confidence"] = round(avg_confidence, 3)
        existing_meta["claims_verified"] = state.get("items_accepted", 0)
        existing_meta["claims_corrected"] = state.get("items_corrected", 0)
        existing_meta["claims_rejected"] = state.get("items_rejected", 0)
        existing_meta["execution_time_ms"] = execution_time_ms
        existing_meta["sources"] = list(state.get("sources_map", {}).values())
        existing_meta["doi_validations"] = doi_validations
        existing_meta["source_filenames"] = source_filenames
        existing_meta["source_summary"] = source_summary
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
            "doi_validations": doi_validations,
            "source_filenames": source_filenames,
            "source_summary": source_summary,
        }

    async def _generate_source_summary(self, state: dict) -> str:
        """Generate a brief summary of the source document via LLM.

        Uses Langfuse prompts (emma_verified_summary_system/user),
        following the same _resolve_prompts pattern as faithfulness
        and external verification.
        """
        source_context = state.get("source_context", "")
        if not source_context:
            return ""

        # Use first ~4000 chars for summary (enough to capture intro/abstract)
        preview = source_context[:4000]
        try:
            system_prompt, user_template = await self._resolve_prompts(
                "emma_verified_summary_system",
                "emma_verified_summary_user",
            )
            user_prompt = user_template.replace("{document_text}", preview)

            from langchain_core.messages import SystemMessage, HumanMessage
            from app.agents.llm_models import get_chat_model

            model = get_chat_model().bind(max_tokens=200, temperature=0.1)
            response = await model.ainvoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ])
            summary = response.content.strip() if response and response.content else ""
            logger.info(f"Source summary generated: {len(summary)} chars")
            return summary
        except Exception as e:
            logger.warning(f"Source summary generation failed: {e}")
            return ""

    # =========================================================================
    # Private helpers — Two-tier verification
    # =========================================================================

    def _get_fidelity_cap(self, state: dict) -> float:
        """Get fidelity confidence cap — sector override or default."""
        mode_config = state.get("mode_config", {})
        return mode_config.get("fidelity_confidence_cap", FIDELITY_CONFIDENCE_CAP)

    @staticmethod
    def _combine_verdicts(
        faithfulness: Dict[str, Any] | None,
        external: Dict[str, Any] | None,
        fidelity_cap: float = FIDELITY_CONFIDENCE_CAP,
    ) -> tuple:
        """Combine faithfulness and external verification into a final verdict.

        Returns (verification_type, confidence, reason, correction).
        """
        has_faithful = faithfulness and faithfulness.get("faithful")
        has_external = external and external.get("supported")
        f_conf = faithfulness.get("confidence", 0.0) if faithfulness else 0.0
        e_conf = external.get("confidence", 0.0) if external else 0.0
        f_reason = faithfulness.get("reason", "") if faithfulness else ""
        e_reason = external.get("reason", "") if external else ""
        correction = faithfulness.get("correction") if faithfulness else None

        if has_faithful and has_external:
            # Best case: faithful to source AND independently corroborated
            return (
                "corroborated",
                min(max(f_conf, e_conf), 0.99),
                f"Fiel al documento fuente y corroborado externamente. {e_reason}".strip(),
                correction,
            )
        elif has_faithful:
            # Source-faithful but no external evidence
            return (
                "fidelity_only",
                min(f_conf, fidelity_cap),
                f"Fiel al documento fuente (sin corroboración externa). {f_reason}".strip(),
                correction,
            )
        elif has_external:
            # No source doc, but external evidence supports it
            return (
                "independent",
                e_conf,
                f"Respaldado por evidencia independiente. {e_reason}".strip(),
                None,
            )
        else:
            # Neither tier passed
            reason_parts = []
            if faithfulness and not has_faithful:
                reason_parts.append(f"No fiel al fuente: {f_reason}")
            if external and not has_external:
                reason_parts.append(f"Sin respaldo externo: {e_reason}")
            if not faithfulness and not external:
                reason_parts.append("Sin evidencia disponible")
            return (
                "unsupported",
                0.0,
                " | ".join(reason_parts),
                correction,
            )

    async def _llm_faithfulness_check(
        self,
        claim_text: str,
        source_evidence: List[Dict],
    ) -> Dict[str, Any]:
        """Tier 1: Check if the claim faithfully represents the source document.

        This is an NLI-style entailment check — the claim (hypothesis) should
        be entailed by the source (premise). Not a fact-check, but a
        faithfulness check.
        """
        source_text = self._build_evidence_text(source_evidence, max_chars=6000)

        system_prompt, user_template = await self._resolve_prompts(
            "emma_verified_faithfulness_system",
            "emma_verified_faithfulness_user",
        )
        user_prompt = user_template.replace("{claim_text}", claim_text).replace("{source_text}", source_text)

        result = await self._call_llm_json(system_prompt, user_prompt, tier_label="faithfulness")

        correction = result.get("correction")
        # LLM sometimes returns the string "null" instead of JSON null
        if isinstance(correction, str) and correction.strip().lower() == "null":
            correction = None

        return {
            "faithful": result.get("faithful", False),
            "confidence": float(result.get("confidence", 0.0)),
            "reason": result.get("reason", ""),
            "correction": correction,
        }

    async def _llm_external_verify(
        self,
        claim_text: str,
        external_evidence: List[Dict],
    ) -> Dict[str, Any]:
        """Tier 2: Check if the claim is supported by independent evidence.

        Evidence here comes from Weaviate (excluding source docs), DOI
        validation, CENDOJ jurisprudence, or web search.
        """
        evidence_text = self._build_evidence_text(external_evidence, max_chars=8000)

        system_prompt, user_template = await self._resolve_prompts(
            "emma_verified_external_system",
            "emma_verified_external_user",
        )
        user_prompt = user_template.replace("{claim_text}", claim_text).replace("{evidence_text}", evidence_text)

        result = await self._call_llm_json(system_prompt, user_prompt, tier_label="external")

        return {
            "supported": result.get("supported", False),
            "confidence": float(result.get("confidence", 0.0)),
            "reason": result.get("reason", ""),
        }

    # =========================================================================
    # Shared LLM utilities
    # =========================================================================

    @staticmethod
    def _build_evidence_text(evidence: List[Dict], max_chars: int = 8000) -> str:
        """Build labeled evidence text from evidence list, capped at max_chars."""
        parts = []
        total = 0
        for e in evidence:
            source = e.get("source", "internal")
            if source == "doi":
                label = f"[DOI Validado: {e.get('document_title', 'Unknown')} - {e.get('url', '')}]"
            elif source == "doi_invalid":
                label = f"[⚠ DOI INVALIDO: {e.get('document_title', 'Unknown')}]"
            elif source == "doi_mismatch":
                label = f"[⚠ DOI NO CORRESPONDE: {e.get('document_title', 'Unknown')} - {e.get('url', '')}]"
            elif source == "crossref":
                label = f"[CrossRef: {e.get('document_title', 'Unknown')} - {e.get('url', '')}]"
            elif source == "citation_unverified":
                label = f"[⚠ CITA NO VERIFICABLE: {e.get('document_title', 'Unknown')}]"
            elif source == "web":
                label = f"[Web: {e.get('document_title', 'Unknown')} - {e.get('url', '')}]"
            elif source == "uploaded":
                label = f"[Documento Fuente: {e.get('document_title', 'Unknown')}]"
            elif source == "jurisprudence":
                label = f"[Jurisprudencia: {e.get('document_title', 'Unknown')} - {e.get('url', '')}]"
            else:
                label = f"[Documento Interno: {e.get('document_title', 'Unknown')}]"
            part = f"{label}\n{e.get('text_excerpt', '')}"
            if total + len(part) > max_chars:
                remaining = max_chars - total
                if remaining > 100:
                    parts.append(part[:remaining] + "...")
                break
            parts.append(part)
            total += len(part)
        return "\n\n".join(parts)

    async def _resolve_prompts(self, system_name: str, user_name: str) -> tuple:
        """Resolve a system+user prompt pair from Langfuse."""
        from app.services.langfuse_prompt_client import get_langfuse_prompt_client
        client = get_langfuse_prompt_client()
        sys_prompt = await client.get_prompt(system_name)
        usr_prompt = await client.get_prompt(user_name)
        return sys_prompt.content, usr_prompt.content

    async def _call_llm_json(
        self,
        system_prompt: str,
        user_prompt: str,
        tier_label: str = "eval",
    ) -> Dict[str, Any]:
        """Call LLM and parse JSON response with robust fallback parsing."""
        try:
            from langchain_core.messages import SystemMessage, HumanMessage
            from app.agents.llm_models import get_planner_model

            model = get_planner_model().bind(temperature=0.0, max_tokens=500, seed=42)
            llm_response = await model.ainvoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ])

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

                logger.debug(f"[{tier_label}] Raw LLM response: {content[:300]}")

                try:
                    parsed = json.loads(content)
                    logger.info(
                        f"[{tier_label}] LLM verdict: "
                        f"faithful={parsed.get('faithful', 'N/A')} "
                        f"supported={parsed.get('supported', 'N/A')} "
                        f"confidence={parsed.get('confidence', 'N/A')} "
                        f"reason={str(parsed.get('reason', ''))[:80]}"
                    )
                    return parsed
                except json.JSONDecodeError:
                    # Regex fallback: find the first JSON object in the response
                    json_match = re.search(r'\{[^{}]*\}', content, re.DOTALL)
                    if json_match:
                        try:
                            parsed = json.loads(json_match.group())
                            logger.info(f"[{tier_label}] LLM verdict (regex parsed): {parsed}")
                            return parsed
                        except json.JSONDecodeError:
                            pass

                # Last resort: keyword detection
                lower = content.lower()
                if '"faithful": true' in lower or '"supported": true' in lower:
                    logger.warning(f"[{tier_label}] LLM response parsed via keyword detection")
                    return {"faithful": True, "supported": True, "confidence": 0.7, "reason": "Parsed from non-JSON"}

                logger.warning(f"[{tier_label}] Could not parse LLM response: {content[:200]}")

        except Exception as e:
            logger.error(f"[{tier_label}] LLM evaluation call failed: {e}")

        return {}


# Register at import time
register_strategy("verified", VerifiedStrategy())
