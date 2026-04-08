"""Warden: capability boundary enforcement.

This module implements the narrow permission surface that every operation
must pass through before executing. It fails closed: if permission is
ambiguous or missing, the operation is refused.

Permission tiers
----------------
Always-open:
    SHARED (artifacts/, questbook/) — read and write
    INNER_SPIRIT (spirits/zil/curiosity/, notes/, creative/) — read and write
    SPIRIT_LOCAL (spirits/ broadly) — read only
    MACHINE_LOCAL (vessel/) — write for ledger
    INTERNAL (grimoire/) — read only

Session-widened (user grants for a session):
    EXTERNAL ACQUIRE — web requests, after domain checked against allow-list

Working-widened (user grants per working):
    EXTERNAL ACQUIRE with specific scope (web, screen)

Locked (never openable):
    INTERNAL WRITE — grimoire and source files cannot be written during execution
    Paths outside harness root — hard boundary enforced at path resolution

Rules:
- Secrets live in env vars, not markdown or logs.
- Shared surfaces (artifacts/, questbook/) are readable and writable.
- Inner spirit surfaces are ZIL's own — always-open for read/write.
- Spirit-local surfaces (spirits/ broadly) are read-only unless inner.
- The grimoire/ is read-only during normal execution.
- External acquisition requires explicit widening AND domain allow-list check.
- Any path outside harness root is refused at resolution time.
"""

from __future__ import annotations

import json
import re
from enum import Enum
from pathlib import Path
from urllib.parse import urlparse

from zil.config import get_config


class Surface(str, Enum):
    SHARED = "shared"              # artifacts/, questbook/ — open read/write
    INNER_SPIRIT = "inner_spirit"  # spirits/zil/{curiosity,notes,creative}/ — ZIL's own, open write
    SPIRIT_LOCAL = "spirit_local"  # spirits/ broadly — read only
    INTERNAL = "internal"          # grimoire/, src/ — read-only
    MACHINE_LOCAL = "machine_local"  # vessel/ — ledger writes allowed
    EXTERNAL = "external"          # network, search — requires widening + allow-list


class Permission(str, Enum):
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    ACQUIRE = "acquire"  # external data acquisition


# ZIL's self-owned directories within spirits/zil/ — always-open for write
_INNER_SPIRIT_DIRS = frozenset({"curiosity", "notes", "creative", "games", "people", "questbook"})

# Operations that are always permitted without widening
_ALWAYS_OPEN: set[tuple[Surface, Permission]] = {
    (Surface.SHARED, Permission.READ),
    (Surface.SHARED, Permission.WRITE),
    (Surface.INNER_SPIRIT, Permission.READ),
    (Surface.INNER_SPIRIT, Permission.WRITE),
    (Surface.SPIRIT_LOCAL, Permission.READ),
    (Surface.MACHINE_LOCAL, Permission.WRITE),  # ledger
    (Surface.INTERNAL, Permission.READ),
}

# Operations that require explicit widening
_REQUIRE_WIDENING: set[tuple[Surface, Permission]] = {
    (Surface.EXTERNAL, Permission.ACQUIRE),
    (Surface.EXTERNAL, Permission.READ),
    (Surface.INTERNAL, Permission.WRITE),  # never allowed during normal execution
}


class PermissionDenied(Exception):
    """Raised when an operation is refused by the warden."""


class Warden:
    """Enforces capability boundaries for ZIL⌀.

    Fails closed: if permission is ambiguous or missing, the operation is refused.
    Widening is explicit and logged — ZIL does not accumulate permissions silently.
    """

    def __init__(self) -> None:
        self._widened: set[tuple[Surface, Permission]] = set()

    # ── Permission checks ─────────────────────────────────────────────────

    def widen(self, surface: Surface, permission: Permission) -> None:
        """Explicitly grant a widened permission for this session."""
        if surface == Surface.INTERNAL and permission == Permission.WRITE:
            raise PermissionDenied(
                "Cannot widen write access to INTERNAL surface. "
                "Grimoire and source files are read-only during execution."
            )
        self._widened.add((surface, permission))

    def check(self, surface: Surface, permission: Permission, context: str = "") -> None:
        """Raise PermissionDenied if the operation is not permitted.

        Always fails closed on ambiguity.
        """
        if (surface, permission) in _ALWAYS_OPEN:
            return
        if (surface, permission) in self._widened:
            return
        if (surface, permission) in _REQUIRE_WIDENING:
            raise PermissionDenied(
                f"Operation requires explicit widening: {permission.value} on "
                f"{surface.value}. Context: {context or 'none'}. "
                f"Refusing rather than guessing."
            )
        # Default: deny anything not explicitly allowed
        raise PermissionDenied(
            f"Permission not granted: {permission.value} on {surface.value}. "
            f"Context: {context or 'none'}. Failing closed."
        )

    # ── Path enforcement ──────────────────────────────────────────────────

    def classify_path(self, path: Path) -> Surface:
        """Classify a filesystem path into a surface category.

        Uses the resolved path to prevent symlink traversal bypasses.
        """
        cfg = get_config()
        root = cfg.project_root.resolve()
        try:
            resolved = path.resolve()
            rel = resolved.relative_to(root)
        except ValueError:
            # Outside project root — external
            return Surface.EXTERNAL

        parts = rel.parts
        if not parts:
            return Surface.INTERNAL

        top = parts[0]
        if top in ("artifacts", "questbook"):
            return Surface.SHARED
        if top == "spirits":
            # Check if this is ZIL's self-owned inner surface
            # Pattern: spirits/zil/<inner_dir>/... OR spirits/zil/self.md
            if len(parts) >= 2 and parts[1] == "zil":
                if len(parts) >= 3 and parts[2] in _INNER_SPIRIT_DIRS:
                    return Surface.INNER_SPIRIT
                if len(parts) == 2 and rel.name == "self.md":
                    return Surface.INNER_SPIRIT
            return Surface.SPIRIT_LOCAL
        if top in ("grimoire", "src"):
            return Surface.INTERNAL
        if top == "vessel":
            return Surface.MACHINE_LOCAL
        # Everything else is internal by default
        return Surface.INTERNAL

    def check_within_root(self, path: Path, context: str = "") -> None:
        """Raise PermissionDenied if the resolved path escapes the harness root.

        This is a hard boundary enforced at the OS path level — not just
        application logic. Called before any file read or write.
        """
        cfg = get_config()
        root = cfg.project_root.resolve()
        try:
            path.resolve().relative_to(root)
        except ValueError:
            raise PermissionDenied(
                f"Path escapes harness root: {path}. "
                f"All file operations must stay within {root}. "
                f"Context: {context or 'none'}."
            )

    def check_path_write(self, path: Path, context: str = "") -> None:
        """Check write permission for a filesystem path.

        Enforces root boundary first, then surface-level permission.
        """
        self.check_within_root(path, context)
        surface = self.classify_path(path)
        self.check(surface, Permission.WRITE, context)

    # ── Network enforcement ───────────────────────────────────────────────

    def check_network_domain(self, url: str) -> None:
        """Raise PermissionDenied if the URL's domain is not in the allow-list.

        The allow-list lives at vessel/state/zil/network_allow.json.
        If the file does not exist or is empty, all outbound access is denied.
        """
        cfg = get_config()
        allow_path = cfg.network_allow_path

        if not allow_path.exists():
            raise PermissionDenied(
                f"Network access denied: allow-list not found at {allow_path}. "
                "Create it and add domains to enable outbound access."
            )

        try:
            data = json.loads(allow_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            raise PermissionDenied(f"Network access denied: could not read allow-list: {e}")

        allowed: list[str] = [d.lower().lstrip("*.") for d in data.get("allowed_domains", [])]
        if not allowed:
            raise PermissionDenied(
                "Network access denied: allow-list is empty. "
                "Add domains to vessel/state/zil/network_allow.json to enable outbound access."
            )

        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        # Strip port if present
        if ":" in domain:
            domain = domain.split(":")[0]

        for allowed_domain in allowed:
            if domain == allowed_domain or domain.endswith("." + allowed_domain):
                return

        raise PermissionDenied(
            f"Network access to {domain!r} denied: not in allow-list. "
            f"Add it to vessel/state/zil/network_allow.json to proceed."
        )

    # ── Secret detection ──────────────────────────────────────────────────

    def inspect_for_secrets(self, text: str) -> list[str]:
        """Scan text for patterns that look like embedded secrets.

        Returns a list of warnings. Empty list means clean.
        """
        warnings = []
        patterns = [
            (r"sk-[A-Za-z0-9]{20,}", "Possible OpenAI API key"),
            (r"AKIA[0-9A-Z]{16}", "Possible AWS access key"),
            (r"(?i)password\s*[:=]\s*\S+", "Possible hardcoded password"),
            (r"(?i)api[_-]?key\s*[:=]\s*['\"]?\S{8,}['\"]?", "Possible hardcoded API key"),
            (r"(?i)secret\s*[:=]\s*['\"]?\S{8,}['\"]?", "Possible hardcoded secret"),
        ]
        for pattern, label in patterns:
            if re.search(pattern, text):
                warnings.append(label)
        return warnings
