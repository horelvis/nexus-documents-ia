#!/usr/bin/env python3
"""
Phase 3 evaluator for Emma RAG query understanding.

Metrics:
- scope_accuracy
- entity_precision (type-level, macro avg)
- topk_recall_proxy (on synthetic candidate pools)
"""

import argparse
import json
import sys
import types
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

import yaml


@dataclass
class EvalCaseResult:
    case_id: str
    scope_expected: str
    scope_predicted: str
    scope_ok: bool
    entity_precision: float
    entities_expected: List[str]
    entities_predicted: List[str]
    topk_recall: float | None = None


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


def _bootstrap_modules(service_dir: Path):
    for pkg in [
        "app",
        "app.agents",
        "app.agents.langgraph",
        "app.agents.langgraph.tools",
        "app.agents.langgraph.sectors",
    ]:
        _ensure_package(pkg)

    _load_module(
        "app.agents.langgraph.tools.base",
        service_dir / "app/agents/langgraph/tools/base.py",
    )
    _load_module(
        "app.agents.langgraph.sectors.config",
        service_dir / "app/agents/langgraph/sectors/config.py",
    )
    _load_module(
        "app.agents.langgraph.sectors.predictive_config",
        service_dir / "app/agents/langgraph/sectors/predictive_config.py",
    )
    registry = _load_module(
        "app.agents.langgraph.sectors.registry",
        service_dir / "app/agents/langgraph/sectors/registry.py",
    )
    extractor = _load_module(
        "app.agents.langgraph.sectors.entity_extractor",
        service_dir / "app/agents/langgraph/sectors/entity_extractor.py",
    )
    smart_search = _load_module(
        "app.agents.langgraph.tools.smart_search",
        service_dir / "app/agents/langgraph/tools/smart_search.py",
    )
    return registry, extractor, smart_search


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


def _entity_precision(expected: Set[str], predicted: Set[str]) -> float:
    if not predicted:
        return 1.0 if not expected else 0.0
    return len(expected & predicted) / len(predicted)


def _evaluate(
    dataset: Dict[str, Any],
    merged_patterns: Dict[str, List[str]],
    extract_entities,
    tool,
    rerank_fn,
) -> Tuple[List[EvalCaseResult], Dict[str, Any]]:
    top_k = int(dataset.get("meta", {}).get("top_k", 3))
    results: List[EvalCaseResult] = []
    topk_values: List[float] = []

    for case in dataset["cases"]:
        query = case["query"]
        entities = extract_entities(query, merged_patterns)
        scope_decision = tool._detect_scope("auto", query, entities)

        expected_scope = case["expected_scope"]
        predicted_scope = _scope_label(scope_decision)
        scope_ok = expected_scope == predicted_scope

        expected_entity_types = set(case.get("expected_entity_types", []))
        predicted_entity_types = set(entities.keys())
        ent_prec = _entity_precision(expected_entity_types, predicted_entity_types)

        topk_recall = None
        if case.get("candidates") and case.get("expected_topk_doc_ids"):
            reranked = rerank_fn(
                results=case["candidates"],
                graph_document_ids=set(case.get("graph_document_ids", [])),
                query_entities=entities,
                weights=tool._get_rerank_weights({}),
            )
            predicted_ids = [r.get("document_id", "") for r in reranked[:top_k]]
            expected_ids = set(case["expected_topk_doc_ids"])
            hits = len(expected_ids & set(predicted_ids))
            topk_recall = hits / max(1, len(expected_ids))
            topk_values.append(topk_recall)

        results.append(
            EvalCaseResult(
                case_id=case["id"],
                scope_expected=expected_scope,
                scope_predicted=predicted_scope,
                scope_ok=scope_ok,
                entity_precision=ent_prec,
                entities_expected=sorted(expected_entity_types),
                entities_predicted=sorted(predicted_entity_types),
                topk_recall=topk_recall,
            )
        )

    scope_accuracy = sum(1 for r in results if r.scope_ok) / len(results)
    entity_precision_macro = sum(r.entity_precision for r in results) / len(results)
    topk_recall_proxy = sum(topk_values) / len(topk_values) if topk_values else 0.0

    summary = {
        "cases": len(results),
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "scope_accuracy": round(scope_accuracy, 4),
        "entity_precision_macro": round(entity_precision_macro, 4),
        "topk_recall_proxy": round(topk_recall_proxy, 4),
        "topk_case_count": len(topk_values),
    }
    return results, summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Emma RAG Phase 3 metrics")
    parser.add_argument(
        "--dataset",
        default="config/rag_phase3_eval.yaml",
        help="Path to phase-3 dataset YAML (relative to emma-agent-service).",
    )
    parser.add_argument(
        "--output",
        default="scripts/benchmark_results/rag_phase3_eval.json",
        help="Output JSON file (relative to emma-agent-service).",
    )
    args = parser.parse_args()

    service_dir = Path(__file__).resolve().parents[1]
    dataset_path = (service_dir / args.dataset).resolve()
    output_path = (service_dir / args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with dataset_path.open("r", encoding="utf-8") as f:
        dataset = yaml.safe_load(f)

    registry, extractor, smart_search = _bootstrap_modules(service_dir)
    merged_patterns = _merge_patterns(
        registry.SECTOR_CONFIGS,
        sectors=["documental", "legal"],
    )
    tool = smart_search.SmartSearchTool()

    results, summary = _evaluate(
        dataset=dataset,
        merged_patterns=merged_patterns,
        extract_entities=extractor.extract_entities,
        tool=tool,
        rerank_fn=smart_search._rerank_results,
    )

    payload = {
        "summary": summary,
        "results": [r.__dict__ for r in results],
    }
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Dataset: {dataset_path}")
    print(f"Output:  {output_path}")
    print("")
    print(f"scope_accuracy:        {summary['scope_accuracy']:.4f}")
    print(f"entity_precision_macro:{summary['entity_precision_macro']:.4f}")
    print(f"topk_recall_proxy:     {summary['topk_recall_proxy']:.4f} (n={summary['topk_case_count']})")


if __name__ == "__main__":
    main()
