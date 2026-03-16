"""agent.py — Cortiq Decision Copilot
Orchestrates multi-step research + report generation for equity and startup analysis.
"""
import json
from typing import AsyncGenerator, Tuple

from researcher import search_topic
from reporter import stream_equity_report, stream_startup_report


def build_equity_queries(ticker: str, thesis: str) -> list[str]:
    return [
        f"{ticker} resultado financeiro receita lucro EBITDA 2025 2026",
        f"{ticker} valuation múltiplos P/L EV/EBITDA target price analistas",
        f"{ticker} catalisadores crescimento perspectivas setor mercado",
        f"{ticker} riscos ameaças regulatório competição headwinds",
        f"{ticker} notícias recentes eventos corporativos dividendos 2025",
        f"{thesis or ticker} tese investimento análise fundamentalista",
    ]


def build_startup_queries(name: str, url: str, thesis: str) -> list[str]:
    return [
        f"{name} founders CEO CTO fundadores experiência background exits anteriores",
        f"{name} startup rodada investimento funding captação valuação série seed",
        f"{name} mercado endereçável TAM crescimento setor tendência",
        f"{name} concorrentes competidores alternativas comparação market share",
        f"{name} tração clientes receita ARR crescimento produto métricas",
        f"{name} notícias lançamentos parcerias expansão 2025 2026",
        f"{name} problemas críticas desafios riscos {thesis or ''}".strip(),
    ]


async def run_equity_analysis(
    ticker: str, thesis: str = "", mandate: str = ""
) -> AsyncGenerator[Tuple[str, str], None]:
    yield "status", f"Iniciando análise de {ticker}..."

    queries = build_equity_queries(ticker, thesis)
    yield "queries", json.dumps(queries, ensure_ascii=False)

    all_results = []
    for i, query in enumerate(queries, 1):
        yield "status", f"[{i}/{len(queries)}] {query[:65]}..."
        results = search_topic(query)
        all_results.extend(results)

    yield "status", "Sintetizando análise com DeepSeek..."

    async for chunk in stream_equity_report(all_results, ticker, thesis, mandate):
        yield "chunk", chunk

    yield "done", "Análise concluída"


async def run_startup_analysis(
    name: str, url: str = "", thesis: str = ""
) -> AsyncGenerator[Tuple[str, str], None]:
    yield "status", f"Iniciando due diligence: {name}..."

    queries = build_startup_queries(name, url, thesis)
    yield "queries", json.dumps(queries, ensure_ascii=False)

    all_results = []
    for i, query in enumerate(queries, 1):
        yield "status", f"[{i}/{len(queries)}] {query[:65]}..."
        results = search_topic(query)
        all_results.extend(results)

    yield "status", "Gerando VC memo com DeepSeek..."

    async for chunk in stream_startup_report(all_results, name, url, thesis):
        yield "chunk", chunk

    yield "done", "Due diligence concluída"
