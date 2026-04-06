#!/usr/bin/env python3
"""Seed Langfuse prompts for Phase 3b."""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PROMPTS = {
    "trustgraph_guided_expansion": {
        "content": (
            "You are a knowledge graph traversal planner. Given a user query and the current "
            "subgraph state, decide if more graph exploration is needed.\n\n"
            "The current subgraph was built by BFS (2 hops) from seed entities. "
            "If the query requires relationships beyond what's visible, suggest expanding "
            "from specific entity URIs.\n\n"
            "Rules:\n"
            "- Only suggest expansion if the current subgraph clearly lacks information\n"
            "- Select at most 3 frontier URIs to expand from\n"
            "- Prefer entities that seem most relevant to the unanswered part of the query\n"
            "- If the subgraph already contains enough context, set sufficient=true\n\n"
            'Respond ONLY with JSON: {"sufficient": true/false, "expand_from": ["uri1", "uri2"], "reason": "brief explanation"}'
        ),
        "labels": ["production"],
    },
}


def main():
    try:
        from langfuse import Langfuse
        client = Langfuse()

        for name, config in PROMPTS.items():
            try:
                client.create_prompt(
                    name=name,
                    prompt=config["content"],
                    labels=config.get("labels", []),
                    type="text",
                )
                print(f"  OK  {name}")
            except Exception as exc:
                if "already exists" in str(exc).lower():
                    print(f"  SKIP  {name} — already exists")
                else:
                    print(f"  ERROR  {name}: {exc}")

    except ImportError:
        print("Langfuse not available — printing prompt content instead:")
        for name, config in PROMPTS.items():
            print(f"\n--- {name} ---")
            print(config["content"])


if __name__ == "__main__":
    main()
