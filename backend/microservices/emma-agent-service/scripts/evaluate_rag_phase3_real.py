#!/usr/bin/env python3
"""
Phase 3 shadow evaluation on real anonymized queries from emma_sessions.

This script:
1) Extracts recent user messages from PostgreSQL (via docker exec + psql)
2) Anonymizes PII in queries
3) Builds a high-precision silver-labeled subset (documents/legislation/all)
4) Evaluates current scope routing against that subset
"""

import argparse
import asyncio
import json
import re
import sys
import types
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

import asyncpg

async def _extract_queries(
    db_host: str,
    db_port: int,
    db_user: str,
    db_password: str,
    db_name: str,
    session_limit: int,
    message_limit: int,
) -> List[str]:
    sql = f"""
WITH recent AS (
    SELECT messages::jsonb AS messages
    FROM emma_sessions
    ORDER BY updated_at DESC
    LIMIT {session_limit}
)
SELECT msg->>'content' AS content
FROM recent
JOIN LATERAL jsonb_array_elements(
    CASE WHEN jsonb_typeof(messages)='array' THEN messages ELSE '[]'::jsonb END
) AS msg ON TRUE
WHERE msg->>'role' = 'user'
  AND COALESCE(msg->>'content', '') <> ''
LIMIT {message_limit};
""".strip()

    conn = await asyncpg.connect(
        host=db_host,
        port=db_port,
        user=db_user,
        password=db_password,
        database=db_name,
    )
    try:
        rows = await conn.fetch(sql)
    finally:
        await conn.close()

    queries = [str(row["content"]).strip() for row in rows if row["content"]]
    # keep order but deduplicate exact duplicates
    seen: Set[str] = set()
    dedup = []
    for q in queries:
        if q not in seen:
            dedup.append(q)
            seen.add(q)
    return dedup


_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b", re.IGNORECASE)
_PHONE_RE = re.compile(r"(?:\+?\d[\d\s().-]{7,}\d)")
_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_DNI_RE = re.compile(r"\b(?:\d{8}[A-Z]|[XYZ]\d{7}[A-Z])\b", re.IGNORECASE)
_IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b")
_LONG_NUM_RE = re.compile(r"\b\d{5,}\b")
_NAME_RE = re.compile(
    r"\b([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+(?:de(?:\s+la)?|del|y))?\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)\b"
)


def anonymize_query(text: str) -> str:
    t = text.strip()
    t = _EMAIL_RE.sub("<EMAIL>", t)
    t = _PHONE_RE.sub("<PHONE>", t)
    t = _URL_RE.sub("<URL>", t)
    t = _DNI_RE.sub("<ID>", t)
    t = _IBAN_RE.sub("<IBAN>", t)
    t = _NAME_RE.sub("<NAME>", t)
    t = _LONG_NUM_RE.sub("<NUM>", t)
    return re.sub(r"\s+", " ", t).strip()


def _contains_keyword(text: str, keyword: str) -> bool:
    pattern = rf"(?<!\w){re.escape(keyword)}(?!\w)"
    return re.search(pattern, text) is not None


LEGAL_SILVER = {
    "ley", "leyes", "articulo", "artículo", "boe", "real decreto",
    "estatuto", "normativa", "reglamento", "rgpd", "lopdgdd", "codigo", "código",
}
DOCS_SILVER = {
    "factura", "facturas", "contrato", "contratos",
    "nomina", "nominas", "nómina", "nóminas",
    "documento", "documentos", "expediente", "expedientes",
    "informe", "informes", "carpeta", "carpetas", "archivo", "archivos",
}


def silver_label(query: str) -> str | None:
    q = query.lower()
    legal = any(_contains_keyword(q, kw) for kw in LEGAL_SILVER)
    docs = any(_contains_keyword(q, kw) for kw in DOCS_SILVER)
    if legal and docs:
        return "all"
    if legal:
        return "legislation"
    if docs:
        return "documents"
    return None


def _ensure_package(name: str) -> None:
    if name in sys.modules:
        return
    pkg = types.ModuleType(name)
    pkg.__path__ = []  # type: ignore[attr-defined]
    sys.modules[name] = pkg


def _load_module(name: str, file_path: Path):
    spec = spec_from_file_location(name, file_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load module {name} from {file_path}")
    module = module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _bootstrap(service_dir: Path):
    for pkg in [
        "app",
        "app.agents",
        "app.agents.langgraph",
        "app.agents.langgraph.tools",
        "app.agents.langgraph.sectors",
    ]:
        _ensure_package(pkg)

    _load_module("app.agents.langgraph.tools.base", service_dir / "app/agents/langgraph/tools/base.py")
    _load_module("app.agents.langgraph.sectors.config", service_dir / "app/agents/langgraph/sectors/config.py")
    _load_module("app.agents.langgraph.sectors.predictive_config", service_dir / "app/agents/langgraph/sectors/predictive_config.py")
    registry = _load_module("app.agents.langgraph.sectors.registry", service_dir / "app/agents/langgraph/sectors/registry.py")
    extractor = _load_module("app.agents.langgraph.sectors.entity_extractor", service_dir / "app/agents/langgraph/sectors/entity_extractor.py")
    smart = _load_module("app.agents.langgraph.tools.smart_search", service_dir / "app/agents/langgraph/tools/smart_search.py")
    return registry, extractor, smart


def _merge_patterns(sector_configs: Dict[str, Any], sectors: List[str]) -> Dict[str, List[str]]:
    merged: Dict[str, List[str]] = {}
    for sector in sectors:
        sc = sector_configs.get(sector)
        if not sc:
            continue
        for entity_type, regexes in sc.entity_patterns.items():
            merged.setdefault(entity_type, [])
            for rgx in regexes:
                if rgx not in merged[entity_type]:
                    merged[entity_type].append(rgx)
    return merged


def _scope_label(scope_decision: Dict[str, Any]) -> str:
    docs = bool(scope_decision.get("search_docs"))
    legal = bool(scope_decision.get("search_legislation"))
    if docs and legal:
        return "all"
    if docs:
        return "documents"
    if legal:
        return "legislation"
    return "none"


def main() -> None:
    parser = argparse.ArgumentParser(description="Real anonymized shadow eval for Phase 3")
    parser.add_argument("--db-host", default="db")
    parser.add_argument("--db-port", type=int, default=5432)
    parser.add_argument("--db-user", default="nexus_user")
    parser.add_argument("--db-password", default="nexus_password")
    parser.add_argument("--db-name", default="nexus_db")
    parser.add_argument("--session-limit", type=int, default=500)
    parser.add_argument("--message-limit", type=int, default=2000)
    parser.add_argument("--output", default="scripts/benchmark_results/rag_phase3_real_shadow.json")
    args = parser.parse_args()

    service_dir = Path(__file__).resolve().parents[1]
    output_path = (service_dir / args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    queries = asyncio.run(_extract_queries(
        db_host=args.db_host,
        db_port=args.db_port,
        db_user=args.db_user,
        db_password=args.db_password,
        db_name=args.db_name,
        session_limit=args.session_limit,
        message_limit=args.message_limit,
    ))
    anonymized = [anonymize_query(q) for q in queries]

    # Remove empty/ultra-short
    anonymized = [q for q in anonymized if len(q) >= 8]

    registry, extractor, smart = _bootstrap(service_dir)
    merged_patterns = _merge_patterns(registry.SECTOR_CONFIGS, ["documental", "legal"])
    tool = smart.SmartSearchTool()

    silver = []
    for q in anonymized:
        label = silver_label(q)
        if label is None:
            continue
        entities = extractor.extract_entities(q, merged_patterns)
        pred = _scope_label(tool._detect_scope("auto", q, entities))
        silver.append(
            {
                "query": q,
                "expected_scope_silver": label,
                "predicted_scope": pred,
                "scope_ok": pred == label,
                "entities": sorted(entities.keys()),
            }
        )

    total = len(anonymized)
    labeled = len(silver)
    accuracy = (sum(1 for r in silver if r["scope_ok"]) / labeled) if labeled else 0.0
    fallback_all = sum(1 for r in silver if r["predicted_scope"] == "all")

    report = {
        "summary": {
            "total_anonymized_queries": total,
            "silver_labeled_queries": labeled,
            "scope_accuracy_silver": round(accuracy, 4),
            "predicted_all_ratio": round((fallback_all / labeled), 4) if labeled else 0.0,
            "db_host": args.db_host,
            "db_name": args.db_name,
        },
        "sample_queries": anonymized[:200],
        "silver_results": silver[:500],
    }

    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Output: {output_path}")
    print(f"total_anonymized_queries: {total}")
    print(f"silver_labeled_queries:   {labeled}")
    print(f"scope_accuracy_silver:    {accuracy:.4f}")
    print(f"predicted_all_ratio:      {(fallback_all / labeled) if labeled else 0.0:.4f}")


if __name__ == "__main__":
    main()
