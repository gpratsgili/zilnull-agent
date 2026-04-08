---
name: "write_memory"
description: "Propose a typed memory record. The record is validated before being committed to a memory layer."
spellbook: "adept"
charge: 1
surface: "spirit_local"
status: "active"
---

## What this cast does

Submits a typed memory record as a candidate. The record passes through
`memory/validators.py` before any write occurs. Validation failure is logged
but does not crash the session.

This cast proposes and validates. A separate charge of `2` is incurred when the
record is committed to durable storage (`durable_memory_commit` in chargebook.md).

## Inputs

- `record`: typed memory object — must be one of:
  - `EpistemicMemory`
  - `RelationalMemory`
  - `BehavioralObservation`

## Outputs

- `ValidationResult`: `{ passed, warnings, errors, sanitized }`

## Charge

`1` — writing memory is not free. It requires judgment and has persistence cost.

## Critical constraints

- `EpistemicMemory` with `claim_owner: user` must use `truth_status: user_belief`.
  Setting `world_fact` for a user-owned claim is a memory contamination violation.
- Records with embedded secrets are rejected.
- High-confidence relational records without evidence generate a warning.

## Permission surface

`spirit_local` — writes to `spirits/zil/memories/window/` or `archive/`.

## Implementation

`grimoire/engine/zil/memory/store.py` — `MemoryStore.write_window()`, `write_archive()`
`grimoire/engine/zil/memory/validators.py` — `validate_memory()`
