"""Tool registry.

ZIL⌀ has a narrow default tool surface. Tools must be explicitly registered
before they can be used. This prevents capability creep and makes widening visible.

In version 1, the default open surface is:
  - local_fs: read/write within allowed paths
  - No external acquisition by default

External tools (search, web) require explicit opt-in via warden.widen().
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Any


@dataclass
class ToolSpec:
    name: str
    description: str
    handler: Callable[..., Any]
    charge_operation: str = "local_state_inspection"
    requires_widening: bool = False
    surface: str = "shared"


class ToolRegistry:
    """Registry of available tools for ZIL⌀."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        self._tools[spec.name] = spec

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def list_available(self, *, include_widening_required: bool = False) -> list[str]:
        return [
            name
            for name, spec in self._tools.items()
            if include_widening_required or not spec.requires_widening
        ]

    def call(self, name: str, **kwargs) -> Any:
        spec = self._tools.get(name)
        if spec is None:
            raise ValueError(f"Unknown tool: {name!r}. Available: {self.list_available()}")
        return spec.handler(**kwargs)


# Module-level default registry
_registry: ToolRegistry | None = None


def get_registry() -> ToolRegistry:
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
        _register_defaults(_registry)
    return _registry


def _register_defaults(registry: ToolRegistry) -> None:
    """Register the narrow always-open tool surface."""
    from zil.tools import local_fs

    registry.register(ToolSpec(
        name="read_file",
        description="Read a file from an allowed path.",
        handler=local_fs.read_file,
        charge_operation="local_state_inspection",
        requires_widening=False,
        surface="shared",
    ))
    registry.register(ToolSpec(
        name="write_file",
        description="Write a file to an allowed path (artifacts/ or questbook/).",
        handler=local_fs.write_file,
        charge_operation="local_state_inspection",
        requires_widening=False,
        surface="shared",
    ))
    registry.register(ToolSpec(
        name="list_files",
        description="List files in an allowed directory.",
        handler=local_fs.list_files,
        charge_operation="local_state_inspection",
        requires_widening=False,
        surface="shared",
    ))
    registry.register(ToolSpec(
        name="web_search",
        description="Search the web for information.",
        handler=_stub_web_search,
        charge_operation="external_acquisition_search_burst",
        requires_widening=True,
        surface="external",
    ))


def _stub_web_search(query: str) -> str:
    return (
        "[Web search is not enabled in version 1. "
        "Enable it by widening the EXTERNAL surface via warden.widen().]"
    )
