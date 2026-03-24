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
DRAFTS_DIR = os.path.join(
    os.environ.get("PERSISTENT_DATA_DIR", os.path.join(os.path.dirname(__file__), "data")),
    "drafts"
)

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

VERDICT_KEYWORDS = [
    "TESE MANTIDA",
    "TESE ALTERADA",
    "TESE INVALIDADA",
    "INVESTIR",
    "MONITORAR",
    "PASSAR",
    "COMPRAR",
    "MANTER",
    "REDUZIR",
    "VENDER",
]
ALERT_LEVELS = {"VERDE": "green", "AMARELO": "amber", "VERMELHO": "red"}
COLOR_TO_ALERT = {"green": "VERDE", "amber": "AMARELO", "red": "VERMELHO"}
SEVERITY_RANK = {"VERDE": 0, "AMARELO": 1, "VERMELHO": 2}


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "portfolio"


def _normalize_portfolios(config: dict) -> list[dict]:
    """Support both legacy global watchlist and per-manager portfolio configs."""
    default_recipients = config.get("recipients", [])
    default_mandate = config.get("mandate", "")
    portfolios = config.get("portfolios") or []

    if portfolios:
        normalized = []
        for idx, item in enumerate(portfolios, 1):
            portfolio_name = (
                item.get("name")
                or item.get("portfolio_name")
                or item.get("portfolio")
                or f"Portfolio {idx}"
            ).strip()
            manager_name = (
                item.get("manager_name")
                or item.get("manager")
                or portfolio_name
            ).strip()

            normalized.append({
                "id": item.get("id") or _slugify(f"{manager_name}-{portfolio_name}"),
                "portfolio_name": portfolio_name,
                "manager_name": manager_name,
                "equity": item.get("equity") or item.get("equities") or [],
                "startups": item.get("startups") or [],
                "recipients": item.get("recipients") or default_recipients,
                "mandate": item.get("mandate") or item.get("notes") or default_mandate,
                "alert_recipients": item.get("alert_recipients") or item.get("recipients") or default_recipients,
                "auto_send_alerts": bool(item.get("auto_send_alerts", False)),
            })
        return normalized

    return [{
        "id": _slugify(config.get("name", "watchlist-geral")),
        "portfolio_name": config.get("name", "Watchlist Geral"),
        "manager_name": config.get("manager_name", "Equipe Cortiq"),
        "equity": config.get("equity", []),
        "startups": config.get("startups", []),
        "recipients": default_recipients,
        "mandate": default_mandate,
        "alert_recipients": config.get("alert_recipients") or default_recipients,
        "auto_send_alerts": bool(config.get("auto_send_alerts", False)),
    }]


def _extract_verdict(summary: str) -> str:
    upper = summary.upper()
    for keyword in VERDICT_KEYWORDS:
        if keyword in upper:
            return keyword
    return "—"


def _extract_alert_level(summary: str, verdict: str) -> str:
    match = re.search(r"Alerta hoje:\s*(VERDE|AMARELO|VERMELHO)", summary, re.IGNORECASE)
    if match:
        return match.group(1).upper()

    verdict_upper = verdict.upper()
    if any(k in verdict_upper for k in ["INVALIDADA", "PASSAR", "REDUZIR", "VENDER"]):
        return "VERMELHO"
    if any(k in verdict_upper for k in ["ALTERADA", "MONITORAR", "MANTER"]):
        return "AMARELO"
    return "VERDE"


def _extract_trigger(summary: str) -> str:
    match = re.search(r"Gatilho:\s*(.+)", summary, re.IGNORECASE)
    return match.group(1).strip() if match else ""


def _load_previous_portfolio_draft(portfolio_id: str, current_draft_id: str) -> dict | None:
    for draft in load_drafts():
        if draft.get("id") == current_draft_id:
            continue
        if draft.get("portfolio_id") == portfolio_id:
            return draft
    return None


def _build_alerts(analyses: list[dict], previous_draft: dict | None) -> list[dict]:
    previous_map = {}
    if previous_draft:
        previous_map = {
            item.get("key"): item
            for item in previous_draft.get("analyses", [])
        }

    alerts = []
    for item in analyses:
        previous = previous_map.get(item["key"])
        reasons = []

        if item["alert_level"] == "VERMELHO":
            reasons.append("alerta critico")
        elif item["alert_level"] == "AMARELO" and not previous:
            reasons.append("novo item com alerta")

        if previous:
            previous_verdict = previous.get("verdict", "—")
            previous_alert = previous.get("alert_level") or COLOR_TO_ALERT.get(previous.get("color", "green"), "VERDE")

            if previous_verdict != item["verdict"]:
                reasons.append(f"veredito mudou de {previous_verdict} para {item['verdict']}")
            if SEVERITY_RANK[item["alert_level"]] > SEVERITY_RANK.get(previous_alert, 0):
                reasons.append(f"alerta piorou de {previous_alert} para {item['alert_level']}")

        if item["alert_level"] in ("AMARELO", "VERMELHO") and not reasons:
            reasons.append("gatilho relevante no radar")

        if reasons:
            alerts.append({
                "key": item["key"],
                "mode": item["mode"],
                "verdict": item["verdict"],
                "alert_level": item["alert_level"],
                "trigger": item.get("trigger", ""),
                "reason": "; ".join(reasons),
            })

    alerts.sort(key=lambda item: SEVERITY_RANK[item["alert_level"]], reverse=True)
    return alerts


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
    verdict = _extract_verdict(summary)
    alert_level = _extract_alert_level(summary, verdict)
    trigger = _extract_trigger(summary)
    color = ALERT_LEVELS.get(alert_level, "green")

    return {
        "mode": mode,
        "key": name,
        "verdict": verdict,
        "color": color,
        "alert_level": alert_level,
        "trigger": trigger,
        "summary": summary,
    }


def _build_markdown(analyses: list, alerts: list, date_str: str, portfolio: dict) -> str:
    equities  = [a for a in analyses if a["mode"] == "equity"]
    startups  = [a for a in analyses if a["mode"] == "startup"]

    lines = [f"# Cortiq Portfolio Watch — {portfolio['portfolio_name']} — {date_str}", ""]
    lines.append(f"**Gestor:** {portfolio['manager_name']}")
    if portfolio.get("mandate"):
        lines.append(f"**Mandato / contexto:** {portfolio['mandate']}")
    lines.append("")

    if alerts:
        lines += ["## 🚨 Alertas Automáticos", ""]
        for alert in alerts:
            icon = {"VERDE": "🟢", "AMARELO": "🟡", "VERMELHO": "🔴"}.get(alert["alert_level"], "⚪")
            trigger = f" Gatilho: {alert['trigger']}" if alert.get("trigger") else ""
            lines.append(
                f"- {icon} **{alert['key']}** — {alert['verdict']} — {alert['reason']}.{trigger}"
            )
        lines += ["", "---", ""]

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

    lines += [
        "---",
        f"*Gerado automaticamente · Gestor: {portfolio['manager_name']} · Portfolio: {portfolio['portfolio_name']}*",
    ]
    return "\n".join(lines)


def _build_alert_email_markdown(draft: dict) -> str:
    alerts = draft.get("alerts", [])
    lines = [
        f"# Alerta Cortiq — {draft.get('portfolio_name', 'Portfolio')}",
        "",
        f"**Gestor:** {draft.get('manager_name', 'N/A')}",
        f"**Data:** {draft.get('date', '')}",
        "",
    ]
    for alert in alerts:
        icon = {"VERDE": "🟢", "AMARELO": "🟡", "VERMELHO": "🔴"}.get(alert["alert_level"], "⚪")
        lines.append(f"## {icon} {alert['key']}")
        lines.append(f"**Veredito:** {alert['verdict']}")
        lines.append(f"**Motivo:** {alert['reason']}")
        if alert.get("trigger"):
            lines.append(f"**Gatilho:** {alert['trigger']}")
        lines.append("")
    return "\n".join(lines)


async def _generate_portfolio_draft(portfolio: dict, now: datetime, date_str: str) -> dict:
    draft_id = f"{now.strftime('%Y-%m-%d')}--{portfolio['id']}"

    equity_items = portfolio.get("equity", [])
    startup_items = portfolio.get("startups", [])

    # Run all items concurrently
    tasks = (
        [_analyze_item(e["ticker"], "equity",  EQUITY_QUERIES)  for e in equity_items] +
        [_analyze_item(s["name"],   "startup", STARTUP_QUERIES) for s in startup_items]
    )
    analyses = await asyncio.gather(*tasks) if tasks else []
    previous_draft = _load_previous_portfolio_draft(portfolio["id"], draft_id)
    alerts = _build_alerts(list(analyses), previous_draft)

    content = _build_markdown(list(analyses), alerts, date_str, portfolio)
    subject_target = portfolio["portfolio_name"]
    if portfolio["manager_name"].lower() != portfolio["portfolio_name"].lower():
        subject_target = f"{portfolio['manager_name']} — {portfolio['portfolio_name']}"

    draft = {
        "id": draft_id,
        "date": date_str,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "draft",
        "subject": f"Cortiq Portfolio Watch — {subject_target} — {date_str}",
        "content": content,
        "analyses": list(analyses),
        "alerts": alerts,
        "recipients": portfolio.get("recipients", []),
        "alert_recipients": portfolio.get("alert_recipients", []),
        "auto_send_alerts": portfolio.get("auto_send_alerts", False),
        "portfolio_id": portfolio["id"],
        "portfolio_name": portfolio["portfolio_name"],
        "manager_name": portfolio["manager_name"],
        "mandate": portfolio.get("mandate", ""),
        "previous_draft_id": previous_draft.get("id") if previous_draft else None,
        "sent_at": None,
    }

    os.makedirs(DRAFTS_DIR, exist_ok=True)
    path = os.path.join(DRAFTS_DIR, f"{draft_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(draft, f, ensure_ascii=False, indent=2)

    if draft["alerts"] and draft.get("auto_send_alerts"):
        send_alert_email(draft)

    return draft


async def run_watchlist_briefing(portfolio_id: str | None = None) -> list[dict]:
    """Generate one draft per configured portfolio. Returns the created drafts."""
    watchlist_path = os.path.join(os.path.dirname(__file__), "watchlist.json")
    with open(watchlist_path, encoding="utf-8") as f:
        watchlist = json.load(f)

    now = datetime.now(SAO_PAULO)
    date_str = now.strftime("%a, %d %b %Y").capitalize()
    portfolios = _normalize_portfolios(watchlist)

    if portfolio_id:
        portfolios = [p for p in portfolios if p["id"] == portfolio_id]
        if not portfolios:
            raise ValueError(f"Portfolio não encontrado: {portfolio_id}")

    drafts = await asyncio.gather(
        *[_generate_portfolio_draft(portfolio, now, date_str) for portfolio in portfolios]
    )
    return list(drafts)


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


def send_alert_email(draft: dict) -> bool:
    """Send only the alert section to alert recipients."""
    api_key = os.environ.get("RESEND_API_KEY", "")
    recipients = draft.get("alert_recipients", [])
    if not api_key or not recipients or not draft.get("alerts"):
        return False

    try:
        import resend
        resend.api_key = api_key

        from_addr = os.environ.get("BRIEF_FROM_EMAIL", "onboarding@resend.dev")
        html = _markdown_to_html(_build_alert_email_markdown(draft))

        resend.Emails.send({
            "from": f"Cortiq Alerts <{from_addr}>",
            "to": recipients,
            "subject": f"Alerta Cortiq — {draft.get('portfolio_name', 'Portfolio')} — {draft.get('date', '')}",
            "html": html,
        })
        return True
    except Exception as e:
        print(f"[alerts] email error: {e}")
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
