"""main.py — Cortiq Decision Copilot
FastAPI server with SSE streaming for equity + startup analysis.
"""
import json
import os

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

from agent import run_equity_analysis, run_startup_analysis

load_dotenv()

app = FastAPI(title="Cortiq Decision Copilot")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
STATIC_DIR = os.path.join(FRONTEND_DIR, "static")

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index():
    with open(os.path.join(FRONTEND_DIR, "index.html"), encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.get("/health")
def health():
    return {"status": "ok", "product": "Cortiq Decision Copilot"}


def _sse(event: str, data: str) -> str:
    return f"event: {event}\ndata: {data}\n\n"


@app.get("/analyze/equity")
async def analyze_equity(ticker: str, thesis: str = "", mandate: str = ""):
    """SSE: Real-time equity thesis validation."""
    async def gen():
        try:
            async for event, data in run_equity_analysis(ticker, thesis, mandate):
                yield _sse(event, data)
        except Exception as e:
            yield _sse("error", str(e))
            yield _sse("done", "Falhou")

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


@app.get("/analyze/startup")
async def analyze_startup(name: str, url: str = "", thesis: str = ""):
    """SSE: Real-time startup due diligence."""
    async def gen():
        try:
            async for event, data in run_startup_analysis(name, url, thesis):
                yield _sse(event, data)
        except Exception as e:
            yield _sse("error", str(e))
            yield _sse("done", "Falhou")

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )
