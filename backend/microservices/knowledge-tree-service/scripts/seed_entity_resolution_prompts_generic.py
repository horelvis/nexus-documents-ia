#!/usr/bin/env python3
"""Seed Langfuse prompts for generic entity resolution.

Adds prompts for organizations and places (person resolution was seeded in
scripts/seed_entity_resolution_prompt.py and continues to work).

Run: docker compose exec knowledge-tree-service \
         python scripts/seed_entity_resolution_prompts_generic.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PROMPTS = {
    "trustgraph_entity_resolution_organizations": {
        "content": (
            "Eres un resolvedor de entidades especializado en nombres de organizaciones "
            "(empresas, marcas, entidades bancarias, administraciones públicas) en español.\n"
            "Recibirás una lista de entidades tipo 'organization' extraídas de documentos.\n"
            "Tu tarea: agrupar las entidades que representen a LA MISMA organización.\n"
            "\n"
            "Casos que DEBES agrupar (misma organización):\n"
            "- Sufijos corporativos: 'BBVA' = 'BBVA S.A.' = 'BBVA, S.A.' = 'Banco BBVA'\n"
            "- Variantes de capitalización: 'movistar' = 'Movistar' = 'MOVISTAR'\n"
            "- Prefijos de producto: 'Movistar' = 'miMovistar' = 'iMovistar Plus+'\n"
            "  (si claramente se refiere al mismo proveedor comercial)\n"
            "- Acrónimo + forma larga si están enlazados inequívocamente:\n"
            "  'AEAT' = 'Agencia Tributaria' = 'Agencia Estatal de Administración Tributaria'\n"
            "- Truncaciones con asteriscos: 'Banco S***********' = 'Banco Santander'\n"
            "  (si redactado de forma evidente)\n"
            "\n"
            "Casos que NO debes agrupar (organizaciones distintas):\n"
            "- Mismo nombre base pero sector distinto: 'Apple Inc.' (tech) ≠ 'Apple Bank'\n"
            "- Filiales con nombre reconocible propio: 'Telefónica' ≠ 'Movistar'\n"
            "  (son corporación y marca comercial, pero muchas veces se refieren a ellas\n"
            "  como entidades distintas a efectos de compliance/contratación — sé\n"
            "  conservador).\n"
            "- Cuando haya ambigüedad, NO agrupes (falsos positivos son peor que duplicados).\n"
            "\n"
            "Para cada cluster con 2+ miembros:\n"
            "- canonical_uri = el URI con el label más completo (preferir forma legal con\n"
            "  sufijo corporativo si existe; si no, la forma comercial más conocida).\n"
            "- member_uris = todos los URIs del cluster (incluyendo el canónico).\n"
            "- canonical_label = label correspondiente al canonical_uri.\n"
            "\n"
            "Entidades con UN solo miembro NO deben aparecer en la salida.\n"
            "\n"
            "Responde ÚNICAMENTE con JSON, sin texto antes ni después, sin ```:\n"
            '{"clusters": [{"canonical_uri": "...", "canonical_label": "...", "member_uris": ["...", "..."]}]}\n'
            "\n"
            "Entrada:\n"
            "{{entities_json}}\n"
        ),
        "labels": ["production"],
    },
    "trustgraph_entity_resolution_places": {
        "content": (
            "Eres un resolvedor de entidades especializado en nombres de lugares "
            "(ciudades, calles, direcciones, regiones) en español.\n"
            "Recibirás una lista de entidades tipo 'place' extraídas de documentos.\n"
            "Tu tarea: agrupar las entidades que representen EL MISMO lugar físico.\n"
            "\n"
            "Casos que DEBES agrupar (mismo lugar):\n"
            "- Fragmento de dirección + dirección completa SI el fragmento identifica\n"
            "  unívocamente el lugar: 'Calle Mayor 15' = 'Calle Mayor 15, Madrid' = 'C/ Mayor 15'\n"
            "- Variantes de capitalización: 'molina de segura' = 'Molina de Segura'\n"
            "- Abreviaturas: 'C/ Mayor' = 'Calle Mayor'\n"
            "- Truncaciones con asteriscos si son claramente la misma dirección redactada:\n"
            "  'Calle Compos**********' = 'Calle Compostela 5'\n"
            "- Errores tipográficos pequeños: 'Molina de Seguar' = 'Molina de Segura'\n"
            "\n"
            "Casos que NO debes agrupar (lugares distintos):\n"
            "- Mismo nombre de calle en ciudades distintas: 'Calle Mayor' (Madrid) ≠\n"
            "  'Calle Mayor' (Valencia) — no agrupes calles sin ciudad identificada\n"
            "  a menos que el contexto sea claro.\n"
            "- Ciudades próximas pero distintas: 'Molina de Segura' ≠ 'Murcia'.\n"
            "- Direcciones con mismo nombre de calle pero números distintos:\n"
            "  'Calle Mayor 5' ≠ 'Calle Mayor 15'.\n"
            "- Cuando haya ambigüedad, NO agrupes.\n"
            "\n"
            "Para cada cluster con 2+ miembros:\n"
            "- canonical_uri = el URI con la dirección más completa (ciudad + calle + número).\n"
            "- member_uris = todos los URIs del cluster.\n"
            "- canonical_label = label correspondiente al canonical_uri.\n"
            "\n"
            "Entidades con UN solo miembro NO deben aparecer en la salida.\n"
            "\n"
            "Responde ÚNICAMENTE con JSON, sin texto antes ni después, sin ```:\n"
            '{"clusters": [{"canonical_uri": "...", "canonical_label": "...", "member_uris": ["...", "..."]}]}\n'
            "\n"
            "Entrada:\n"
            "{{entities_json}}\n"
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
        print("Langfuse not available — prompt content:")
        for name, config in PROMPTS.items():
            print(f"\n--- {name} ---")
            print(config["content"])


if __name__ == "__main__":
    main()
