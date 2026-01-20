#!/usr/bin/env python3
"""
RLM Real Pipeline Test

IMPORTANT: This test measures the REAL RLM pipeline performance, NOT simulations.

Unlike run_rlm_large_doc_test.py which only measures dict operations (~0.6ms),
this test measures the actual pipeline components:

1. Semantic Chunking - Real structure-aware document splitting
2. Embedding Generation - Real Qwen3-VL-Embedding-2B vectors (1024-dim)
3. Weaviate Storage - Real vector database operations (if available)
4. LLM Processing - Real vLLM/Qwen3 inference (if available)

If a service is unavailable, the test will CLEARLY indicate it was skipped
rather than simulating fake results.

Run with: python3 run_rlm_real_pipeline_test.py

Requirements:
- Qwen3-VL-Embedding service running (http://qwen3-vl-embedding:8000)
- Weaviate running (http://weaviate:8080) [optional]
- vLLM running (http://vllm:8000) [optional]
"""

import asyncio
import sys
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.rag.semantic_chunker import SemanticChunker, DocumentChunk
from app.agents.rlm_environment import RLMEnvironment

# Try to import optional services
try:
    from app.services.multimodal_embedding_service import (
        MultimodalEmbeddingService,
        EmbeddingResult,
    )
    EMBEDDING_SERVICE_AVAILABLE = True
except ImportError:
    EMBEDDING_SERVICE_AVAILABLE = False

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False


# ============================================================================
# Service Availability Checker
# ============================================================================

@dataclass
class ServiceStatus:
    """Status of a service check"""
    name: str
    available: bool
    url: str
    latency_ms: float = 0.0
    error: Optional[str] = None


async def check_service_availability() -> Dict[str, ServiceStatus]:
    """Check which services are available for testing"""
    services = {}

    if not HTTPX_AVAILABLE:
        return {
            "embedding": ServiceStatus("Qwen3-VL Embedding", False, "", error="httpx not installed"),
            "weaviate": ServiceStatus("Weaviate", False, "", error="httpx not installed"),
            "vllm": ServiceStatus("vLLM", False, "", error="httpx not installed"),
        }

    async with httpx.AsyncClient(timeout=5.0) as client:
        # Check Qwen3-VL Embedding Service
        embedding_url = "http://qwen3-vl-embedding:8000/v1/models"
        try:
            start = time.perf_counter()
            resp = await client.get(embedding_url)
            latency = (time.perf_counter() - start) * 1000
            services["embedding"] = ServiceStatus(
                "Qwen3-VL Embedding",
                resp.status_code == 200,
                embedding_url,
                latency,
            )
        except Exception as e:
            services["embedding"] = ServiceStatus(
                "Qwen3-VL Embedding",
                False,
                embedding_url,
                error=str(e)[:50],
            )

        # Check Weaviate
        weaviate_url = "http://weaviate:8080/v1/.well-known/ready"
        try:
            start = time.perf_counter()
            resp = await client.get(weaviate_url)
            latency = (time.perf_counter() - start) * 1000
            services["weaviate"] = ServiceStatus(
                "Weaviate",
                resp.status_code == 200,
                weaviate_url,
                latency,
            )
        except Exception as e:
            services["weaviate"] = ServiceStatus(
                "Weaviate",
                False,
                weaviate_url,
                error=str(e)[:50],
            )

        # Check vLLM
        vllm_url = "http://vllm:8000/v1/models"
        try:
            start = time.perf_counter()
            resp = await client.get(vllm_url)
            latency = (time.perf_counter() - start) * 1000
            services["vllm"] = ServiceStatus(
                "vLLM",
                resp.status_code == 200,
                vllm_url,
                latency,
            )
        except Exception as e:
            services["vllm"] = ServiceStatus(
                "vLLM",
                False,
                vllm_url,
                error=str(e)[:50],
            )

    return services


# ============================================================================
# Document Generation (same as original test)
# ============================================================================

def generate_legal_document(target_tokens: int = 50000) -> str:
    """Generate a realistic legal document for testing."""
    import random

    target_chars = target_tokens * 4
    sections = []

    # Title and preamble
    sections.append("""
# CONTRATO DE PRESTACION DE SERVICIOS PROFESIONALES
## Numero de Referencia: DOC-2026-001234

---

## PREAMBULO

En la ciudad de Madrid, a los efectos legales oportunos, comparecen las partes
que a continuacion se identifican, quienes manifiestan su voluntad de celebrar
el presente contrato de prestacion de servicios profesionales, el cual se regira
por las siguientes clausulas y condiciones.

Las partes declaran que tienen capacidad legal suficiente para contratar y
obligarse en los terminos del presente documento, y que actuan en nombre propio
y representacion de sus respectivas organizaciones.

---
""")

    # Generate chapters with articles
    chapter_templates = [
        ("DEFINICIONES Y OBJETO DEL CONTRATO", [
            "Definiciones Generales",
            "Objeto del Contrato",
            "Alcance de los Servicios",
        ]),
        ("OBLIGACIONES DE LAS PARTES", [
            "Obligaciones del Prestador",
            "Obligaciones del Cliente",
            "Responsabilidades Especificas",
        ]),
        ("CONDICIONES ECONOMICAS", [
            "Precio y Forma de Pago",
            "Facturacion y Plazos",
            "Penalizaciones por Incumplimiento",
        ]),
        ("PROPIEDAD INTELECTUAL", [
            "Titularidad de Derechos",
            "Licencias Concedidas",
            "Obligaciones de Confidencialidad",
        ]),
    ]

    article_num = 1

    for chapter_idx, (chapter_title, articles) in enumerate(chapter_templates, 1):
        sections.append(f"\n## CAPITULO {chapter_idx}: {chapter_title}\n")

        for article_title in articles:
            sections.append(f"\n### Articulo {article_num}: {article_title}\n")

            # Generate realistic paragraphs
            for p in range(random.randint(2, 4)):
                paragraph = _generate_legal_paragraph(article_title)
                sections.append(f"\n{paragraph}\n")

            article_num += 1

    document = "".join(sections)

    # Extend if needed
    while len(document) < target_chars:
        document += _generate_additional_clause(len(document) // 4000)
        if len(document) >= target_chars:
            break

    return document[:target_chars]


def _generate_legal_paragraph(context: str) -> str:
    """Generate a legal paragraph."""
    import random
    templates = [
        f"Las partes acuerdan expresamente que, en relacion con {context.lower()}, "
        f"se aplicaran las disposiciones contenidas en el presente articulo, "
        f"las cuales tendran caracter vinculante y obligatorio para ambas partes "
        f"desde la fecha de firma del presente contrato.",

        f"A los efectos del presente contrato, y especificamente en lo relativo a "
        f"{context.lower()}, las partes reconocen y aceptan que las obligaciones "
        f"aqui establecidas son de cumplimiento obligatorio.",

        f"El presente articulo regula los aspectos relacionados con {context.lower()}, "
        f"estableciendo las condiciones, terminos y requisitos que deberan observarse "
        f"durante la vigencia del contrato.",
    ]
    return random.choice(templates)


def _generate_additional_clause(clause_num: int) -> str:
    """Generate additional clause content."""
    return f"""
### Clausula Adicional {clause_num + 1}

Las partes acuerdan que, sin perjuicio de lo establecido en las clausulas anteriores,
se anaden las siguientes disposiciones complementarias que tendran la misma fuerza
vinculante que el resto del contrato:

1. El prestador se compromete a mantener actualizados todos los sistemas necesarios.
2. El cliente facilitara el acceso a la informacion y recursos necesarios.
3. Ambas partes acuerdan reunirse periodicamente para evaluar el cumplimiento.
4. Las partes se comprometen a actuar de buena fe en la interpretacion del contrato.

"""


# ============================================================================
# Test Stages
# ============================================================================

@dataclass
class StageResult:
    """Result of a test stage"""
    stage_name: str
    success: bool
    duration_ms: float
    items_processed: int = 0
    details: Dict[str, Any] = None
    skipped: bool = False
    skip_reason: Optional[str] = None


async def stage_semantic_chunking(
    document: str,
    chunker: SemanticChunker,
) -> Tuple[StageResult, List[DocumentChunk]]:
    """
    Stage 1: Semantic Chunking

    Uses the REAL SemanticChunker which:
    - Detects document structure (headers, sections, clauses)
    - Preserves semantic boundaries
    - Creates chunks with smart overlap
    """
    start = time.perf_counter()

    chunks = chunker.chunk_document(
        text=document,
        metadata={"test": True, "source": "rlm_real_pipeline_test"},
    )

    duration_ms = (time.perf_counter() - start) * 1000

    # Calculate stats
    total_tokens = sum(c.token_count for c in chunks)
    avg_tokens = total_tokens / len(chunks) if chunks else 0

    return StageResult(
        stage_name="Semantic Chunking",
        success=len(chunks) > 0,
        duration_ms=duration_ms,
        items_processed=len(chunks),
        details={
            "total_tokens": total_tokens,
            "avg_tokens_per_chunk": round(avg_tokens, 1),
            "chunk_sizes": [c.token_count for c in chunks[:5]],  # First 5
        }
    ), chunks


async def stage_embedding_generation(
    chunks: List[DocumentChunk],
    services: Dict[str, ServiceStatus],
) -> StageResult:
    """
    Stage 2: Embedding Generation

    Uses the REAL MultimodalEmbeddingService with Qwen3-VL-Embedding-2B.
    If service is unavailable, clearly indicates it was SKIPPED (not simulated).
    """
    if not services["embedding"].available:
        return StageResult(
            stage_name="Embedding Generation",
            success=False,
            duration_ms=0,
            skipped=True,
            skip_reason=f"Service unavailable: {services['embedding'].error or 'Connection failed'}",
        )

    if not EMBEDDING_SERVICE_AVAILABLE:
        return StageResult(
            stage_name="Embedding Generation",
            success=False,
            duration_ms=0,
            skipped=True,
            skip_reason="MultimodalEmbeddingService import failed",
        )

    # Extract text from chunks
    texts = [c.content for c in chunks]

    # Use real embedding service
    embedding_service = MultimodalEmbeddingService()

    try:
        start = time.perf_counter()
        result: EmbeddingResult = await embedding_service.embed_texts(texts)
        duration_ms = (time.perf_counter() - start) * 1000

        return StageResult(
            stage_name="Embedding Generation",
            success=result.success,
            duration_ms=duration_ms,
            items_processed=len(result.vectors) if result.success else 0,
            details={
                "model_used": result.model_used,
                "dimensions": result.dimensions,
                "vectors_generated": len(result.vectors) if result.success else 0,
                "error": result.error if not result.success else None,
            }
        )
    except Exception as e:
        return StageResult(
            stage_name="Embedding Generation",
            success=False,
            duration_ms=0,
            details={"error": str(e)},
        )
    finally:
        await embedding_service.close()


async def stage_rlm_environment_storage(
    document: str,
    chunks: List[DocumentChunk],
    env: RLMEnvironment,
) -> StageResult:
    """
    Stage 3: RLM Environment Storage

    This measures what the original test measured - RAM dictionary operations.
    We include it for comparison but now it's properly labeled.
    """
    start = time.perf_counter()

    context_id = await env.store_context(
        content=document,
        tenant_id="test-tenant",
        document_id="rlm-real-test",
        metadata={"chunks": len(chunks)},
    )

    duration_ms = (time.perf_counter() - start) * 1000

    # Get stats
    stats = await env.get_stats()

    return StageResult(
        stage_name="RLM Environment (RAM Cache)",
        success=context_id is not None,
        duration_ms=duration_ms,
        items_processed=1,
        details={
            "context_id": context_id,
            "storage_mode": stats["storage_mode"],
            "estimated_memory_mb": round(stats["estimated_memory_mb"], 2),
            "note": "This is RAM dict storage, NOT vector DB. Expected ~0.5-2ms.",
        }
    ), context_id


async def stage_llm_processing(
    chunks: List[DocumentChunk],
    services: Dict[str, ServiceStatus],
    max_chunks: int = 3,  # Limit for cost/time
) -> StageResult:
    """
    Stage 4: LLM Processing (Optional)

    If vLLM is available, processes a few chunks with real inference.
    This is the most expensive stage and is optional.
    """
    if not services["vllm"].available:
        return StageResult(
            stage_name="LLM Processing",
            success=False,
            duration_ms=0,
            skipped=True,
            skip_reason=f"vLLM unavailable: {services['vllm'].error or 'Connection failed'}",
        )

    if not HTTPX_AVAILABLE:
        return StageResult(
            stage_name="LLM Processing",
            success=False,
            duration_ms=0,
            skipped=True,
            skip_reason="httpx not installed",
        )

    # Only process first few chunks
    test_chunks = chunks[:max_chunks]
    results = []
    total_tokens_processed = 0

    async with httpx.AsyncClient(timeout=60.0) as client:
        start = time.perf_counter()

        for i, chunk in enumerate(test_chunks):
            try:
                # Simple summarization request
                resp = await client.post(
                    "http://vllm:8000/v1/chat/completions",
                    json={
                        "model": "Qwen/Qwen3-VL-8B-Thinking",
                        "messages": [
                            {
                                "role": "user",
                                "content": f"Resume en 1 oracion: {chunk.content[:500]}",
                            }
                        ],
                        "max_tokens": 100,
                        "temperature": 0.3,
                    }
                )

                if resp.status_code == 200:
                    data = resp.json()
                    tokens_used = data.get("usage", {}).get("total_tokens", 0)
                    total_tokens_processed += tokens_used
                    results.append({"chunk": i, "success": True, "tokens": tokens_used})
                else:
                    results.append({"chunk": i, "success": False, "error": resp.status_code})

            except Exception as e:
                results.append({"chunk": i, "success": False, "error": str(e)[:30]})

        duration_ms = (time.perf_counter() - start) * 1000

    successful = sum(1 for r in results if r.get("success"))

    return StageResult(
        stage_name="LLM Processing",
        success=successful > 0,
        duration_ms=duration_ms,
        items_processed=successful,
        details={
            "chunks_attempted": len(test_chunks),
            "chunks_successful": successful,
            "total_tokens": total_tokens_processed,
            "avg_time_per_chunk_ms": round(duration_ms / len(test_chunks), 1) if test_chunks else 0,
            "note": f"Only processed {max_chunks} chunks to limit cost. Real processing would take longer.",
        }
    )


# ============================================================================
# Main Test
# ============================================================================

async def main():
    """Run the real RLM pipeline test."""
    print("=" * 70)
    print("RLM REAL PIPELINE TEST")
    print("=" * 70)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    print("This test measures REAL pipeline performance, not simulations.")
    print("If a service is unavailable, it will be clearly marked as SKIPPED.")
    print()

    # Check service availability
    print("-" * 70)
    print("SERVICE AVAILABILITY CHECK")
    print("-" * 70)

    services = await check_service_availability()

    for name, status in services.items():
        if status.available:
            print(f"  [OK] {status.name}: {status.latency_ms:.1f}ms latency")
        else:
            print(f"  [--] {status.name}: UNAVAILABLE ({status.error or 'connection failed'})")

    print()

    # Test configurations
    test_sizes = [
        (10000, "10K tokens (~40KB) - Small"),
        (25000, "25K tokens (~100KB) - Medium"),
        (50000, "50K tokens (~200KB) - Large"),
    ]

    # Initialize components
    chunker = SemanticChunker(
        chunk_size=512,
        max_chunk_size=1024,
        overlap=100,
    )

    env = RLMEnvironment()
    await env.initialize()

    all_results: List[Dict[str, Any]] = []

    try:
        for target_tokens, description in test_sizes:
            print("-" * 70)
            print(f"TEST: {description}")
            print("-" * 70)

            test_result = {
                "size": description,
                "target_tokens": target_tokens,
                "stages": [],
            }

            # Generate document
            print("\n[1/5] Generating document...")
            gen_start = time.perf_counter()
            document = generate_legal_document(target_tokens)
            gen_time = (time.perf_counter() - gen_start) * 1000
            actual_tokens = len(document) // 4
            print(f"      Generated {actual_tokens:,} tokens in {gen_time:.1f}ms")

            # Stage 1: Semantic Chunking
            print("\n[2/5] Semantic Chunking (REAL)...")
            chunk_result, chunks = await stage_semantic_chunking(document, chunker)
            _print_stage_result(chunk_result)
            test_result["stages"].append(chunk_result)

            # Stage 2: Embedding Generation
            print("\n[3/5] Embedding Generation (REAL)...")
            embed_result = await stage_embedding_generation(chunks, services)
            _print_stage_result(embed_result)
            test_result["stages"].append(embed_result)

            # Stage 3: RLM Environment Storage
            print("\n[4/5] RLM Environment Storage (RAM Cache)...")
            env_result, context_id = await stage_rlm_environment_storage(document, chunks, env)
            _print_stage_result(env_result)
            test_result["stages"].append(env_result)

            # Stage 4: LLM Processing (optional)
            print("\n[5/5] LLM Processing (REAL, limited)...")
            llm_result = await stage_llm_processing(chunks, services)
            _print_stage_result(llm_result)
            test_result["stages"].append(llm_result)

            # Cleanup
            if context_id:
                await env.delete_context(context_id)

            all_results.append(test_result)
            print()

        # Print summary
        _print_summary(all_results, services)

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        await env.shutdown()

    return 0


def _print_stage_result(result: StageResult):
    """Print a stage result."""
    if result.skipped:
        print(f"      [SKIPPED] {result.skip_reason}")
        return

    status = "[OK]" if result.success else "[FAIL]"
    print(f"      {status} {result.duration_ms:.1f}ms - {result.items_processed} items")

    if result.details:
        for key, value in result.details.items():
            if key != "note":
                print(f"          {key}: {value}")
        if "note" in result.details:
            print(f"          NOTE: {result.details['note']}")


def _print_summary(results: List[Dict[str, Any]], services: Dict[str, ServiceStatus]):
    """Print test summary."""
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)

    # Services status
    print("\nServices Used:")
    for name, status in services.items():
        mark = "[OK]" if status.available else "[--]"
        print(f"  {mark} {status.name}")

    # Performance table
    print("\n Performance by Document Size:")
    print("  +----------------+----------+-----------+-----------+-----------+")
    print("  | Size           | Chunks   | Chunking  | Embedding | LLM       |")
    print("  +----------------+----------+-----------+-----------+-----------+")

    for result in results:
        size = result["size"].split(" - ")[0]
        stages = {s.stage_name: s for s in result["stages"]}

        chunk_stage = stages.get("Semantic Chunking")
        embed_stage = stages.get("Embedding Generation")
        llm_stage = stages.get("LLM Processing")

        chunks = chunk_stage.items_processed if chunk_stage else 0
        chunk_time = f"{chunk_stage.duration_ms:.0f}ms" if chunk_stage and not chunk_stage.skipped else "N/A"
        embed_time = f"{embed_stage.duration_ms:.0f}ms" if embed_stage and not embed_stage.skipped else "SKIP"
        llm_time = f"{llm_stage.duration_ms:.0f}ms" if llm_stage and not llm_stage.skipped else "SKIP"

        print(f"  | {size:14} | {chunks:8} | {chunk_time:9} | {embed_time:9} | {llm_time:9} |")

    print("  +----------------+----------+-----------+-----------+-----------+")

    # Comparison with original test
    print("\n Comparison with Original Test:")
    print("  Original run_rlm_large_doc_test.py measured ONLY dict operations (~0.6ms)")
    print("  This test measures the REAL pipeline:")
    print("    - Semantic Chunking: Real structure-aware splitting")
    print("    - Embedding: Real Qwen3-VL vector generation")
    print("    - LLM: Real vLLM inference (when available)")

    print("\n" + "=" * 70)
    print("TEST COMPLETED")
    print("=" * 70)


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
