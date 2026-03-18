"""main.py — Cortiq Decision Copilot v2
FastAPI server with SSE streaming, daily briefing scheduler, and draft review API.
"""
import asyncio
import json
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
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
async def update_watchlist(request):
    import json
    body = await request.json()
    path = os.path.join(BASE_DIR, "watchlist.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(body, f, ensure_ascii=False, indent=2)
    return {"ok": True}
