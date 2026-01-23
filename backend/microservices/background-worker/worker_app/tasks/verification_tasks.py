"""
Celery tasks for claim verification.

Implements the "Verifier" component of the Agent Self-Verifies pattern.
Each task searches Weaviate for evidence and uses vLLM to evaluate
whether the evidence supports the given claim.

Task Flow:
    1. Receive claim text and context
    2. Search Weaviate for relevant evidence (hybrid search)
    3. Use vLLM to evaluate if evidence supports the claim
    4. If rejected but correctable, generate a correction
    5. Return VerificationResult
"""

import asyncio
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from worker_app.celery_app import celery_app

logger = logging.getLogger(__name__)

# Configuration from environment
WEAVIATE_SERVICE_URL = os.getenv("WEAVIATE_SERVICE_URL", "http://weaviate-service:8000")
VLLM_BASE_URL = os.getenv("VLLM_BASE_URL", "http://vllm:8000/v1")
VLLM_MODEL = os.getenv("VLLM_MODEL", "Qwen/Qwen3-4B")
MICROSERVICES_API_KEY = os.getenv("MICROSERVICES_API_KEY", "")

# Verification parameters
EVIDENCE_SEARCH_LIMIT = 5  # Max documents to search
SIMILARITY_THRESHOLD = 0.65  # Min similarity for evidence consideration
CONFIDENCE_THRESHOLD = 0.7  # Default confidence threshold


def _run_async(coro):
    """Run async coroutine in sync context."""
    return asyncio.run(coro)


async def _search_weaviate_evidence(
    claim_text: str,
    tenant_id: str,
    context_document_ids: Optional[List[str]] = None,
    collections: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Search Weaviate for evidence related to the claim.

    Uses hybrid search (semantic + keyword) to find relevant documents.

    Args:
        claim_text: The claim to find evidence for
        tenant_id: Tenant identifier
        context_document_ids: Optional specific documents to search
        collections: Optional collections to search

    Returns:
        List of evidence matches with similarity scores
    """
    # Build collection name from tenant_id (format: Nouxcube_{tenant_id}_documents)
    sanitized_tenant = tenant_id.replace("-", "_")
    collection_name = collections[0] if collections else f"Nouxcube_{sanitized_tenant}_documents"

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Use the weaviate-service search endpoint
            response = await client.post(
                f"{WEAVIATE_SERVICE_URL}/weaviate/collections/{collection_name}/search",
                headers={
                    "Content-Type": "application/json",
                    "X-API-Key": MICROSERVICES_API_KEY,
                },
                json={
                    "query": claim_text,
                    "tenant_id": tenant_id,
                    "limit": EVIDENCE_SEARCH_LIMIT,
                    "search_type": "hybrid",
                    "is_admin": True,  # Bypass ACL for verification
                },
            )

            if response.status_code == 200:
                data = response.json()
                results = data.get("results", [])

                # Transform to evidence format
                evidence = []
                for result in results:
                    # Calculate similarity (distance is inverse)
                    distance = result.get("distance", 1.0)
                    similarity = 1.0 - min(distance, 1.0)

                    if similarity >= SIMILARITY_THRESHOLD:
                        evidence.append({
                            "document_id": result.get("document_id", ""),
                            "document_title": result.get("title", ""),
                            "chunk_id": result.get("chunk_id"),
                            "text_excerpt": result.get("content", "")[:500],  # Limit excerpt length
                            "similarity_score": round(similarity, 3),
                        })

                logger.info(f"🔍 Found {len(evidence)} evidence matches for claim")
                return evidence

            else:
                logger.warning(f"⚠️ Weaviate search returned {response.status_code}")
                return []

    except Exception as e:
        logger.error(f"❌ Weaviate search failed: {e}")
        return []


async def _evaluate_claim_with_llm(
    claim_text: str,
    evidence: List[Dict[str, Any]],
    confidence_threshold: float = CONFIDENCE_THRESHOLD,
) -> Dict[str, Any]:
    """
    Use vLLM to evaluate if the evidence supports the claim.

    The LLM analyzes the claim against the evidence and returns:
    - supported: bool - whether evidence supports the claim
    - confidence: float - confidence in the assessment
    - correction: Optional[str] - suggested correction if not supported

    Args:
        claim_text: The claim to evaluate
        evidence: List of evidence documents
        confidence_threshold: Threshold for accepting claim

    Returns:
        Evaluation result dict
    """
    if not evidence:
        return {
            "supported": False,
            "confidence": 0.0,
            "reason": "No evidence found to support the claim",
            "correction": None,
        }

    # Build evidence context
    evidence_text = "\n\n".join([
        f"[Document: {e.get('document_title', 'Unknown')}]\n{e['text_excerpt']}"
        for e in evidence
    ])

    # Evaluation prompt
    system_prompt = """You are a fact-checking assistant. Your task is to evaluate if a claim is supported by the given evidence.

Respond ONLY with a JSON object (no markdown, no explanation):
{
    "supported": true/false,
    "confidence": 0.0-1.0,
    "reason": "brief explanation",
    "correction": "corrected claim text if not supported but correctable, else null"
}

Rules:
- supported=true only if evidence directly confirms the claim
- confidence reflects how strongly evidence supports/refutes
- correction should preserve meaning but fix factual errors
- If claim is completely unsupported, correction=null
- NEVER use <think> tags or reasoning blocks in your response
- Output the JSON directly, nothing else"""

    user_prompt = f"""CLAIM TO VERIFY:
{claim_text}

EVIDENCE:
{evidence_text}

Evaluate if the claim is supported by the evidence. Respond with JSON only."""

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{VLLM_BASE_URL}/chat/completions",
                headers={"Content-Type": "application/json"},
                json={
                    "model": VLLM_MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.1,  # Low temperature for consistent evaluation
                    "max_tokens": 500,
                    # Stop sequences to prevent extra output
                    "stop": ["<think>"],
                    # Qwen3 specific: disable thinking mode
                    "extra_body": {
                        "chat_template_kwargs": {
                            "enable_thinking": False
                        }
                    }
                },
            )

            if response.status_code == 200:
                data = response.json()
                content = data["choices"][0]["message"]["content"]

                # Parse JSON from response
                # Handle potential thinking tags or markdown
                content = content.strip()

                # Remove <think>...</think> blocks (Qwen3 thinking mode)
                content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL)
                # Handle unclosed <think> tags (truncated by max_tokens)
                if '<think>' in content:
                    content = content[:content.find('<think>')]
                content = content.strip()

                if content.startswith("```"):
                    content = content.split("```")[1]
                    if content.startswith("json"):
                        content = content[4:]
                    content = content.strip()

                # Try to extract JSON
                try:
                    result = json.loads(content)
                    return {
                        "supported": result.get("supported", False),
                        "confidence": float(result.get("confidence", 0.0)),
                        "reason": result.get("reason", ""),
                        "correction": result.get("correction"),
                    }
                except json.JSONDecodeError:
                    logger.warning(f"⚠️ Failed to parse LLM JSON: {content[:200]}")
                    # Fallback: try to extract values manually
                    supported = "true" in content.lower() and "supported" in content.lower()
                    return {
                        "supported": supported,
                        "confidence": 0.5,
                        "reason": "Could not parse LLM response",
                        "correction": None,
                    }

            else:
                logger.error(f"❌ vLLM returned {response.status_code}: {response.text}")
                return {
                    "supported": False,
                    "confidence": 0.0,
                    "reason": f"LLM evaluation failed: {response.status_code}",
                    "correction": None,
                }

    except Exception as e:
        logger.error(f"❌ LLM evaluation failed: {e}")
        return {
            "supported": False,
            "confidence": 0.0,
            "reason": f"LLM error: {str(e)}",
            "correction": None,
        }


async def _verify_claim(
    claim_id: str,
    claim_text: str,
    tenant_id: str,
    context_document_ids: Optional[List[str]] = None,
    collections: Optional[List[str]] = None,
    confidence_threshold: float = CONFIDENCE_THRESHOLD,
) -> Dict[str, Any]:
    """
    Core verification logic.

    1. Search Weaviate for evidence
    2. Evaluate claim against evidence using vLLM
    3. Return structured result

    Args:
        claim_id: Unique identifier for the claim
        claim_text: The claim text to verify
        tenant_id: Tenant identifier
        context_document_ids: Optional document IDs to search
        collections: Optional collections to search
        confidence_threshold: Minimum confidence to accept

    Returns:
        VerificationResult as dict
    """
    start_time = time.time()

    try:
        # Step 1: Search for evidence
        evidence = await _search_weaviate_evidence(
            claim_text=claim_text,
            tenant_id=tenant_id,
            context_document_ids=context_document_ids,
            collections=collections,
        )

        # Step 2: Evaluate claim with LLM
        evaluation = await _evaluate_claim_with_llm(
            claim_text=claim_text,
            evidence=evidence,
            confidence_threshold=confidence_threshold,
        )

        # Step 3: Determine status
        if evaluation["supported"] and evaluation["confidence"] >= confidence_threshold:
            status = "verified"
        elif evaluation["correction"]:
            status = "corrected"
        else:
            status = "rejected"

        # Calculate verification time
        verification_time_ms = int((time.time() - start_time) * 1000)

        # Build evidence matches
        evidence_matches = [
            {
                "document_id": e["document_id"],
                "document_title": e.get("document_title"),
                "chunk_id": e.get("chunk_id"),
                "text_excerpt": e["text_excerpt"],
                "similarity_score": e["similarity_score"],
                "supports_claim": evaluation["supported"],
            }
            for e in evidence
        ]

        result = {
            "claim_id": claim_id,
            "status": status,
            "confidence": evaluation["confidence"],
            "evidence": evidence_matches,
            "correction": evaluation.get("correction"),
            "rejection_reason": evaluation.get("reason") if status == "rejected" else None,
            "verification_time_ms": verification_time_ms,
            "verified_at": datetime.now(timezone.utc).isoformat(),
        }

        logger.info(
            f"✅ Claim verification complete: status={status}, "
            f"confidence={evaluation['confidence']:.2f}, time={verification_time_ms}ms"
        )

        return result

    except Exception as e:
        verification_time_ms = int((time.time() - start_time) * 1000)
        logger.error(f"❌ Claim verification failed: {e}")

        return {
            "claim_id": claim_id,
            "status": "error",
            "confidence": 0.0,
            "evidence": [],
            "correction": None,
            "rejection_reason": f"Verification error: {str(e)}",
            "verification_time_ms": verification_time_ms,
            "verified_at": datetime.now(timezone.utc).isoformat(),
        }


@celery_app.task(
    name="verification.verify_claim",
    bind=True,
    max_retries=2,
    default_retry_delay=5,
    time_limit=60,  # Hard timeout at 60 seconds
    soft_time_limit=55,  # Soft timeout at 55 seconds
)
def verify_claim_task(
    self,
    claim_id: str,
    claim_text: str,
    tenant_id: str,
    context_document_ids: Optional[List[str]] = None,
    collections: Optional[List[str]] = None,
    confidence_threshold: float = CONFIDENCE_THRESHOLD,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Celery task to verify a single claim.

    This is the main entry point called by the VerifiedDocumentService.
    It runs the async verification in a sync context.

    Args:
        claim_id: Unique identifier for the claim
        claim_text: The claim text to verify
        tenant_id: Tenant identifier
        context_document_ids: Optional document IDs to search
        collections: Optional collections to search
        confidence_threshold: Minimum confidence to accept
        session_id: Optional session ID for tracking

    Returns:
        VerificationResult as dict
    """
    logger.info(
        f"🔍 Starting claim verification: claim_id={claim_id[:16]}..., "
        f"tenant={tenant_id}"
    )

    try:
        result = _run_async(
            _verify_claim(
                claim_id=claim_id,
                claim_text=claim_text,
                tenant_id=tenant_id,
                context_document_ids=context_document_ids,
                collections=collections,
                confidence_threshold=confidence_threshold,
            )
        )

        # Add session ID to result for tracking
        if session_id:
            result["session_id"] = session_id

        return result

    except Exception as e:
        logger.error(f"❌ verify_claim_task failed: {e}")

        # Retry on transient errors
        if "timeout" in str(e).lower() or "connection" in str(e).lower():
            raise self.retry(exc=e)

        return {
            "claim_id": claim_id,
            "status": "error",
            "confidence": 0.0,
            "evidence": [],
            "correction": None,
            "rejection_reason": f"Task error: {str(e)}",
            "verification_time_ms": 0,
            "verified_at": datetime.now(timezone.utc).isoformat(),
            "session_id": session_id,
        }


@celery_app.task(
    name="verification.batch_verify_claims",
    bind=True,
    time_limit=300,  # 5 minute timeout for batch
)
def batch_verify_claims_task(
    self,
    claims: List[Dict[str, str]],
    tenant_id: str,
    context_document_ids: Optional[List[str]] = None,
    collections: Optional[List[str]] = None,
    confidence_threshold: float = CONFIDENCE_THRESHOLD,
) -> Dict[str, Any]:
    """
    Batch verify multiple claims (sequential execution).

    Note: This runs claims sequentially, not in parallel, to ensure
    each claim is verified against the most recent context.

    Args:
        claims: List of {"id": str, "text": str} dicts
        tenant_id: Tenant identifier
        context_document_ids: Optional document IDs to search
        collections: Optional collections to search
        confidence_threshold: Minimum confidence to accept

    Returns:
        Batch result with all verifications
    """
    logger.info(f"📦 Starting batch verification: {len(claims)} claims")

    start_time = time.time()
    results = []
    verified_count = 0
    rejected_count = 0
    corrected_count = 0

    for claim in claims:
        claim_id = claim.get("id", "")
        claim_text = claim.get("text", "")

        if not claim_text:
            continue

        result = _run_async(
            _verify_claim(
                claim_id=claim_id,
                claim_text=claim_text,
                tenant_id=tenant_id,
                context_document_ids=context_document_ids,
                collections=collections,
                confidence_threshold=confidence_threshold,
            )
        )

        results.append(result)

        # Track statistics
        status = result.get("status", "error")
        if status == "verified":
            verified_count += 1
        elif status == "rejected":
            rejected_count += 1
        elif status == "corrected":
            corrected_count += 1

    total_time_ms = int((time.time() - start_time) * 1000)

    return {
        "results": results,
        "total_claims": len(claims),
        "verified_count": verified_count,
        "rejected_count": rejected_count,
        "corrected_count": corrected_count,
        "total_time_ms": total_time_ms,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
