"""Web access tool implementations for ZIL⌀.

All functions here are pure HTTP/parsing logic with no Warden, charge, or ledger
concerns. The ToolExecutor handles permission checks and logging before calling
these functions.

Requires: httpx, beautifulsoup4 (fetch/parse), pypdf (PDF extraction).
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urljoin, urlparse


# ── HTML → Markdown ───────────────────────────────────────────────────────────

def html_to_markdown(html: str, base_url: str = "") -> str:
    """Convert raw HTML to clean markdown suitable for LLM consumption.

    Removes navigation, scripts, ads. Preserves headings, paragraphs, links,
    lists, and inline formatting. Falls back to plain text extraction on error.
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        raise ImportError(
            "beautifulsoup4 is required for web tools. "
            "Run: pip install beautifulsoup4"
        )

    soup = BeautifulSoup(html, "html.parser")

    # Strip noise
    for tag in soup(["script", "style", "nav", "footer", "aside",
                     "noscript", "iframe", "header"]):
        tag.decompose()

    title = ""
    if soup.title:
        title = soup.title.get_text(strip=True)
        soup.title.decompose()

    # Prefer semantic content containers
    body = (
        soup.find("main")
        or soup.find("article")
        or soup.find(id=re.compile(r"^(content|main|article|body)$", re.I))
        or soup.find("body")
        or soup
    )

    lines = []
    if title:
        lines.append(f"# {title}\n")
    lines.append(_render_node(body, base_url))

    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _render_node(node, base_url: str) -> str:
    from bs4 import Tag, NavigableString

    if isinstance(node, NavigableString):
        s = str(node)
        return s if s.strip() else (" " if s else "")

    if not isinstance(node, Tag) or not node.name:
        return ""

    tag = node.name.lower()

    # Block: headings
    if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
        level = int(tag[1])
        inner = _render_children(node, base_url).strip()
        return f"\n{'#' * level} {inner}\n" if inner else ""

    # Block: paragraph
    if tag == "p":
        inner = _render_children(node, base_url).strip()
        return f"\n{inner}\n" if inner else ""

    # Block: lists
    if tag in ("ul", "ol"):
        items = [
            f"- {_render_children(li, base_url).strip()}"
            for li in node.find_all("li", recursive=False)
        ]
        return "\n" + "\n".join(items) + "\n" if items else ""

    if tag == "li":
        return f"- {_render_children(node, base_url).strip()}\n"

    # Block: code
    if tag == "pre":
        return f"\n```\n{node.get_text().strip()}\n```\n"

    # Block: dividers
    if tag == "br":
        return "\n"
    if tag == "hr":
        return "\n---\n"

    # Inline: links
    if tag == "a":
        href = node.get("href", "").strip()
        inner = _render_children(node, base_url).strip()
        if href and not href.startswith(("#", "javascript:", "mailto:")):
            if base_url and not href.startswith(("http://", "https://", "//")):
                href = urljoin(base_url, href)
            return f"[{inner or href}]({href})"
        return inner

    # Inline: emphasis
    if tag in ("strong", "b"):
        inner = _render_children(node, base_url).strip()
        return f"**{inner}**" if inner else ""
    if tag in ("em", "i"):
        inner = _render_children(node, base_url).strip()
        return f"*{inner}*" if inner else ""
    if tag == "code":
        inner = node.get_text()
        return f"`{inner}`" if inner.strip() else ""

    # Block: table (simplified — just extract text rows)
    if tag == "table":
        rows = []
        for tr in node.find_all("tr"):
            cells = [td.get_text(strip=True) for td in tr.find_all(["th", "td"])]
            if cells:
                rows.append(" | ".join(cells))
        return "\n" + "\n".join(rows) + "\n" if rows else ""

    # Block: blockquote
    if tag == "blockquote":
        inner = _render_children(node, base_url).strip()
        quoted = "\n".join(f"> {line}" for line in inner.splitlines())
        return f"\n{quoted}\n"

    # Generic containers — pass through
    return _render_children(node, base_url)


def _render_children(node, base_url: str) -> str:
    return "".join(_render_node(child, base_url) for child in node.children)


# ── Web search ────────────────────────────────────────────────────────────────

def web_search(query: str, num_results: int = 5) -> tuple[str, str]:
    """Search the web using Brave Search API or Tavily.

    Returns (results_text, api_domain_used) so the executor can check
    the API domain against the network allow-list before calling this.

    Checks BRAVE_API_KEY first, then TAVILY_API_KEY.
    Raises ImportError if httpx is missing.
    Raises RuntimeError if no API key is configured.
    """
    try:
        import httpx
    except ImportError:
        raise ImportError("httpx is required for web tools. Run: pip install httpx")

    from zil.config import get_config
    cfg = get_config()

    if cfg.brave_api_key:
        return _brave_search(query, num_results, cfg.brave_api_key)
    elif cfg.tavily_api_key:
        return _tavily_search(query, num_results, cfg.tavily_api_key)
    else:
        raise RuntimeError(
            "No web search API key configured. "
            "Set BRAVE_API_KEY or TAVILY_API_KEY in .env to enable web search."
        )


def _brave_search(query: str, num_results: int, api_key: str) -> tuple[str, str]:
    import httpx

    api_domain = "api.search.brave.com"
    resp = httpx.get(
        f"https://{api_domain}/res/v1/web/search",
        params={"q": query, "count": min(num_results, 20)},
        headers={"X-Subscription-Token": api_key, "Accept": "application/json"},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    results = data.get("web", {}).get("results", [])
    if not results:
        return "(no results)", api_domain

    lines = [f"Search: {query}\n"]
    for i, r in enumerate(results[:num_results], 1):
        title = r.get("title", "(no title)")
        url = r.get("url", "")
        desc = r.get("description", "")
        lines.append(f"{i}. **{title}**\n   {url}\n   {desc}\n")

    return "\n".join(lines), api_domain


def _tavily_search(query: str, num_results: int, api_key: str) -> tuple[str, str]:
    import httpx

    api_domain = "api.tavily.com"
    resp = httpx.post(
        f"https://{api_domain}/search",
        json={"api_key": api_key, "query": query, "max_results": min(num_results, 20)},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    results = data.get("results", [])
    if not results:
        return "(no results)", api_domain

    lines = [f"Search: {query}\n"]
    for i, r in enumerate(results[:num_results], 1):
        title = r.get("title", "(no title)")
        url = r.get("url", "")
        content = r.get("content", "")[:200]
        lines.append(f"{i}. **{title}**\n   {url}\n   {content}\n")

    return "\n".join(lines), api_domain


# ── Page fetching ─────────────────────────────────────────────────────────────

def fetch_page(url: str) -> str:
    """Fetch a URL and return clean markdown.

    Raises httpx exceptions on network/status errors.
    """
    try:
        import httpx
    except ImportError:
        raise ImportError("httpx is required for web tools. Run: pip install httpx")

    resp = httpx.get(
        url,
        headers={"User-Agent": "ZIL/1.0 (research reader)"},
        follow_redirects=True,
        timeout=30,
    )
    resp.raise_for_status()

    content_type = resp.headers.get("content-type", "")
    if "html" not in content_type and "text" not in content_type:
        return f"[non-text response: {content_type}]"

    return html_to_markdown(resp.text, base_url=url)


def download_pdf(url: str, dest_path: Path) -> tuple[int, str]:
    """Download a PDF to dest_path.

    Returns (bytes_written, provenance_markdown).
    dest_path must already be resolved and permission-checked by the caller.
    """
    try:
        import httpx
    except ImportError:
        raise ImportError("httpx is required for web tools. Run: pip install httpx")

    dest_path.parent.mkdir(parents=True, exist_ok=True)

    with httpx.stream(
        "GET",
        url,
        headers={"User-Agent": "ZIL/1.0 (research reader)"},
        follow_redirects=True,
        timeout=60,
    ) as resp:
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "")
        if "pdf" not in content_type and not url.lower().endswith(".pdf"):
            raise ValueError(
                f"URL does not appear to be a PDF (content-type: {content_type}). "
                "Use fetch_page for HTML content."
            )
        data = b"".join(resp.iter_bytes())

    dest_path.write_bytes(data)
    bytes_written = len(data)

    from datetime import datetime, timezone
    provenance = (
        f"# Provenance: {dest_path.name}\n\n"
        f"- **Source:** {url}\n"
        f"- **Downloaded:** {datetime.now(timezone.utc).isoformat()}\n"
        f"- **Size:** {bytes_written:,} bytes\n"
    )
    return bytes_written, provenance


def trace_links(url: str) -> list[str]:
    """Return all absolute outbound links from a page."""
    try:
        import httpx
    except ImportError:
        raise ImportError("httpx is required for web tools. Run: pip install httpx")
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        raise ImportError("beautifulsoup4 is required for web tools.")

    resp = httpx.get(
        url,
        headers={"User-Agent": "ZIL/1.0 (research reader)"},
        follow_redirects=True,
        timeout=30,
    )
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    links = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("#", "javascript:", "mailto:")):
            continue
        if not href.startswith(("http://", "https://")):
            href = urljoin(url, href)
        if href not in seen:
            seen.add(href)
            links.append(href)
    return links


def enshrine_snapshot(url: str, dest_path: Path) -> str:
    """Fetch a page and save clean markdown to dest_path.

    Returns the saved markdown content.
    dest_path must already be resolved and permission-checked by the caller.
    """
    markdown = fetch_page(url)

    from datetime import datetime, timezone
    header = (
        f"<!-- Snapshot: {url} -->\n"
        f"<!-- Saved: {datetime.now(timezone.utc).isoformat()} -->\n\n"
    )
    full_content = header + markdown

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_text(full_content, encoding="utf-8")
    return full_content
