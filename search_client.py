"""Web search with multiple fallback backends for reliability on cloud servers."""

import asyncio
import html as html_mod
import json
import logging
import urllib.parse
import urllib.request
from typing import List, Optional

logger = logging.getLogger(__name__)

MAX_RESULTS = 5


class SearchResult:
    def __init__(self, title: str, url: str, snippet: str) -> None:
        self.title = title
        self.url = url
        self.snippet = snippet

    def __repr__(self) -> str:
        return f"SearchResult(title={self.title!r})"


async def search_web(query: str, max_results: int = MAX_RESULTS) -> List[SearchResult]:
    """
    Search the web using multiple backends. Tries each in order until one returns results.
    """
    results = await _try_duckduckgo_api(query, max_results)
    if results:
        return results

    results = await _try_wikipedia(query, max_results)
    if results:
        return results

    results = await _try_wikidata(query, max_results)
    if results:
        return results

    logger.warning("All search backends returned no results for: %s", query)
    return []


# ---------------------------------------------------------------------------
# Backend 1: DuckDuckGo Instant Answer API (no scraping, works on cloud)
# ---------------------------------------------------------------------------
async def _try_duckduckgo_api(query: str, max_results: int) -> List[SearchResult]:
    """DuckDuckGo Instant Answer API — free, no API key, returns structured data."""

    def _fetch() -> Optional[List[SearchResult]]:
        url = f"https://api.duckduckgo.com/?q={urllib.parse.quote(query)}&format=json&no_html=1&skip_disambig=1"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; TelegramBot/1.0)",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            logger.debug("DuckDuckGo API failed: %s", e)
            return None

        results: List[SearchResult] = []

        # Abstract (featured snippet / infobox)
        abstract = data.get("AbstractText", "")
        if abstract and data.get("AbstractURL"):
            results.append(SearchResult(
                title=data.get("Heading", "Summary"),
                url=data["AbstractURL"],
                snippet=abstract[:300],
            ))

        # Related topics
        for topic in data.get("RelatedTopics", []):
            if len(results) >= max_results:
                break
            if "Text" in topic and "FirstURL" in topic:
                results.append(SearchResult(
                    title=topic.get("Text", "").split(" - ")[0][:150],
                    url=topic["FirstURL"],
                    snippet=topic.get("Text", "")[:300],
                ))
            # Nested topics
            if "Topics" in topic:
                for subtopic in topic["Topics"]:
                    if len(results) >= max_results:
                        break
                    if "Text" in subtopic and "FirstURL" in subtopic:
                        results.append(SearchResult(
                            title=subtopic.get("Text", "").split(" - ")[0][:150],
                            url=subtopic["FirstURL"],
                            snippet=subtopic.get("Text", "")[:300],
                        ))

        # Results from the HTML scrape endpoint (more web results)
        if len(results) < max_results:
            html_results = _scrape_duckduckgo_html(query, max_results - len(results))
            results.extend(html_results)

        return results if results else None

    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(None, _fetch)
        if result:
            logger.info("DuckDuckGo API returned %d results for: %s", len(result), query)
        return result or []
    except Exception as e:
        logger.debug("DuckDuckGo backend error: %s", e)
        return []


def _scrape_duckduckgo_html(query: str, max_results: int) -> List[SearchResult]:
    """Fallback: scrape DuckDuckGo HTML results."""
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
    except Exception:
        return []

    results: List[SearchResult] = []
    for block in html.split('class="result__body"')[1:]:
        if len(results) >= max_results:
            break
        try:
            # Extract URL
            url_match = block.split('href="')
            if len(url_match) < 2:
                continue
            url = url_match[1].split('"')[0]
            url = urllib.parse.unquote(url)

            # Extract title
            title = ""
            if 'result__a' in block:
                t_start = block.find('>', block.find('result__a')) + 1
                t_end = block.find('</a>', t_start)
                if t_end > t_start:
                    title = html_mod.unescape(block[t_start:t_end].strip())

            # Extract snippet
            snippet = ""
            for marker in ('result__snippet', 'snippet'):
                if marker in block:
                    s_start = block.find('>', block.find(marker)) + 1
                    s_end = block.find('</', s_start)
                    if s_end > s_start:
                        snippet = html_mod.unescape(block[s_start:s_end].strip())
                        break

            if title or snippet:
                results.append(SearchResult(
                    title=title[:150] or "(untitled)",
                    url=url[:200],
                    snippet=snippet[:300] or "",
                ))
        except Exception:
            continue

    return results


# ---------------------------------------------------------------------------
# Backend 2: Wikipedia API (always available, no API key needed)
# ---------------------------------------------------------------------------
async def _try_wikipedia(query: str, max_results: int) -> List[SearchResult]:
    """Search Wikipedia via the MediaWiki API."""

    def _fetch() -> Optional[List[SearchResult]]:
        params = urllib.parse.urlencode({
            "action": "query",
            "list": "search",
            "srsearch": query,
            "format": "json",
            "srlimit": max_results,
            "srprop": "snippet|titlesnippet",
            "utf8": 1,
        })
        url = f"https://en.wikipedia.org/w/api.php?{params}"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "TelegramAgent/1.0 (bot)"},
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            logger.debug("Wikipedia search failed: %s", e)
            return None

        results: List[SearchResult] = []
        for item in data.get("query", {}).get("search", []):
            title = item.get("titlesnippet", item.get("title", ""))
            snippet = html_mod.unescape(item.get("snippet", ""))
            page_title = item.get("title", "")
            url = f"https://en.wikipedia.org/wiki/{urllib.parse.quote(page_title.replace(' ', '_'))}"
            results.append(SearchResult(
                title=html_mod.unescape(title)[:150],
                url=url,
                snippet=snippet[:300],
            ))

        return results if results else None

    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(None, _fetch)
        if result:
            logger.info("Wikipedia returned %d results for: %s", len(result), query)
        return result or []
    except Exception as e:
        logger.debug("Wikipedia backend error: %s", e)
        return []


# ---------------------------------------------------------------------------
# Backend 3: Wikidata / DBpedia fallback (very broad coverage)
# ---------------------------------------------------------------------------
async def _try_wikidata(query: str, max_results: int) -> List[SearchResult]:
    """Search Wikidata entities via the MediaWiki API."""

    def _fetch() -> Optional[List[SearchResult]]:
        params = urllib.parse.urlencode({
            "action": "wbsearchentities",
            "search": query,
            "language": "en",
            "format": "json",
            "limit": max_results,
        })
        url = f"https://www.wikidata.org/w/api.php?{params}"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "TelegramAgent/1.0 (bot)"},
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            logger.debug("Wikidata search failed: %s", e)
            return None

        results: List[SearchResult] = []
        for item in data.get("search", []):
            title = item.get("label", item.get("id", ""))
            desc = item.get("description", "")
            entity_id = item.get("id", "")
            url = f"https://www.wikidata.org/wiki/{entity_id}"
            results.append(SearchResult(
                title=title[:150],
                url=url,
                snippet=desc[:300] if desc else f"Wikidata entity: {entity_id}",
            ))

        return results if results else None

    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(None, _fetch)
        if result:
            logger.info("Wikidata returned %d results for: %s", len(result), query)
        return result or []
    except Exception as e:
        logger.debug("Wikidata backend error: %s", e)
        return []


# ---------------------------------------------------------------------------
# Formatting for AI context
# ---------------------------------------------------------------------------
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
