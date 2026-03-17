# Video Script (Short)

**Duration:** ~90–120s

## 1) Hook (0–10s)
“Cortiq now isn’t just a research agent — it can **improve its own pipeline** with benchmarked experiments.”

## 2) Core: Loop Overview (10–40s)
- Show `config/` (mutation surface).
- Show `benchmarks/` (fixed cases).
- Show `scripts/experiment_engine.py`.

Narration:
“Changes are limited to configs. Benchmarks are fixed. We run baseline + candidates, compare, then keep/discard and log everything.”

## 3) Run the loop (40–80s)
Run:
```bash
python scripts/experiment_engine.py --candidates 3
```
Show:
- baseline run
- 3 candidate runs
- decisions KEEP/DISCARD
- promotion result
- experiments log + baseline lineage

Narration:
“This produces an auditable registry of experiments, with a promotion gate and rollback ready.”

## 4) Bonus (Optional) (80–100s)
Mention:
“With Tavily quota enabled, this same loop runs on real sources and real latency.”

## 5) Close (100–120s)
“Cortiq moved from ‘write a report’ to ‘evaluate and evolve the research pipeline with measurable benchmarks.’”
