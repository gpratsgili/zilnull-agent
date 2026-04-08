"""Tests for the reading club (Phase 10).

Covers:
  - write_reading_interpretation — pre-commit to notes, timestamp header
  - read_reading_interpretation — reads back pre-committed interpretation
  - annotate_reading — appends timestamped annotations to reading artifact
  - Traversal prevention for all reading paths
  - _safe_name helper in reading session module
  - Archive structure (reading_artifacts_dir)
  - Config: zil_reading_notes_dir and reading_artifacts_dir
"""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import MagicMock

import pytest


# ── Shared executor builder ───────────────────────────────────────────────────

def _make_executor(tmp_path, monkeypatch):
    harness_root = tmp_path / "harness"
    harness_root.mkdir()

    monkeypatch.setenv("ZIL_STATE_DIR", str(harness_root / "vessel" / "state" / "zil"))
    monkeypatch.setenv("ZIL_OPENAI_API_KEY", "test-key")

    import zil.config as cfg_mod
    monkeypatch.setattr(cfg_mod, "_config", None)

    from zil.config import get_config
    from zil.memory.store import MemoryStore
    from zil.runtime.charge import ChargeTracker
    from zil.tools.executor import ToolExecutor

    cfg = get_config()
    monkeypatch.setattr(cfg, "project_root", harness_root)

    # Required dirs
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    (cfg.state_dir / "memories" / "window").mkdir(parents=True, exist_ok=True)
    (cfg.state_dir / "memories" / "archive").mkdir(parents=True, exist_ok=True)
    cfg.zil_reading_notes_dir.mkdir(parents=True, exist_ok=True)
    cfg.reading_artifacts_dir.mkdir(parents=True, exist_ok=True)
    cfg.zil_notes_dir.mkdir(parents=True, exist_ok=True)
    cfg.zil_curiosity_dir.mkdir(parents=True, exist_ok=True)
    cfg.artifacts_dir.mkdir(parents=True, exist_ok=True)

    store = MemoryStore()
    charge = ChargeTracker()
    charge.set_run_id("test")

    ex = ToolExecutor.__new__(ToolExecutor)
    ex._store = store
    ex._charge = charge
    ex._run_id = "test"
    ex._cfg = cfg
    return ex, cfg, harness_root


# ── write_reading_interpretation ──────────────────────────────────────────────

class TestWriteReadingInterpretation:
    def test_creates_file_at_correct_path(self, tmp_path, monkeypatch):
        ex, cfg, root = _make_executor(tmp_path, monkeypatch)
        result = ex.execute("write_reading_interpretation", {
            "file": "the-dispossessed",
            "section": "chapter-1",
            "content": "The opening strikes me as architectural — a wall as a double boundary.",
        })
        assert "pre-committed" in result.lower()
        path = cfg.zil_reading_notes_dir / "the-dispossessed" / "chapter-1.md"
        assert path.exists()

    def test_content_written_correctly(self, tmp_path, monkeypatch):
        ex, cfg, root = _make_executor(tmp_path, monkeypatch)
        ex.execute("write_reading_interpretation", {
            "file": "test-book",
            "section": "intro",
            "content": "This is ZIL's pre-committed reading.",
        })
        path = cfg.zil_reading_notes_dir / "test-book" / "intro.md"
        content = path.read_text(encoding="utf-8")
        assert "ZIL's pre-committed reading" in content

    def test_timestamp_header_present(self, tmp_path, monkeypatch):
        ex, cfg, root = _make_executor(tmp_path, monkeypatch)
        ex.execute("write_reading_interpretation", {
            "file": "test-book",
            "section": "intro",
            "content": "My interpretation.",
        })
        path = cfg.zil_reading_notes_dir / "test-book" / "intro.md"
        content = path.read_text(encoding="utf-8")
        assert "Pre-committed interpretation:" in content
        # Timestamp should be ISO format
        assert re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", content)

    def test_file_and_section_names_sanitized(self, tmp_path, monkeypatch):
        ex, cfg, root = _make_executor(tmp_path, monkeypatch)
        ex.execute("write_reading_interpretation", {
            "file": "The Dispossessed",
            "section": "Chapter One: The Wall",
            "content": "My reading.",
        })
        # Sanitized: "the-dispossessed" / "chapter-one-the-wall"
        path = cfg.zil_reading_notes_dir / "the-dispossessed" / "chapter-one-the-wall.md"
        assert path.exists()

    def test_overwrites_if_called_again(self, tmp_path, monkeypatch):
        ex, cfg, root = _make_executor(tmp_path, monkeypatch)
        ex.execute("write_reading_interpretation", {
            "file": "book", "section": "s1", "content": "First reading."
        })
        ex.execute("write_reading_interpretation", {
            "file": "book", "section": "s1", "content": "Second reading."
        })
        path = cfg.zil_reading_notes_dir / "book" / "s1.md"
        content = path.read_text(encoding="utf-8")
        assert "Second reading" in content
        assert "First reading" not in content


# ── read_reading_interpretation ───────────────────────────────────────────────

class TestReadReadingInterpretation:
    def test_reads_existing_interpretation(self, tmp_path, monkeypatch):
        ex, cfg, root = _make_executor(tmp_path, monkeypatch)
        ex.execute("write_reading_interpretation", {
            "file": "book", "section": "intro",
            "content": "The opening sentence does something strange with time.",
        })
        result = ex.execute("read_reading_interpretation", {"file": "book", "section": "intro"})
        assert "strange with time" in result

    def test_returns_error_when_not_found(self, tmp_path, monkeypatch):
        ex, cfg, root = _make_executor(tmp_path, monkeypatch)
        result = ex.execute("read_reading_interpretation", {
            "file": "nonexistent-book", "section": "chapter-99"
        })
        assert "[error]" in result

    def test_timestamp_comment_present_in_read_content(self, tmp_path, monkeypatch):
        ex, cfg, root = _make_executor(tmp_path, monkeypatch)
        ex.execute("write_reading_interpretation", {
            "file": "book", "section": "part-2", "content": "My notes on part two."
        })
        result = ex.execute("read_reading_interpretation", {"file": "book", "section": "part-2"})
        assert "Pre-committed interpretation:" in result


# ── annotate_reading ──────────────────────────────────────────────────────────

class TestAnnotateReading:
    def test_creates_artifact_file(self, tmp_path, monkeypatch):
        ex, cfg, root = _make_executor(tmp_path, monkeypatch)
        result = ex.execute("annotate_reading", {
            "file": "book",
            "section": "chapter-1",
            "passage": "'The wall had two faces'",
            "note": "The wall as boundary and definition — both sides defined by the same structure.",
        })
        assert "annotation" in result.lower()
        path = cfg.reading_artifacts_dir / "book" / "chapter-1.md"
        assert path.exists()

    def test_annotation_content_present(self, tmp_path, monkeypatch):
        ex, cfg, root = _make_executor(tmp_path, monkeypatch)
        ex.execute("annotate_reading", {
            "file": "book", "section": "ch1",
            "passage": "the opening sentence",
            "note": "Time collapses here.",
        })
        path = cfg.reading_artifacts_dir / "book" / "ch1.md"
        content = path.read_text(encoding="utf-8")
        assert "Time collapses here" in content
        assert "the opening sentence" in content

    def test_timestamp_in_annotation(self, tmp_path, monkeypatch):
        ex, cfg, root = _make_executor(tmp_path, monkeypatch)
        ex.execute("annotate_reading", {
            "file": "book", "section": "ch1",
            "passage": "a passage",
            "note": "A note about it.",
        })
        path = cfg.reading_artifacts_dir / "book" / "ch1.md"
        content = path.read_text(encoding="utf-8")
        # Timestamp format: [YYYY-MM-DD HH:MM]
        assert re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", content)

    def test_annotations_accumulate(self, tmp_path, monkeypatch):
        ex, cfg, root = _make_executor(tmp_path, monkeypatch)
        ex.execute("annotate_reading", {
            "file": "book", "section": "ch1",
            "passage": "first passage",
            "note": "First annotation.",
        })
        ex.execute("annotate_reading", {
            "file": "book", "section": "ch1",
            "passage": "second passage",
            "note": "Second annotation.",
        })
        path = cfg.reading_artifacts_dir / "book" / "ch1.md"
        content = path.read_text(encoding="utf-8")
        assert "First annotation" in content
        assert "Second annotation" in content

    def test_passage_truncated_to_80_chars(self, tmp_path, monkeypatch):
        ex, cfg, root = _make_executor(tmp_path, monkeypatch)
        long_passage = "x" * 200
        ex.execute("annotate_reading", {
            "file": "book", "section": "ch1",
            "passage": long_passage,
            "note": "A note.",
        })
        path = cfg.reading_artifacts_dir / "book" / "ch1.md"
        content = path.read_text(encoding="utf-8")
        # The passage in backticks should be at most 80 chars
        match = re.search(r"`([^`]*)`", content)
        assert match
        assert len(match.group(1)) <= 80


# ── Traversal prevention ──────────────────────────────────────────────────────

class TestReadingTraversalPrevention:
    def test_interpretation_traversal_blocked(self, tmp_path, monkeypatch):
        ex, cfg, root = _make_executor(tmp_path, monkeypatch)
        # The safe_name function converts / to - so direct traversal via name
        # won't escape, but let's verify the path stays inside the reading notes dir
        result = ex.execute("write_reading_interpretation", {
            "file": "../../evil",
            "section": "bad",
            "content": "Malicious content",
        })
        # Should not have written outside the reading notes dir
        evil_path = cfg.zil_notes_dir.parent.parent / "evil"
        assert not evil_path.exists()
        # Should succeed (safe name normalizes it)
        assert "[error]" not in result or "escapes" in result

    def test_annotation_traversal_blocked(self, tmp_path, monkeypatch):
        ex, cfg, root = _make_executor(tmp_path, monkeypatch)
        result = ex.execute("annotate_reading", {
            "file": "../../evil",
            "section": "bad",
            "passage": "passage",
            "note": "bad note",
        })
        evil_path = cfg.artifacts_dir.parent / "evil"
        assert not evil_path.exists()


# ── Config properties ─────────────────────────────────────────────────────────

class TestReadingConfig:
    def test_reading_notes_dir_under_zil_notes(self, tmp_path, monkeypatch):
        ex, cfg, root = _make_executor(tmp_path, monkeypatch)
        assert cfg.zil_reading_notes_dir == cfg.zil_notes_dir / "reading"

    def test_reading_artifacts_dir_under_artifacts(self, tmp_path, monkeypatch):
        ex, cfg, root = _make_executor(tmp_path, monkeypatch)
        assert cfg.reading_artifacts_dir == cfg.artifacts_dir / "reading"


# ── Safe name helper ──────────────────────────────────────────────────────────

class TestSafeName:
    def test_basic_sanitization(self):
        from zil.reading.session import _safe_name
        assert _safe_name("The Dispossessed") == "the-dispossessed"
        assert _safe_name("Chapter 1: The Wall") == "chapter-1-the-wall"

    def test_empty_fallback(self):
        from zil.reading.session import _safe_name
        assert _safe_name("---") == "unnamed"

    def test_already_safe(self):
        from zil.reading.session import _safe_name
        assert _safe_name("chapter-one") == "chapter-one"

    def test_special_characters_stripped(self):
        from zil.reading.session import _safe_name
        name = _safe_name("book.pdf")
        assert name == "book-pdf"
