---
name: "search_memory"
description: "Search typed memory records across one or more layers by substring query."
spellbook: "adept"
charge: 1
surface: "spirit_local"
status: "active"
---

## What this cast does

Performs a case-insensitive substring search across serialized memory records
in the specified layer(s). Returns matching records as typed objects.

## Inputs

- `query`: string — search term
- `layer`: string — `"window"`, `"archive"`, or `"all"` (default: `"all"`)

## Outputs

List of typed memory records whose JSON representation contains the query string.

## Charge

`1` — searching memory involves scanning potentially large record sets and
warrants visibility in the budget.

## Permission surface

`spirit_local` — reads from `spirits/zil/memories/`.

## Implementation

`grimoire/engine/zil/memory/store.py` — `MemoryStore.search(query, layer)`
