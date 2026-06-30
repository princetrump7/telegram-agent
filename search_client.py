"""Web search using Wikipedia & DuckDuckGo — no API keys needed."""

import json
import logging
import re
import urllib.parse
from typing import List

logger = logging.getLogger(__name__)

MAX_RESULTS = 5

# HTML tag stripping
_RE_TAG = re.compile(r"<[^>]+>|&nbsp;")


def _clean(text: str) -> str:
    """Strip HTML tags and unescape entities."""
    text = _RE_TAG.sub(" ", text)
    text = html_unescape(text)
    return " ".join(text.split())


def html_unescape(s: str) -> str:
    """Unescape HTML entities."""
    import html as _html
    return _html.unescape(s)


class SearchResult:
    def __init__(self, title: str, url: str, snippet: str) -> None:
        self.title = title
        self.url = url
        self.snippet = snippet

    def __repr__(self) -> str:
        return f"SearchResult(title={self.title!r})"


async def search_web(query: str, max_results: int = MAX_RESULTS) -> List[SearchResult]:
    """
    Search the web. Tries DuckDuckGo first, then Wikipedia as fallback.
    """
    # Try DuckDuckGo HTML scrape first
    results = await _search_duckduckgo(query, max_results)
    if results:
        return results

    # Fallback to Wikipedia
    results = await _search_wikipedia(query, max_results)
    if results:
        return results

    logger.warning("All search backends returned no results for: %s", query)
    return []


# ---------------------------------------------------------------------------
# DuckDuckGo search — uses the /html/ endpoint
# ---------------------------------------------------------------------------
async def _search_duckduckgo(query: str, max_results: int) -> List[SearchResult]:
    """Search DuckDuckGo HTML endpoint."""

    def _do_search() -> List[SearchResult]:
        import urllib.request
        import urllib.error

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
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                html = resp.read().decode("utf-8", errors="replace")
        except Exception as e:
            logger.debug("DuckDuckGo HTML request failed: %s", e)
            return []

        return _parse_ddg_html(html, max_results)

    import asyncio
    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(None, _do_search)
    except Exception as e:
        logger.debug("DuckDuckGo error: %s", e)
        return []


def _parse_ddg_html(html: str, max_results: int) -> List[SearchResult]:
    """Parse DuckDuckGo HTML search results."""
    results: List[SearchResult] = []

    # Try parsing result blocks
    for block in html.split('class="result__body"')[1:]:
        if len(results) >= max_results:
            break
        try:
            title, url, snippet = _parse_ddg_block(block)
            if title:
                results.append(SearchResult(title=title[:150], url=url[:200], snippet=snippet[:300]))
        except Exception:
            continue

    # Fallback: try parsing older format with result__a directly
    if not results:
        for block in html.split('class="result__a"')[1:]:
            if len(results) >= max_results:
                break
            try:
                # Extract everything after <a ...> up to </a>
                tag_end = block.find(">")
                if tag_end < 0:
                    continue
                link_end = block.find("</a>", tag_end)
                title = _clean(block[tag_end + 1 : link_end]) if link_end > tag_end else ""
                if title:
                    results.append(SearchResult(
                        title=title[:150],
                        url="",
                        snippet="",
                    ))
            except Exception:
                continue

    return results


def _parse_ddg_block(block: str) -> tuple:
    """Parse a single DDG result block."""
    # URL
    url = ""
    for href_marker in ('href="', 'href=\''):
        if href_marker in block:
            after_href = block.split(href_marker, 1)[1]
            quote = href_marker[-1]
            url_end = after_href.find(quote)
            if url_end > 0:
                url = urllib.parse.unquote(after_href[:url_end])
                break

    # Title from result__a
    title = ""
    if 'class="result__a"' in block or 'class="result__a ' in block:
        a_start = block.find('class="result__a"')
        if a_start < 0:
            a_start = block.find('class="result__a ')
        tag_end = block.find(">", a_start)
        link_end = block.find("</a>", tag_end)
        if link_end > tag_end > 0:
            title = _clean(block[tag_end + 1 : link_end])

    # Snippet
    snippet = ""
    for cls in ('class="result__snippet"', 'class="snippet"'):
        if cls in block:
            tag_end = block.find(">", block.find(cls))
            if tag_end < 0:
                continue
            close_tag = block.find("</a>", tag_end)
            if close_tag < 0:
                close_tag = block.find("</div>", tag_end)
            if close_tag < 0:
                close_tag = block.find("</span>", tag_end)
            if close_tag > tag_end:
                snippet = _clean(block[tag_end + 1 : close_tag])
                break

    return title, url, snippet


# ---------------------------------------------------------------------------
# Wikipedia search — reliable, always available API
# ---------------------------------------------------------------------------
async def _search_wikipedia(query: str, max_results: int) -> List[SearchResult]:
    """Search Wikipedia via the MediaWiki API."""

    def _do_search() -> List[SearchResult]:
        import urllib.request
        import urllib.error

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
            headers={"User-Agent": "TelegramAgent/1.0 (github.com/princetrump7/telegram-agent)"},
        )

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            logger.debug("Wikipedia API failed: %s", e)
            return []

        results: List[SearchResult] = []
        for item in data.get("query", {}).get("search", []):
            page_title = item.get("title", "")
            title = _clean(item.get("titlesnippet", page_title))
            snippet = _clean(item.get("snippet", ""))
            wurl = f"https://en.wikipedia.org/wiki/{urllib.parse.quote(page_title.replace(' ', '_'))}"
            results.append(SearchResult(title=title[:150], url=wurl, snippet=snippet[:300]))

        return results

    import asyncio
    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(None, _do_search)
    except Exception as e:
        logger.debug("Wikipedia error: %s", e)
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
