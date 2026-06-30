"""Web search client using DuckDuckGo (free, no API key needed)."""

import asyncio
import logging
from typing import List

from duckduckgo_search import DDGS

logger = logging.getLogger(__name__)


class SearchResult:
    def __init__(self, title: str, url: str, snippet: str) -> None:
        self.title = title
        self.url = url
        self.snippet = snippet

    def __repr__(self) -> str:
        return f"SearchResult(title={self.title!r})"


async def search_web(query: str, max_results: int = 5) -> List[SearchResult]:
    """
    Search the web using DuckDuckGo and return structured results.
    Runs the synchronous DDGS call in a thread to avoid blocking.
    """
    loop = asyncio.get_event_loop()

    def _search() -> list[dict]:
        with DDGS() as ddgs:
            raw = list(ddgs.text(query, max_results=max_results))
            return raw

    try:
        raw_results = await loop.run_in_executor(None, _search)
    except Exception as e:
        logger.warning("Web search failed: %s", e)
        return []

    results: list[SearchResult] = []
    for r in raw_results:
        results.append(
            SearchResult(
                title=r.get("title", ""),
                url=r.get("href", ""),
                snippet=r.get("body", ""),
            )
        )

    return results


def format_search_results(results: List[SearchResult], query: str) -> str:
    """Format web search results into a block for the AI context."""
    if not results:
        return f"No results found for: {query}"

    lines = [
        f"Web search results for \"{query}\":",
        "---",
    ]
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r.title}")
        lines.append(f"   URL: {r.url}")
        lines.append(f"   {r.snippet}")
        lines.append("")

    return "\n".join(lines)
