"""briefing_runner.py — Cortiq Decision Copilot
Generates the daily morning brief for the watchlist and saves as a draft.
"""
import asyncio
import json
import os
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from researcher import search_topic, deduplicate_results
from reporter import generate_brief_entry

SAO_PAULO = ZoneInfo("America/Sao_Paulo")
DRAFTS_DIR = "drafts"

EQUITY_QUERIES = lambda ticker: [
    f"{ticker} resultado financeiro EBITDA receita lucro 2025",
    f"{ticker} notícias recentes eventos catalisadores riscos",
    f"{ticker} valuation preço analistas recomendação",
]

STARTUP_QUERIES = lambda name: [
    f"{name} tração clientes receita crescimento 2025 2026",
    f"{name} notícias funding rodada parcerias expansão recente",
    f"{name} problemas riscos desafios concorrência",
]


async def _analyze_item(name: str, mode: str, queries_fn) -> dict:
    """Run lightweight research + brief summary for one watchlist item."""
    loop = asyncio.get_event_loop()
    queries = queries_fn(name)

    # Parallel search
    results_nested = await asyncio.gather(
        *[loop.run_in_executor(None, search_topic, q, 3) for q in queries]
    )
    results = deduplicate_results([r for sub in results_nested for r in sub])

    summary = await generate_brief_entry(results, name, mode)

    # Extract verdict from summary
    verdict = "—"
    for kw in ["TESE MANTIDA", "INVESTIR", "MANTER", "MONITORAR",
                "TESE ALTERADA", "TESE INVALIDADA", "PASSAR", "REDUZIR", "VENDER", "COMPRAR"]:
        if kw in summary.upper():
            verdict = kw
            break

    color = "green"
    if any(k in verdict for k in ["ALTERADA", "MONITORAR", "MANTER"]):
        color = "amber"
    if any(k in verdict for k in ["INVALIDADA", "PASSAR", "REDUZIR", "VENDER"]):
        color = "red"

    return {"mode": mode, "key": name, "verdict": verdict, "color": color, "summary": summary}


def _build_markdown(analyses: list, date_str: str) -> str:
    equities  = [a for a in analyses if a["mode"] == "equity"]
    startups  = [a for a in analyses if a["mode"] == "startup"]
    attention = [a for a in analyses if a["color"] in ("amber", "red")]

    lines = [f"# Cortiq Morning Brief — {date_str}", ""]

    if equities:
        lines += ["## 📊 Watchlist — Equities", ""]
        for a in equities:
            icon = {"green": "🟢", "amber": "🟡", "red": "🔴"}.get(a["color"], "⚪")
            lines += [f"### {icon} {a['key']}", "", a["summary"], ""]

    if startups:
        lines += ["---", "", "## 🔬 Watchlist — Startups", ""]
        for a in startups:
            icon = {"green": "🟢", "amber": "🟡", "red": "🔴"}.get(a["color"], "⚪")
            lines += [f"### {icon} {a['key']}", "", a["summary"], ""]

    if attention:
        lines += ["---", "", "## ⚡ Pontos de Atenção Hoje", ""]
        for a in attention:
            lines.append(f"- **{a['key']}**: {a['verdict']}")
        lines.append("")

    lines += [
        "---",
        f"*Gerado automaticamente às 07:00 · Cortiq Decision Copilot*",
    ]
    return "\n".join(lines)


async def run_watchlist_briefing() -> dict:
    """Generate the daily briefing and save as draft. Returns the draft."""
    watchlist_path = os.path.join(os.path.dirname(__file__), "watchlist.json")
    with open(watchlist_path, encoding="utf-8") as f:
        watchlist = json.load(f)

    now = datetime.now(SAO_PAULO)
    date_str = now.strftime("%a, %d %b %Y").capitalize()
    draft_id = now.strftime("%Y-%m-%d")

    equity_items  = watchlist.get("equity", [])
    startup_items = watchlist.get("startups", [])

    # Run all items concurrently
    tasks = (
        [_analyze_item(e["ticker"], "equity",  EQUITY_QUERIES)  for e in equity_items] +
        [_analyze_item(s["name"],   "startup", STARTUP_QUERIES) for s in startup_items]
    )
    analyses = await asyncio.gather(*tasks)

    content = _build_markdown(list(analyses), date_str)

    draft = {
        "id": draft_id,
        "date": date_str,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "draft",
        "subject": f"Cortiq Morning Brief — {date_str}",
        "content": content,
        "analyses": list(analyses),
        "recipients": watchlist.get("recipients", []),
        "sent_at": None,
    }

    os.makedirs(DRAFTS_DIR, exist_ok=True)
    path = os.path.join(DRAFTS_DIR, f"{draft_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(draft, f, ensure_ascii=False, indent=2)

    return draft


def load_drafts() -> list:
    os.makedirs(DRAFTS_DIR, exist_ok=True)
    drafts = []
    for fname in sorted(os.listdir(DRAFTS_DIR), reverse=True):
        if fname.endswith(".json"):
            try:
                with open(os.path.join(DRAFTS_DIR, fname), encoding="utf-8") as f:
                    drafts.append(json.load(f))
            except Exception:
                pass
    return drafts


def load_draft(draft_id: str) -> dict | None:
    path = os.path.join(DRAFTS_DIR, f"{draft_id}.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_draft(draft: dict) -> None:
    os.makedirs(DRAFTS_DIR, exist_ok=True)
    path = os.path.join(DRAFTS_DIR, f"{draft['id']}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(draft, f, ensure_ascii=False, indent=2)


def send_brief_email(draft: dict) -> bool:
    """Send the brief via Resend. Returns True on success."""
    api_key = os.environ.get("RESEND_API_KEY", "")
    if not api_key:
        return False

    recipients = draft.get("recipients", [])
    if not recipients:
        return False

    try:
        import resend
        resend.api_key = api_key

        from_addr = os.environ.get("BRIEF_FROM_EMAIL", "onboarding@resend.dev")

        # Convert markdown to simple HTML
        html = _markdown_to_html(draft["content"])

        resend.Emails.send({
            "from": f"Cortiq Brief <{from_addr}>",
            "to": recipients,
            "subject": draft["subject"],
            "html": html,
        })
        return True
    except Exception as e:
        print(f"[briefing] email error: {e}")
        return False


def _markdown_to_html(md: str) -> str:
    """Minimal markdown → HTML for email."""
    lines = md.split("\n")
    html_lines = []
    for line in lines:
        if line.startswith("# "):
            html_lines.append(f'<h1 style="color:#1e293b;font-family:sans-serif">{line[2:]}</h1>')
        elif line.startswith("## "):
            html_lines.append(f'<h2 style="color:#334155;font-family:sans-serif;border-bottom:1px solid #e2e8f0">{line[3:]}</h2>')
        elif line.startswith("### "):
            html_lines.append(f'<h3 style="color:#0f172a;font-family:sans-serif">{line[4:]}</h3>')
        elif line.startswith("---"):
            html_lines.append('<hr style="border:none;border-top:1px solid #e2e8f0">')
        elif line.startswith("- "):
            html_lines.append(f'<li style="font-family:sans-serif;color:#334155">{line[2:]}</li>')
        elif line.startswith("*") and line.endswith("*"):
            html_lines.append(f'<p style="color:#94a3b8;font-size:12px;font-family:sans-serif">{line[1:-1]}</p>')
        elif line.strip():
            # Bold
            text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', line)
            html_lines.append(f'<p style="font-family:sans-serif;color:#334155;line-height:1.6">{text}</p>')
        else:
            html_lines.append('<br>')
    return f'<div style="max-width:640px;margin:0 auto;padding:24px">' + "\n".join(html_lines) + "</div>"
