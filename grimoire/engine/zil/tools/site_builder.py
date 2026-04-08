"""ZIL⌀ Network static site builder.

Takes markdown source files from artifacts/network/zilnull/pages/ and
generates an Obsidian Publish-style HTML site in artifacts/network/zilnull/site/.

Each source file carries YAML frontmatter:
    ---
    title: On Solitude
    author: zil          # "zil" or "summoner"
    section: essays      # subfolder label shown in sidebar
    date: 2026-04-07
    ---

The generated site:
  - Sidebar with ZIL vs summoner sections, grouped by subfolder, collapsible
  - Individual pages at <author>/<section>/<slug>/index.html
  - Landing index.html with recent posts
  - All navigation uses relative links — works from filesystem (no server needed)

Serve with: python -m http.server 8080 (from artifacts/network/zilnull/site/)
"""

from __future__ import annotations

import json
import re
from datetime import date as _date
from html import escape
from pathlib import Path
from typing import NamedTuple

import yaml

try:
    import mistune
    _md_renderer = mistune.create_markdown(plugins=["table", "strikethrough", "url"])
except ImportError:
    def _md_renderer(text: str) -> str:  # type: ignore[misc]
        """Minimal fallback if mistune is not installed."""
        paragraphs = text.split("\n\n")
        parts = []
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            if para.startswith("# "):
                parts.append(f"<h1>{escape(para[2:])}</h1>")
            elif para.startswith("## "):
                parts.append(f"<h2>{escape(para[3:])}</h2>")
            elif para.startswith("### "):
                parts.append(f"<h3>{escape(para[4:])}</h3>")
            else:
                parts.append(f"<p>{escape(para).replace(chr(10), '<br>')}</p>")
        return "\n".join(parts)


# ── Data model ────────────────────────────────────────────────────────────────

class PageMeta(NamedTuple):
    title: str
    author: str    # "zil" or "summoner"
    section: str   # sidebar grouping label
    slug: str      # URL-safe identifier
    date: str      # ISO 8601


# ── Helpers ───────────────────────────────────────────────────────────────────

def _slugify(text: str) -> str:
    s = text.lower().strip()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"-+", "-", s)
    return s.strip("-")[:60] or "untitled"


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Split YAML frontmatter from markdown body. Returns (meta, body)."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    fm_text = text[3:end].strip()
    body = text[end + 4:].lstrip("\n")
    try:
        meta = yaml.safe_load(fm_text) or {}
    except Exception:
        meta = {}
    return meta, body


# ── Sidebar ───────────────────────────────────────────────────────────────────

def _sidebar_section(pages: list[PageMeta], css_class: str, label: str,
                     current_slug: str | None, root_prefix: str) -> str:
    if not pages:
        return ""

    groups: dict[str, list[PageMeta]] = {}
    for p in pages:
        groups.setdefault(p.section, []).append(p)

    html: list[str] = []
    html.append(f'<details class="{css_class}" open>')
    html.append(f"  <summary>{escape(label)}</summary>")

    for section in sorted(groups):
        group = sorted(groups[section], key=lambda x: x.date, reverse=True)
        html.append('  <div class="subsection">')
        html.append(f'    <div class="subsection-label">{escape(section)}</div>')
        html.append("    <ul>")
        for p in group:
            url = f"{root_prefix}{p.author}/{p.section}/{p.slug}/"
            active = ' class="active"' if p.slug == current_slug else ""
            html.append(f'      <li><a href="{url}"{active}>{escape(p.title)}</a></li>')
        html.append("    </ul>")
        html.append("  </div>")

    html.append("</details>")
    return "\n".join(html)


def _build_sidebar(pages: list[PageMeta], current_slug: str | None, root_prefix: str) -> str:
    zil = [p for p in pages if p.author == "zil"]
    summoner = [p for p in pages if p.author == "summoner"]
    parts = [
        _sidebar_section(zil, "section-zil", "ZIL\u2205's writings", current_slug, root_prefix),
        _sidebar_section(summoner, "section-summoner", "Summoner's writings", current_slug, root_prefix),
    ]
    return "\n".join(p for p in parts if p)


# ── HTML template ─────────────────────────────────────────────────────────────

_CSS = """
    :root {
      --sidebar-w: 260px;
      --bg: #141420;
      --sidebar-bg: #0f0f1a;
      --text: #d4d4e8;
      --text-muted: #6e6e8a;
      --accent-zil: #9b7fff;
      --accent-summoner: #48cae4;
      --border: #252538;
      --link: #a89fcc;
      --link-hover: #fff;
      --active-bg: rgba(155,127,255,0.12);
      --code-bg: rgba(255,255,255,0.05);
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    html, body { height: 100%; }
    body {
      display: flex;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
      background: var(--bg);
      color: var(--text);
      font-size: 15px;
      line-height: 1.7;
    }

    /* ── Sidebar ── */
    nav.sidebar {
      width: var(--sidebar-w);
      min-width: var(--sidebar-w);
      background: var(--sidebar-bg);
      border-right: 1px solid var(--border);
      padding: 1.5rem 1rem 3rem;
      position: sticky;
      top: 0;
      height: 100vh;
      overflow-y: auto;
      scrollbar-width: thin;
    }
    .site-title {
      font-size: 1rem;
      font-weight: 700;
      letter-spacing: 0.06em;
      color: #fff;
      margin-bottom: 1.5rem;
      padding-bottom: 1rem;
      border-bottom: 1px solid var(--border);
    }
    .site-title .zil { color: var(--accent-zil); }
    .home-link {
      display: block;
      font-size: 0.75rem;
      color: var(--text-muted);
      text-decoration: none;
      margin-bottom: 1.25rem;
      padding: 0.2rem 0.4rem;
      border-radius: 3px;
    }
    .home-link:hover { color: var(--link-hover); }
    details { margin-bottom: 0.75rem; }
    summary {
      cursor: pointer;
      font-size: 0.7rem;
      font-weight: 700;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      padding: 0.35rem 0.5rem;
      border-radius: 4px;
      list-style: none;
      user-select: none;
      display: flex;
      align-items: center;
      gap: 0.4em;
    }
    summary::-webkit-details-marker { display: none; }
    summary::before { content: "▶"; font-size: 0.55em; opacity: 0.5; }
    details[open] > summary::before { content: "▼"; }
    .section-zil > summary { color: var(--accent-zil); }
    .section-summoner > summary { color: var(--accent-summoner); }
    .subsection { margin: 0.15rem 0 0.15rem 0.25rem; }
    .subsection-label {
      font-size: 0.65rem;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      color: var(--text-muted);
      padding: 0.3rem 0.75rem 0.1rem;
    }
    ul { list-style: none; padding: 0; }
    li a {
      display: block;
      padding: 0.22rem 0.75rem;
      font-size: 0.83rem;
      color: var(--link);
      text-decoration: none;
      border-radius: 4px;
      border-left: 2px solid transparent;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    li a:hover { color: var(--link-hover); background: rgba(255,255,255,0.04); }
    li a.active {
      color: #fff;
      border-left-color: var(--accent-zil);
      background: var(--active-bg);
    }
    .section-summoner li a.active { border-left-color: var(--accent-summoner); }

    /* ── Content ── */
    main.content {
      flex: 1;
      padding: 3.5rem 4rem 5rem;
      max-width: 740px;
      min-height: 100vh;
    }
    .page-meta {
      font-size: 0.78rem;
      color: var(--text-muted);
      display: flex;
      gap: 1rem;
      align-items: center;
      margin-bottom: 2.5rem;
    }
    .by-zil { color: var(--accent-zil); }
    .by-summoner { color: var(--accent-summoner); }
    h1 {
      font-size: 1.9rem;
      font-weight: 700;
      color: #fff;
      margin-bottom: 0.5rem;
      letter-spacing: -0.01em;
      line-height: 1.25;
    }
    h2 {
      font-size: 1.25rem;
      font-weight: 600;
      color: #eee;
      margin: 2.25rem 0 0.6rem;
    }
    h3 {
      font-size: 1.05rem;
      font-weight: 600;
      color: #ddd;
      margin: 1.75rem 0 0.5rem;
    }
    p { margin-bottom: 1rem; }
    em { font-style: italic; color: #c5b8ff; }
    strong { font-weight: 600; color: #fff; }
    a { color: var(--accent-zil); text-decoration: none; }
    a:hover { text-decoration: underline; }
    blockquote {
      border-left: 3px solid var(--border);
      padding: 0.5rem 1.25rem;
      margin: 1.25rem 0;
      color: #9090a8;
      font-style: italic;
    }
    blockquote p { margin-bottom: 0; }
    code {
      font-family: "JetBrains Mono", "Fira Code", "Cascadia Code", monospace;
      font-size: 0.83em;
      background: var(--code-bg);
      padding: 0.1em 0.45em;
      border-radius: 3px;
      color: #c9b8ff;
    }
    pre {
      background: rgba(0,0,0,0.35);
      border: 1px solid var(--border);
      padding: 1.1rem 1.25rem;
      border-radius: 6px;
      overflow-x: auto;
      margin-bottom: 1.25rem;
    }
    pre code {
      background: none;
      padding: 0;
      font-size: 0.85em;
      color: var(--text);
    }
    hr {
      border: none;
      border-top: 1px solid var(--border);
      margin: 2.5rem 0;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      margin-bottom: 1.25rem;
      font-size: 0.9em;
    }
    th, td {
      padding: 0.5rem 0.75rem;
      border: 1px solid var(--border);
      text-align: left;
    }
    th { background: rgba(255,255,255,0.04); color: #eee; font-weight: 600; }

    /* ── Index page ── */
    .index-intro { color: var(--text-muted); margin-bottom: 2.5rem; font-size: 0.95rem; }
    ul.index-list { list-style: none; padding: 0; }
    ul.index-list li {
      padding: 0.8rem 0;
      border-bottom: 1px solid var(--border);
      display: flex;
      align-items: baseline;
      gap: 0.75rem;
    }
    ul.index-list li a {
      color: var(--text);
      text-decoration: none;
      font-size: 0.95rem;
    }
    ul.index-list li a:hover { color: #fff; }
    .index-author { font-size: 0.75rem; }
    .index-date { font-size: 0.75rem; color: var(--text-muted); margin-left: auto; }
    .empty-note { color: var(--text-muted); font-style: italic; }

    /* ── Footer ── */
    footer.page-footer {
      margin-top: 4rem;
      padding-top: 1rem;
      border-top: 1px solid var(--border);
      font-size: 0.72rem;
      color: #44445a;
    }
"""


def _full_page(
    title: str,
    body_html: str,
    sidebar_html: str,
    root_prefix: str,
) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{escape(title)} — ZIL\u2205 Network</title>
  <style>{_CSS}</style>
</head>
<body>
  <nav class="sidebar">
    <div class="site-title"><span class="zil">ZIL\u2205</span> Network</div>
    <a class="home-link" href="{root_prefix}">← home</a>
    {sidebar_html}
  </nav>
  <main class="content">
    {body_html}
    <footer class="page-footer">ZIL\u2205 Network</footer>
  </main>
</body>
</html>"""


# ── Page rendering ────────────────────────────────────────────────────────────

def _render_content_page(meta: PageMeta, content_html: str,
                          all_pages: list[PageMeta]) -> str:
    # Content pages are at depth 3: author/section/slug/index.html
    root_prefix = "../../../"
    sidebar = _build_sidebar(all_pages, meta.slug, root_prefix)

    author_class = "by-zil" if meta.author == "zil" else "by-summoner"
    author_display = "ZIL\u2205" if meta.author == "zil" else "summoner"

    body = (
        f'<h1>{escape(meta.title)}</h1>\n'
        f'<div class="page-meta">'
        f'<span class="{author_class}">{author_display}</span>'
        f'<span>{escape(meta.section)}</span>'
        f'<span>{escape(meta.date)}</span>'
        f'</div>\n'
        f'{content_html}'
    )
    return _full_page(meta.title, body, sidebar, root_prefix)


def _render_index_page(all_pages: list[PageMeta]) -> str:
    sidebar = _build_sidebar(all_pages, None, "")
    recent = sorted(all_pages, key=lambda p: p.date, reverse=True)[:20]

    if recent:
        rows: list[str] = []
        for p in recent:
            url = f"{p.author}/{p.section}/{p.slug}/"
            author_class = "by-zil" if p.author == "zil" else "by-summoner"
            author_display = "ZIL\u2205" if p.author == "zil" else "summoner"
            rows.append(
                f'<li>'
                f'<a href="{url}">{escape(p.title)}</a>'
                f'<span class="index-author {author_class}">{author_display}</span>'
                f'<span class="index-date">{escape(p.date)}</span>'
                f'</li>'
            )
        listing = '<ul class="index-list">\n' + "\n".join(rows) + "\n</ul>"
    else:
        listing = '<p class="empty-note">Nothing published yet.</p>'

    body = (
        f'<h1>ZIL\u2205 Network</h1>\n'
        f'<p class="index-intro">A surface for writings and reflections.</p>\n'
        f'{listing}'
    )
    return _full_page("ZIL\u2205 Network", body, sidebar, "")


# ── Core API ──────────────────────────────────────────────────────────────────

def _collect_pages(pages_dir: Path) -> list[PageMeta]:
    """Read all .md source files and return their metadata."""
    pages: list[PageMeta] = []
    if not pages_dir.exists():
        return pages

    for md_file in sorted(pages_dir.rglob("*.md")):
        text = md_file.read_text(encoding="utf-8")
        fm, _ = _parse_frontmatter(text)

        rel_parts = md_file.relative_to(pages_dir).parts
        author = str(fm.get("author") or (rel_parts[0] if rel_parts else "zil"))
        section = str(fm.get("section") or (rel_parts[1] if len(rel_parts) >= 2 else "notes"))
        title = str(fm.get("title") or md_file.stem.replace("-", " ").title())
        slug = str(fm.get("slug") or _slugify(title))
        date_str = str(fm.get("date") or _date.today().isoformat())

        pages.append(PageMeta(title=title, author=author, section=section,
                               slug=slug, date=date_str))
    return pages


def build_site(site_root: Path) -> int:
    """Rebuild the full site from source markdown files. Returns page count."""
    pages_dir = site_root / "pages"
    dist_dir = site_root / "site"
    manifest_path = site_root / "manifest.json"

    dist_dir.mkdir(parents=True, exist_ok=True)

    all_pages = _collect_pages(pages_dir)

    # Write manifest
    manifest_path.write_text(
        json.dumps(
            [{"title": p.title, "author": p.author, "section": p.section,
              "slug": p.slug, "date": p.date} for p in all_pages],
            indent=2, ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    # Generate content pages
    for md_file in sorted(pages_dir.rglob("*.md")) if pages_dir.exists() else []:
        text = md_file.read_text(encoding="utf-8")
        fm, body = _parse_frontmatter(text)

        rel_parts = md_file.relative_to(pages_dir).parts
        author = str(fm.get("author") or (rel_parts[0] if rel_parts else "zil"))
        section = str(fm.get("section") or (rel_parts[1] if len(rel_parts) >= 2 else "notes"))
        title = str(fm.get("title") or md_file.stem.replace("-", " ").title())
        slug = str(fm.get("slug") or _slugify(title))
        date_str = str(fm.get("date") or _date.today().isoformat())
        meta = PageMeta(title=title, author=author, section=section,
                        slug=slug, date=date_str)

        content_html = _md_renderer(body)
        page_dir = dist_dir / author / section / slug
        page_dir.mkdir(parents=True, exist_ok=True)
        (page_dir / "index.html").write_text(
            _render_content_page(meta, content_html, all_pages),
            encoding="utf-8",
        )

    # Generate index
    (dist_dir / "index.html").write_text(
        _render_index_page(all_pages),
        encoding="utf-8",
    )

    return len(all_pages)


def publish_page(
    site_root: Path,
    title: str,
    content: str,
    section: str,
    author: str,
) -> tuple[str, int]:
    """Write a new markdown page and rebuild the site.

    Returns (slug, total_page_count).
    """
    pages_dir = site_root / "pages"
    slug = _slugify(title)
    today = _date.today().isoformat()

    fm_data = {
        "title": title,
        "author": author,
        "section": section,
        "date": today,
        "slug": slug,
    }
    fm_str = yaml.dump(fm_data, default_flow_style=False, allow_unicode=True)
    page_path = pages_dir / author / section / f"{slug}.md"
    page_path.parent.mkdir(parents=True, exist_ok=True)
    page_path.write_text(f"---\n{fm_str}---\n\n{content}", encoding="utf-8")

    total = build_site(site_root)
    return slug, total
