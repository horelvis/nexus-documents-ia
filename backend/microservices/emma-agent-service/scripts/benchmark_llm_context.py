#!/usr/bin/env python3
"""
Benchmark LLM response time with incremental context sizes.

Tests the SGLang/vLLM endpoint with increasing context lengths to find
where throughput degrades. Useful for diagnosing timeout issues.

Usage:
    docker compose exec emma-agent-service python scripts/benchmark_llm_context.py
    docker compose exec emma-agent-service python scripts/benchmark_llm_context.py --max-tokens 8000
    docker compose exec emma-agent-service python scripts/benchmark_llm_context.py --url http://sglang:8000/v1
"""

import argparse
import json
import os
import sys
import time

import httpx

# Default SGLang URL
DEFAULT_URL = os.getenv("SGLANG_BASE_URL", "http://sglang:8000/v1")
DEFAULT_MODEL = os.getenv("SGLANG_MODEL", "QuantTrio/Qwen3.5-27B-AWQ")

# Context sizes to test (in approximate tokens, ~4 chars per token)
CONTEXT_SIZES = [100, 500, 1000, 2000, 4000, 8000, 16000, 32000]

# ANSI colors
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"


def generate_context(target_tokens: int) -> str:
    """Generate filler context text of approximately target_tokens tokens."""
    # ~4 chars per token
    base = "Este es un documento legal sobre contratos laborales. "
    chars_needed = target_tokens * 4
    repeats = max(1, chars_needed // len(base))
    return (base * repeats)[:chars_needed]


def benchmark_call(
    url: str,
    model: str,
    context_tokens: int,
    max_completion: int = 50,
    enable_thinking: bool = False,
) -> dict:
    """Make a single benchmark call and return timing + usage info."""
    context = generate_context(context_tokens)
    prompt = f"""Dado el siguiente contexto, responde brevemente: ¿De qué trata este texto?

CONTEXTO:
{context}

RESPUESTA (máximo 2 frases):"""

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": max_completion,
        "chat_template_kwargs": {"enable_thinking": enable_thinking},
    }

    t0 = time.time()
    try:
        with httpx.Client(timeout=120.0) as client:
            resp = client.post(f"{url}/chat/completions", json=payload)
            resp.raise_for_status()
            data = resp.json()
    except httpx.TimeoutException:
        return {
            "context_tokens": context_tokens,
            "status": "TIMEOUT",
            "latency_s": time.time() - t0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "tokens_per_sec": 0,
            "content": "",
        }
    except Exception as e:
        return {
            "context_tokens": context_tokens,
            "status": f"ERROR: {e}",
            "latency_s": time.time() - t0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "tokens_per_sec": 0,
            "content": "",
        }

    latency = time.time() - t0
    usage = data.get("usage", {})
    prompt_tokens = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)
    content = data["choices"][0]["message"].get("content", "")

    tokens_per_sec = completion_tokens / latency if latency > 0 else 0

    return {
        "context_tokens": context_tokens,
        "status": "OK",
        "latency_s": latency,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "tokens_per_sec": round(tokens_per_sec, 1),
        "content": content[:100],
    }


def main():
    parser = argparse.ArgumentParser(description="Benchmark LLM context sizes")
    parser.add_argument("--url", default=DEFAULT_URL, help="SGLang base URL")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Model name")
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=32000,
        help="Max context size to test (default: 32000)",
    )
    parser.add_argument(
        "--thinking",
        action="store_true",
        help="Enable thinking mode (default: disabled)",
    )
    args = parser.parse_args()

    sizes = [s for s in CONTEXT_SIZES if s <= args.max_tokens]

    print(f"\n{BOLD}LLM Context Size Benchmark{RESET}")
    print(f"  URL     : {args.url}")
    print(f"  Model   : {args.model}")
    print(f"  Thinking: {'ON' if args.thinking else 'OFF'}")
    print(f"  Sizes   : {sizes}")
    print()
    print(f"{'Context':>8} {'Status':>8} {'Latency':>9} {'Prompt':>8} {'Compl':>7} {'tok/s':>7} {'Response':>30}")
    print("-" * 90)

    for size in sizes:
        result = benchmark_call(
            url=args.url,
            model=args.model,
            context_tokens=size,
            enable_thinking=args.thinking,
        )

        status = result["status"]
        if status == "OK":
            tps = result["tokens_per_sec"]
            if tps >= 10:
                color = GREEN
            elif tps >= 3:
                color = YELLOW
            else:
                color = RED
            status_str = f"{color}{status:>8}{RESET}"
        else:
            status_str = f"{RED}{status[:8]:>8}{RESET}"

        print(
            f"{size:>8} {status_str} {result['latency_s']:>8.1f}s "
            f"{result['prompt_tokens']:>8} {result['completion_tokens']:>7} "
            f"{result['tokens_per_sec']:>6.1f} "
            f"{result['content'][:30]}"
        )

        # Stop if we get a timeout or very slow response
        if status == "TIMEOUT" or (status == "OK" and result["tokens_per_sec"] < 0.5):
            print(f"\n{RED}Stopping: throughput too low at {size} tokens context{RESET}")
            break

    print()


if __name__ == "__main__":
    main()
