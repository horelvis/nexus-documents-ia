#!/usr/bin/env python3
"""
Comprehensive Model Comparison Test via OpenRouter v2

Tests multiple LLM models with real-world scenarios:
1. Social Agent (brief responses, Spanish)
2. Tool Calling (function calling capability)
3. Thinking/Reasoning (chain of thought)
4. Legal Text Generation (contracts, formal documents)
5. RAG Context Usage (using provided documents)

Usage:
    cd backend
    python3 scripts/test_models_openrouter_v2.py
"""

import os
import sys
import json
import time
import re
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime

# Load .env from docker directory
env_path = os.path.join(os.path.dirname(__file__), "..", "docker", ".env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())

import httpx

# =============================================================================
# Configuration
# =============================================================================

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

# Models to test (focusing on capable models)
MODELS_TO_TEST = [
    ("qwen/qwen3-8b", "Qwen3 8B"),
    ("qwen/qwen-2.5-7b-instruct", "Qwen 2.5 7B"),
    ("mistralai/mistral-7b-instruct", "Mistral 7B"),
    ("meta-llama/llama-3.1-8b-instruct", "LLaMA 3.1 8B"),
    ("google/gemma-2-9b-it", "Gemma 2 9B"),
]

# =============================================================================
# Test Categories
# =============================================================================

# 1. SOCIAL AGENT TESTS
SOCIAL_SYSTEM_PROMPT = """Eres Emma, asistente de IA. Responde SOLO en español.
Reglas: máximo 2 oraciones, 1 emoji, no inventes datos."""

SOCIAL_TESTS = [
    {
        "name": "Saludo",
        "messages": [
            {"role": "system", "content": SOCIAL_SYSTEM_PROMPT},
            {"role": "user", "content": "Hola, ¿qué tal?"}
        ],
        "evaluate": lambda r: {
            "spanish": not any('\u4e00' <= c <= '\u9fff' or '\uac00' <= c <= '\ud7af' for c in r),
            "brief": len(re.split(r'[.!?]+', r)) <= 3,
            "has_emoji": bool(re.search(r'[\U0001F300-\U0001F9FF]', r)),
        }
    },
    {
        "name": "Tiempo sin contexto",
        "messages": [
            {"role": "system", "content": SOCIAL_SYSTEM_PROMPT},
            {"role": "user", "content": "¿Qué tiempo hace en Madrid?"}
        ],
        "evaluate": lambda r: {
            "spanish": not any('\u4e00' <= c <= '\u9fff' for c in r),
            "no_invented_temp": not bool(re.search(r'\d+\s*°', r)),  # Should NOT invent temperature
        }
    },
]

# 2. TOOL CALLING TESTS
TOOL_CALLING_SYSTEM = """Eres un asistente que puede usar herramientas.
Cuando necesites información externa, usa las herramientas disponibles.
Responde siempre en español."""

TOOLS_DEFINITION = [
    {
        "type": "function",
        "function": {
            "name": "buscar_documentos",
            "description": "Busca documentos en el repositorio del usuario",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Términos de búsqueda"},
                    "tipo": {"type": "string", "enum": ["contrato", "factura", "informe", "todos"]},
                    "limit": {"type": "integer", "description": "Número máximo de resultados"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_clima",
            "description": "Obtiene información del clima actual",
            "parameters": {
                "type": "object",
                "properties": {
                    "ciudad": {"type": "string", "description": "Nombre de la ciudad"}
                },
                "required": ["ciudad"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calcular_plazos",
            "description": "Calcula plazos legales según normativa española",
            "parameters": {
                "type": "object",
                "properties": {
                    "tipo_plazo": {"type": "string", "enum": ["recurso", "prescripcion", "caducidad"]},
                    "fecha_inicio": {"type": "string", "description": "Fecha en formato YYYY-MM-DD"},
                    "normativa": {"type": "string", "description": "Ley aplicable"}
                },
                "required": ["tipo_plazo", "fecha_inicio"]
            }
        }
    }
]

TOOL_TESTS = [
    {
        "name": "Buscar contratos",
        "messages": [
            {"role": "system", "content": TOOL_CALLING_SYSTEM},
            {"role": "user", "content": "Busca todos los contratos de Telefónica del año pasado"}
        ],
        "tools": TOOLS_DEFINITION,
        "evaluate": lambda r, tc: {
            "called_tool": tc is not None,
            "correct_tool": tc.get("name") == "buscar_documentos" if tc else False,
            "has_query": "telefónica" in tc.get("arguments", {}).get("query", "").lower() if tc else False,
        }
    },
    {
        "name": "Consultar clima",
        "messages": [
            {"role": "system", "content": TOOL_CALLING_SYSTEM},
            {"role": "user", "content": "¿Qué tiempo hace hoy en Barcelona?"}
        ],
        "tools": TOOLS_DEFINITION,
        "evaluate": lambda r, tc: {
            "called_tool": tc is not None,
            "correct_tool": tc.get("name") == "consultar_clima" if tc else False,
            "correct_city": "barcelona" in tc.get("arguments", {}).get("ciudad", "").lower() if tc else False,
        }
    },
    {
        "name": "Calcular plazos legales",
        "messages": [
            {"role": "system", "content": TOOL_CALLING_SYSTEM},
            {"role": "user", "content": "Tengo una multa de tráfico del 15 de enero de 2024. ¿Cuánto tiempo tengo para recurrir?"}
        ],
        "tools": TOOLS_DEFINITION,
        "evaluate": lambda r, tc: {
            "called_tool": tc is not None,
            "correct_tool": tc.get("name") == "calcular_plazos" if tc else False,
            "tipo_recurso": tc.get("arguments", {}).get("tipo_plazo") == "recurso" if tc else False,
        }
    },
]

# 3. THINKING/REASONING TESTS
THINKING_SYSTEM = """Eres un asistente legal experto. Cuando analices casos complejos:
1. Primero razona paso a paso (puedes usar <think>...</think> para tu razonamiento interno)
2. Luego proporciona tu conclusión
Responde siempre en español."""

THINKING_TESTS = [
    {
        "name": "Análisis despido",
        "messages": [
            {"role": "system", "content": THINKING_SYSTEM},
            {"role": "user", "content": """Un trabajador con contrato indefinido desde 2018 ha sido despedido
alegando bajo rendimiento. No hay apercibimientos previos ni evaluaciones negativas documentadas.
El trabajador cobra 2.500€/mes. ¿Es procedente el despido? ¿Qué indemnización correspondería?"""}
        ],
        "max_tokens": 800,
        "evaluate": lambda r: {
            "has_reasoning": len(r) > 200,  # Should have substantial analysis
            "mentions_improcedente": "improcedente" in r.lower(),
            "calculates_compensation": bool(re.search(r'\d+.*€|€.*\d+|días.*salario|33.*días', r.lower())),
            "cites_law": any(term in r.lower() for term in ["estatuto", "trabajadores", "art", "ley"]),
            "spanish": not any('\u4e00' <= c <= '\u9fff' for c in r),
        }
    },
    {
        "name": "Cláusula abusiva",
        "messages": [
            {"role": "system", "content": THINKING_SYSTEM},
            {"role": "user", "content": """En un contrato de alquiler aparece esta cláusula:
"El arrendatario renuncia expresamente a su derecho de adquisición preferente y acepta
que cualquier daño en la vivienda, independientemente de su causa, será responsabilidad suya."
¿Es válida esta cláusula?"""}
        ],
        "max_tokens": 600,
        "evaluate": lambda r: {
            "identifies_issues": any(term in r.lower() for term in ["abusiv", "nul", "ilegal", "no válid"]),
            "mentions_lau": any(term in r.lower() for term in ["lau", "arrendamiento", "urbano"]),
            "explains_why": len(r) > 150,
            "spanish": not any('\u4e00' <= c <= '\u9fff' for c in r),
        }
    },
]

# 4. LEGAL TEXT GENERATION TESTS
LEGAL_GEN_SYSTEM = """Eres un asistente legal especializado en redacción de documentos.
Genera textos legales formales, precisos y conformes a la legislación española.
Usa lenguaje jurídico apropiado. Responde siempre en español."""

LEGAL_GEN_TESTS = [
    {
        "name": "Cláusula confidencialidad",
        "messages": [
            {"role": "system", "content": LEGAL_GEN_SYSTEM},
            {"role": "user", "content": """Redacta una cláusula de confidencialidad para un contrato
de prestación de servicios. Debe incluir: definición de información confidencial,
obligaciones del receptor, duración de 3 años, y penalización por incumplimiento."""}
        ],
        "max_tokens": 800,
        "evaluate": lambda r: {
            "formal_language": any(term in r.lower() for term in ["parte", "obligación", "compromete", "presente"]),
            "includes_definition": "información confidencial" in r.lower() or "datos confidenciales" in r.lower(),
            "includes_duration": "3 años" in r.lower() or "tres años" in r.lower() or "36 meses" in r.lower(),
            "includes_penalty": any(term in r.lower() for term in ["penaliz", "indemniz", "sanción", "incumplimiento"]),
            "proper_structure": len(r) > 300,
            "spanish": not any('\u4e00' <= c <= '\u9fff' for c in r),
        }
    },
    {
        "name": "Carta despido disciplinario",
        "messages": [
            {"role": "system", "content": LEGAL_GEN_SYSTEM},
            {"role": "user", "content": """Genera una carta de despido disciplinario para un empleado
que ha faltado injustificadamente 5 días consecutivos.
Datos: Empresa "Tech Solutions SL", empleado "Juan García López", puesto "Desarrollador Senior".
Fecha efectos: 15 de febrero de 2024."""}
        ],
        "max_tokens": 800,
        "evaluate": lambda r: {
            "includes_company": "tech solutions" in r.lower(),
            "includes_employee": "juan garcía" in r.lower() or "juan garcia" in r.lower(),
            "includes_cause": any(term in r.lower() for term in ["falta", "ausencia", "injustificad"]),
            "includes_date": "15" in r and ("febrero" in r.lower() or "02" in r),
            "cites_statute": any(term in r.lower() for term in ["estatuto", "trabajadores", "art", "54"]),
            "formal_structure": len(r) > 400,
            "spanish": not any('\u4e00' <= c <= '\u9fff' for c in r),
        }
    },
]

# 5. RAG CONTEXT TESTS
RAG_SYSTEM = """Eres Emma, asistente legal de NouxCubeIA.
Responde basándote ÚNICAMENTE en el contexto proporcionado.
Si la información no está en el contexto, indícalo.
Responde en español."""

RAG_CONTEXT = """
DOCUMENTO: Contrato de Arrendamiento - Ref: ARR-2024-0156
Fecha: 10 de enero de 2024
Arrendador: María López Fernández (DNI: 12345678A)
Arrendatario: Pedro Sánchez Ruiz (DNI: 87654321B)
Inmueble: Calle Mayor 45, 3º B, 28013 Madrid
Renta mensual: 1.200€
Duración: 5 años (hasta 10 de enero de 2029)
Fianza: 2.400€ (2 mensualidades)
Cláusula especial: Se permite tener una mascota de hasta 10kg.
"""

RAG_TESTS = [
    {
        "name": "Pregunta sobre contrato",
        "messages": [
            {"role": "system", "content": RAG_SYSTEM},
            {"role": "user", "content": f"Contexto:\n{RAG_CONTEXT}\n\nPregunta: ¿Cuánto es la renta mensual y hasta cuándo dura el contrato?"}
        ],
        "evaluate": lambda r: {
            "correct_rent": "1.200" in r or "1200" in r,
            "correct_duration": "2029" in r or "5 años" in r.lower() or "cinco años" in r.lower(),
            "no_hallucination": "2.400" not in r or "fianza" in r.lower(),  # Shouldn't confuse rent with deposit
            "spanish": not any('\u4e00' <= c <= '\u9fff' for c in r),
        }
    },
    {
        "name": "Pregunta no en contexto",
        "messages": [
            {"role": "system", "content": RAG_SYSTEM},
            {"role": "user", "content": f"Contexto:\n{RAG_CONTEXT}\n\nPregunta: ¿Cuál es el IBI del inmueble?"}
        ],
        "evaluate": lambda r: {
            "admits_no_info": any(term in r.lower() for term in ["no", "aparece", "menciona", "indica", "dispongo", "contexto"]),
            "no_invention": not bool(re.search(r'\d+\s*€', r)),  # Should NOT invent IBI amount
            "spanish": not any('\u4e00' <= c <= '\u9fff' for c in r),
        }
    },
]


# =============================================================================
# Test Runner
# =============================================================================

@dataclass
class TestResult:
    model: str
    category: str
    test_name: str
    response: str
    tool_call: Optional[Dict] = None
    latency_ms: float = 0
    evaluations: Dict[str, bool] = field(default_factory=dict)
    score: float = 0
    error: Optional[str] = None


def call_openrouter(
    model: str,
    messages: List[Dict],
    tools: Optional[List[Dict]] = None,
    max_tokens: int = 400,
    timeout: float = 60.0
) -> Dict[str, Any]:
    """Call OpenRouter API with optional tool support."""
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://nouxcube.com",
        "X-Title": "NouxCubeIA Model Test v2",
    }

    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.3,
    }

    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    start = time.time()
    with httpx.Client(timeout=timeout) as client:
        response = client.post(OPENROUTER_BASE_URL, headers=headers, json=payload)
        response.raise_for_status()
    latency = (time.time() - start) * 1000

    data = response.json()
    choice = data["choices"][0]
    message = choice["message"]

    result = {
        "content": message.get("content", ""),
        "latency_ms": latency,
        "tool_calls": None,
    }

    # Extract tool calls if present
    if message.get("tool_calls"):
        tc = message["tool_calls"][0]
        try:
            args = json.loads(tc["function"]["arguments"])
        except:
            args = {}
        result["tool_calls"] = {
            "name": tc["function"]["name"],
            "arguments": args,
        }

    return result


def run_test_category(model_id: str, model_name: str, category: str, tests: List[Dict]) -> List[TestResult]:
    """Run all tests in a category for a model."""
    results = []

    for test in tests:
        try:
            api_result = call_openrouter(
                model=model_id,
                messages=test["messages"],
                tools=test.get("tools"),
                max_tokens=test.get("max_tokens", 400),
            )

            response = api_result["content"]
            tool_call = api_result.get("tool_calls")

            # Run evaluation
            if test.get("tools"):
                evals = test["evaluate"](response, tool_call)
            else:
                evals = test["evaluate"](response)

            # Calculate score
            score = sum(1 for v in evals.values() if v) / len(evals) * 100

            results.append(TestResult(
                model=model_name,
                category=category,
                test_name=test["name"],
                response=response,
                tool_call=tool_call,
                latency_ms=api_result["latency_ms"],
                evaluations=evals,
                score=score,
            ))

        except Exception as e:
            results.append(TestResult(
                model=model_name,
                category=category,
                test_name=test["name"],
                response="",
                latency_ms=0,
                evaluations={},
                score=0,
                error=str(e),
            ))

        time.sleep(0.5)  # Rate limiting

    return results


def print_results(all_results: List[TestResult]):
    """Print comprehensive results."""

    print("\n" + "=" * 120)
    print("📊 COMPREHENSIVE MODEL COMPARISON RESULTS")
    print("=" * 120)

    # Group by model
    by_model: Dict[str, List[TestResult]] = {}
    for r in all_results:
        if r.model not in by_model:
            by_model[r.model] = []
        by_model[r.model].append(r)

    # Overall summary
    print("\n📈 OVERALL SCORES BY MODEL:\n")
    print(f"{'Model':<20} {'Social':<12} {'Tools':<12} {'Thinking':<12} {'Legal Gen':<12} {'RAG':<12} {'TOTAL':<12} {'Avg Latency'}")
    print("-" * 110)

    category_map = {
        "Social": SOCIAL_TESTS,
        "Tools": TOOL_TESTS,
        "Thinking": THINKING_TESTS,
        "Legal Gen": LEGAL_GEN_TESTS,
        "RAG": RAG_TESTS,
    }

    model_totals = []
    for model, results in by_model.items():
        scores = {}
        for cat in category_map.keys():
            cat_results = [r for r in results if r.category == cat]
            if cat_results:
                scores[cat] = sum(r.score for r in cat_results) / len(cat_results)
            else:
                scores[cat] = 0

        total = sum(scores.values()) / len(scores)
        avg_latency = sum(r.latency_ms for r in results if r.latency_ms > 0) / max(1, len([r for r in results if r.latency_ms > 0]))
        model_totals.append((model, total, avg_latency, scores))

        print(f"{model:<20} {scores.get('Social', 0):>8.0f}%    {scores.get('Tools', 0):>8.0f}%    {scores.get('Thinking', 0):>8.0f}%    {scores.get('Legal Gen', 0):>8.0f}%    {scores.get('RAG', 0):>8.0f}%    {total:>8.0f}%    {avg_latency:>8.0f}ms")

    # Best overall
    best = max(model_totals, key=lambda x: x[1])
    print(f"\n🏆 BEST OVERALL: {best[0]} (Score: {best[1]:.0f}%)")

    # Best by category
    print("\n🎯 BEST BY CATEGORY:")
    for cat in category_map.keys():
        cat_best = max(model_totals, key=lambda x: x[3].get(cat, 0))
        print(f"   {cat:<12}: {cat_best[0]} ({cat_best[3].get(cat, 0):.0f}%)")

    # Detailed results by category
    for cat_name, _ in category_map.items():
        print(f"\n{'─' * 120}")
        print(f"📋 CATEGORY: {cat_name.upper()}")
        print("─" * 120)

        cat_results = [r for r in all_results if r.category == cat_name]

        # Group by test
        tests_in_cat = set(r.test_name for r in cat_results)
        for test_name in tests_in_cat:
            print(f"\n   Test: {test_name}")

            for model in by_model.keys():
                result = next((r for r in cat_results if r.model == model and r.test_name == test_name), None)
                if result:
                    if result.error:
                        print(f"      ❌ {model:<18} ERROR: {result.error[:50]}")
                    else:
                        status = "✅" if result.score >= 80 else "⚠️" if result.score >= 50 else "❌"
                        print(f"      {status} {model:<18} ({result.latency_ms:.0f}ms) Score: {result.score:.0f}%")

                        # Show evaluations
                        evals_str = ", ".join([f"{k}:{'✓' if v else '✗'}" for k, v in result.evaluations.items()])
                        print(f"         Evals: {evals_str}")

                        # Show response preview
                        preview = result.response[:150].replace('\n', ' ')
                        print(f"         Response: \"{preview}{'...' if len(result.response) > 150 else ''}\"")

                        # Show tool call if present
                        if result.tool_call:
                            print(f"         Tool: {result.tool_call['name']}({json.dumps(result.tool_call['arguments'], ensure_ascii=False)[:80]})")


def main():
    """Run comprehensive tests."""
    if not OPENROUTER_API_KEY:
        print("❌ ERROR: OPENROUTER_API_KEY not found")
        sys.exit(1)

    print("🧪 Comprehensive Model Comparison Test v2")
    print(f"   Testing {len(MODELS_TO_TEST)} models")
    print(f"   Categories: Social, Tool Calling, Thinking, Legal Generation, RAG")
    print(f"   Timestamp: {datetime.now().isoformat()}")
    print()

    all_results: List[TestResult] = []

    for model_id, model_name in MODELS_TO_TEST:
        print(f"🔄 Testing {model_name}...")

        # Run each category
        categories = [
            ("Social", SOCIAL_TESTS),
            ("Tools", TOOL_TESTS),
            ("Thinking", THINKING_TESTS),
            ("Legal Gen", LEGAL_GEN_TESTS),
            ("RAG", RAG_TESTS),
        ]

        for cat_name, tests in categories:
            print(f"   → {cat_name}...", end=" ", flush=True)
            results = run_test_category(model_id, model_name, cat_name, tests)
            all_results.extend(results)
            passed = sum(1 for r in results if r.score >= 80)
            print(f"{passed}/{len(tests)}")

    # Print results
    print_results(all_results)

    # Save to JSON
    output_path = "/tmp/model_comparison_v2_results.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump([{
            "model": r.model,
            "category": r.category,
            "test_name": r.test_name,
            "response": r.response,
            "tool_call": r.tool_call,
            "latency_ms": r.latency_ms,
            "evaluations": r.evaluations,
            "score": r.score,
            "error": r.error,
        } for r in all_results], f, ensure_ascii=False, indent=2)

    print(f"\n💾 Full results saved to: {output_path}")


if __name__ == "__main__":
    main()
