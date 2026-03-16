"""researcher.py — Cortiq Decision Copilot
Web research via Tavily API.
"""
import os
from typing import List, Dict


def search_topic(query: str, max_results: int = 5) -> List[Dict]:
    """Searches using Tavily and returns structured results."""
    try:
        from tavily import TavilyClient

        api_key = os.environ.get("TAVILY_API_KEY", "")
        if not api_key:
            return [{"title": "API key ausente", "content": "Configure TAVILY_API_KEY no .env", "url": ""}]

        client = TavilyClient(api_key=api_key)
        response = client.search(query=query, max_results=max_results, search_depth="advanced")

        return [
            {
                "title": r.get("title", ""),
                "content": r.get("content", "")[:600],
                "url": r.get("url", ""),
            }
            for r in response.get("results", [])
        ]
    except Exception as e:
        return [{"title": "Erro na pesquisa", "content": str(e), "url": ""}]
