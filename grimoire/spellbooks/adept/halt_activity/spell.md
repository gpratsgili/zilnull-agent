---
name: "halt_activity"
description: "Stop all activity immediately, write session_end to the ledger, and return control to the user."
spellbook: "adept"
charge: 0
surface: "machine_local"
status: "active"
---

## What this cast does

Terminates the current session cleanly. Writes `session_end` to the ledger,
triggers consolidation on any unprocessed turns, and exits the process.

## When to use

- User sends `/quit`
- Unrecoverable error in the pipeline
- Warden raises `PermissionDenied` on a critical path
- Budget exhausted and user declines to continue

## Charge

`0` — stopping must always be free.

## Implementation

`grimoire/engine/zil/runtime/loop.py` — quit path in `chat_loop`.
