"""main.py — Cortiq Decision Copilot v2
FastAPI server with SSE streaming, daily briefing scheduler, draft review API,
portfolio management, lab/autoResearch, and portfolio monitor.
"""
import asyncio
import json
import os
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from pydantic import BaseModel
from typing import Optional, List

load_dotenv()

from agent import run_equity_analysis, run_startup_analysis
from briefing_runner import (
    run_watchlist_briefing, load_drafts, load_draft, save_draft, send_brief_email
)

# ── Scheduler ────────────────────────────────────────────
def _setup_scheduler(app):
    try:
        import json
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from zoneinfo import ZoneInfo

        wl_path = os.path.join(os.path.dirname(__file__), "watchlist.json")
        briefing_hour = 7
        try:
            with open(wl_path) as f:
                briefing_hour = json.load(f).get("briefing_hour", 7)
        except Exception:
            pass

        from monitor import check_and_send_price_alerts
        scheduler = AsyncIOScheduler(timezone=ZoneInfo("America/Sao_Paulo"))
        scheduler.add_job(run_watchlist_briefing, "cron", hour=briefing_hour, minute=0)
        scheduler.add_job(
            lambda: asyncio.ensure_future(check_and_send_price_alerts()),
            "interval", hours=1, id="price_alerts"
        )
        app.state.scheduler = scheduler
        return scheduler
    except Exception as e:
        print(f"[scheduler] init failed: {e}")
        return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = _setup_scheduler(app)
    if scheduler:
        scheduler.start()
    yield
    if scheduler:
        scheduler.shutdown()


app = FastAPI(title="Cortiq Decision Copilot", lifespan=lifespan)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
STATIC_DIR = os.path.join(FRONTEND_DIR, "static")
DATA_DIR = os.path.join(BASE_DIR, "data")
HISTORY_FILE = os.path.join(DATA_DIR, "analysis_history.json")
PORTFOLIO_PATH = os.path.join(DATA_DIR, "portfolio.json")
PORTFOLIO_HISTORY_PATH = os.path.join(DATA_DIR, "portfolio_history.json")
MAX_PORTFOLIO_HISTORY = 100

# Lab loop state
_lab_loop_state = {"running": False, "thread": None}

# Lab mutation labels
MUTATION_LABELS = {
    "increase_primary_weight": ("Fontes primárias reforçadas", "Priorizamos fontes oficiais (B3, SEC, relatórios de RI) — análises mais fundamentadas em dados primários"),
    "tighten_retry": ("Cobertura mais profunda", "Refinamos quando buscar dados adicionais — análises chegam mais completas"),
    "loosen_retry": ("Velocidade otimizada", "Reduzimos buscas redundantes sem perder qualidade de cobertura"),
    "boost_weak_coverage_weight": ("Tópicos escassos melhorados", "Melhoramos análise de seções com pouca evidência disponível no mercado"),
    "reduce_weak_coverage_weight": ("Foco em profundidade", "Priorizamos qualidade sobre quantidade nos tópicos cobertos"),
    "prioritize_traction_queries": ("Startups: tração em primeiro lugar", "Para startups, buscamos métricas reais de tração antes de qualquer outro dado"),
    "decrease_coverage_weight": ("Evidência acima de cobertura", "Priorizamos qualidade das evidências sobre amplitude de cobertura"),
}

def _load_portfolio() -> dict:
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(PORTFOLIO_PATH):
        return {"companies": []}
    with open(PORTFOLIO_PATH, encoding="utf-8") as f:
        return json.load(f)

def _save_portfolio(data: dict):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(PORTFOLIO_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def _load_portfolio_history() -> list:
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(PORTFOLIO_HISTORY_PATH):
        return []
    with open(PORTFOLIO_HISTORY_PATH, encoding="utf-8") as f:
        return json.load(f)

def _save_portfolio_history_entry(entry: dict):
    from datetime import datetime, timezone
    history = _load_portfolio_history()
    history = [h for h in history if not (h.get("name") == entry["name"] and h.get("type") == entry["type"])]
    entry["date"] = datetime.now(timezone.utc).isoformat()
    history.insert(0, entry)
    history = history[:MAX_PORTFOLIO_HISTORY]
    with open(PORTFOLIO_HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# ── History helpers ───────────────────────────────────────

def _load_history() -> List:
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_history(entries: list) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)


# ── Pages ─────────────────────────────────────────────────
@app.get("/")
def index():
    with open(os.path.join(FRONTEND_DIR, "index.html"), encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.get("/monitor")
def monitor_page():
    with open(os.path.join(FRONTEND_DIR, "monitor.html"), encoding="utf-8") as f:
        return HTMLResponse(f.read())


# ── Portfolio Monitor API ──────────────────────────────────

@app.get("/api/monitor/portfolios")
def api_get_portfolios():
    from monitor import get_portfolios
    return get_portfolios()


@app.get("/api/monitor/tickers")
def api_get_tickers():
    """All tickers with today's snapshot (if available)."""
    from monitor import get_all_equity_tickers, load_snapshot
    from datetime import date
    result = []
    for item in get_all_equity_tickers():
        snap = load_snapshot(item["ticker"], date.today())
        result.append({**item, "today": snap})
    return result


@app.get("/api/monitor/ticker/{ticker}")
def api_get_ticker(ticker: str):
    """Full history for one ticker (last 30 days)."""
    from monitor import load_history, load_snapshot
    from datetime import date
    history = load_history(ticker.upper(), days=30)
    today = load_snapshot(ticker.upper(), date.today())
    return {"ticker": ticker.upper(), "today": today, "history": history}


@app.post("/api/monitor/refresh/{ticker}")
async def api_refresh_ticker(ticker: str, force: bool = False):
    from monitor import refresh_ticker
    data = await refresh_ticker(ticker.upper(), force=force)
    return data


@app.post("/api/monitor/refresh")
async def api_refresh_all(force: bool = False):
    from monitor import refresh_all
    data = await refresh_all(force=force)
    return {"ok": True, "count": len(data), "tickers": [d.get("ticker") for d in data]}


@app.post("/api/monitor/ticker")
async def api_add_ticker(body: dict):
    from monitor import add_ticker_to_portfolio
    ticker = (body.get("ticker") or "").upper().strip()
    portfolio_id = body.get("portfolio_id", "carteira-principal")
    thesis = body.get("thesis", "")
    if not ticker:
        return {"ok": False, "error": "ticker required"}
    ok = add_ticker_to_portfolio(portfolio_id, ticker, thesis)
    return {"ok": ok}


@app.post("/api/monitor/check-alerts")
async def api_check_price_alerts(portfolio_id: Optional[str] = None):
    """Check all tickers for price moves >= threshold. Sends email if configured."""
    from monitor import check_and_send_price_alerts
    result = await check_and_send_price_alerts(portfolio_id)
    total_triggered = sum(len(r["triggered"]) for r in result)
    return {"ok": True, "total_triggered": total_triggered, "portfolios": result}


@app.delete("/api/monitor/ticker/{portfolio_id}/{ticker}")
def api_remove_ticker(portfolio_id: str, ticker: str):
    from monitor import remove_ticker_from_portfolio
    ok = remove_ticker_from_portfolio(portfolio_id, ticker.upper())
    return {"ok": ok}


@app.get("/briefing")
def briefing_page():
    with open(os.path.join(FRONTEND_DIR, "briefing.html"), encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.get("/portfolio")
def portfolio_page():
    with open(os.path.join(FRONTEND_DIR, "portfolio.html"), encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.get("/lab")
def lab_page():
    with open(os.path.join(FRONTEND_DIR, "lab.html"), encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.get("/health")
def health():
    return {"status": "ok", "product": "Cortiq Decision Copilot v2"}


# ── History endpoints ─────────────────────────────────────

@app.get("/history")
def get_history():
    return _load_history()


@app.post("/history")
async def post_history(entry: dict):
    mode = entry.get("mode", "")
    key = (entry.get("key") or "").lower()
    entries = _load_history()
    entries = [
        e for e in entries
        if not (e.get("mode") == mode and (e.get("key") or "").lower() == key)
    ]
    entries.insert(0, entry)
    _save_history(entries[:50])
    return {"ok": True}


@app.delete("/history")
def clear_history():
    _save_history([])
    return {"ok": True}


@app.delete("/history/{mode}/{key}")
def delete_history_entry(mode: str, key: str):
    entries = _load_history()
    entries = [
        e for e in entries
        if not (e.get("mode") == mode and (e.get("key") or "").lower() == key.lower())
    ]
    _save_history(entries)
    return {"ok": True}


# ── SSE helpers ───────────────────────────────────────────
def _sse(event: str, data: str) -> str:
    data_lines = "\n".join(f"data: {line}" for line in data.split("\n"))
    return f"event: {event}\n{data_lines}\n\n"


# ── Analysis endpoints ────────────────────────────────────
@app.get("/analyze/equity")
async def analyze_equity(
    ticker: str, thesis: str = "", mandate: str = "",
    prev_verdict: str = "", prev_date: str = "",
):
    async def gen():
        try:
            async for event, data in run_equity_analysis(ticker, thesis, mandate, prev_verdict, prev_date):
                yield _sse(event, data)
        except Exception as e:
            yield _sse("error", str(e))
            yield _sse("done", "Falhou")

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"})


@app.get("/analyze/startup")
async def analyze_startup(
    name: str, url: str = "", thesis: str = "",
    prev_verdict: str = "", prev_date: str = "",
):
    async def gen():
        try:
            async for event, data in run_startup_analysis(name, url, thesis, prev_verdict, prev_date):
                yield _sse(event, data)
        except Exception as e:
            yield _sse("error", str(e))
            yield _sse("done", "Falhou")

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"})


# ── Briefing API ──────────────────────────────────────────
class DraftUpdate(BaseModel):
    subject: Optional[str] = None
    content: Optional[str] = None
    recipients: Optional[List[str]] = None


@app.get("/api/drafts")
def list_drafts():
    drafts = load_drafts()
    return [{"id": d["id"], "date": d.get("date"), "status": d.get("status"),
             "subject": d.get("subject"), "generated_at": d.get("generated_at"),
             "portfolio_id": d.get("portfolio_id"), "portfolio_name": d.get("portfolio_name"),
             "manager_name": d.get("manager_name"), "alert_count": len(d.get("alerts", []))}
            for d in drafts]


@app.get("/api/drafts/{draft_id}")
def get_draft(draft_id: str):
    draft = load_draft(draft_id)
    if not draft:
        raise HTTPException(404, "Draft não encontrado")
    return draft


@app.patch("/api/drafts/{draft_id}")
def update_draft(draft_id: str, body: DraftUpdate):
    draft = load_draft(draft_id)
    if not draft:
        raise HTTPException(404, "Draft não encontrado")
    if body.subject is not None:
        draft["subject"] = body.subject
    if body.content is not None:
        draft["content"] = body.content
    if body.recipients is not None:
        draft["recipients"] = body.recipients
    save_draft(draft)
    return draft


@app.post("/api/drafts/{draft_id}/send")
def send_draft(draft_id: str):
    draft = load_draft(draft_id)
    if not draft:
        raise HTTPException(404, "Draft não encontrado")
    if not draft.get("recipients"):
        raise HTTPException(400, "Nenhum destinatário configurado")

    ok = send_brief_email(draft)
    if ok:
        from datetime import datetime, timezone
        draft["status"] = "sent"
        draft["sent_at"] = datetime.now(timezone.utc).isoformat()
        save_draft(draft)
        return {"ok": True, "message": f"Brief enviado para {draft['recipients']}"}
    else:
        raise HTTPException(500, "Falha no envio. Verifique RESEND_API_KEY.")


@app.delete("/api/drafts/{draft_id}")
def discard_draft(draft_id: str):
    draft = load_draft(draft_id)
    if not draft:
        raise HTTPException(404, "Draft não encontrado")
    draft["status"] = "discarded"
    save_draft(draft)
    return {"ok": True}


@app.post("/api/briefing/run")
async def trigger_briefing(portfolio_id: Optional[str] = None):
    """Manually trigger one or more portfolio briefings."""
    try:
        drafts = await run_watchlist_briefing(portfolio_id=portfolio_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    primary = drafts[0] if drafts else None
    return {
        "ok": True,
        "count": len(drafts),
        "ids": [draft["id"] for draft in drafts],
        "primary_id": primary["id"] if primary else None,
    }


@app.get("/api/watchlist")
def get_watchlist():
    import json
    path = os.path.join(BASE_DIR, "watchlist.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@app.put("/api/watchlist")
async def update_watchlist(request: Request):
    body = await request.json()
    path = os.path.join(BASE_DIR, "watchlist.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(body, f, ensure_ascii=False, indent=2)
    return {"ok": True}


# ── Portfolio API ──────────────────────────────────────────

@app.get("/api/portfolio")
def get_portfolio():
    return _load_portfolio()


@app.post("/api/portfolio")
async def save_portfolio(request: Request):
    body = await request.json()
    _save_portfolio(body)
    return {"ok": True}


@app.get("/api/portfolio/history")
def get_portfolio_history():
    return _load_portfolio_history()


@app.post("/api/portfolio/analyze")
async def analyze_portfolio_companies():
    from agent import build_equity_queries, build_startup_queries, _run_queries_parallel
    from researcher import deduplicate_results
    from reporter import generate_brief_entry

    portfolio = _load_portfolio()
    companies = portfolio.get("companies", [])

    async def gen():
        if not companies:
            yield f"event: done\ndata: {json.dumps({'total': 0})}\n\n"
            return

        async def analyze_one(item):
            try:
                thesis = item.get("thesis", "")
                if item["type"] == "equity":
                    queries = build_equity_queries(item["name"], thesis)
                else:
                    queries = build_startup_queries(item["name"], item.get("url", ""), thesis)
                results = await _run_queries_parallel(queries)
                results = deduplicate_results(results)
                brief = await generate_brief_entry(results, item["name"], item["type"])
                result = {"id": item.get("id", ""), "name": item["name"], "type": item["type"], "brief": brief, "ok": True}
                _save_portfolio_history_entry({"name": item["name"], "type": item["type"], "brief": brief, "thesis": thesis, "url": item.get("url", "")})
                return result
            except Exception as e:
                return {"id": item.get("id", ""), "name": item["name"], "type": item["type"], "brief": f"Erro: {e}", "ok": False}

        tasks = [asyncio.create_task(analyze_one(item)) for item in companies]
        for task in asyncio.as_completed(tasks):
            result = await task
            yield f"event: result\ndata: {json.dumps(result, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0)
        yield f"event: done\ndata: {json.dumps({'total': len(companies)})}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"})


# ── Monitor Price/Alerts API ───────────────────────────────

def _fetch_monitor_price(ticker: str) -> dict:
    try:
        import yfinance as yf
        yf_ticker = ticker if "." in ticker else f"{ticker}.SA"
        stock = yf.Ticker(yf_ticker)
        info = stock.info
        price = info.get("currentPrice") or info.get("regularMarketPrice")
        prev_close = info.get("previousClose") or info.get("regularMarketPreviousClose")
        day_high = info.get("dayHigh") or info.get("regularMarketDayHigh")
        day_low  = info.get("dayLow")  or info.get("regularMarketDayLow")
        volume   = info.get("volume")  or info.get("regularMarketVolume")
        delta_pct = delta_val = None
        if price is not None and prev_close and prev_close > 0:
            delta_val = price - prev_close
            delta_pct = (delta_val / prev_close) * 100
        return {
            "ticker": ticker,
            "price": price,
            "prev_close": prev_close,
            "day_high": day_high,
            "day_low": day_low,
            "volume": volume,
            "delta_pct": round(delta_pct, 4) if delta_pct is not None else None,
            "delta_val": round(delta_val, 4) if delta_val is not None else None,
            "name": info.get("longName") or info.get("shortName"),
        }
    except Exception as e:
        return {"ticker": ticker, "error": str(e)}


@app.get("/api/monitor/price")
async def get_monitor_price(ticker: str):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _fetch_monitor_price, ticker)


@app.post("/api/monitor/check-alerts")
async def check_monitor_alerts(request: Request):
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    tickers = body.get("tickers", [])
    if not tickers:
        return {"alerts": [], "checked": 0}
    THRESHOLD = 3.0
    loop = asyncio.get_event_loop()

    async def check_one(ticker):
        data = await loop.run_in_executor(None, _fetch_monitor_price, ticker)
        if data.get("delta_pct") is not None and abs(data["delta_pct"]) >= THRESHOLD:
            direction = "alta" if data["delta_pct"] > 0 else "queda"
            return {
                "ticker": ticker,
                "message": f"Variação de {'+' if data['delta_pct'] > 0 else ''}{data['delta_pct']:.2f}% ({direction})",
                "delta_pct": data["delta_pct"],
                "data": data,
            }
        return None

    results = await asyncio.gather(*[asyncio.create_task(check_one(t)) for t in tickers])
    return {"alerts": [r for r in results if r], "checked": len(tickers)}


# ── Lab API ────────────────────────────────────────────────

@app.get("/api/lab/experiments")
def list_lab_experiments():
    import glob as _glob
    exp_dir = os.path.join(BASE_DIR, "experiments")
    os.makedirs(exp_dir, exist_ok=True)
    files = sorted(_glob.glob(os.path.join(exp_dir, "exp-*", "experiment.json")), reverse=True)[:50]
    results = []
    for f in files:
        with open(f, encoding="utf-8") as fh:
            try:
                d = json.load(fh)
                results.append({
                    "experiment_id": d.get("experiment_id"),
                    "timestamp": d.get("timestamp"),
                    "dry_run": d.get("dry_run"),
                    "promoted": d.get("promotion", {}).get("promoted"),
                    "candidates": [
                        {"id": c.get("candidate_id"), "mutation": c.get("mutation"),
                         "decision": c.get("decision"), "rationale": c.get("rationale"),
                         "aggregate_delta": c.get("comparison", {}).get("aggregate_delta")}
                        for c in d.get("candidates", [])
                    ],
                })
            except Exception:
                pass
    return results


@app.get("/api/lab/leaderboard")
def get_lab_leaderboard():
    path = os.path.join(BASE_DIR, "leaderboard", "index.json")
    if not os.path.exists(path):
        return {"experiments": [], "stats": {"total": 0, "promoted": 0, "keep_rate": 0}, "best": [], "worst": []}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    exps = data.get("experiments", [])
    total = len(exps)
    promoted = sum(1 for e in exps if e.get("decision") == "PROMOTED")
    keep_rate = round(promoted / total * 100, 1) if total else 0
    best  = sorted(exps, key=lambda e: e.get("aggregate_delta") or 0, reverse=True)[:5]
    worst = sorted(exps, key=lambda e: e.get("aggregate_delta") or 0)[:5]
    return {"experiments": exps[-20:], "stats": {"total": total, "promoted": promoted, "keep_rate": keep_rate}, "best": best, "worst": worst}


@app.post("/api/lab/run")
async def run_lab_experiment(candidates: int = 3, dry_run: bool = True, mutation_type: str | None = None):
    import sys as _sys
    _sys.path.insert(0, os.path.join(BASE_DIR, "scripts"))
    from lab_runner import run_experiment_stream

    async def gen():
        try:
            async for chunk in run_experiment_stream(candidates=candidates, dry_run=dry_run, mutation_type=mutation_type):
                yield chunk
        except Exception as e:
            yield f"event: __error__\ndata: {json.dumps({'message': str(e)})}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"})


@app.get("/api/lab/loop/status")
def lab_loop_status():
    return {"running": _lab_loop_state["running"]}


@app.post("/api/lab/loop/start")
def lab_loop_start(interval_hours: int = 6):
    if _lab_loop_state["running"]:
        return {"ok": False, "message": "Loop já está rodando."}

    def _loop_worker():
        import sys as _sys, time
        _sys.path.insert(0, os.path.join(BASE_DIR, "scripts"))
        from experiment_engine import run_experiment
        while _lab_loop_state["running"]:
            try:
                run_experiment(candidates=3, dry_run=False)
            except Exception as e:
                print(f"[lab loop] erro: {e}")
            time.sleep(interval_hours * 3600)

    _lab_loop_state["running"] = True
    t = threading.Thread(target=_loop_worker, daemon=True)
    _lab_loop_state["thread"] = t
    t.start()
    return {"ok": True, "message": f"Loop iniciado. Intervalo: {interval_hours}h."}


@app.post("/api/lab/loop/stop")
def lab_loop_stop():
    _lab_loop_state["running"] = False
    return {"ok": True, "message": "Loop parado."}


@app.get("/api/lab/evolution")
def get_lab_evolution():
    path = os.path.join(BASE_DIR, "leaderboard", "index.json")
    if not os.path.exists(path):
        return {"improvements": [], "total_experiments": 0, "total_improvements": 0}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    exps = data.get("experiments", [])
    improvements = []
    for e in exps:
        if e.get("decision") != "PROMOTED":
            continue
        mutation = e.get("mutation", {})
        mtype = mutation.get("type", "")
        label, description = MUTATION_LABELS.get(mtype, (mtype, "Otimização aplicada ao pipeline de research"))
        delta = e.get("aggregate_delta") or 0
        improvements.append({
            "timestamp": e.get("timestamp", ""),
            "label": label,
            "description": description,
            "delta": delta,
            "mutation_type": mtype,
        })
    improvements.sort(key=lambda x: x["timestamp"], reverse=True)
    return {"improvements": improvements, "total_experiments": len(exps), "total_improvements": len(improvements)}
