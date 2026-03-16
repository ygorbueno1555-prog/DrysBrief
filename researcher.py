"""researcher.py — Cortiq Decision Copilot v2
Web research via Tavily API. Returns enriched, deduplicated results.
"""
import os
from typing import List, Dict


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
    """Search via Tavily. Returns enriched, structured results."""
    try:
        from tavily import TavilyClient

        api_key = os.environ.get("TAVILY_API_KEY", "")
        if not api_key:
            return [{"title": "API key ausente", "content": "Configure TAVILY_API_KEY", "url": "", "query": query, "source_type": "error"}]

        client = TavilyClient(api_key=api_key)
        response = client.search(query=query, max_results=max_results, search_depth="advanced")

        return [
            {
                "title": r.get("title", ""),
                "content": r.get("content", "")[:600],
                "url": r.get("url", ""),
                "query": query,
                "source_type": _infer_source_type(r.get("url", "")),
            }
            for r in response.get("results", [])
        ]
    except Exception as e:
        return [{"title": "Erro na pesquisa", "content": str(e), "url": "", "query": query, "source_type": "error"}]
