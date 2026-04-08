---
name: "create_artifact"
description: "Create a new durable file under artifacts/ for notes, reports, drafts, guides, exports, or other concrete work product."
spellbook: "artifact"
charge: 0
surface: "shared"
status: "active"
---

## What this cast does

Writes a new file to `artifacts/<path>`. Creates any missing parent directories.
Refuses to overwrite an existing file — use `edit_artifact` to modify existing artifacts.

## Inputs

- `path`: string — relative path under `artifacts/` (e.g. `"notes/meeting-2026-04-05.md"`)
- `content`: string — the file content

## Outputs

- File written to `artifacts/<path>`
- `tool_call` + `tool_result` events appended to the ledger

## Charge

`0` — producing durable work product is core, not a premium path.

## Permission surface

`shared` — writes to `artifacts/` only. Warden blocks writes outside this surface.
Warden also scans content for embedded secrets before writing.

## Rules

- Path must be relative and must not escape `artifacts/` (no `..` traversal)
- If the file already exists, this cast fails — use `edit_artifact` instead
- Secrets detected in content cause the write to be rejected

## Implementation

`grimoire/engine/zil/tools/local_fs.py` — `write_file()` (Phase 4: exposed as OpenAI tool)
