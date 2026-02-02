#!/usr/bin/env python3
"""
Benchmark para evaluación de modelos LLM en dominio legal.

Ejecuta preguntas contra el modelo vLLM directo y/o el pipeline RAG completo (Emma),
evaluando respuestas con LLM-as-judge (semántico) + keyword recall.

Uso:
    # Solo modelo directo, sin juez
    python scripts/benchmark_model.py --mode model --judge-provider none --verbose

    # Solo RAG pipeline
    python scripts/benchmark_model.py --mode rag --tenant-id 00000000-0000-0000-0000-000000000001

    # Comparativa completa
    python scripts/benchmark_model.py --mode both --tenant-id 00000000-0000-0000-0000-000000000001 --judge-provider openai
"""

import argparse
import asyncio
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx
import yaml


# ─────────────────────────────────────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class KeywordGroup:
    type: str  # "any_of" or "all_of"
    values: list[str]


@dataclass
class BenchmarkQuestion:
    id: str
    question: str
    domain: str
    difficulty: str
    expected_keywords: list[KeywordGroup]
    expected_laws: list[str]
    reference_answer: str


@dataclass
class JudgeScores:
    correctness: float = 0.0
    completeness: float = 0.0
    relevance: float = 0.0
    citation_accuracy: float = 0.0
    coherence: float = 0.0

    @property
    def overall(self) -> float:
        scores = [self.correctness, self.completeness, self.relevance,
                  self.citation_accuracy, self.coherence]
        return sum(scores) / len(scores)


@dataclass
class QuestionResult:
    question_id: str
    question: str
    domain: str
    difficulty: str
    answer: str
    latency_ms: float
    keyword_recall: float
    keyword_details: dict = field(default_factory=dict)
    judge_scores: Optional[JudgeScores] = None
    error: Optional[str] = None


@dataclass
class BenchmarkRun:
    mode: str  # "model" or "rag"
    model_name: str
    timestamp: str
    results: list[QuestionResult] = field(default_factory=list)

    @property
    def avg_keyword_recall(self) -> float:
        valid = [r.keyword_recall for r in self.results if r.error is None]
        return sum(valid) / len(valid) if valid else 0.0

    @property
    def avg_judge_overall(self) -> Optional[float]:
        valid = [r.judge_scores.overall for r in self.results
                 if r.judge_scores is not None and r.error is None]
        return sum(valid) / len(valid) if valid else None

    def avg_judge_dim(self, dim: str) -> Optional[float]:
        valid = [getattr(r.judge_scores, dim) for r in self.results
                 if r.judge_scores is not None and r.error is None]
        return sum(valid) / len(valid) if valid else None

    def latency_percentile(self, p: float) -> float:
        latencies = sorted(r.latency_ms for r in self.results if r.error is None)
        if not latencies:
            return 0.0
        idx = int(len(latencies) * p / 100)
        return latencies[min(idx, len(latencies) - 1)]


# ─────────────────────────────────────────────────────────────────────────────
# Load questions
# ─────────────────────────────────────────────────────────────────────────────

def load_questions(yaml_path: str) -> list[BenchmarkQuestion]:
    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    questions = []
    for q in data["questions"]:
        kw_groups = [KeywordGroup(type=g["type"], values=g["values"])
                     for g in q.get("expected_keywords", [])]
        questions.append(BenchmarkQuestion(
            id=q["id"],
            question=q["question"],
            domain=q["domain"],
            difficulty=q["difficulty"],
            expected_keywords=kw_groups,
            expected_laws=q.get("expected_laws", []),
            reference_answer=q.get("reference_answer", ""),
        ))
    return questions


# ─────────────────────────────────────────────────────────────────────────────
# Query backends
# ─────────────────────────────────────────────────────────────────────────────

async def query_vllm(question: str, config: argparse.Namespace) -> tuple[str, float]:
    """Query vLLM or OpenAI-compatible API (including OpenRouter). Returns (answer, latency_ms)."""
    url = f"{config.vllm_url}/chat/completions"
    body = {
        "model": config.vllm_model,
        "messages": [
            {"role": "system", "content": "Eres un asistente legal experto en derecho español. Responde de forma precisa citando la legislación aplicable."},
            {"role": "user", "content": question},
        ],
        "max_tokens": 2048,
        "temperature": 0.6,
        "stream": False,
    }
    headers = {}
    if config.model_api_key:
        headers["Authorization"] = f"Bearer {config.model_api_key}"

    async with httpx.AsyncClient(timeout=120) as client:
        t0 = time.perf_counter()
        resp = await client.post(url, json=body, headers=headers)
        latency = (time.perf_counter() - t0) * 1000
        resp.raise_for_status()
        data = resp.json()
        answer = data["choices"][0]["message"]["content"]
        # Strip thinking tags if present
        answer = re.sub(r"<think>.*?</think>", "", answer, flags=re.DOTALL).strip()
        return answer, latency


async def query_emma_rag(question: str, tenant_id: str, config: argparse.Namespace) -> tuple[str, float]:
    """Query Emma RAG pipeline via SSE streaming. Returns (answer, latency_ms)."""
    url = f"{config.emma_url}/emma/query/stream"
    api_key = config.api_key
    body = {
        "query": question,
        "tenant_id": tenant_id,
        "query_type": "search",
        "is_admin": True,
        "deep_reasoning": True,
    }
    headers = {"X-API-Key": api_key, "Content-Type": "application/json"}

    answer = ""
    async with httpx.AsyncClient(timeout=180) as client:
        t0 = time.perf_counter()
        async with client.stream("POST", url, json=body, headers=headers) as resp:
            resp.raise_for_status()
            event_type = None
            async for line in resp.aiter_lines():
                line = line.strip()
                if line.startswith("event:"):
                    event_type = line[6:].strip()
                elif line.startswith("data:") and event_type:
                    data_str = line[5:].strip()
                    if not data_str:
                        continue
                    try:
                        data = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    if event_type == "done" and "answer" in data:
                        answer = data["answer"]
                    elif event_type == "complete" and "answer" in data:
                        answer = data["answer"]
                    elif event_type == "content" and "content" in data:
                        # Accumulate streaming content as fallback
                        if not answer:
                            answer += data["content"]

        latency = (time.perf_counter() - t0) * 1000
    return answer, latency


# ─────────────────────────────────────────────────────────────────────────────
# Evaluation: Keywords
# ─────────────────────────────────────────────────────────────────────────────

def evaluate_keywords(answer: str, keyword_groups: list[KeywordGroup]) -> tuple[float, dict]:
    """
    Compute keyword recall with any_of/all_of semantics.
    Returns (recall_score, details_dict).
    """
    if not keyword_groups:
        return 1.0, {"groups": [], "note": "no keywords defined"}

    answer_lower = answer.lower()
    matched = 0
    details = []

    for group in keyword_groups:
        values_lower = [v.lower() for v in group.values]

        if group.type == "any_of":
            found = [v for v in values_lower if v in answer_lower]
            hit = len(found) > 0
            details.append({
                "type": "any_of",
                "values": group.values,
                "matched": found,
                "hit": hit,
            })
        else:  # all_of
            found = [v for v in values_lower if v in answer_lower]
            hit = len(found) == len(values_lower)
            details.append({
                "type": "all_of",
                "values": group.values,
                "matched": found,
                "hit": hit,
            })

        if hit:
            matched += 1

    recall = matched / len(keyword_groups)
    return recall, {"groups": details, "recall": recall}


# ─────────────────────────────────────────────────────────────────────────────
# Evaluation: LLM-as-Judge
# ─────────────────────────────────────────────────────────────────────────────

JUDGE_PROMPT = """\
Eres un evaluador experto en derecho español. Evalúa la respuesta del modelo comparándola con la respuesta de referencia.

**Pregunta**: {question}

**Respuesta de referencia**: {reference}

**Respuesta del modelo**: {answer}

Evalúa la respuesta del modelo en estas 5 dimensiones (0-10):

1. **correctness**: Corrección jurídica de la información proporcionada.
2. **completeness**: Completitud respecto a los puntos clave de la referencia.
3. **relevance**: Pertinencia y foco en la pregunta formulada.
4. **citation_accuracy**: Precisión en las citas legales (leyes, artículos, decretos).
5. **coherence**: Claridad, estructura y facilidad de comprensión.

Responde EXCLUSIVAMENTE con un JSON válido (sin markdown, sin texto adicional):
{{"correctness": X, "completeness": X, "relevance": X, "citation_accuracy": X, "coherence": X}}
"""


async def evaluate_with_judge(
    question: str, answer: str, reference: str, config: argparse.Namespace
) -> JudgeScores:
    """Use an LLM judge to score the answer on 5 dimensions."""
    prompt = JUDGE_PROMPT.format(question=question, reference=reference, answer=answer)

    if config.judge_provider == "openai":
        return await _judge_openai(prompt, config)
    elif config.judge_provider == "anthropic":
        return await _judge_anthropic(prompt, config)
    elif config.judge_provider == "vllm":
        return await _judge_vllm(prompt, config)
    else:
        raise ValueError(f"Unknown judge provider: {config.judge_provider}")


async def _judge_openai(prompt: str, config: argparse.Namespace) -> JudgeScores:
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"}
    body = {
        "model": config.judge_model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 256,
        "temperature": 0.0,
    }
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(url, json=body, headers=headers)
        resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"]
    return _parse_judge_response(text)


async def _judge_anthropic(prompt: str, config: argparse.Namespace) -> JudgeScores:
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": os.environ["ANTHROPIC_API_KEY"],
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    body = {
        "model": config.judge_model,
        "max_tokens": 256,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0,
    }
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(url, json=body, headers=headers)
        resp.raise_for_status()
        text = resp.json()["content"][0]["text"]
    return _parse_judge_response(text)


async def _judge_vllm(prompt: str, config: argparse.Namespace) -> JudgeScores:
    url = f"{config.vllm_url}/chat/completions"
    body = {
        "model": config.vllm_model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 256,
        "temperature": 0.0,
        "stream": False,
    }
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(url, json=body)
        resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"]
    return _parse_judge_response(text)


def _parse_judge_response(text: str) -> JudgeScores:
    """Extract JSON scores from judge response, tolerating markdown fences."""
    # Strip markdown code fences
    text = re.sub(r"```json\s*", "", text)
    text = re.sub(r"```\s*", "", text)
    text = text.strip()

    # Find JSON object
    match = re.search(r"\{[^}]+\}", text)
    if not match:
        raise ValueError(f"Could not parse judge response: {text[:200]}")

    data = json.loads(match.group())
    return JudgeScores(
        correctness=float(data.get("correctness", 0)),
        completeness=float(data.get("completeness", 0)),
        relevance=float(data.get("relevance", 0)),
        citation_accuracy=float(data.get("citation_accuracy", 0)),
        coherence=float(data.get("coherence", 0)),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Orchestrator
# ─────────────────────────────────────────────────────────────────────────────

async def run_benchmark(
    questions: list[BenchmarkQuestion], mode: str, config: argparse.Namespace
) -> BenchmarkRun:
    """Run benchmark for a single mode (model or rag)."""
    model_name = config.vllm_model if mode == "model" else f"emma-rag({config.vllm_model})"
    run = BenchmarkRun(
        mode=mode,
        model_name=model_name,
        timestamp=datetime.now().isoformat(),
    )

    total = len(questions)
    for i, q in enumerate(questions, 1):
        prefix = f"[{i}/{total}] [{q.domain}] {q.id}"
        print(f"  {prefix} ... ", end="", flush=True)

        try:
            if mode == "model":
                answer, latency = await query_vllm(q.question, config)
            else:
                answer, latency = await query_emma_rag(q.question, config.tenant_id, config)

            kw_recall, kw_details = evaluate_keywords(answer, q.expected_keywords)

            judge_scores = None
            if config.judge_provider != "none":
                try:
                    judge_scores = await evaluate_with_judge(
                        q.question, answer, q.reference_answer, config
                    )
                except Exception as e:
                    print(f"judge error: {e}", end=" ")

            result = QuestionResult(
                question_id=q.id,
                question=q.question,
                domain=q.domain,
                difficulty=q.difficulty,
                answer=answer,
                latency_ms=round(latency, 1),
                keyword_recall=round(kw_recall, 3),
                keyword_details=kw_details,
                judge_scores=judge_scores,
            )

            judge_str = f"judge={judge_scores.overall:.1f}" if judge_scores else "no-judge"
            print(f"kw={kw_recall:.2f} {judge_str} {latency:.0f}ms")

            if config.verbose and judge_scores:
                print(f"         C={judge_scores.correctness:.0f} Co={judge_scores.completeness:.0f} "
                      f"R={judge_scores.relevance:.0f} Ci={judge_scores.citation_accuracy:.0f} "
                      f"Ch={judge_scores.coherence:.0f}")

        except Exception as e:
            print(f"ERROR: {e}")
            result = QuestionResult(
                question_id=q.id, question=q.question, domain=q.domain,
                difficulty=q.difficulty, answer="", latency_ms=0,
                keyword_recall=0, error=str(e),
            )

        run.results.append(result)

    return run


# ─────────────────────────────────────────────────────────────────────────────
# Output
# ─────────────────────────────────────────────────────────────────────────────

def print_run_summary(run: BenchmarkRun):
    """Print summary for a single run."""
    print(f"\n{'─' * 50}")
    print(f"  {run.mode.upper()} — {run.model_name}")
    print(f"{'─' * 50}")

    errors = sum(1 for r in run.results if r.error)
    print(f"  Preguntas: {len(run.results)} ({errors} errores)")
    print(f"  Keyword Recall (avg):  {run.avg_keyword_recall:.3f}")

    if run.avg_judge_overall is not None:
        print(f"  Judge Overall (avg):   {run.avg_judge_overall:.2f}/10")
        for dim in ["correctness", "completeness", "relevance", "citation_accuracy", "coherence"]:
            val = run.avg_judge_dim(dim)
            if val is not None:
                print(f"    {dim:20s}: {val:.2f}")

    print(f"  Latencia p50:          {run.latency_percentile(50):.0f} ms")
    print(f"  Latencia p90:          {run.latency_percentile(90):.0f} ms")


def print_comparison_table(model_run: Optional[BenchmarkRun], rag_run: Optional[BenchmarkRun]):
    """Print side-by-side comparison when mode=both."""
    if not model_run or not rag_run:
        return

    print(f"\n{'=' * 64}")
    print(f"  BENCHMARK COMPARATIVO | {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  Model: {model_run.model_name}")
    print(f"{'=' * 64}")
    print(f"  {'Métrica':<28s} {'Modelo':>8s} {'RAG':>8s} {'Δ':>8s}")
    print(f"  {'─' * 56}")

    rows = [
        ("Keyword Recall (avg)", model_run.avg_keyword_recall, rag_run.avg_keyword_recall, False),
    ]

    if model_run.avg_judge_overall is not None and rag_run.avg_judge_overall is not None:
        rows.insert(0, ("Judge Overall (avg)", model_run.avg_judge_overall, rag_run.avg_judge_overall, False))
        for dim in ["correctness", "completeness", "citation_accuracy"]:
            m_val = model_run.avg_judge_dim(dim)
            r_val = rag_run.avg_judge_dim(dim)
            if m_val is not None and r_val is not None:
                rows.append((f"  Judge {dim}", m_val, r_val, False))

    rows.append(("Latencia p50 (ms)", model_run.latency_percentile(50), rag_run.latency_percentile(50), True))
    rows.append(("Latencia p90 (ms)", model_run.latency_percentile(90), rag_run.latency_percentile(90), True))

    for label, m_val, r_val, is_latency in rows:
        if is_latency:
            delta = ""
            print(f"  {label:<28s} {m_val:>8.0f} {r_val:>8.0f} {delta:>8s}")
        else:
            if m_val > 0:
                pct = ((r_val - m_val) / m_val) * 100
                delta = f"{pct:+.0f}%"
            else:
                delta = "N/A"
            fmt = ".3f" if m_val <= 1 else ".2f"
            print(f"  {label:<28s} {m_val:>8{fmt}} {r_val:>8{fmt}} {delta:>8s}")

    print(f"  {'=' * 56}\n")


def save_results(runs: list[BenchmarkRun], output_dir: str, config: argparse.Namespace):
    """Save benchmark results as JSON."""
    os.makedirs(output_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    modes = "+".join(r.mode for r in runs)
    model_slug = config.vllm_model.replace("/", "_")
    filename = f"benchmark_{ts}_{modes}_{model_slug}.json"
    path = os.path.join(output_dir, filename)

    def serialize(obj):
        if hasattr(obj, "__dataclass_fields__"):
            return asdict(obj)
        return str(obj)

    payload = {
        "timestamp": datetime.now().isoformat(),
        "config": {
            "vllm_model": config.vllm_model,
            "vllm_url": config.vllm_url,
            "judge_provider": config.judge_provider,
            "judge_model": config.judge_model,
            "emma_url": config.emma_url,
            "tenant_id": getattr(config, "tenant_id", None),
        },
        "runs": [asdict(r) for r in runs],
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=serialize)

    print(f"Resultados guardados en: {path}")
    return path


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Benchmark para evaluación de modelos LLM en dominio legal",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--mode", choices=["model", "rag", "both"], default="both",
                        help="Modo de ejecución (default: both)")
    parser.add_argument("--tenant-id", default="00000000-0000-0000-0000-000000000001",
                        help="Tenant ID para RAG (default: on-premise default)")
    parser.add_argument("--judge-provider", choices=["openai", "anthropic", "vllm", "none"],
                        default="none", help="Proveedor LLM para juez semántico (default: none)")
    parser.add_argument("--judge-model", default="gpt-4o-mini",
                        help="Modelo del juez (default: gpt-4o-mini)")
    parser.add_argument("--vllm-url", default=os.getenv("VLLM_BASE_URL", "http://localhost:8001/v1"),
                        help="URL base de vLLM (default: http://localhost:8001/v1)")
    parser.add_argument("--vllm-model", default=os.getenv("VLLM_MODEL", "horelvis/boe-legal-qwen-7b-awq"),
                        help="Modelo vLLM (default: horelvis/boe-legal-qwen-7b-awq)")
    parser.add_argument("--model-api-key", default=os.getenv("MODEL_API_KEY", ""),
                        help="API key para el endpoint del modelo (OpenRouter, OpenAI, etc.)")
    parser.add_argument("--emma-url", default=os.getenv("EMMA_URL", "http://localhost:8009"),
                        help="URL de Emma Agent Service (default: http://localhost:8009)")
    parser.add_argument("--api-key", default=os.getenv("MICROSERVICES_API_KEY", ""),
                        help="API key para Emma (default: $MICROSERVICES_API_KEY)")
    parser.add_argument("--output-dir", default=None,
                        help="Directorio de salida (default: scripts/benchmark_results/)")
    parser.add_argument("--questions-file", default=None,
                        help="Archivo YAML de preguntas (default: config/benchmark_questions.yaml)")
    parser.add_argument("--verbose", action="store_true", help="Mostrar detalles por pregunta")
    return parser.parse_args()


async def main():
    config = parse_args()

    # Resolve paths relative to script location
    script_dir = Path(__file__).parent
    service_dir = script_dir.parent

    if config.questions_file is None:
        config.questions_file = str(service_dir / "config" / "benchmark_questions.yaml")
    if config.output_dir is None:
        config.output_dir = str(script_dir / "benchmark_results")

    # Validate
    if config.mode in ("rag", "both") and not config.api_key:
        print("ERROR: Se requiere --api-key o $MICROSERVICES_API_KEY para modo RAG")
        sys.exit(1)

    # Load questions
    questions = load_questions(config.questions_file)
    print(f"\n{'=' * 64}")
    print(f"  BENCHMARK LLM LEGAL — {len(questions)} preguntas")
    print(f"  Modelo: {config.vllm_model}")
    print(f"  Modo: {config.mode} | Juez: {config.judge_provider}")
    print(f"{'=' * 64}\n")

    runs: list[BenchmarkRun] = []
    model_run = None
    rag_run = None

    if config.mode in ("model", "both"):
        print("▶ Ejecutando: MODELO DIRECTO")
        model_run = await run_benchmark(questions, "model", config)
        runs.append(model_run)
        print_run_summary(model_run)

    if config.mode in ("rag", "both"):
        print("\n▶ Ejecutando: RAG PIPELINE (Emma)")
        rag_run = await run_benchmark(questions, "rag", config)
        runs.append(rag_run)
        print_run_summary(rag_run)

    if config.mode == "both":
        print_comparison_table(model_run, rag_run)

    save_results(runs, config.output_dir, config)


if __name__ == "__main__":
    asyncio.run(main())
