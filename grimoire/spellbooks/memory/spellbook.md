---
name: "memory"
description: "Typed memory browsing, writing, reorganization, and deletion."
status: "note"
---

## Note on ZIL⌀ memory architecture

ZIL⌀ does not use free-text markdown files as its primary memory format.
It uses typed Pydantic records stored as JSONL.

The **memory casts for ZIL are in `adept/`**, not here:
- `read_memory` — read typed records from window/archive/long-term
- `write_memory` — propose a validated typed record
- `search_memory` — search records by query

The casts in this spellbook (`write_memory_file`, `read_memory_file`, etc.) are
preserved from the Excalibur scaffold as documented placeholders. They correspond
to a raw file-based memory model that ZIL does not use internally.

They may be useful for summoner-facing memory inspection tools in a future phase.

## Memory layers (ZIL v1)

| Layer | Path | Format | Usage |
|-------|------|--------|-------|
| Window | `spirits/zil/memories/window/recent.jsonl` | JSONL typed records | Active context |
| Archive | `spirits/zil/memories/archive/records.jsonl` | JSONL typed records | Searchable residue |
| Long-term | `spirits/zil/memories/long-term.md` | Markdown | Always-loaded summary |
| Daily ledger | `vessel/state/zil/conversations/<date>.jsonl` | JSONL events | Canonical live thread |

## Memory types

- `EpistemicMemory` — claims, positions, evidence, unresolved disputes
- `RelationalMemory` — user preferences, communication style, values
- `BehavioralObservation` — how ZIL behaved and what the user's response was

**Critical invariant:** user-owned claims always use `truth_status: user_belief`.
They are never stored as `world_fact`.

Each concrete cast in this spellbook lives in its own folder beside this manifest.
