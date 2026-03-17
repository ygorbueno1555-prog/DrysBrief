"""proposer.py

Gera mutações controladas (heurístico) ou stub de LLM.
"""
from __future__ import annotations

import json
import os
import random
from typing import Dict, List

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _config_dir() -> str:
    return os.getenv("CORTIQ_CONFIG_DIR", os.path.join(BASE_DIR, "config"))


def _load(path: str) -> Dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _write(path: str, data: Dict) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def propose_heuristic(mutation_type: str | None = None) -> Dict:
    base_dir = _config_dir()
    eval_path = os.path.join(base_dir, "evaluation_rules.json")
    retry_path = os.path.join(base_dir, "retry_rules.json")
    query_path = os.path.join(base_dir, "query_strategy.json")

    mutation_type = mutation_type or random.choice([
        "increase_primary_weight",
        "tighten_retry",
        "loosen_retry",
        "boost_weak_coverage_weight",
        "reduce_weak_coverage_weight",
        "prioritize_traction_queries",
        "decrease_coverage_weight",
    ])

    mutation = {"type": mutation_type, "changes": {}}

    if mutation_type == "increase_primary_weight":
        rules = _load(eval_path)
        rules["primary_weight"] = round(min(0.3, rules.get("primary_weight", 0.1) + 0.05), 2)
        _write(eval_path, rules)
        mutation["changes"]["evaluation_rules.primary_weight"] = rules["primary_weight"]

    elif mutation_type == "tighten_retry":
        rules = _load(retry_path)
        rules["coverage_threshold"] = round(min(0.85, rules.get("coverage_threshold", 0.75) + 0.05), 2)
        _write(retry_path, rules)
        mutation["changes"]["retry_rules.coverage_threshold"] = rules["coverage_threshold"]

    elif mutation_type == "loosen_retry":
        rules = _load(retry_path)
        rules["coverage_threshold"] = round(max(0.6, rules.get("coverage_threshold", 0.75) - 0.05), 2)
        _write(retry_path, rules)
        mutation["changes"]["retry_rules.coverage_threshold"] = rules["coverage_threshold"]

    elif mutation_type == "boost_weak_coverage_weight":
        rules = _load(eval_path)
        rules["weak_coverage_weight"] = round(min(0.6, rules.get("weak_coverage_weight", 0.4) + 0.1), 2)
        _write(eval_path, rules)
        mutation["changes"]["evaluation_rules.weak_coverage_weight"] = rules["weak_coverage_weight"]

    elif mutation_type == "reduce_weak_coverage_weight":
        rules = _load(eval_path)
        rules["weak_coverage_weight"] = round(max(0.2, rules.get("weak_coverage_weight", 0.4) - 0.1), 2)
        _write(eval_path, rules)
        mutation["changes"]["evaluation_rules.weak_coverage_weight"] = rules["weak_coverage_weight"]

    elif mutation_type == "prioritize_traction_queries":
        rules = _load(query_path)
        priority = rules.get("priority_startup", [])
        if "traction" in priority:
            priority.remove("traction")
        rules["priority_startup"] = ["traction"] + priority
        _write(query_path, rules)
        mutation["changes"]["query_strategy.priority_startup"] = rules["priority_startup"]

    elif mutation_type == "decrease_coverage_weight":
        rules = _load(eval_path)
        rules["coverage_weight"] = round(max(0.2, rules.get("coverage_weight", 0.45) - 0.15), 2)
        _write(eval_path, rules)
        mutation["changes"]["evaluation_rules.coverage_weight"] = rules["coverage_weight"]

    return mutation


if __name__ == "__main__":
    mut = propose_heuristic()
    print(json.dumps(mut, ensure_ascii=False, indent=2))
