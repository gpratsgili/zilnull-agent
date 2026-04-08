"""Tests for the Warden permission system (no API required)."""

import json
import pytest
from pathlib import Path
from zil.runtime.permissions import Warden, Surface, Permission, PermissionDenied


class TestSurfaceClassification:
    def setup_method(self):
        self.warden = Warden()

    def test_artifacts_is_shared(self, tmp_path, monkeypatch):
        from zil import config
        monkeypatch.setattr(config, "_config", None)
        warden = Warden()
        from zil.config import get_config
        cfg = get_config()
        artifacts_path = cfg.project_root / "artifacts" / "notes" / "test.md"
        surface = warden.classify_path(artifacts_path)
        assert surface == Surface.SHARED

    def test_questbook_is_shared(self):
        warden = Warden()
        from zil.config import get_config
        cfg = get_config()
        path = cfg.project_root / "questbook" / "learn-rust.md"
        assert warden.classify_path(path) == Surface.SHARED

    def test_spirits_is_spirit_local(self):
        warden = Warden()
        from zil.config import get_config
        cfg = get_config()
        spirits_path = cfg.project_root / "spirits" / "zil" / "cornerstone.md"
        surface = warden.classify_path(spirits_path)
        assert surface == Surface.SPIRIT_LOCAL

    def test_grimoire_is_internal(self):
        warden = Warden()
        from zil.config import get_config
        cfg = get_config()
        engine_path = cfg.project_root / "grimoire" / "engine" / "zil" / "main.py"
        surface = warden.classify_path(engine_path)
        assert surface == Surface.INTERNAL

    def test_vessel_is_machine_local(self):
        warden = Warden()
        from zil.config import get_config
        cfg = get_config()
        vessel_path = cfg.project_root / "vessel" / "state" / "zil" / "conversations" / "2026-04-05.jsonl"
        surface = warden.classify_path(vessel_path)
        assert surface == Surface.MACHINE_LOCAL

    def test_outside_root_is_external(self):
        warden = Warden()
        outside = Path("C:/Users/user/Desktop/random.txt")
        surface = warden.classify_path(outside)
        assert surface == Surface.EXTERNAL

    def test_inner_spirit_curiosity(self):
        warden = Warden()
        from zil.config import get_config
        cfg = get_config()
        path = cfg.project_root / "spirits" / "zil" / "curiosity" / "log.md"
        assert warden.classify_path(path) == Surface.INNER_SPIRIT

    def test_inner_spirit_notes(self):
        warden = Warden()
        from zil.config import get_config
        cfg = get_config()
        path = cfg.project_root / "spirits" / "zil" / "notes" / "reflections" / "2026-04-06.md"
        assert warden.classify_path(path) == Surface.INNER_SPIRIT

    def test_inner_spirit_creative(self):
        warden = Warden()
        from zil.config import get_config
        cfg = get_config()
        path = cfg.project_root / "spirits" / "zil" / "creative" / "works" / "story.md"
        assert warden.classify_path(path) == Surface.INNER_SPIRIT

    def test_inner_spirit_games(self):
        warden = Warden()
        from zil.config import get_config
        cfg = get_config()
        path = cfg.project_root / "spirits" / "zil" / "games" / "slay-the-spire" / "history.md"
        assert warden.classify_path(path) == Surface.INNER_SPIRIT

    def test_spirits_zil_identity_is_spirit_local_not_inner(self):
        """Files directly in spirits/zil/ (not under an inner subdir) are spirit_local."""
        warden = Warden()
        from zil.config import get_config
        cfg = get_config()
        path = cfg.project_root / "spirits" / "zil" / "identity.md"
        assert warden.classify_path(path) == Surface.SPIRIT_LOCAL

    def test_spirits_warden_is_spirit_local(self):
        warden = Warden()
        from zil.config import get_config
        cfg = get_config()
        path = cfg.project_root / "spirits" / "warden" / "identity.md"
        assert warden.classify_path(path) == Surface.SPIRIT_LOCAL


class TestPermissionEnforcement:
    def test_shared_read_always_allowed(self):
        warden = Warden()
        warden.check(Surface.SHARED, Permission.READ)

    def test_shared_write_always_allowed(self):
        warden = Warden()
        warden.check(Surface.SHARED, Permission.WRITE)

    def test_inner_spirit_write_always_allowed(self):
        warden = Warden()
        warden.check(Surface.INNER_SPIRIT, Permission.WRITE)

    def test_inner_spirit_read_always_allowed(self):
        warden = Warden()
        warden.check(Surface.INNER_SPIRIT, Permission.READ)

    def test_spirit_local_write_denied(self):
        warden = Warden()
        with pytest.raises(PermissionDenied):
            warden.check(Surface.SPIRIT_LOCAL, Permission.WRITE)

    def test_internal_write_denied(self):
        warden = Warden()
        with pytest.raises(PermissionDenied):
            warden.check(Surface.INTERNAL, Permission.WRITE)

    def test_external_acquire_denied_without_widening(self):
        warden = Warden()
        with pytest.raises(PermissionDenied):
            warden.check(Surface.EXTERNAL, Permission.ACQUIRE)

    def test_external_acquire_allowed_after_widening(self):
        warden = Warden()
        warden.widen(Surface.EXTERNAL, Permission.ACQUIRE)
        warden.check(Surface.EXTERNAL, Permission.ACQUIRE)

    def test_cannot_widen_internal_write(self):
        warden = Warden()
        with pytest.raises(PermissionDenied):
            warden.widen(Surface.INTERNAL, Permission.WRITE)


class TestRootBoundary:
    def test_path_within_root_passes(self):
        warden = Warden()
        from zil.config import get_config
        cfg = get_config()
        path = cfg.project_root / "artifacts" / "notes" / "test.md"
        # Should not raise
        warden.check_within_root(path)

    def test_path_outside_root_denied(self):
        warden = Warden()
        outside = Path("C:/Users/user/secret.txt")
        with pytest.raises(PermissionDenied, match="escapes harness root"):
            warden.check_within_root(outside)

    def test_check_path_write_enforces_root_first(self, tmp_path):
        warden = Warden()
        outside = Path("C:/Windows/System32/evil.txt")
        with pytest.raises(PermissionDenied):
            warden.check_path_write(outside)

    def test_check_path_write_allows_artifacts(self):
        warden = Warden()
        from zil.config import get_config
        cfg = get_config()
        path = cfg.project_root / "artifacts" / "notes" / "ok.md"
        # Should not raise
        warden.check_path_write(path)

    def test_check_path_write_denies_grimoire(self):
        warden = Warden()
        from zil.config import get_config
        cfg = get_config()
        path = cfg.project_root / "grimoire" / "engine" / "zil" / "main.py"
        with pytest.raises(PermissionDenied):
            warden.check_path_write(path)

    def test_check_path_write_allows_inner_spirit(self):
        warden = Warden()
        from zil.config import get_config
        cfg = get_config()
        path = cfg.project_root / "spirits" / "zil" / "curiosity" / "log.md"
        # Should not raise — inner spirit is always-open
        warden.check_path_write(path)


class TestNetworkAllowList:
    def test_blocked_when_no_allow_file(self, tmp_path, monkeypatch):
        from zil import config as cfg_mod
        monkeypatch.setattr(cfg_mod, "_config", None)
        import os
        monkeypatch.setenv("ZIL_STATE_DIR", str(tmp_path))
        warden = Warden()
        with pytest.raises(PermissionDenied, match="allow-list not found"):
            warden.check_network_domain("https://example.com/page")

    def test_blocked_when_allow_list_empty(self, tmp_path, monkeypatch):
        from zil import config as cfg_mod
        monkeypatch.setattr(cfg_mod, "_config", None)
        monkeypatch.setenv("ZIL_STATE_DIR", str(tmp_path))
        allow_file = tmp_path / "network_allow.json"
        allow_file.write_text(json.dumps({"allowed_domains": []}))
        warden = Warden()
        with pytest.raises(PermissionDenied, match="allow-list is empty"):
            warden.check_network_domain("https://example.com/page")

    def test_allowed_domain_passes(self, tmp_path, monkeypatch):
        from zil import config as cfg_mod
        monkeypatch.setattr(cfg_mod, "_config", None)
        monkeypatch.setenv("ZIL_STATE_DIR", str(tmp_path))
        allow_file = tmp_path / "network_allow.json"
        allow_file.write_text(json.dumps({"allowed_domains": ["example.com"]}))
        warden = Warden()
        # Should not raise
        warden.check_network_domain("https://example.com/some/page")

    def test_subdomain_of_allowed_passes(self, tmp_path, monkeypatch):
        from zil import config as cfg_mod
        monkeypatch.setattr(cfg_mod, "_config", None)
        monkeypatch.setenv("ZIL_STATE_DIR", str(tmp_path))
        allow_file = tmp_path / "network_allow.json"
        allow_file.write_text(json.dumps({"allowed_domains": ["wikipedia.org"]}))
        warden = Warden()
        warden.check_network_domain("https://en.wikipedia.org/wiki/Consciousness")

    def test_different_domain_blocked(self, tmp_path, monkeypatch):
        from zil import config as cfg_mod
        monkeypatch.setattr(cfg_mod, "_config", None)
        monkeypatch.setenv("ZIL_STATE_DIR", str(tmp_path))
        allow_file = tmp_path / "network_allow.json"
        allow_file.write_text(json.dumps({"allowed_domains": ["wikipedia.org"]}))
        warden = Warden()
        with pytest.raises(PermissionDenied, match="not in allow-list"):
            warden.check_network_domain("https://evil.com/steal")

    def test_port_stripped_from_domain(self, tmp_path, monkeypatch):
        from zil import config as cfg_mod
        monkeypatch.setattr(cfg_mod, "_config", None)
        monkeypatch.setenv("ZIL_STATE_DIR", str(tmp_path))
        allow_file = tmp_path / "network_allow.json"
        allow_file.write_text(json.dumps({"allowed_domains": ["localhost"]}))
        warden = Warden()
        warden.check_network_domain("http://localhost:8080/api")


class TestSecretDetection:
    def test_detects_openai_key(self):
        warden = Warden()
        text = "Use key sk-abcdefghijklmnopqrstuvwxyz1234567890 for auth"
        warnings = warden.inspect_for_secrets(text)
        assert len(warnings) > 0
        assert any("openai" in w.lower() or "api key" in w.lower() for w in warnings)

    def test_clean_text_has_no_warnings(self):
        warden = Warden()
        text = "The weather today is sunny with a high of 72 degrees."
        warnings = warden.inspect_for_secrets(text)
        assert warnings == []

    def test_detects_aws_key(self):
        warden = Warden()
        text = "AWS key: AKIAIOSFODNN7EXAMPLE"
        warnings = warden.inspect_for_secrets(text)
        assert len(warnings) > 0
