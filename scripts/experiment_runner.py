"""experiment_runner.py

Rodada mínima de self-improving loop:
- mutation em configs
- run baseline/candidate
- compare
- log em experiments/
"""
from __future__ import annotations

import json
import os
import shutil
from datetime import datetime

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONFIG_DIR = os.path.join(BASE_DIR, "config")
RUNS_DIR = os.path.join(BASE_DIR, "runs")
EXPER_DIR = os.path.join(BASE_DIR, "experiments")


def _now() -> str:
    return datetime.utcnow().strftime("%Y%m%d-%H%M%S")


def _load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _write_json(path: str, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def _run_benchmark(config_dir: str, label: str) -> str:
    cmd = (
        f"CORTIQ_CONFIG_DIR={config_dir} "
        f"{os.path.join(BASE_DIR, 'backend', '.venv', 'bin', 'python')} "
        f"{os.path.join(BASE_DIR, 'scripts', 'benchmark_runner.py')} --dry-run --version {label}"
    )
    os.system(cmd)
    # pega o último run com o label
    runs = sorted([f for f in os.listdir(RUNS_DIR) if f.startswith('run-') and f.endswith('.json') and label in f])
    return os.path.join(RUNS_DIR, runs[-1])


def run_experiment() -> dict:
    os.makedirs(EXPER_DIR, exist_ok=True)
    exp_id = f"exp-{_now()}"
    exp_path = os.path.join(EXPER_DIR, exp_id)
    os.makedirs(exp_path, exist_ok=True)

    baseline_dir = os.path.join(exp_path, "baseline")
    candidate_dir = os.path.join(exp_path, "candidate")
    shutil.copytree(CONFIG_DIR, baseline_dir)
    shutil.copytree(CONFIG_DIR, candidate_dir)

    # Mutation mínima: aumentar peso de primary source
    eval_path = os.path.join(candidate_dir, "evaluation_rules.json")
    rules = _load_json(eval_path)
    rules["primary_weight"] = round(min(0.25, rules.get("primary_weight", 0.1) + 0.05), 2)
    _write_json(eval_path, rules)

    baseline_run = _run_benchmark(baseline_dir, "baseline")
    candidate_run = _run_benchmark(candidate_dir, "candidate")

    # compare
    compare_cmd = (
        f"{os.path.join(BASE_DIR, 'backend', '.venv', 'bin', 'python')} "
        f"{os.path.join(BASE_DIR, 'scripts', 'compare_runs.py')} {baseline_run} {candidate_run}"
    )
    compare_output = os.popen(compare_cmd).read()
    compare_data = json.loads(compare_output)

    decision = compare_data.get("recommendation")

    log = {
        "experiment_id": exp_id,
        "hypothesis": "Increase primary weight improves aggregate score without harming critic usefulness.",
        "baseline_config": baseline_dir,
        "candidate_config": candidate_dir,
        "baseline_run": baseline_run,
        "candidate_run": candidate_run,
        "comparison": compare_data,
        "decision": decision,
    }

    _write_json(os.path.join(exp_path, "experiment.json"), log)
    return log


if __name__ == "__main__":
    out = run_experiment()
    print(json.dumps(out, ensure_ascii=False, indent=2))
