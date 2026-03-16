"""equity_data.py — Cortiq Decision Copilot
Fetches real market data via yfinance for Brazilian equities.
"""
import asyncio
from typing import Optional


def _fetch_equity_data(ticker: str) -> dict:
    """Fetch real market data. Returns empty dict on failure."""
    try:
        import yfinance as yf

        # Brazilian tickers need .SA suffix
        yf_ticker = ticker if "." in ticker else f"{ticker}.SA"
        stock = yf.Ticker(yf_ticker)
        info = stock.info

        def fmt_brl(v):
            if v is None:
                return None
            if v >= 1_000_000_000:
                return f"R$ {v/1_000_000_000:.1f}B"
            if v >= 1_000_000:
                return f"R$ {v/1_000_000:.0f}M"
            return f"R$ {v:,.0f}"

        def fmt_usd(v):
            if v is None:
                return None
            if v >= 1_000_000_000:
                return f"US$ {v/1_000_000_000:.1f}B"
            if v >= 1_000_000:
                return f"US$ {v/1_000_000:.0f}M"
            return f"US$ {v:,.0f}"

        price = info.get("currentPrice") or info.get("regularMarketPrice")
        market_cap = info.get("marketCap")
        currency = info.get("currency", "BRL")
        fmt = fmt_brl if currency == "BRL" else fmt_usd

        return {
            "ticker": ticker,
            "price": f"R$ {price:.2f}" if price else None,
            "change_pct": (
                f"{info.get('regularMarketChangePercent', 0):.2f}%"
                if info.get("regularMarketChangePercent") is not None else None
            ),
            "market_cap": fmt(market_cap),
            "pe_trailing": f"{info.get('trailingPE'):.1f}x" if info.get("trailingPE") else None,
            "pe_forward": f"{info.get('forwardPE'):.1f}x" if info.get("forwardPE") else None,
            "pb": f"{info.get('priceToBook'):.2f}x" if info.get("priceToBook") else None,
            "ev_ebitda": f"{info.get('enterpriseToEbitda'):.1f}x" if info.get("enterpriseToEbitda") else None,
            "div_yield": f"{info.get('dividendYield', 0)*100:.2f}%" if info.get("dividendYield") else None,
            "week_52_high": f"R$ {info.get('fiftyTwoWeekHigh'):.2f}" if info.get("fiftyTwoWeekHigh") else None,
            "week_52_low": f"R$ {info.get('fiftyTwoWeekLow'):.2f}" if info.get("fiftyTwoWeekLow") else None,
            "revenue_ttm": fmt(info.get("totalRevenue")),
            "ebitda": fmt(info.get("ebitda")),
            "net_margin": f"{info.get('profitMargins', 0)*100:.1f}%" if info.get("profitMargins") else None,
            "sector": info.get("sector") or info.get("sectorDisp"),
            "name": info.get("longName") or info.get("shortName"),
        }
    except Exception:
        return {}


async def get_equity_data(ticker: str) -> dict:
    """Async wrapper around yfinance fetch."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _fetch_equity_data, ticker)


def format_market_data(data: dict) -> str:
    """Format market data as a structured string for LLM context."""
    if not data:
        return ""

    lines = [f"DADOS DE MERCADO REAIS — {data.get('ticker')} ({data.get('name', '')})"]
    fields = [
        ("Preço atual", "price"),
        ("Variação hoje", "change_pct"),
        ("Market Cap", "market_cap"),
        ("P/L (trailing)", "pe_trailing"),
        ("P/L (forward)", "pe_forward"),
        ("P/VP", "pb"),
        ("EV/EBITDA", "ev_ebitda"),
        ("Dividend Yield", "div_yield"),
        ("Máx 52 semanas", "week_52_high"),
        ("Mín 52 semanas", "week_52_low"),
        ("Receita (TTM)", "revenue_ttm"),
        ("EBITDA", "ebitda"),
        ("Margem líquida", "net_margin"),
        ("Setor", "sector"),
    ]
    for label, key in fields:
        val = data.get(key)
        if val:
            lines.append(f"  {label}: {val}")

    return "\n".join(lines)
