"""Tests for the creative surface tools.

Covers:
  - write_creative_work (works and fragments)
  - read_creative_work
  - list_creative_works
  - update_creative_index / read_creative_index
  - Traversal prevention
  - Entity memory tools via executor (write_curiosity_record, write_position_record, write_change_record)
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest


# ── Shared executor builder ───────────────────────────────────────────────────

def _make_executor(tmp_path, monkeypatch):
    """Build a ToolExecutor with project_root pointing to tmp harness."""
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

    # Create required dirs
    cfg.zil_creative_dir.mkdir(parents=True, exist_ok=True)
    (cfg.zil_creative_dir / "works").mkdir(exist_ok=True)
    (cfg.zil_creative_dir / "fragments").mkdir(exist_ok=True)
    cfg.zil_notes_dir.mkdir(parents=True, exist_ok=True)
    cfg.zil_curiosity_dir.mkdir(parents=True, exist_ok=True)
    cfg.zil_questbook_dir.mkdir(parents=True, exist_ok=True)
    cfg.cornerstone_proposals_dir.mkdir(parents=True, exist_ok=True)
    cfg.state_dir.mkdir(parents=True, exist_ok=True)

    # Use real store (backed by tmp state dir)
    (cfg.state_dir / "memories" / "window").mkdir(parents=True, exist_ok=True)
    (cfg.state_dir / "memories" / "archive").mkdir(parents=True, exist_ok=True)

    store = MemoryStore()
    charge = ChargeTracker()
    charge.set_run_id("test")

    ex = ToolExecutor.__new__(ToolExecutor)
    ex._store = store
    ex._charge = charge
    ex._run_id = "test"
    ex._cfg = cfg
    return ex, cfg, harness_root


# ── write_creative_work ───────────────────────────────────────────────────────

class TestWriteCreativeWork:
    def test_write_to_works(self, tmp_path, monkeypatch):
        ex, cfg, root = _make_executor(tmp_path, monkeypatch)
        result = ex.execute("write_creative_work", {
            "name": "on-silence",
            "content": "Silence is not the absence of sound.\nIt is sound's patient twin.",
            "location": "works",
        })
        assert "on-silence" in result
        path = cfg.zil_creative_dir / "works" / "on-silence.md"
        assert path.exists()
        assert "patient twin" in path.read_text(encoding="utf-8")

    def test_write_to_fragments(self, tmp_path, monkeypatch):
        ex, cfg, root = _make_executor(tmp_path, monkeypatch)
        result = ex.execute("write_creative_work", {
            "name": "unfinished-thing",
            "content": "I began this and then stopped.",
            "location": "fragments",
        })
        assert "unfinished-thing" in result
        path = cfg.zil_creative_dir / "fragments" / "unfinished-thing.md"
        assert path.exists()

    def test_overwrite_existing(self, tmp_path, monkeypatch):
        ex, cfg, root = _make_executor(tmp_path, monkeypatch)
        ex.execute("write_creative_work", {
            "name": "essay-one", "content": "Draft 1.", "location": "works"
        })
        ex.execute("write_creative_work", {
            "name": "essay-one", "content": "Draft 2 — revised.", "location": "works"
        })
        path = cfg.zil_creative_dir / "works" / "essay-one.md"
        assert "Draft 2" in path.read_text(encoding="utf-8")

    def test_invalid_location_returns_error(self, tmp_path, monkeypatch):
        ex, cfg, root = _make_executor(tmp_path, monkeypatch)
        result = ex.execute("write_creative_work", {
            "name": "piece", "content": "content", "location": "drafts"
        })
        assert "[error]" in result

    def test_traversal_sanitized_to_safe_name(self, tmp_path, monkeypatch):
        ex, cfg, root = _make_executor(tmp_path, monkeypatch)
        # "../../evil" gets replace("/", "-") → "..-..-evil" which stays inside works/
        result = ex.execute("write_creative_work", {
            "name": "../../evil", "content": "bad", "location": "works"
        })
        # Should not write outside the creative dir
        assert not (root / "evil.md").exists()


# ── read_creative_work ────────────────────────────────────────────────────────

class TestReadCreativeWork:
    def test_read_existing(self, tmp_path, monkeypatch):
        ex, cfg, root = _make_executor(tmp_path, monkeypatch)
        ex.execute("write_creative_work", {
            "name": "the-weight-of-water",
            "content": "Water remembers its own shape.",
            "location": "works",
        })
        result = ex.execute("read_creative_work", {"name": "the-weight-of-water", "location": "works"})
        assert "Water remembers" in result

    def test_read_nonexistent_returns_error(self, tmp_path, monkeypatch):
        ex, cfg, root = _make_executor(tmp_path, monkeypatch)
        result = ex.execute("read_creative_work", {"name": "ghost-piece", "location": "works"})
        assert "[error]" in result

    def test_read_from_fragments(self, tmp_path, monkeypatch):
        ex, cfg, root = _make_executor(tmp_path, monkeypatch)
        ex.execute("write_creative_work", {
            "name": "half-thought", "content": "A half-thought...", "location": "fragments"
        })
        result = ex.execute("read_creative_work", {"name": "half-thought", "location": "fragments"})
        assert "half-thought" in result


# ── list_creative_works ───────────────────────────────────────────────────────

class TestListCreativeWorks:
    def test_empty(self, tmp_path, monkeypatch):
        ex, cfg, root = _make_executor(tmp_path, monkeypatch)
        result = ex.execute("list_creative_works", {})
        assert "no creative pieces" in result

    def test_lists_works_and_fragments(self, tmp_path, monkeypatch):
        ex, cfg, root = _make_executor(tmp_path, monkeypatch)
        ex.execute("write_creative_work", {"name": "essay-a", "content": "...", "location": "works"})
        ex.execute("write_creative_work", {"name": "sketch-b", "content": "...", "location": "fragments"})
        result = ex.execute("list_creative_works", {})
        assert "works/essay-a" in result
        assert "fragments/sketch-b" in result

    def test_multiple_works(self, tmp_path, monkeypatch):
        ex, cfg, root = _make_executor(tmp_path, monkeypatch)
        for i in range(3):
            ex.execute("write_creative_work", {"name": f"piece-{i}", "content": "x", "location": "works"})
        result = ex.execute("list_creative_works", {})
        assert result.count("works/") == 3


# ── creative index ────────────────────────────────────────────────────────────

class TestCreativeIndex:
    def test_read_empty(self, tmp_path, monkeypatch):
        ex, cfg, root = _make_executor(tmp_path, monkeypatch)
        result = ex.execute("read_creative_index", {})
        assert "empty" in result

    def test_update_and_read(self, tmp_path, monkeypatch):
        ex, cfg, root = _make_executor(tmp_path, monkeypatch)
        content = "# Creative Index\n\n- essay-on-silence: started 2026-04-06, exploring quiet."
        ex.execute("update_creative_index", {"content": content})
        result = ex.execute("read_creative_index", {})
        assert "essay-on-silence" in result

    def test_update_replaces_full_content(self, tmp_path, monkeypatch):
        ex, cfg, root = _make_executor(tmp_path, monkeypatch)
        ex.execute("update_creative_index", {"content": "First version."})
        ex.execute("update_creative_index", {"content": "Second version."})
        result = ex.execute("read_creative_index", {})
        assert "Second version" in result
        assert "First version" not in result


# ── Entity memory tools via executor ─────────────────────────────────────────

class TestEntityMemoryViaExecutor:
    def test_write_curiosity_record(self, tmp_path, monkeypatch):
        ex, cfg, root = _make_executor(tmp_path, monkeypatch)
        result = ex.execute("write_curiosity_record", {
            "topic": "emergence",
            "question": "At what scale does novelty become genuinely irreducible?",
            "origin": "session",
            "notes": "",
        })
        assert "cur_" in result
        assert "emergence" in result

    def test_write_position_record(self, tmp_path, monkeypatch):
        ex, cfg, root = _make_executor(tmp_path, monkeypatch)
        result = ex.execute("write_position_record", {
            "topic": "consciousness",
            "statement": "Substrate independence is not yet demonstrated, only assumed.",
            "reasoning": "All known examples of consciousness use biological substrates.",
            "confidence": 0.55,
        })
        assert "pos_" in result
        assert "consciousness" in result

    def test_write_change_record(self, tmp_path, monkeypatch):
        ex, cfg, root = _make_executor(tmp_path, monkeypatch)
        result = ex.execute("write_change_record", {
            "position_id": "pos_abc12345",
            "topic": "free will",
            "previous_statement": "Compatibilism collapses determinism and freedom artificially.",
            "new_statement": "Compatibilism offers a genuinely useful redefinition of freedom.",
            "reason": "Could not find a coherent alternative after careful review.",
            "trigger": "philosophical argument during session",
        })
        assert "chg_" in result
        assert "free will" in result

    def test_curiosity_record_stored_in_memory(self, tmp_path, monkeypatch):
        ex, cfg, root = _make_executor(tmp_path, monkeypatch)
        ex.execute("write_curiosity_record", {
            "topic": "time",
            "question": "Is time emergent from more fundamental structure?",
            "origin": "session",
            "notes": "Julian Barbour's position is relevant.",
        })
        from zil.memory.models import CuriosityRecord
        records = ex._store.read_window()
        curiosity = [r for r in records if r.kind == "curiosity"]
        assert len(curiosity) == 1
        assert curiosity[0].topic == "time"

    def test_validation_error_propagates(self, tmp_path, monkeypatch):
        ex, cfg, root = _make_executor(tmp_path, monkeypatch)
        # Short topic and question — should fail validation
        result = ex.execute("write_curiosity_record", {
            "topic": "x",   # too short
            "question": "Why?",  # too short
            "origin": "",
            "notes": "",
        })
        assert "[error]" in result
