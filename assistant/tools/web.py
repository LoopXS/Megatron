"""Web tools for the assistant: fetch a URL and search the web (risk auto).

Both side-effecting primitives are injected: ``fetch`` performs the HTTP GET
and ``search`` performs the web search, so the module itself never opens a
socket and stays unit-testable.  The Telethon glue supplies real ones (an
aiohttp fetch and the repository's existing search plumbing); only the
standard library and the assistant core types are imported here, so the
module loads standalone in tests.  See spec section 8.
"""

import html
import re

from .._agent_core import Tool, ToolContext, ToolResult

#: Longest readable body ``web.fetch_url`` returns before truncating.
MAX_FETCH_CHARS = 8000

#: Element content (script/style) must be dropped before tags are stripped,
#: otherwise the code inside would leak into the readable text.
_ELEMENT_RE = re.compile(
    r"<(script|style)\b[^>]*>.*?</\1\s*>", re.IGNORECASE | re.DOTALL
)
_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


def strip_html(text: str) -> str:
    """Turn an HTML document into collapsed, readable plain text.

    ``<script>``/``<style>`` elements are removed whole, every remaining tag
    is dropped, basic entities (``&amp;``, ``&nbsp;`` and friends) are
    unescaped, and runs of whitespace collapse to single spaces.
    """

    text = _ELEMENT_RE.sub(" ", text)
    text = _TAG_RE.sub(" ", text)
    text = html.unescape(text)
    return _WHITESPACE_RE.sub(" ", text).strip()


async def _fetch_url(fetch, arguments) -> ToolResult:
    """Validate a URL, fetch it, and return its capped readable text."""

    url = arguments.get("url", "")
    if not isinstance(url, str) or not url.startswith(
        ("http://", "https://")
    ):
        return ToolResult(
            f"error: refusing non-http(s) url: {url!r}", error=True
        )

    body = strip_html(await fetch(url))
    if len(body) > MAX_FETCH_CHARS:
        total = len(body)
        body = (
            body[:MAX_FETCH_CHARS]
            + f"\n\n[truncated: showing first {MAX_FETCH_CHARS} "
            f"of {total} characters]"
        )
    return ToolResult(body)


async def _web_search(search, arguments) -> ToolResult:
    """Run a search and render the results as a numbered list."""

    query = arguments.get("query", "")
    n = arguments.get("n", 5)
    results = await search(query, n)
    if not results:
        return ToolResult(f"No results for: {query}")

    lines = []
    for index, item in enumerate(results, 1):
        title = item.get("title", "")
        url = item.get("url", "")
        snippet = item.get("snippet", "")
        lines.append(f"{index}. {title}\n   {url}\n   {snippet}")
    return ToolResult("\n".join(lines))


def build_web_tools(fetch, search) -> list[Tool]:
    """Build ``web.fetch_url`` and ``web.web_search`` from injected callables.

    ``fetch`` is ``async (url) -> str`` returning the raw response body;
    ``search`` is ``async (query, n) -> list[dict]`` where each dict carries
    ``title``, ``url`` and ``snippet``.  Both tools are risk ``auto``.
    """

    async def fetch_url(arguments, context: ToolContext) -> ToolResult:
        return await _fetch_url(fetch, arguments)

    async def web_search(arguments, context: ToolContext) -> ToolResult:
        return await _web_search(search, arguments)

    return [
        Tool(
            name="web.fetch_url",
            description=(
                "Fetch a URL over http(s) and return its readable text with "
                "HTML removed. Only http:// and https:// are allowed."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The http(s) URL to fetch.",
                    }
                },
                "required": ["url"],
            },
            risk="auto",
            handler=fetch_url,
            summarize=lambda arguments: arguments.get("url", ""),
        ),
        Tool(
            name="web.web_search",
            description=(
                "Search the web and return the top results as a numbered "
                "list of titles, URLs and snippets."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query.",
                    },
                    "n": {
                        "type": "integer",
                        "description": "How many results to return.",
                    },
                },
                "required": ["query"],
            },
            risk="auto",
            handler=web_search,
            summarize=lambda arguments: arguments.get("query", ""),
        ),
    ]
