"""Web search using DuckDuckGo's API directly (no library dependency needed)."""

import asyncio
import json
import logging
import urllib.request
import urllib.error
import urllib.parse
from typing import List

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
    Search the web using DuckDuckGo's HTML API and return structured results.
    Runs in a thread to avoid blocking the event loop.
    """
    loop = asyncio.get_event_loop()

    def _search() -> list[dict]:
        url = "https://html.duckduckgo.com/html/"
        data = urllib.parse.urlencode({"q": query}).encode()
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                html = resp.read().decode("utf-8", errors="replace")
        except Exception as e:
            logger.warning("DuckDuckGo request failed: %s", e)
            return []

        # Parse results from HTML — extract result blocks
        results: list[dict] = []
        try:
            for block in html.split('<div class="result__body">')[1:]:
                if len(results) >= max_results:
                    break

                # Title
                title = ""
                title_match = block.split('<a rel="nofollow" class="result__a" href="')
                if len(title_match) > 1:
                    after_href = title_match[1]
                    url_end = after_href.find('"')
                    url = urllib.parse.unquote(after_href[:url_end]) if url_end > 0 else ""
                    title_start = after_href.find(">", url_end) + 1
                    title_end = after_href.find("</a>", title_start)
                    if title_end > title_start:
                        title = after_href[title_start:title_end].strip()
                        import html as html_mod
                        title = html_mod.unescape(title)
                else:
                    url = ""
                    title = ""

                # Snippet
                snippet = ""
                snippet_marker = '<a class="result__snippet"'
                if snippet_marker in block:
                    # Parse as <a class="result__snippet" ...>...</a>
                    s_start = block.find(snippet_marker)
                    s_tag_end = block.find(">", s_start) + 1
                    s_end = block.find("</a>", s_tag_end)
                    if s_end > s_tag_end:
                        snippet = block[s_tag_end:s_end].strip()
                        import html as html_mod
                        snippet = html_mod.unescape(snippet)

                # Fallback: try result__snippet as a div
                if not snippet:
                    alt_marker = 'class="result__snippet"'
                    if alt_marker in block:
                        a_start = block.find(alt_marker)
                        a_tag_end = block.find(">", a_start) + 1
                        a_close = block.find("</", a_tag_end)
                        if a_close > a_tag_end:
                            snippet = block[a_tag_end:a_close].strip()
                            import html as html_mod
                            snippet = html_mod.unescape(snippet)

                if title or snippet:
                    results.append({
                        "title": title or "(untitled)",
                        "url": url or "",
                        "body": snippet or "",
                    })
        except Exception as e:
            logger.warning("Error parsing DuckDuckGo results: %s", e)

        logger.info("Parsed %d/%d results from DuckDuckGo", len(results), max_results)
        return results

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
                url=r.get("url", ""),
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
