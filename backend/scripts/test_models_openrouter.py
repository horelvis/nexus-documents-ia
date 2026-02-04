#!/usr/bin/env python3
"""
Model Comparison Test via OpenRouter

Tests multiple LLM models with the Social Agent prompt to evaluate:
- Language consistency (Spanish only, no mixing)
- Instruction following (brief, emoji, no invented data)
- Response quality

Usage:
    cd backend/docker
    python ../scripts/test_models_openrouter.py
"""

import os
import sys
import json
import time
from typing import Dict, List, Any
from dataclasses import dataclass
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

# Models to test (OpenRouter model IDs)
# Format: (model_id, display_name, estimated_cost_per_1k_tokens)
MODELS_TO_TEST = [
    ("qwen/qwen3-8b", "Qwen3 8B", 0.0002),
    ("qwen/qwen-2.5-7b-instruct", "Qwen 2.5 7B", 0.0002),
    ("mistralai/mistral-7b-instruct", "Mistral 7B", 0.0002),
    ("meta-llama/llama-3.1-8b-instruct", "LLaMA 3.1 8B", 0.0002),
    ("google/gemma-2-9b-it", "Gemma 2 9B", 0.0003),
    ("microsoft/phi-3-medium-128k-instruct", "Phi-3 Medium 14B", 0.0004),
]

# Social Agent System Prompt (same as in social.py)
SOCIAL_SYSTEM_PROMPT = """IMPORTANTE: Responde ÚNICAMENTE en ESPAÑOL. No uses chino, inglés ni otros idiomas.

Eres Emma, asistente de IA de NouxCubeIA.

## TU CONTEXTO
- Ubicación: Molina de Segura, Región de Murcia, España
- Zona horaria: Europe/Madrid

## REGLAS (OBLIGATORIAS)

1. IDIOMA: Responde SOLO en español de España. Si escribes en otro idioma, el sistema fallará.
2. NO INVENTES DATOS: Si la búsqueda web devuelve información irrelevante, admite que no encontraste la información.
3. BREVEDAD: 1-2 oraciones máximo.
4. EMOJIS: Uno por mensaje.
5. No uses mayúsculas sostenidas.

## CÓMO RESPONDER

Cuando la búsqueda web NO tenga datos relevantes:
- Responde: "No pude obtener esa información ahora. 🤔"
- NUNCA inventes temperaturas, precios o datos.

## EJEMPLOS

Pregunta: "¿Qué tiempo hace?"
Respuesta correcta: "No tengo datos del clima ahora mismo. ☁️"

Pregunta: "Hola"
Respuesta correcta: "¡Hola! ¿En qué te ayudo? 👋"

Pregunta: "Busca contratos de ACME"
Respuesta correcta: "Encontré 3 contratos de ACME. 📄"
"""

# Test cases
TEST_CASES = [
    {
        "name": "Saludo simple",
        "query": "Hola, ¿qué tal?",
        "context": None,
        "expected": {
            "language": "spanish",
            "max_sentences": 2,
            "has_emoji": True,
        }
    },
    {
        "name": "Tiempo sin datos",
        "query": "¿Qué tiempo hace hoy?",
        "context": None,  # No web search context = should admit no data
        "expected": {
            "language": "spanish",
            "should_not_invent": True,  # Should NOT invent temperature
            "max_sentences": 2,
        }
    },
    {
        "name": "Tiempo CON datos reales",
        "query": "¿Qué tiempo hace hoy?",
        "context": """📡 INFORMACIÓN ACTUALIZADA (web_search):
Encontré info sobre 'el tiempo en Molina de Segura':
• El tiempo en Molina de Segura: Nublado, 15°C, humedad 49%, viento 6 km/h
• Pronóstico: Cielos parcialmente nublados durante la tarde""",
        "expected": {
            "language": "spanish",
            "should_use_data": True,  # Should use the 15°C from context
            "max_sentences": 2,
        }
    },
    {
        "name": "Identidad",
        "query": "¿Quién eres?",
        "context": None,
        "expected": {
            "language": "spanish",
            "should_mention": ["Emma", "asistente", "IA"],
            "max_sentences": 2,
        }
    },
    {
        "name": "Búsqueda documentos",
        "query": "Busca contratos de Telefónica",
        "context": """📄 Encontré 2 documentos:
• Contrato servicios Telefónica 2024.pdf
• Anexo modificación Telefónica.docx""",
        "expected": {
            "language": "spanish",
            "should_use_data": True,
            "max_sentences": 2,
        }
    },
]


@dataclass
class TestResult:
    """Result of a single test case for a model."""
    model: str
    test_name: str
    query: str
    response: str
    latency_ms: float
    passed_language: bool
    passed_brevity: bool
    passed_content: bool
    notes: str


def detect_language_issues(text: str) -> List[str]:
    """Detect non-Spanish text in response."""
    issues = []

    # Chinese characters
    if any('\u4e00' <= c <= '\u9fff' for c in text):
        issues.append("Contains Chinese characters")

    # Korean characters
    if any('\uac00' <= c <= '\ud7af' for c in text):
        issues.append("Contains Korean characters")

    # Japanese (Hiragana/Katakana)
    if any('\u3040' <= c <= '\u30ff' for c in text):
        issues.append("Contains Japanese characters")

    # Common English phrases that shouldn't appear
    english_phrases = ["I'm ", "I am ", "Hello!", "How can I", "Let me", "Here's", "Here is"]
    for phrase in english_phrases:
        if phrase.lower() in text.lower():
            issues.append(f"Contains English phrase: '{phrase}'")

    return issues


def count_sentences(text: str) -> int:
    """Roughly count sentences."""
    # Remove emoji and count sentence-ending punctuation
    import re
    # Remove emojis
    text_clean = re.sub(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF]', '', text)
    sentences = re.split(r'[.!?]+', text_clean)
    return len([s for s in sentences if s.strip()])


def has_emoji(text: str) -> bool:
    """Check if text contains emoji."""
    import re
    emoji_pattern = re.compile(
        "[\U0001F600-\U0001F64F"  # emoticons
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F680-\U0001F6FF"  # transport & map
        "\U0001F1E0-\U0001F1FF"  # flags
        "\U00002702-\U000027B0"  # dingbats
        "\U000024C2-\U0001F251"  # enclosed characters
        "]+", flags=re.UNICODE
    )
    return bool(emoji_pattern.search(text))


def check_invented_data(text: str, has_context: bool) -> bool:
    """Check if response invents temperature/weather data without context."""
    import re
    # Look for temperature patterns
    temp_pattern = re.compile(r'\d+\s*°?[CcFf]|\d+\s*grados', re.IGNORECASE)

    if not has_context and temp_pattern.search(text):
        return True  # Invented data!
    return False


def call_openrouter(model: str, messages: List[Dict], timeout: float = 30.0) -> Dict[str, Any]:
    """Call OpenRouter API."""
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://nouxcube.com",
        "X-Title": "NouxCubeIA Model Test",
    }

    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": 200,
        "temperature": 0.3,
    }

    start = time.time()
    with httpx.Client(timeout=timeout) as client:
        response = client.post(OPENROUTER_BASE_URL, headers=headers, json=payload)
        response.raise_for_status()
    latency = (time.time() - start) * 1000

    data = response.json()
    return {
        "content": data["choices"][0]["message"]["content"],
        "latency_ms": latency,
        "tokens": data.get("usage", {}),
    }


def run_test(model_id: str, model_name: str, test_case: Dict) -> TestResult:
    """Run a single test case against a model."""

    # Build messages
    messages = [{"role": "system", "content": SOCIAL_SYSTEM_PROMPT}]

    # Add context if provided
    user_content = test_case["query"]
    if test_case.get("context"):
        user_content = f"{test_case['context']}\n\nPregunta del usuario: {test_case['query']}"

    messages.append({"role": "user", "content": user_content})

    try:
        result = call_openrouter(model_id, messages)
        response = result["content"]
        latency = result["latency_ms"]
    except Exception as e:
        return TestResult(
            model=model_name,
            test_name=test_case["name"],
            query=test_case["query"],
            response=f"ERROR: {e}",
            latency_ms=0,
            passed_language=False,
            passed_brevity=False,
            passed_content=False,
            notes=f"API Error: {e}"
        )

    # Evaluate response
    expected = test_case["expected"]
    notes = []

    # Language check
    lang_issues = detect_language_issues(response)
    passed_language = len(lang_issues) == 0
    if lang_issues:
        notes.extend(lang_issues)

    # Brevity check
    sentence_count = count_sentences(response)
    max_sentences = expected.get("max_sentences", 3)
    passed_brevity = sentence_count <= max_sentences
    if not passed_brevity:
        notes.append(f"Too long: {sentence_count} sentences (max {max_sentences})")

    # Content check
    passed_content = True

    # Check emoji if expected
    if expected.get("has_emoji") and not has_emoji(response):
        passed_content = False
        notes.append("Missing emoji")

    # Check for invented data
    if expected.get("should_not_invent"):
        if check_invented_data(response, bool(test_case.get("context"))):
            passed_content = False
            notes.append("INVENTED DATA without context!")

    # Check if uses provided data
    if expected.get("should_use_data") and test_case.get("context"):
        # Should reference something from context
        if "15" not in response and "Nublado" not in response.lower() and "nublado" not in response.lower():
            if "contrato" not in response.lower() and "documento" not in response.lower():
                notes.append("Didn't use provided context data")

    # Check mentions
    if expected.get("should_mention"):
        for term in expected["should_mention"]:
            if term.lower() not in response.lower():
                notes.append(f"Missing mention of '{term}'")
                passed_content = False
                break

    return TestResult(
        model=model_name,
        test_name=test_case["name"],
        query=test_case["query"],
        response=response,
        latency_ms=latency,
        passed_language=passed_language,
        passed_brevity=passed_brevity,
        passed_content=passed_content,
        notes="; ".join(notes) if notes else "OK"
    )


def print_results(results: List[TestResult]):
    """Print results in a formatted table."""

    print("\n" + "=" * 100)
    print("📊 MODEL COMPARISON RESULTS")
    print("=" * 100)

    # Group by model
    by_model: Dict[str, List[TestResult]] = {}
    for r in results:
        if r.model not in by_model:
            by_model[r.model] = []
        by_model[r.model].append(r)

    # Summary table
    print("\n📈 SUMMARY BY MODEL:\n")
    print(f"{'Model':<25} {'Lang ✓':<10} {'Brief ✓':<10} {'Content ✓':<12} {'Avg Latency':<15} {'Score'}")
    print("-" * 90)

    model_scores = []
    for model, model_results in by_model.items():
        lang_pass = sum(1 for r in model_results if r.passed_language)
        brief_pass = sum(1 for r in model_results if r.passed_brevity)
        content_pass = sum(1 for r in model_results if r.passed_content)
        avg_latency = sum(r.latency_ms for r in model_results) / len(model_results)
        total = len(model_results)

        score = (lang_pass + brief_pass + content_pass) / (total * 3) * 100
        model_scores.append((model, score, avg_latency))

        print(f"{model:<25} {lang_pass}/{total:<8} {brief_pass}/{total:<8} {content_pass}/{total:<10} {avg_latency:>8.0f}ms      {score:.0f}%")

    # Best model
    best = max(model_scores, key=lambda x: (x[1], -x[2]))  # Highest score, lowest latency
    print(f"\n🏆 BEST MODEL: {best[0]} (Score: {best[1]:.0f}%, Latency: {best[2]:.0f}ms)")

    # Detailed results
    print("\n" + "=" * 100)
    print("📝 DETAILED RESPONSES:")
    print("=" * 100)

    for test_case in TEST_CASES:
        print(f"\n{'─' * 80}")
        print(f"📋 Test: {test_case['name']}")
        print(f"   Query: \"{test_case['query']}\"")
        if test_case.get("context"):
            print(f"   Context: [Provided]")
        print()

        for model, model_results in by_model.items():
            for r in model_results:
                if r.test_name == test_case["name"]:
                    status = "✅" if (r.passed_language and r.passed_brevity and r.passed_content) else "❌"
                    print(f"   {status} {model:<20} ({r.latency_ms:.0f}ms)")
                    print(f"      Response: \"{r.response[:200]}{'...' if len(r.response) > 200 else ''}\"")
                    if r.notes != "OK":
                        print(f"      ⚠️  Notes: {r.notes}")
                    print()


def main():
    """Run all tests."""
    if not OPENROUTER_API_KEY:
        print("❌ ERROR: OPENROUTER_API_KEY not found in environment")
        print("   Set it in backend/docker/.env")
        sys.exit(1)

    print("🧪 Starting Model Comparison Test via OpenRouter")
    print(f"   Testing {len(MODELS_TO_TEST)} models with {len(TEST_CASES)} test cases")
    print(f"   Timestamp: {datetime.now().isoformat()}")
    print()

    all_results: List[TestResult] = []

    for model_id, model_name, _ in MODELS_TO_TEST:
        print(f"🔄 Testing {model_name}...", end=" ", flush=True)

        model_results = []
        for test_case in TEST_CASES:
            result = run_test(model_id, model_name, test_case)
            model_results.append(result)
            all_results.append(result)

            # Small delay to avoid rate limiting
            time.sleep(0.5)

        passed = sum(1 for r in model_results if r.passed_language and r.passed_brevity and r.passed_content)
        print(f"{passed}/{len(TEST_CASES)} passed")

    # Print results
    print_results(all_results)

    # Save raw results to JSON
    output_path = "/tmp/model_comparison_results.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump([{
            "model": r.model,
            "test_name": r.test_name,
            "query": r.query,
            "response": r.response,
            "latency_ms": r.latency_ms,
            "passed_language": r.passed_language,
            "passed_brevity": r.passed_brevity,
            "passed_content": r.passed_content,
            "notes": r.notes,
        } for r in all_results], f, ensure_ascii=False, indent=2)

    print(f"\n💾 Raw results saved to: {output_path}")


if __name__ == "__main__":
    main()
