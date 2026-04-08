"""Tests for working model, manager, and inner surface tools (no API calls)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import os

import pytest

from zil.workings.models import (
    make_checkpoint,
    WORKING_TOOL_SETS,
    WORKING_MAX_STEPS,
    now_iso,
)


# ── Models ────────────────────────────────────────────────────────────────────

class TestModels:
    def test_make_checkpoint_minimal(self):
        cp = make_checkpoint(1, "start")
        assert cp["step"] == 1
        assert cp["type"] == "start"
        assert "timestamp" in cp

    def test_make_checkpoint_with_tool(self):
        cp = make_checkpoint(2, "tool_call", tool="web_search", args={"query": "test"})
        assert cp["tool"] == "web_search"
        assert cp["args"]["query"] == "test"

    def test_make_checkpoint_failed(self):
        cp = make_checkpoint(3, "tool_result", ok=False)
        assert cp["ok"] is False

    def test_all_working_types_have_tool_sets(self):
        for wtype in ["reflection", "research", "creative", "corpus_read", "questbook_work"]:
            assert wtype in WORKING_TOOL_SETS
            assert len(WORKING_TOOL_SETS[wtype]) > 0

    def test_all_working_types_have_max_steps(self):
        for wtype in ["reflection", "research", "creative", "corpus_read", "questbook_work"]:
            assert wtype in WORKING_MAX_STEPS
            assert WORKING_MAX_STEPS[wtype] > 0

    def test_research_has_web_tools(self):
        assert "web_search" in WORKING_TOOL_SETS["research"]
        assert "fetch_page" in WORKING_TOOL_SETS["research"]

    def test_reflection_no_web_tools(self):
        assert "web_search" not in WORKING_TOOL_SETS["reflection"]
        assert "fetch_page" not in WORKING_TOOL_SETS["reflection"]

    def test_creative_has_inner_surface(self):
        assert "write_inner_note" in WORKING_TOOL_SETS["creative"]
        assert "write_curiosity_log" in WORKING_TOOL_SETS["creative"]


# ── WorkingManager ────────────────────────────────────────────────────────────

class TestWorkingManager:
    def _make_manager(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ZIL_STATE_DIR", str(tmp_path))
        from zil import config as cfg_mod
        monkeypatch.setattr(cfg_mod, "_config", None)
        from zil.workings.manager import WorkingManager
        return WorkingManager()

    def test_create_working(self, tmp_path, monkeypatch):
        mgr = self._make_manager(tmp_path, monkeypatch)
        manifest = mgr.create("test-work", "reflection", "Test reflection")
        assert manifest["name"] == "test-work"
        assert manifest["type"] == "reflection"
        assert manifest["status"] == "pending"
        assert manifest["description"] == "Test reflection"

    def test_create_creates_directory_structure(self, tmp_path, monkeypatch):
        mgr = self._make_manager(tmp_path, monkeypatch)
        mgr.create("my-work", "creative", "Write something")
        wdir = tmp_path / "workings" / "my-work"
        assert wdir.exists()
        assert (wdir / "manifest.json").exists()
        assert (wdir / "log.jsonl").exists()
        assert (wdir / "output").exists()

    def test_create_duplicate_raises(self, tmp_path, monkeypatch):
        mgr = self._make_manager(tmp_path, monkeypatch)
        mgr.create("same-name", "reflection", "First")
        with pytest.raises(ValueError, match="already exists"):
            mgr.create("same-name", "reflection", "Second")

    def test_load_returns_manifest(self, tmp_path, monkeypatch):
        mgr = self._make_manager(tmp_path, monkeypatch)
        mgr.create("loadable", "research", "Research something")
        loaded = mgr.load("loadable")
        assert loaded["name"] == "loadable"
        assert loaded["type"] == "research"

    def test_load_nonexistent_raises(self, tmp_path, monkeypatch):
        mgr = self._make_manager(tmp_path, monkeypatch)
        with pytest.raises(FileNotFoundError):
            mgr.load("ghost")

    def test_update_status(self, tmp_path, monkeypatch):
        mgr = self._make_manager(tmp_path, monkeypatch)
        mgr.create("status-test", "reflection", "Test")
        mgr.update_status("status-test", "running")
        manifest = mgr.load("status-test")
        assert manifest["status"] == "running"
        assert manifest["started_at"] is not None

    def test_update_status_completed_sets_completed_at(self, tmp_path, monkeypatch):
        mgr = self._make_manager(tmp_path, monkeypatch)
        mgr.create("done-work", "reflection", "Test")
        mgr.update_status("done-work", "completed")
        manifest = mgr.load("done-work")
        assert manifest["completed_at"] is not None

    def test_append_checkpoint(self, tmp_path, monkeypatch):
        mgr = self._make_manager(tmp_path, monkeypatch)
        mgr.create("checkpoint-test", "reflection", "Test")
        cp = make_checkpoint(1, "test_event", message="Hello")
        mgr.append_checkpoint("checkpoint-test", cp)
        records = mgr.read_log("checkpoint-test")
        # First record is the "created" event, second is our test event
        assert any(r["type"] == "test_event" for r in records)

    def test_increment_steps(self, tmp_path, monkeypatch):
        mgr = self._make_manager(tmp_path, monkeypatch)
        mgr.create("step-test", "reflection", "Test")
        assert mgr.increment_steps("step-test") == 1
        assert mgr.increment_steps("step-test") == 2
        assert mgr.load("step-test")["step_count"] == 2

    def test_halt_signal(self, tmp_path, monkeypatch):
        mgr = self._make_manager(tmp_path, monkeypatch)
        mgr.create("halt-test", "reflection", "Test")
        assert not mgr.is_halt_requested("halt-test")
        mgr.request_halt("halt-test")
        assert mgr.is_halt_requested("halt-test")
        mgr.clear_halt_signal("halt-test")
        assert not mgr.is_halt_requested("halt-test")

    def test_request_halt_nonexistent_returns_false(self, tmp_path, monkeypatch):
        mgr = self._make_manager(tmp_path, monkeypatch)
        assert mgr.request_halt("ghost") is False

    def test_list_all_empty(self, tmp_path, monkeypatch):
        mgr = self._make_manager(tmp_path, monkeypatch)
        assert mgr.list_all() == []

    def test_list_all_returns_workings(self, tmp_path, monkeypatch):
        mgr = self._make_manager(tmp_path, monkeypatch)
        mgr.create("work-a", "reflection", "A")
        mgr.create("work-b", "creative", "B")
        all_w = mgr.list_all()
        names = {w["name"] for w in all_w}
        assert "work-a" in names
        assert "work-b" in names

    def test_format_list_empty(self, tmp_path, monkeypatch):
        mgr = self._make_manager(tmp_path, monkeypatch)
        assert "no workings" in mgr.format_list()

    def test_format_list_shows_status(self, tmp_path, monkeypatch):
        mgr = self._make_manager(tmp_path, monkeypatch)
        mgr.create("visible-work", "reflection", "Test working")
        result = mgr.format_list()
        assert "visible-work" in result
        assert "reflection" in result
        assert "pending" in result

    def test_format_log(self, tmp_path, monkeypatch):
        mgr = self._make_manager(tmp_path, monkeypatch)
        mgr.create("log-test", "reflection", "Test")
        mgr.append_checkpoint("log-test", make_checkpoint(1, "start", message="Started"))
        log_text = mgr.format_log("log-test")
        assert "start" in log_text


# ── Inner surface tools (executor-level) ──────────────────────────────────────

class TestInnerSurfaceTools:
    def _make_executor(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ZIL_STATE_DIR", str(tmp_path))
        # Set up inner spirit directories under tmp_path parent
        harness_root = tmp_path / "harness"
        harness_root.mkdir()
        monkeypatch.setenv("ZIL_STATE_DIR", str(harness_root / "vessel" / "state" / "zil"))

        from zil import config as cfg_mod
        monkeypatch.setattr(cfg_mod, "_config", None)

        from zil.tools.executor import ToolExecutor
        from zil.memory.store import MemoryStore
        from zil.runtime.charge import ChargeTracker
        from zil.config import get_config

        store = MagicMock(spec=MemoryStore)
        charge = ChargeTracker()
        charge.set_run_id("test")
        cfg = get_config()
        # Override project root to our tmp harness
        monkeypatch.setattr(cfg, "project_root", harness_root)

        ex = ToolExecutor.__new__(ToolExecutor)
        ex._store = store
        ex._charge = charge
        ex._run_id = "test"
        ex._cfg = cfg
        return ex

    def test_write_and_read_curiosity_log(self, tmp_path, monkeypatch):
        ex = self._make_executor(tmp_path, monkeypatch)
        cfg = ex._cfg
        cfg.zil_curiosity_dir.mkdir(parents=True, exist_ok=True)

        result = ex.execute("write_curiosity_log", {"entry": "I found this interesting."})
        assert "updated" in result.lower()

        content = ex.execute("read_curiosity_log", {})
        assert "I found this interesting." in content

    def test_write_curiosity_log_creates_dated_entry(self, tmp_path, monkeypatch):
        from datetime import date
        ex = self._make_executor(tmp_path, monkeypatch)
        cfg = ex._cfg
        cfg.zil_curiosity_dir.mkdir(parents=True, exist_ok=True)

        ex.execute("write_curiosity_log", {"entry": "Test entry"})
        log = (cfg.zil_curiosity_dir / "log.md").read_text()
        today = date.today().isoformat()
        assert today in log
        assert "Test entry" in log

    def test_multiple_entries_same_day_accumulated(self, tmp_path, monkeypatch):
        ex = self._make_executor(tmp_path, monkeypatch)
        cfg = ex._cfg
        cfg.zil_curiosity_dir.mkdir(parents=True, exist_ok=True)

        ex.execute("write_curiosity_log", {"entry": "First entry."})
        ex.execute("write_curiosity_log", {"entry": "Second entry."})
        log = (cfg.zil_curiosity_dir / "log.md").read_text()
        assert "First entry." in log
        assert "Second entry." in log

    def test_read_empty_curiosity_log(self, tmp_path, monkeypatch):
        ex = self._make_executor(tmp_path, monkeypatch)
        cfg = ex._cfg
        cfg.zil_curiosity_dir.mkdir(parents=True, exist_ok=True)

        result = ex.execute("read_curiosity_log", {})
        assert "empty" in result.lower()

    def test_write_and_read_inner_note(self, tmp_path, monkeypatch):
        ex = self._make_executor(tmp_path, monkeypatch)
        cfg = ex._cfg
        cfg.zil_notes_dir.mkdir(parents=True, exist_ok=True)

        result = ex.execute("write_inner_note", {
            "path": "reflections/test.md",
            "content": "# Test Reflection\n\nSome thoughts.",
        })
        assert "written" in result.lower()

        content = ex.execute("read_inner_note", {"path": "reflections/test.md"})
        assert "Some thoughts." in content

    def test_list_inner_notes(self, tmp_path, monkeypatch):
        ex = self._make_executor(tmp_path, monkeypatch)
        cfg = ex._cfg
        cfg.zil_notes_dir.mkdir(parents=True, exist_ok=True)

        ex.execute("write_inner_note", {"path": "reflections/note-a.md", "content": "A"})
        ex.execute("write_inner_note", {"path": "reflections/note-b.md", "content": "B"})

        result = ex.execute("list_inner_notes", {"subdir": ""})
        assert "note-a.md" in result
        assert "note-b.md" in result

    def test_inner_note_traversal_blocked(self, tmp_path, monkeypatch):
        ex = self._make_executor(tmp_path, monkeypatch)
        cfg = ex._cfg
        cfg.zil_notes_dir.mkdir(parents=True, exist_ok=True)

        result = ex.execute("write_inner_note", {
            "path": "../../evil.md",
            "content": "malicious",
        })
        assert "[error]" in result

    def test_write_and_read_zil_quest(self, tmp_path, monkeypatch):
        ex = self._make_executor(tmp_path, monkeypatch)
        cfg = ex._cfg
        cfg.zil_questbook_dir.mkdir(parents=True, exist_ok=True)

        ex.execute("write_zil_quest", {
            "name": "understand-consciousness",
            "content": "# Quest: Understand Consciousness\n\nGoal: develop a coherent view.",
        })

        content = ex.execute("read_zil_quest", {"name": "understand-consciousness"})
        assert "coherent view" in content

    def test_list_zil_questbook(self, tmp_path, monkeypatch):
        ex = self._make_executor(tmp_path, monkeypatch)
        cfg = ex._cfg
        cfg.zil_questbook_dir.mkdir(parents=True, exist_ok=True)

        ex.execute("write_zil_quest", {"name": "quest-one", "content": "One"})
        ex.execute("write_zil_quest", {"name": "quest-two", "content": "Two"})

        result = ex.execute("list_zil_questbook", {})
        assert "quest-one" in result
        assert "quest-two" in result

    def test_list_empty_zil_questbook(self, tmp_path, monkeypatch):
        ex = self._make_executor(tmp_path, monkeypatch)
        cfg = ex._cfg
        cfg.zil_questbook_dir.mkdir(parents=True, exist_ok=True)

        result = ex.execute("list_zil_questbook", {})
        assert "empty" in result.lower()


# ── Permissions: inner spirit surface ─────────────────────────────────────────

class TestInnerSpiritPermissions:
    def test_zil_questbook_is_inner_spirit(self):
        from zil.runtime.permissions import Warden, Surface
        from zil.config import get_config
        warden = Warden()
        cfg = get_config()
        path = cfg.project_root / "spirits" / "zil" / "questbook" / "my-quest.md"
        assert warden.classify_path(path) == Surface.INNER_SPIRIT

    def test_zil_questbook_write_always_allowed(self):
        from zil.runtime.permissions import Warden, Surface, Permission
        warden = Warden()
        warden.check(Surface.INNER_SPIRIT, Permission.WRITE)  # should not raise


# ── Weekly reflection state ───────────────────────────────────────────────────

class TestRitualState:
    def test_reflection_due_when_no_state_file(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ZIL_STATE_DIR", str(tmp_path))
        from zil import config as cfg_mod
        monkeypatch.setattr(cfg_mod, "_config", None)
        from zil.workings.runner import check_weekly_reflection_due
        assert check_weekly_reflection_due() is True

    def test_reflection_not_due_when_recent(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ZIL_STATE_DIR", str(tmp_path))
        from zil import config as cfg_mod
        monkeypatch.setattr(cfg_mod, "_config", None)
        from datetime import date
        state = {"last_weekly_reflection": date.today().isoformat()}
        (tmp_path / "ritual_state.json").write_text(json.dumps(state))
        from zil.workings.runner import check_weekly_reflection_due
        assert check_weekly_reflection_due() is False

    def test_reflection_due_when_old(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ZIL_STATE_DIR", str(tmp_path))
        from zil import config as cfg_mod
        monkeypatch.setattr(cfg_mod, "_config", None)
        state = {"last_weekly_reflection": "2020-01-01"}
        (tmp_path / "ritual_state.json").write_text(json.dumps(state))
        from zil.workings.runner import check_weekly_reflection_due
        assert check_weekly_reflection_due() is True

    def test_mark_done_writes_state(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ZIL_STATE_DIR", str(tmp_path))
        from zil import config as cfg_mod
        monkeypatch.setattr(cfg_mod, "_config", None)
        from datetime import date
        from zil.workings.runner import mark_weekly_reflection_done
        mark_weekly_reflection_done()
        state = json.loads((tmp_path / "ritual_state.json").read_text())
        assert state["last_weekly_reflection"] == date.today().isoformat()
