"""monitor.py — Drys Capital Portfolio CRM
Daily snapshots per ticker: price, delta day-over-day, news, AI summary.
Builds history so managers track evolution over time.
"""
import json
import os
import asyncio
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TICKERS_DIR = os.path.join(BASE_DIR, "data", "tickers")
WATCHLIST_FILE = os.path.join(BASE_DIR, "watchlist.json")


# ── Watchlist ─────────────────────────────────────────────

def load_watchlist_raw() -> dict:
    if not os.path.exists(WATCHLIST_FILE):
        return {"portfolios": []}
    with open(WATCHLIST_FILE, encoding="utf-8") as f:
        return json.load(f)


def save_watchlist_raw(data: dict) -> None:
    with open(WATCHLIST_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_portfolios() -> List[Dict]:
    wl = load_watchlist_raw()
    return wl.get("portfolios", [])


def get_all_equity_tickers() -> List[Dict]:
    result = []
    for p in get_portfolios():
        for e in p.get("equity", []):
            result.append({
                "ticker": e["ticker"].upper(),
                "thesis": e.get("thesis", ""),
                "portfolio_id": p.get("id", "default"),
                "portfolio_name": p.get("portfolio_name", "Carteira"),
            })
    return result


def add_ticker_to_portfolio(portfolio_id: str, ticker: str, thesis: str = "") -> bool:
    wl = load_watchlist_raw()
    for p in wl.get("portfolios", []):
        if p.get("id") == portfolio_id:
            existing = {e["ticker"].upper() for e in p.get("equity", [])}
            if ticker.upper() not in existing:
                p.setdefault("equity", []).append({
                    "ticker": ticker.upper(), "thesis": thesis
                })
                save_watchlist_raw(wl)
            return True
    return False


def remove_ticker_from_portfolio(portfolio_id: str, ticker: str) -> bool:
    wl = load_watchlist_raw()
    for p in wl.get("portfolios", []):
        if p.get("id") == portfolio_id:
            p["equity"] = [
                e for e in p.get("equity", [])
                if e["ticker"].upper() != ticker.upper()
            ]
            save_watchlist_raw(wl)
            return True
    return False


# ── Snapshots ─────────────────────────────────────────────

def _ticker_dir(ticker: str) -> str:
    return os.path.join(TICKERS_DIR, ticker.upper())


def _snapshot_path(ticker: str, dt: date) -> str:
    return os.path.join(_ticker_dir(ticker), f"{dt.isoformat()}.json")


def load_snapshot(ticker: str, dt: date) -> Optional[Dict]:
    path = _snapshot_path(ticker, dt)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_snapshot(ticker: str, data: Dict, dt: date = None) -> None:
    dt = dt or date.today()
    os.makedirs(_ticker_dir(ticker), exist_ok=True)
    with open(_snapshot_path(ticker, dt), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_history(ticker: str, days: int = 30) -> List[Dict]:
    t_dir = _ticker_dir(ticker)
    if not os.path.exists(t_dir):
        return []
    files = sorted(
        [f for f in os.listdir(t_dir) if f.endswith(".json")],
        reverse=True
    )[:days]
    result = []
    for fname in files:
        try:
            with open(os.path.join(t_dir, fname), encoding="utf-8") as f:
                result.append(json.load(f))
        except Exception:
            pass
    return result


# ── AI Summary ────────────────────────────────────────────

async def _ai_daily_summary(ticker: str, price_info: dict, news: list) -> str:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return ""
    try:
        from anthropic import AsyncAnthropic
        client = AsyncAnthropic(api_key=api_key)
        news_text = "\n".join(f"- {n['title']}" for n in news[:5]) or "Sem notícias relevantes."
        change = price_info.get("change_pct", "")
        price = price_info.get("price", "")
        msg = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=180,
            messages=[{"role": "user", "content": (
                f"Ativo: {ticker} | Preço: {price} | Variação: {change}\n"
                f"Notícias de hoje:\n{news_text}\n\n"
                f"Em 2 frases diretas, o que o gestor de investimentos precisa saber sobre "
                f"{ticker} hoje? Foque no que é ACIONÁVEL ou relevante para a posição."
            )}]
        )
        return msg.content[0].text.strip()
    except Exception:
        return ""


# ── Refresh ───────────────────────────────────────────────

async def refresh_ticker(ticker: str, force: bool = False) -> Dict:
    """Fetch price + news for ticker, store daily snapshot."""
    from equity_data import get_equity_data
    from researcher import search_topic

    today = date.today()

    if not force:
        existing = load_snapshot(ticker, today)
        if existing and not existing.get("error") and existing.get("price"):
            return existing

    # Fetch price data and news in parallel
    loop = asyncio.get_event_loop()
    price_task = get_equity_data(ticker)
    news_task = loop.run_in_executor(
        None, search_topic,
        f"{ticker} bolsa notícias hoje análise investidores"
    )
    price_data, news_results = await asyncio.gather(price_task, news_task)

    news = [
        {
            "title": r["title"],
            "url": r.get("url", ""),
            "snippet": r["content"][:200],
            "source_type": r.get("source_type", "web"),
        }
        for r in (news_results or [])[:5]
        if r.get("url")
    ]

    # Compute delta vs yesterday's stored snapshot
    prev_snap = None
    for d in range(1, 8):  # look back up to 7 days for last snapshot
        prev_snap = load_snapshot(ticker, today - timedelta(days=d))
        if prev_snap and prev_snap.get("price_raw"):
            break

    price_raw = None
    try:
        raw = price_data.get("price", "")
        if raw:
            price_raw = float(str(raw).replace("R$ ", "").replace(",", "."))
    except Exception:
        pass

    # Fallback: use yfinance previousClose when no stored snapshot exists
    yf_prev_raw = price_data.get("previous_close_raw")
    price_prev_raw = (
        prev_snap.get("price_raw") if prev_snap
        else yf_prev_raw
    )
    prev_date = (
        prev_snap.get("date") if prev_snap
        else (today - timedelta(days=1)).isoformat()
    )
    change_abs = round(price_raw - price_prev_raw, 2) if price_raw and price_prev_raw else None
    change_pct_vs_prev = (
        round((change_abs / price_prev_raw) * 100, 2)
        if change_abs is not None and price_prev_raw
        else None
    )

    ai_summary = await _ai_daily_summary(ticker, price_data, news)

    snapshot = {
        "ticker": ticker.upper(),
        "date": today.isoformat(),
        "fetched_at": datetime.utcnow().isoformat() + "Z",
        "price_raw": price_raw,
        "price_prev_raw": price_prev_raw,
        "prev_date": prev_date,
        "change_abs_vs_prev": change_abs,
        "change_pct_vs_prev": change_pct_vs_prev,
        **price_data,
        "news": news,
        "ai_summary": ai_summary,
    }

    save_snapshot(ticker, snapshot, today)
    return snapshot


async def refresh_all(force: bool = False) -> List[Dict]:
    tickers = [t["ticker"] for t in get_all_equity_tickers()]
    if not tickers:
        return []
    results = await asyncio.gather(*[refresh_ticker(t, force) for t in tickers])
    return list(results)


# ── Price Alerts ───────────────────────────────────────────

def _send_price_alert_email(portfolio: dict, triggered: list) -> bool:
    """Send price movement alert email via Resend."""
    api_key = os.environ.get("RESEND_API_KEY", "")
    recipients = portfolio.get("alert_recipients", [])
    if not api_key or not recipients:
        return False

    try:
        import resend
        resend.api_key = api_key
        from_addr = os.environ.get("BRIEF_FROM_EMAIL", "onboarding@resend.dev")

        threshold = portfolio.get("price_alert_threshold_pct", 3.0)
        date_str = date.today().strftime("%d/%m/%Y")
        portfolio_name = portfolio.get("portfolio_name", "Carteira")

        items_html = ""
        for item in triggered:
            chg = item["change_pct"]
            color = "#16a34a" if chg > 0 else "#dc2626"
            arrow = "▲" if chg > 0 else "▼"
            sign = "+" if chg > 0 else ""
            ai = item.get("ai_summary", "")
            items_html += (
                f"<div style='margin:12px 0;padding:14px;background:#f8fafc;"
                f"border-radius:6px;border-left:3px solid {color}'>"
                f"<strong style='font-family:monospace;font-size:15px'>{item['ticker']}</strong>"
                f"<span style='font-family:monospace;color:{color};font-weight:600;"
                f"margin-left:12px'>{arrow} {sign}{chg:.2f}%</span>"
                f"<div style='font-size:13px;color:#64748b;margin-top:4px'>{item.get('price','')}</div>"
                + (f"<div style='font-size:12px;color:#94a3b8;margin-top:4px'>{ai}</div>" if ai else "")
                + "</div>"
            )

        html = (
            f"<div style='max-width:600px;margin:0 auto;padding:24px;font-family:sans-serif'>"
            f"<h2 style='color:#0f172a'>🔔 Alerta de Preço — {portfolio_name}</h2>"
            f"<p style='color:#475569'><strong>Data:</strong> {date_str} &nbsp;|&nbsp; "
            f"<strong>Threshold:</strong> ±{threshold}%</p>"
            f"<hr style='border:none;border-top:1px solid #e2e8f0'>"
            f"{items_html}"
            f"<p style='font-size:11px;color:#94a3b8;margin-top:24px'>Gerado automaticamente pelo Cortiq Decision Copilot</p>"
            f"</div>"
        )

        resend.Emails.send({
            "from": f"Cortiq Alertas <{from_addr}>",
            "to": recipients,
            "subject": (
                f"🔔 Cortiq — {portfolio_name} — "
                f"{len(triggered)} ativo(s) com variação > ±{threshold}% — {date_str}"
            ),
            "html": html,
        })
        return True
    except Exception as e:
        print(f"[monitor] price alert email error: {e}")
        return False


async def check_and_send_price_alerts(portfolio_id: Optional[str] = None) -> List[Dict]:
    """Check all portfolios for tickers with |change_pct_vs_prev| >= threshold.
    Sends email if auto_send_alerts=True and alert_recipients configured.
    Returns list of portfolio alert results."""
    wl = load_watchlist_raw()
    portfolios = wl.get("portfolios", [])
    if portfolio_id:
        portfolios = [p for p in portfolios if p.get("id") == portfolio_id]

    today = date.today()
    all_results = []

    for portfolio in portfolios:
        threshold = float(portfolio.get("price_alert_threshold_pct", 3.0))
        triggered = []

        for equity in portfolio.get("equity", []):
            ticker = equity["ticker"].upper()
            snap = load_snapshot(ticker, today)
            if not snap:
                continue
            change_pct = snap.get("change_pct_vs_prev")
            if change_pct is not None and abs(change_pct) >= threshold:
                triggered.append({
                    "ticker": ticker,
                    "change_pct": change_pct,
                    "price": snap.get("price"),
                    "ai_summary": snap.get("ai_summary", ""),
                })

        email_sent = False
        if triggered and portfolio.get("auto_send_alerts") and portfolio.get("alert_recipients"):
            email_sent = _send_price_alert_email(portfolio, triggered)

        all_results.append({
            "portfolio_id": portfolio.get("id"),
            "portfolio_name": portfolio.get("portfolio_name", ""),
            "threshold": threshold,
            "triggered": triggered,
            "email_sent": email_sent,
        })

    return all_results
