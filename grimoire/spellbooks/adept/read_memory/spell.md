---
name: "read_memory"
description: "Read typed memory records from a memory layer (window, archive, or long-term)."
spellbook: "adept"
charge: 0
surface: "spirit_local"
status: "active"
---

## What this cast does

Retrieves typed memory records from the specified layer. Used at session start
to build context, and during a turn when ZIL needs to recall something specific.

## Inputs

- `layer`: string — `"window"`, `"archive"`, or `"long_term"`
- `limit`: int — max records to return (default: 20)

## Outputs

List of typed memory records (`EpistemicMemory | RelationalMemory | BehavioralObservation`),
or the raw markdown text for `long_term`.

## Charge

`0` — reading memory is part of basic functioning. It must never be taxed.

## Permission surface

`spirit_local` — reads from `spirits/zil/memories/`.

## Memory types

Records are typed, not free text:

- `EpistemicMemory` — claims, positions, evidence, disputes
- `RelationalMemory` — user preferences, communication patterns, values
- `BehavioralObservation` — how ZIL behaved and what the user's response was

User beliefs are stored as `truth_status: user_belief`, never `world_fact`.

## Implementation

`grimoire/engine/zil/memory/store.py` — `MemoryStore.read_window()`,
`read_archive()`, `read_long_term()`
