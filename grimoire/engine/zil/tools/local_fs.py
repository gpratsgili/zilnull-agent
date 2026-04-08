"""Local filesystem tool implementations.

All paths are validated against allowed surfaces before any read/write.
"""

from __future__ import annotations

from pathlib import Path

from zil.config import get_config
from zil.runtime.permissions import Warden, Surface, Permission, PermissionDenied

_warden = Warden()


def _resolve(path_str: str) -> Path:
    cfg = get_config()
    path = Path(path_str)
    if not path.is_absolute():
        path = cfg.project_root / path
    return path.resolve()


def read_file(path: str) -> str:
    """Read a file. Allowed on shared and spirit-local surfaces."""
    resolved = _resolve(path)
    surface = _warden.classify_path(resolved)
    _warden.check(surface, Permission.READ, context=f"read_file({path})")
    if not resolved.exists():
        raise FileNotFoundError(f"File not found: {resolved}")
    return resolved.read_text(encoding="utf-8")


def write_file(path: str, content: str) -> str:
    """Write a file. Restricted to shared surfaces (artifacts/, questbook/)."""
    resolved = _resolve(path)
    surface = _warden.classify_path(resolved)
    if surface not in (Surface.SHARED,):
        raise PermissionDenied(
            f"write_file is only permitted on shared surfaces (artifacts/, questbook/). "
            f"Path {path!r} resolves to surface {surface.value}."
        )
    _warden.check(surface, Permission.WRITE, context=f"write_file({path})")

    # Check for embedded secrets before writing
    warnings = _warden.inspect_for_secrets(content)
    if warnings:
        raise PermissionDenied(
            f"Refusing to write file: possible secrets detected. Warnings: {warnings}"
        )

    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(content, encoding="utf-8")
    return f"Written: {resolved}"


def list_files(directory: str) -> list[str]:
    """List files in a directory. Allowed on shared surfaces."""
    resolved = _resolve(directory)
    surface = _warden.classify_path(resolved)
    _warden.check(surface, Permission.READ, context=f"list_files({directory})")
    if not resolved.is_dir():
        raise NotADirectoryError(f"Not a directory: {resolved}")
    return [str(p.relative_to(resolved)) for p in sorted(resolved.iterdir())]
