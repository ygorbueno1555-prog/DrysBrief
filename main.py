"""main.py — Cortiq Decision Copilot v2
FastAPI server with SSE streaming, daily briefing scheduler, and draft review API.
"""
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

        scheduler = AsyncIOScheduler(timezone=ZoneInfo("America/Sao_Paulo"))
        scheduler.add_job(run_watchlist_briefing, "cron", hour=briefing_hour, minute=0)
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

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# ── Pages ─────────────────────────────────────────────────
@app.get("/")
def index():
    with open(os.path.join(FRONTEND_DIR, "index.html"), encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.get("/briefing")
def briefing_page():
    with open(os.path.join(FRONTEND_DIR, "briefing.html"), encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.get("/health")
def health():
    return {"status": "ok", "product": "Cortiq Decision Copilot v2"}


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
