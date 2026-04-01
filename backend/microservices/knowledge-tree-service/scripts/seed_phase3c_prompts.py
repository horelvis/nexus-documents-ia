#!/usr/bin/env python3
"""Seed Langfuse prompts for Phase 3c — Knowledge Expert."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PROMPTS = {
    "trustgraph_report_generation": {
        "content": (
            "You are a knowledge expert. Generate a {{report_type}} for {{entity_name}}.\n\n"
            "VERIFIED DATA FROM KNOWLEDGE GRAPH:\n{{assembled_graph_markdown}}\n\n"
            "RULES:\n"
            "- Use ONLY the provided data. Do not invent information.\n"
            "- Every claim must include [Source: doc_id, confidence: X.XX]\n"
            "- KPIs go in a dedicated section with table format.\n"
            "- If a fact has confidence < 0.60, mark it as 'dato no verificado'.\n"
            "- If contradictions exist, report them explicitly.\n"
            "- Language: {{language}}\n"
            "- Structure the report with clear headings matching the section titles provided.\n"
            "- Be concise but thorough — include all verified facts."
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
