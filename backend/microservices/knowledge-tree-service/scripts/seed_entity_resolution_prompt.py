#!/usr/bin/env python3
"""Seed Langfuse prompt for person entity resolution.

The prompt clusters duplicate person entities (same individual extracted
under slightly different labels) so they can be MERGEd in FalkorDB.

Run: docker compose exec knowledge-tree-service python scripts/seed_entity_resolution_prompt.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PROMPTS = {
    "trustgraph_entity_resolution_persons": {
        "content": (
            "Eres un resolvedor de entidades especializado en nombres de personas en español.\n"
            "Recibirás una lista de entidades tipo 'persona' extraídas de varios documentos.\n"
            "Tu tarea: agrupar las entidades que representen a LA MISMA persona física.\n"
            "\n"
            "Casos que DEBES agrupar (misma persona):\n"
            "- Nombre completo vs nombre de pila: 'Juan Pérez' = 'Juan'\n"
            "- Honoríficos: 'D. Juan Pérez' = 'Don Juan Pérez' = 'Juan Pérez'\n"
            "- Abreviaturas de apellido: 'Juan P.' = 'Juan Pérez'\n"
            "- Truncaciones con asteriscos: 'Juan P***' = 'Juan Pérez' (redactado)\n"
            "- Nombre + ID concatenado: 'Juan Pérez 12***34' = 'Juan Pérez'\n"
            "- Typos evidentes: 'Juaan Pérez' = 'Juan Pérez'\n"
            "\n"
            "Casos que NO debes agrupar (personas distintas):\n"
            "- Mismo nombre de pila, apellidos distintos: 'Juan Pérez' ≠ 'Juan López'\n"
            "- Mismo apellido, nombres distintos: 'Juan Pérez' ≠ 'María Pérez'\n"
            "- Cuando haya ambigüedad, NO agrupes (falsos positivos son peor que duplicados).\n"
            "\n"
            "Para cada cluster con 2+ miembros:\n"
            "- canonical_uri = el URI cuyo label sea más completo/informativo (preferir nombre completo\n"
            "  con apellidos sobre nombre de pila; preferir versiones con identificadores sobre versiones\n"
            "  sin identificador).\n"
            "- member_uris = todos los URIs de la lista original que pertenecen al cluster (incluyendo\n"
            "  el canónico).\n"
            "- canonical_label = el label correspondiente al canonical_uri.\n"
            "\n"
            "Entidades con UN solo miembro (sin duplicados) NO deben aparecer en la salida.\n"
            "\n"
            "Responde ÚNICAMENTE con JSON, sin texto antes ni después, sin ```:\n"
            '{"clusters": [{"canonical_uri": "...", "canonical_label": "...", "member_uris": ["...", "..."]}]}\n'
            "\n"
            "Entrada:\n"
            "{{persons_json}}\n"
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
                    print(f"  SKIP  {name} — already exists (use --force in production to overwrite)")
                else:
                    print(f"  ERROR  {name}: {exc}")
    except ImportError:
        print("Langfuse not available — prompt content:")
        for name, config in PROMPTS.items():
            print(f"\n--- {name} ---")
            print(config["content"])


if __name__ == "__main__":
    main()
