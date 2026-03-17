# Submission Summary (Short)

Cortiq is now a **self‑improving research engine** with a controlled mutation surface and benchmarked evaluation loop.

**What’s new:**
- Fixed benchmark suite (startup + equity)
- Runner + compare for aggregate scoring
- Multi‑candidate experiments with KEEP/DISCARD
- Promotion gate, baseline lineage, and rollback
- Full experiment registry + leaderboard

**Why it matters:**
- Moves from “report generation” to **auditable pipeline improvement**
- Prevents regressions and enables measurable evolution

**Core loop:**
mutation → benchmark → compare → keep/discard → promote/rollback

**Status:**
Ready for submission. Real‑API execution (Tavily) is optional and can be enabled when quota is available.
