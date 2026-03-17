"""compare_runs.py

Compara baseline vs candidato e recomenda keep/discard.
"""
from __future__ import annotations

import json
import os
from typing import Dict

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RUNS_DIR = os.path.join(BASE_DIR, "runs")


def load_run(path: str) -> Dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def compare_runs(baseline_path: str, candidate_path: str) -> Dict:
    base = load_run(baseline_path)
    cand = load_run(candidate_path)

    base_results = {r["id"]: r for r in base["results"]}
    cand_results = {r["id"]: r for r in cand["results"]}

    deltas = []
    for bid, b in base_results.items():
        c = cand_results.get(bid, {})
        deltas.append({
            "id": bid,
            "delta_final_score": round(c.get("final_score", 0) - b.get("final_score", 0), 2),
            "delta_coverage": round(c.get("evaluation", {}).get("coverage_score", 0) - b.get("evaluation", {}).get("coverage_score", 0), 2),
            "delta_evidence": round(c.get("evaluation", {}).get("evidence_score", 0) - b.get("evaluation", {}).get("evidence_score", 0), 2),
            "delta_primary": round(c.get("evaluation", {}).get("primary_source_ratio", 0) - b.get("evaluation", {}).get("primary_source_ratio", 0), 2),
            "delta_retry": (c.get("retry_count", 0) - b.get("retry_count", 0)),
        })

    aggregate_delta = round(cand.get("aggregate_score", 0) - base.get("aggregate_score", 0), 2)
    recommendation = "KEEP" if aggregate_delta >= 0 else "DISCARD"

    return {
        "baseline": baseline_path,
        "candidate": candidate_path,
        "aggregate_delta": aggregate_delta,
        "deltas": deltas,
        "recommendation": recommendation,
    }


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("usage: compare_runs.py <baseline.json> <candidate.json>")
        raise SystemExit(1)
    result = compare_runs(sys.argv[1], sys.argv[2])
    print(json.dumps(result, ensure_ascii=False, indent=2))
