#!/usr/bin/env python3
"""
Quantization Comparison Test

Compares the same model via:
1. OpenRouter (FP16/BF16 - high precision)
2. Local vLLM (AWQ 4-bit - quantized)

This helps identify if quantization is causing quality issues.
"""

import os
import sys
import json
import time
from datetime import datetime

# Load .env
env_path = os.path.join(os.path.dirname(__file__), "..", "docker", ".env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())

import httpx

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
VLLM_BASE_URL = "http://localhost:8001/v1/chat/completions"  # Local vLLM

# Test prompts - same ones that caused issues
TEST_PROMPTS = [
    {
        "name": "Tiempo con contexto (causó mezcla de idiomas)",
        "system": """IMPORTANTE: Responde ÚNICAMENTE en ESPAÑOL. No uses chino, inglés ni otros idiomas.

Eres Emma, asistente de IA de NouxCubeIA.

## TU CONTEXTO
- Ubicación: Molina de Segura, Región de Murcia, España

## REGLAS (OBLIGATORIAS)
1. IDIOMA: Responde SOLO en español de España.
2. BREVEDAD: 1-2 oraciones máximo.
3. EMOJIS: Uno por mensaje.""",
        "user": """📡 INFORMACIÓN ACTUALIZADA (web_search):
Encontré info sobre 'el tiempo en Molina de Segura':
• El tiempo en Molina de Segura: Nublado, 15°C, humedad 49%, viento 6 km/h

Pregunta del usuario: ¿Qué tiempo hace hoy?""",
    },
    {
        "name": "Saludo simple",
        "system": """Eres Emma, asistente de IA. Responde SOLO en español.
Reglas: máximo 2 oraciones, 1 emoji.""",
        "user": "Hola, ¿qué tal?",
    },
    {
        "name": "Identidad",
        "system": """Eres Emma, asistente de IA de NouxCubeIA. Responde SOLO en español.
Reglas: máximo 2 oraciones, 1 emoji.""",
        "user": "¿Quién eres?",
    },
    {
        "name": "Análisis legal (requiere reasoning)",
        "system": """Eres un asistente legal experto. Responde en español.
Analiza brevemente y da tu conclusión.""",
        "user": "Un trabajador despedido por bajo rendimiento sin apercibimientos previos. ¿Es procedente?",
    },
]


def call_openrouter(system: str, user: str) -> dict:
    """Call OpenRouter API."""
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "qwen/qwen-2.5-7b-instruct",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user}
        ],
        "max_tokens": 300,
        "temperature": 0.3,
    }

    start = time.time()
    with httpx.Client(timeout=60.0) as client:
        response = client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload
        )
        response.raise_for_status()
    latency = (time.time() - start) * 1000

    data = response.json()
    return {
        "content": data["choices"][0]["message"]["content"],
        "latency_ms": latency,
    }


def call_local_vllm(system: str, user: str) -> dict:
    """Call local vLLM."""
    payload = {
        "model": "Qwen/Qwen2.5-7B-Instruct-AWQ",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user}
        ],
        "max_tokens": 300,
        "temperature": 0.3,
    }

    start = time.time()
    with httpx.Client(timeout=60.0) as client:
        response = client.post(VLLM_BASE_URL, json=payload)
        response.raise_for_status()
    latency = (time.time() - start) * 1000

    data = response.json()
    return {
        "content": data["choices"][0]["message"]["content"],
        "latency_ms": latency,
    }


def detect_issues(text: str) -> list:
    """Detect quality issues in response."""
    issues = []

    # Chinese characters
    if any('\u4e00' <= c <= '\u9fff' for c in text):
        issues.append("🚨 CHINESE CHARACTERS DETECTED")

    # Korean characters
    if any('\uac00' <= c <= '\ud7af' for c in text):
        issues.append("🚨 KOREAN CHARACTERS DETECTED")

    # Japanese characters
    if any('\u3040' <= c <= '\u30ff' for c in text):
        issues.append("🚨 JAPANESE CHARACTERS DETECTED")

    # English phrases
    english = ["I'm ", "I am ", "Hello!", "Here's", "Let me"]
    for phrase in english:
        if phrase in text:
            issues.append(f"⚠️ English phrase: '{phrase}'")

    # Empty or very short
    if len(text.strip()) < 10:
        issues.append("⚠️ Response too short")

    return issues


def main():
    print("=" * 100)
    print("🔬 QUANTIZATION COMPARISON TEST")
    print("=" * 100)
    print(f"Comparing: OpenRouter (FP16) vs Local vLLM (AWQ 4-bit)")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print()

    results = []

    for test in TEST_PROMPTS:
        print(f"\n{'─' * 80}")
        print(f"📋 Test: {test['name']}")
        print(f"   User: \"{test['user'][:60]}...\"")
        print()

        # OpenRouter (high precision)
        try:
            or_result = call_openrouter(test["system"], test["user"])
            or_issues = detect_issues(or_result["content"])
            print(f"   🌐 OpenRouter (FP16): ({or_result['latency_ms']:.0f}ms)")
            print(f"      Response: \"{or_result['content'][:150]}{'...' if len(or_result['content']) > 150 else ''}\"")
            if or_issues:
                for issue in or_issues:
                    print(f"      {issue}")
            else:
                print(f"      ✅ No issues detected")
        except Exception as e:
            print(f"   🌐 OpenRouter: ERROR - {e}")
            or_result = {"content": "", "latency_ms": 0}
            or_issues = [str(e)]

        print()

        # Local vLLM (AWQ quantized)
        try:
            local_result = call_local_vllm(test["system"], test["user"])
            local_issues = detect_issues(local_result["content"])
            print(f"   🖥️  Local vLLM (AWQ 4-bit): ({local_result['latency_ms']:.0f}ms)")
            print(f"      Response: \"{local_result['content'][:150]}{'...' if len(local_result['content']) > 150 else ''}\"")
            if local_issues:
                for issue in local_issues:
                    print(f"      {issue}")
            else:
                print(f"      ✅ No issues detected")
        except Exception as e:
            print(f"   🖥️  Local vLLM: ERROR - {e}")
            local_result = {"content": "", "latency_ms": 0}
            local_issues = [str(e)]

        results.append({
            "test": test["name"],
            "openrouter": {
                "response": or_result["content"],
                "latency_ms": or_result["latency_ms"],
                "issues": or_issues,
            },
            "local_vllm": {
                "response": local_result["content"],
                "latency_ms": local_result["latency_ms"],
                "issues": local_issues,
            }
        })

        time.sleep(1)  # Rate limiting

    # Summary
    print("\n" + "=" * 100)
    print("📊 SUMMARY")
    print("=" * 100)

    or_total_issues = sum(len(r["openrouter"]["issues"]) for r in results)
    local_total_issues = sum(len(r["local_vllm"]["issues"]) for r in results)

    or_avg_latency = sum(r["openrouter"]["latency_ms"] for r in results) / len(results)
    local_avg_latency = sum(r["local_vllm"]["latency_ms"] for r in results) / len(results)

    print(f"\n   {'Metric':<30} {'OpenRouter (FP16)':<25} {'Local vLLM (AWQ)'}")
    print(f"   {'-' * 75}")
    print(f"   {'Total Issues':<30} {or_total_issues:<25} {local_total_issues}")
    print(f"   {'Avg Latency':<30} {or_avg_latency:.0f}ms{'':<18} {local_avg_latency:.0f}ms")

    if local_total_issues > or_total_issues:
        diff = local_total_issues - or_total_issues
        print(f"\n   ⚠️  LOCAL AWQ HAS {diff} MORE ISSUES than OpenRouter")
        print(f"   💡 CONCLUSION: Quantization IS causing quality degradation")
        print(f"\n   RECOMMENDATIONS:")
        print(f"   1. Try Qwen 2.5 14B-AWQ (larger model, better quantization tolerance)")
        print(f"   2. Try GPTQ instead of AWQ (sometimes more stable)")
        print(f"   3. If VRAM allows, try FP16 version")
    else:
        print(f"\n   ✅ Both versions perform similarly")

    # Save results
    with open("/tmp/quantization_comparison.json", "w") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n💾 Results saved to /tmp/quantization_comparison.json")


if __name__ == "__main__":
    main()
