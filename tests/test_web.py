"""Tests for web tools (no real network calls — httpx mocked)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from zil.tools.web import html_to_markdown, fetch_page, trace_links, enshrine_snapshot


# ── HTML → Markdown ───────────────────────────────────────────────────────────

class TestHtmlToMarkdown:
    def test_title_becomes_h1(self):
        html = "<html><head><title>My Page</title></head><body><p>Hello</p></body></html>"
        md = html_to_markdown(html)
        assert "# My Page" in md
        assert "Hello" in md

    def test_headings_preserved(self):
        html = "<body><h2>Section</h2><p>Text</p></body>"
        md = html_to_markdown(html)
        assert "## Section" in md
        assert "Text" in md

    def test_links_converted(self):
        html = '<body><a href="https://example.com">Click</a></body>'
        md = html_to_markdown(html)
        assert "[Click](https://example.com)" in md

    def test_relative_links_resolved(self):
        html = '<body><a href="/about">About</a></body>'
        md = html_to_markdown(html, base_url="https://example.com/page")
        assert "https://example.com/about" in md

    def test_script_and_style_removed(self):
        html = "<body><script>alert('xss')</script><style>.x{}</style><p>Clean</p></body>"
        md = html_to_markdown(html)
        assert "alert" not in md
        assert ".x" not in md
        assert "Clean" in md

    def test_bold_italic(self):
        html = "<body><p><strong>Bold</strong> and <em>italic</em></p></body>"
        md = html_to_markdown(html)
        assert "**Bold**" in md
        assert "*italic*" in md

    def test_unordered_list(self):
        html = "<body><ul><li>One</li><li>Two</li></ul></body>"
        md = html_to_markdown(html)
        assert "- One" in md
        assert "- Two" in md

    def test_code_block(self):
        html = "<body><pre>def foo():\n    pass</pre></body>"
        md = html_to_markdown(html)
        assert "```" in md
        assert "def foo" in md

    def test_nav_footer_removed(self):
        html = "<body><nav>Nav</nav><main><p>Content</p></main><footer>Footer</footer></body>"
        md = html_to_markdown(html)
        assert "Nav" not in md
        assert "Footer" not in md
        assert "Content" in md

    def test_excessive_blank_lines_collapsed(self):
        html = "<body><p>A</p><p>B</p><p>C</p></body>"
        md = html_to_markdown(html)
        # Should not have more than 2 consecutive newlines
        assert "\n\n\n" not in md

    def test_empty_body(self):
        html = "<html><body></body></html>"
        md = html_to_markdown(html)
        assert isinstance(md, str)

    def test_table_extracts_text(self):
        html = "<body><table><tr><th>Name</th><th>Age</th></tr><tr><td>Alice</td><td>30</td></tr></table></body>"
        md = html_to_markdown(html)
        assert "Name" in md
        assert "Alice" in md

    def test_blockquote(self):
        html = "<body><blockquote>A wise saying.</blockquote></body>"
        md = html_to_markdown(html)
        assert ">" in md
        assert "wise saying" in md


# ── fetch_page ────────────────────────────────────────────────────────────────

class TestFetchPage:
    def test_returns_markdown_for_html_response(self):
        html = "<html><head><title>Test</title></head><body><p>Hello world</p></body></html>"
        mock_resp = MagicMock()
        mock_resp.headers = {"content-type": "text/html; charset=utf-8"}
        mock_resp.text = html
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.get", return_value=mock_resp):
            result = fetch_page("https://example.com/test")

        assert "Hello world" in result
        assert "# Test" in result

    def test_non_html_response_flagged(self):
        mock_resp = MagicMock()
        mock_resp.headers = {"content-type": "application/octet-stream"}
        mock_resp.text = ""
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.get", return_value=mock_resp):
            result = fetch_page("https://example.com/file.bin")

        assert "non-text response" in result


# ── trace_links ───────────────────────────────────────────────────────────────

class TestTraceLinks:
    def test_returns_absolute_links(self):
        html = '''
        <html><body>
          <a href="https://external.com/page">External</a>
          <a href="/relative">Relative</a>
          <a href="#anchor">Anchor</a>
        </body></html>
        '''
        mock_resp = MagicMock()
        mock_resp.text = html
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.get", return_value=mock_resp):
            links = trace_links("https://example.com")

        assert "https://external.com/page" in links
        assert "https://example.com/relative" in links
        # Anchor links are excluded
        assert all("#" not in l or l.startswith("http") for l in links)
        assert not any(l == "#anchor" for l in links)

    def test_deduplicates_links(self):
        html = '''
        <html><body>
          <a href="https://example.com/page">Link 1</a>
          <a href="https://example.com/page">Link 2</a>
        </body></html>
        '''
        mock_resp = MagicMock()
        mock_resp.text = html
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.get", return_value=mock_resp):
            links = trace_links("https://example.com")

        assert links.count("https://example.com/page") == 1

    def test_javascript_links_excluded(self):
        html = '<html><body><a href="javascript:void(0)">JS</a></body></html>'
        mock_resp = MagicMock()
        mock_resp.text = html
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.get", return_value=mock_resp):
            links = trace_links("https://example.com")

        assert not any("javascript" in l for l in links)


# ── enshrine_snapshot ─────────────────────────────────────────────────────────

class TestEnshrine:
    def test_saves_markdown_to_path(self, tmp_path):
        html = "<html><head><title>Saved</title></head><body><p>Content</p></body></html>"
        mock_resp = MagicMock()
        mock_resp.headers = {"content-type": "text/html"}
        mock_resp.text = html
        mock_resp.raise_for_status = MagicMock()

        dest = tmp_path / "snapshot.md"
        with patch("httpx.get", return_value=mock_resp):
            content = enshrine_snapshot("https://example.com", dest)

        assert dest.exists()
        assert "Content" in dest.read_text()
        assert "Snapshot" in dest.read_text()  # provenance comment
        assert content == dest.read_text()

    def test_snapshot_includes_source_url(self, tmp_path):
        html = "<html><body><p>Text</p></body></html>"
        mock_resp = MagicMock()
        mock_resp.headers = {"content-type": "text/html"}
        mock_resp.text = html
        mock_resp.raise_for_status = MagicMock()

        dest = tmp_path / "out.md"
        with patch("httpx.get", return_value=mock_resp):
            enshrine_snapshot("https://example.com/article", dest)

        saved = dest.read_text()
        assert "https://example.com/article" in saved


# ── Network domain enforcement (executor-level) ───────────────────────────────

class TestNetworkDomainEnforcement:
    """Verify that ToolExecutor._check_network blocks unlisted domains."""

    def _make_executor(self, tmp_path, allowed_domains):
        import json, os
        from unittest.mock import patch as _patch
        from zil import config as cfg_mod
        cfg_mod._config = None
        allow_file = tmp_path / "network_allow.json"
        allow_file.write_text(json.dumps({"allowed_domains": allowed_domains}))

        with _patch.dict(os.environ, {"ZIL_STATE_DIR": str(tmp_path)}):
            cfg_mod._config = None
            from zil.tools.executor import ToolExecutor
            from zil.memory.store import MemoryStore
            from zil.runtime.charge import ChargeTracker
            # We can't fully init MemoryStore without all dirs, so we mock it
            store = MagicMock(spec=MemoryStore)
            charge = ChargeTracker()
            charge.set_run_id("test")
            ex = ToolExecutor.__new__(ToolExecutor)
            ex._store = store
            ex._charge = charge
            ex._run_id = "test"
            from zil.config import get_config
            ex._cfg = get_config()
        return ex

    def test_blocked_domain_raises(self, tmp_path, monkeypatch):
        import os
        monkeypatch.setenv("ZIL_STATE_DIR", str(tmp_path))
        from zil import config as cfg_mod
        monkeypatch.setattr(cfg_mod, "_config", None)

        allow_file = tmp_path / "network_allow.json"
        allow_file.write_text(json.dumps({"allowed_domains": ["wikipedia.org"]}))

        from zil.runtime.permissions import Warden, PermissionDenied
        warden = Warden()
        with pytest.raises(PermissionDenied):
            warden.check_network_domain("https://evil.com/steal")

    def test_allowed_domain_passes(self, tmp_path, monkeypatch):
        import os
        monkeypatch.setenv("ZIL_STATE_DIR", str(tmp_path))
        from zil import config as cfg_mod
        monkeypatch.setattr(cfg_mod, "_config", None)

        allow_file = tmp_path / "network_allow.json"
        allow_file.write_text(json.dumps({"allowed_domains": ["wikipedia.org"]}))

        from zil.runtime.permissions import Warden
        warden = Warden()
        # Should not raise
        warden.check_network_domain("https://en.wikipedia.org/wiki/Test")
