# Cortiq — Submission Candidate (V4/V5 Loop)

## Core (Required)
**Goal:** Prove a self‑improving loop for the research pipeline without changing the core product flow.

**Core capabilities delivered:**
1. **Mutation surface (configs only)**
   - `config/evaluation_rules.json`
   - `config/retry_rules.json`
   - `config/query_strategy.json`
   - `config/source_ranking.json`
   - `config/critic_rules.json`

2. **Benchmark suite (fixed cases)**
   - `benchmarks/` with startup + equity cases, including:
     - expected sections
     - expected key facts
     - expected primary source domains
     - critical gaps
     - anti‑patterns

3. **Benchmark runner + compare**
   - `scripts/benchmark_runner.py`
   - `scripts/compare_runs.py`
   - Outputs: per‑case scores + aggregate score + artifacts

4. **Self‑improving loop (minimal, real logic)**
   - `scripts/proposer.py` (controlled mutations)
   - `scripts/experiment_engine.py` (baseline + multi‑candidate + compare + keep/discard + promotion)
   - `experiments/` registry + baseline lineage + rollback
   - `leaderboard/index.json`

5. **Promotion gate + rollback**
   - Baseline is versioned, promotions are controlled and auditable.

---

## Bonus (Optional)
**Real API execution (Tavily + LLM)**
- Same loop can run with real sources and real latency.
- Command (once Tavily quota is available):
  ```bash
  python scripts/experiment_engine.py --candidates 3 --real
  ```

---

## What stays fixed (non‑mutable)
- API endpoints
- SSE schema
- artifact format
- core pipeline flow

## What is mutable (controlled surface)
- scoring weights and thresholds
- retry rules
- query prioritization
- source ranking
- critic rubric

---

## Quick demo (dry‑run, zero cost)
```bash
python scripts/experiment_engine.py --candidates 3
```
This runs: baseline + 3 candidates → compare → KEEP/DISCARD → promotion decision.

---

## Notes
- No new UI or frontend changes.
- Core research pipeline intact.
- Focus is on **auditability and comparable improvement** over time.
