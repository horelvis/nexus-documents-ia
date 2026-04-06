#!/usr/bin/env python3
"""
E2E test: graph_rag source_evidence + unified config validation.

Validates:
1. Entity extraction with unified patterns (all domains)
2. graph_rag tool produces source_evidence reasoning steps
3. SSE event stream includes source_evidence with required fields
4. Tool selection works without sector filtering
5. 9B model parameters (response quality, no truncation)

Usage:
    python scripts/test_e2e_graph_rag.py
    python scripts/test_e2e_graph_rag.py --emma-url http://localhost:8019 --verbose
"""

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx


# ── Config ──────────────────────────────────────────────────────────────
EMMA_URL = os.getenv("EMMA_URL", "http://localhost:8019")
TENANT_ID = os.getenv("TENANT_ID", "00000000-0000-0000-0000-000000000001")
API_KEY = os.getenv("MICROSERVICES_API_KEY", "")

# Load from .env if not set
if not API_KEY:
    env_path = os.path.join(os.path.dirname(__file__), "..", "..", "docker", ".env")
    if os.path.exists(env_path):
        for line in open(env_path):
            if line.startswith("MICROSERVICES_API_KEY="):
                API_KEY = line.strip().split("=", 1)[1]
                break


# ── Data classes ────────────────────────────────────────────────────────

@dataclass
class SSEEvent:
    event_type: str
    data: Dict[str, Any]
    raw: str = ""


@dataclass
class TestCase:
    name: str
    query: str
    # What we expect to see
    expect_tools: List[str]  # tool names that should be called
    expect_source_evidence: bool  # should source_evidence reasoning step appear
    expect_entities: List[str]  # entity types we expect in extraction
    expect_answer_keywords: List[str]  # keywords in final answer
    # What we actually got
    events: List[SSEEvent] = field(default_factory=list)
    tools_called: List[str] = field(default_factory=list)
    source_evidence: List[Dict] = field(default_factory=list)
    reasoning_steps: List[Dict] = field(default_factory=list)
    final_answer: str = ""
    latency_ms: float = 0.0
    error: Optional[str] = None
    passed: bool = False


# ── Test cases ──────────────────────────────────────────────────────────

TEST_CASES = [
    TestCase(
        name="graph_rag_relationship_query",
        query="Quién representa a Javier Martinez en sus casos legales?",
        expect_tools=["graph_rag"],
        expect_source_evidence=True,
        expect_entities=["persona"],
        expect_answer_keywords=[],  # depends on data
    ),
    TestCase(
        name="smart_search_persona",
        query="Busca los contratos de María García",
        expect_tools=["smart_search"],
        expect_source_evidence=False,
        expect_entities=[],
        expect_answer_keywords=[],
    ),
    TestCase(
        name="graph_rag_legal_entity",
        query="Qué relación existe entre la LGT y el IRPF?",
        expect_tools=["graph_rag"],
        expect_source_evidence=True,
        expect_entities=[],
        expect_answer_keywords=[],
    ),
    TestCase(
        name="count_query",
        query="Cuántos documentos hay indexados?",
        expect_tools=["structural_query", "list_sources"],  # Either is valid
        expect_source_evidence=False,
        expect_entities=[],
        expect_answer_keywords=["601"],
    ),
    TestCase(
        name="mixed_domain_entities",
        query="Busca la factura de Pedro del Valle por 2.500,00 € del Art. 1902",
        expect_tools=["smart_search"],
        expect_source_evidence=False,
        expect_entities=["persona", "importe", "articulo"],
        expect_answer_keywords=[],
    ),
]


# ── SSE stream consumer ────────────────────────────────────────────────

async def stream_query(query: str, emma_url: str = "", tenant_id: str = "", verbose: bool = False) -> tuple[List[SSEEvent], float]:
    """Send query to Emma SSE endpoint and collect all events."""
    url = f"{emma_url or EMMA_URL}/emma/query/stream"
    body = {
        "query": query,
        "tenant_id": tenant_id or TENANT_ID,
        "is_admin": True,
    }
    headers = {
        "X-API-Key": API_KEY,
        "Content-Type": "application/json",
    }

    events: List[SSEEvent] = []

    async with httpx.AsyncClient(timeout=240) as client:
        t0 = time.perf_counter()
        try:
            async with client.stream("POST", url, json=body, headers=headers) as resp:
                if resp.status_code != 200:
                    body_text = ""
                    async for chunk in resp.aiter_bytes():
                        body_text += chunk.decode(errors="replace")
                    return [SSEEvent("error", {"message": f"HTTP {resp.status_code}: {body_text[:200]}"})], 0

                event_type = ""
                data_buffer = ""

                async for line in resp.aiter_lines():
                    line = line.strip()

                    if not line:
                        # Empty line = end of event
                        if event_type and data_buffer:
                            try:
                                data = json.loads(data_buffer)
                            except json.JSONDecodeError:
                                data = {"raw": data_buffer}
                            evt = SSEEvent(event_type, data, data_buffer)
                            events.append(evt)
                            if verbose:
                                _print_event(evt)
                        event_type = ""
                        data_buffer = ""
                        continue

                    if line.startswith("event:"):
                        event_type = line[6:].strip()
                    elif line.startswith("data:"):
                        chunk = line[5:].strip()
                        data_buffer = chunk if not data_buffer else data_buffer + chunk

        except httpx.ReadTimeout:
            events.append(SSEEvent("error", {"message": "Read timeout (240s)"}))
        except Exception as e:
            events.append(SSEEvent("error", {"message": str(e)}))

        latency = (time.perf_counter() - t0) * 1000

    return events, latency


def _print_event(evt: SSEEvent):
    """Pretty-print an SSE event for verbose mode."""
    if evt.event_type in ("token", "first_token"):
        return  # Skip noisy token events
    data_str = json.dumps(evt.data, ensure_ascii=False, default=str)
    if len(data_str) > 200:
        data_str = data_str[:200] + "..."
    print(f"  [{evt.event_type}] {data_str}")


# ── Analysis ────────────────────────────────────────────────────────────

import re as _re
_TOOL_CALL_RE = _re.compile(r"^(smart_search|graph_rag|structural_query|get_document_content|"
                            r"analyze_domain|web_search|search_jurisprudence|list_sources|"
                            r"query_connector|generate_document|forge_document|send_email|"
                            r"verified_generation|predictive_analysis|terminate)\(")


def analyze_events(tc: TestCase):
    """Extract metrics from collected SSE events."""
    for evt in tc.events:
        # Collect tool calls from agent_reasoning events
        if evt.event_type == "agent_reasoning":
            step = evt.data
            step_type = step.get("type", "")

            # Detect tool calls from detail field (e.g., "smart_search(query=...)")
            detail = step.get("detail", "")
            m = _TOOL_CALL_RE.search(detail)
            if m:
                tool_name = m.group(1)
                if tool_name not in tc.tools_called:
                    tc.tools_called.append(tool_name)

            if step_type == "source_evidence":
                try:
                    evidence = json.loads(step.get("content", "[]"))
                    tc.source_evidence = evidence if isinstance(evidence, list) else []
                except (json.JSONDecodeError, TypeError):
                    pass
            tc.reasoning_steps.append(step)

        # Extract final answer from complete event
        elif evt.event_type == "complete":
            tc.final_answer = evt.data.get("answer", "")
            # Also check reasoning_steps in complete payload
            for step in evt.data.get("reasoning_steps", []):
                if step.get("type") == "source_evidence":
                    try:
                        evidence = json.loads(step.get("content", "[]"))
                        if isinstance(evidence, list) and evidence:
                            tc.source_evidence = evidence
                    except (json.JSONDecodeError, TypeError):
                        pass
                if step.get("type") == "tool_call":
                    tool_name = step.get("source", "")
                    if tool_name and tool_name not in tc.tools_called:
                        tc.tools_called.append(tool_name)

        elif evt.event_type == "error":
            tc.error = evt.data.get("message", str(evt.data))


def validate_test(tc: TestCase) -> List[str]:
    """Validate test case results. Returns list of failure messages."""
    failures: List[str] = []

    if tc.error:
        failures.append(f"Error: {tc.error}")
        return failures

    if not tc.final_answer:
        failures.append("No final answer received")

    # Check at least one expected tool was called (OR logic, not AND)
    if tc.expect_tools:
        found_any = any(t in tc.tools_called for t in tc.expect_tools)
        if not found_any:
            failures.append(f"None of expected tools {tc.expect_tools} called. Called: {tc.tools_called}")

    # Check source_evidence
    if tc.expect_source_evidence and not tc.source_evidence:
        # Soft check — graph_rag may not find evidence for all queries
        failures.append(f"Expected source_evidence but none found (graph may be empty for this query)")

    if tc.source_evidence:
        # Validate source_evidence structure
        for i, src in enumerate(tc.source_evidence):
            for field_name in ("document_id", "document_title", "relationship"):
                if field_name not in src:
                    failures.append(f"source_evidence[{i}] missing '{field_name}'")

    # Check answer keywords
    answer_lower = tc.final_answer.lower()
    for kw in tc.expect_answer_keywords:
        if kw.lower() not in answer_lower:
            failures.append(f"Answer missing keyword '{kw}'")

    # Basic quality checks for 9B
    if tc.final_answer and len(tc.final_answer) < 20:
        failures.append(f"Answer too short ({len(tc.final_answer)} chars) — possible 9B truncation")

    return failures


# ── Entity extraction test (offline) ───────────────────────────────────

def test_entity_extraction() -> List[str]:
    """Test unified entity patterns without hitting the API."""
    failures: List[str] = []

    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from app.agents.langgraph.sectors.config import UNIFIED_ENTITY_PATTERNS
        from app.agents.langgraph.sectors.entity_extractor import extract_entities

        cases = [
            ("factura de Javier Martinez por 1.500,00 €", {"persona", "importe"}),
            ("Art. 1902 del Código Civil", {"articulo"}),
            ("Ana de la Fuente contratos del 15/03/2024", {"persona", "fecha"}),
            ("expediente núm. 2024/1234 BOE-A-2024", {"expediente", "boe"}),
            ("NHC 12345 paciente CIE-10-MC A12.3", {"paciente", "procedimiento"}),
        ]

        for query, expected_types in cases:
            entities = extract_entities(query, UNIFIED_ENTITY_PATTERNS)
            found_types = set(entities.keys())
            missing = expected_types - found_types
            if missing:
                failures.append(f"Entity extraction '{query}': missing types {missing}, got {found_types}")

    except Exception as e:
        failures.append(f"Entity extraction import error: {e}")

    return failures


# ── Main ────────────────────────────────────────────────────────────────

async def main():
    parser = argparse.ArgumentParser(description="E2E test: graph_rag + unified config")
    parser.add_argument("--emma-url", default=EMMA_URL)
    parser.add_argument("--tenant-id", default=TENANT_ID)
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--cases", nargs="*", help="Run specific test cases by name")
    args = parser.parse_args()

    emma_url = args.emma_url
    tenant_id = args.tenant_id

    print(f"{'='*60}")
    print(f"E2E Test: graph_rag source_evidence + unified config")
    print(f"Emma URL: {emma_url}")
    print(f"Tenant:   {tenant_id}")
    print(f"{'='*60}\n")

    # Phase 1: Offline entity extraction test
    print("[Phase 1] Entity extraction (unified patterns)")
    entity_failures = test_entity_extraction()
    if entity_failures:
        for f in entity_failures:
            print(f"  FAIL: {f}")
    else:
        print(f"  PASS: all entity patterns working")

    # Phase 2: Health check
    print("\n[Phase 2] Service health check")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{emma_url}/health")
            if resp.status_code == 200:
                print(f"  PASS: service healthy")
            else:
                print(f"  FAIL: health check returned {resp.status_code}")
                return
    except Exception as e:
        print(f"  FAIL: cannot reach {EMMA_URL}: {e}")
        return

    # Phase 3: SSE stream tests
    print(f"\n[Phase 3] SSE stream tests ({len(TEST_CASES)} cases)")

    cases = TEST_CASES
    if args.cases:
        cases = [tc for tc in TEST_CASES if tc.name in args.cases]

    total_passed = 0
    total_failed = 0
    results_summary: List[Dict] = []

    for tc in cases:
        print(f"\n  --- {tc.name} ---")
        print(f"  Query: {tc.query}")

        tc.events, tc.latency_ms = await stream_query(tc.query, emma_url=emma_url, tenant_id=tenant_id, verbose=args.verbose)
        analyze_events(tc)

        failures = validate_test(tc)
        tc.passed = len(failures) == 0

        if tc.passed:
            total_passed += 1
            print(f"  PASS ({tc.latency_ms:.0f}ms)")
        else:
            total_failed += 1
            for f in failures:
                print(f"  FAIL: {f}")
            print(f"  ({tc.latency_ms:.0f}ms)")

        # Summary
        print(f"  Tools called: {tc.tools_called}")
        if tc.source_evidence:
            print(f"  Source evidence: {len(tc.source_evidence)} items")
            for src in tc.source_evidence[:3]:
                conf = f" (conf: {src['confidence']:.2f})" if src.get('confidence') is not None else ""
                print(f"    - {src.get('relationship', '?')} | {src.get('document_title', '?')}{conf}")
        if tc.final_answer:
            preview = tc.final_answer[:150].replace("\n", " ")
            print(f"  Answer: {preview}...")

        results_summary.append({
            "name": tc.name,
            "passed": tc.passed,
            "latency_ms": round(tc.latency_ms),
            "tools": tc.tools_called,
            "source_evidence_count": len(tc.source_evidence),
            "answer_length": len(tc.final_answer),
            "failures": failures,
        })

    # Final report
    print(f"\n{'='*60}")
    print(f"RESULTS: {total_passed} passed, {total_failed} failed, "
          f"{len(entity_failures)} entity issues")
    print(f"{'='*60}")

    # Save results
    results_path = os.path.join(
        os.path.dirname(__file__), "benchmark_results", "e2e_graph_rag_results.json"
    )
    os.makedirs(os.path.dirname(results_path), exist_ok=True)
    with open(results_path, "w") as f:
        json.dump({
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "emma_url": emma_url,
            "tenant_id": tenant_id,
            "entity_extraction_failures": entity_failures,
            "test_results": results_summary,
        }, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved to: {results_path}")

    sys.exit(1 if total_failed > 0 or entity_failures else 0)


if __name__ == "__main__":
    asyncio.run(main())
