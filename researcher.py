"""researcher.py — Cortiq Decision Copilot v2
Web research via Tavily API. Returns enriched, deduplicated results.
"""
import os
import json
import hashlib
import time
from pathlib import Path
from typing import List, Dict

# ── Simple file-based search cache (TTL = 24h) ───────────────
_CACHE_DIR = Path("search_cache")
_CACHE_TTL = 86400  # 24 hours


def _cache_key(query: str) -> str:
    return hashlib.md5(query.encode()).hexdigest()


def _cache_get(query: str):
    try:
        _CACHE_DIR.mkdir(exist_ok=True)
        path = _CACHE_DIR / f"{_cache_key(query)}.json"
        if path.exists() and (time.time() - path.stat().st_mtime) < _CACHE_TTL:
            return json.loads(path.read_text())
    except Exception:
        pass
    return None


def _cache_set(query: str, results: List[Dict]):
    try:
        _CACHE_DIR.mkdir(exist_ok=True)
        path = _CACHE_DIR / f"{_cache_key(query)}.json"
        path.write_text(json.dumps(results, ensure_ascii=False))
    except Exception:
        pass


def _infer_source_type(url: str) -> str:
    u = url.lower()
    if any(x in u for x in ['bloomberg', 'reuters', 'wsj', 'ft.com', 'valor.com.br',
                              'infomoney', 'exame.com', 'b3.com.br', 'cvm.gov.br']):
        return 'financial_news'
    if any(x in u for x in ['techcrunch', 'startups.com.br', 'startupbase',
                              'crunchbase', 'pitchbook', 'finsiders']):
        return 'startup_media'
    if any(x in u for x in ['ri.', 'investor', 'sec.gov', 'cvm.gov']):
        return 'investor_relations'
    if 'linkedin' in u:
        return 'linkedin'
    if any(x in u for x in ['github', 'docs.', 'developer']):
        return 'technical'
    if '.gov.br' in u:
        return 'regulatory'
    return 'web'


def deduplicate_results(results: List[Dict]) -> List[Dict]:
    seen = set()
    out = []
    for r in results:
        key = r.get('url', '') or r.get('title', '')
        if key and key not in seen:
            seen.add(key)
            out.append(r)
    return out


def search_topic(query: str, max_results: int = 5) -> List[Dict]:
    """Search via Tavily with 24h cache. Returns enriched, structured results."""
    cached = _cache_get(query)
    if cached is not None:
        return cached

    try:
        from tavily import TavilyClient

        api_key = os.environ.get("TAVILY_API_KEY", "")
        if not api_key:
            return [{"title": "API key ausente", "content": "Configure TAVILY_API_KEY", "url": "", "query": query, "source_type": "error"}]

        client = TavilyClient(api_key=api_key)
        # Use "basic" by default — 10x cheaper than "advanced"
        # Set TAVILY_DEPTH=advanced in env to enable deep search
        depth = os.environ.get("TAVILY_DEPTH", "basic")
        response = client.search(query=query, max_results=max_results, search_depth=depth)

        results = [
            {
                "title": r.get("title", ""),
                "content": r.get("content", "")[:600],
                "url": r.get("url", ""),
                "query": query,
                "source_type": _infer_source_type(r.get("url", "")),
            }
            for r in response.get("results", [])
        ]
        _cache_set(query, results)
        return results
    except Exception as e:
        return [{"title": "Erro na pesquisa", "content": str(e), "url": "", "query": query, "source_type": "error"}]
