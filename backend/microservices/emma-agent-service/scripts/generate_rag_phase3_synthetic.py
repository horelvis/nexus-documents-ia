#!/usr/bin/env python3
"""
Generate synthetic Phase-3 evaluation dataset for Emma RAG scope/entity routing.

Output format is compatible with scripts/evaluate_rag_phase3.py.
"""

import argparse
import random
from pathlib import Path
from typing import Any, Dict, List

import yaml


def _mk_case(idx: int, query: str, scope: str, entities: List[str]) -> Dict[str, Any]:
    return {
        "id": f"syn_{idx:04d}",
        "query": query,
        "expected_scope": scope,
        "expected_entity_types": entities,
    }


def build_synthetic_cases(seed: int = 42) -> List[Dict[str, Any]]:
    random.seed(seed)

    people = [
        "Javier Martinez", "Ana de la Fuente", "Maria Lopez", "Carlos Perez",
        "Lucia Gomez", "Pedro Sanchez", "Laura Ruiz", "Marta Gil",
    ]
    doc_singular = ["factura", "contrato", "nomina", "informe", "expediente", "documento"]
    doc_plural = ["facturas", "contratos", "nominas", "informes", "expedientes", "documentos"]
    refs = ["EXP-2025-001", "REF-ACME-77", "FAC-2026-009", "CTR-2024-014"]
    years = ["2023", "2024", "2025", "2026"]
    laws = [
        "Ley 39/2015",
        "Ley 40/2015",
        "Ley Organica 3/2018",
        "Real Decreto 2/2015",
    ]
    topics = ["proteccion de datos", "prevencion de riesgos", "contratacion publica", "compliance laboral"]
    articles = ["14", "24", "54", "1902"]
    boes = ["BOE 25", "BOE 123", "BOE 278", "BOE 12"]

    cases: List[Dict[str, Any]] = []
    i = 1

    # documents
    for _ in range(120):
        p = random.choice(people)
        dp = random.choice(doc_plural)
        d = random.choice(doc_singular)
        y = random.choice(years)
        r = random.choice(refs)
        pattern = random.choice(
            [
                (f"Necesito {dp} de {p}", ["persona"]),
                (f"Muestrame {dp} del año {y}", []),
                (f"Busca {dp} con referencia {r}", ["referencia"]),
                (f"Dame {dp} del ultimo mes", []),
                (f"Quiero el {d} de {p}", ["persona"]),
                (f"Ver {dp} de 2025", []),
            ]
        )
        q, ents = pattern
        cases.append(_mk_case(i, q, "documents", ents))
        i += 1

    # legislation
    for _ in range(120):
        law = random.choice(laws)
        topic = random.choice(topics)
        art = random.choice(articles)
        boe = random.choice(boes)
        pattern = random.choice(
            [
                (f"Que dice el articulo {art} de la {law}", ["articulo", "ley"]),
                (f"Necesito normativa sobre {topic}", []),
                (f"Dame legislacion aplicable a {topic}", []),
                (f"{boe} sobre {topic}", ["boe"]),
                (f"Explica la {law}", ["ley"]),
            ]
        )
        q, ents = pattern
        cases.append(_mk_case(i, q, "legislation", ents))
        i += 1

    # mixed/all
    for _ in range(90):
        p = random.choice(people)
        dp = random.choice(doc_plural)
        law = random.choice(laws)
        topic = random.choice(topics)
        pattern = random.choice(
            [
                (f"Busca {dp} de {p} y la {law}", ["persona", "ley"]),
                (f"Necesito {dp} y normativa sobre {topic}", []),
                (f"Muestrame {dp} de 2025 y legislacion aplicable", []),
                (f"Quiero {dp} de {p} y el articulo 54 del Estatuto", ["persona", "articulo"]),
            ]
        )
        q, ents = pattern
        cases.append(_mk_case(i, q, "all", ents))
        i += 1

    # hard negatives (should remain documents)
    hard_docs = [
        "Quiero una leyenda urbana de contratos",
        "Documentos de normativa interna",
        "Necesito documentos de proteccion de datos de la empresa",
        "Buscame contratos sobre leyendas de onboarding",
        "Muestrame informes de politicas internas",
    ]
    for q in hard_docs:
        cases.append(_mk_case(i, q, "documents", []))
        i += 1

    return cases


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic phase-3 RAG dataset")
    parser.add_argument(
        "--output",
        default="config/rag_phase3_synthetic.yaml",
        help="Output YAML path relative to emma-agent-service root.",
    )
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    service_dir = Path(__file__).resolve().parents[1]
    out_path = (service_dir / args.output).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    cases = build_synthetic_cases(seed=args.seed)
    payload = {
        "meta": {
            "name": "emma_rag_phase3_synthetic",
            "version": "1.0",
            "description": "Synthetic balanced benchmark for scope/entity routing.",
            "top_k": 3,
            "seed": args.seed,
        },
        "cases": cases,
    }
    out_path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")
    print(f"Generated {len(cases)} cases -> {out_path}")


if __name__ == "__main__":
    main()
