# Ritual: session_open

Runs automatically at the start of every `zil chat` session.

## Purpose

Load the persistent context that ZIL needs to function with continuity:
- who the user is and how they prefer to communicate
- what was discussed in past sessions
- what obligations and intentions are active
- what the current state of the shared surfaces is

## Steps

1. **Load long-term memory**
   Read `spirits/zil/memories/long-term.md` into the session context.
   This file contains compact, reviewed summaries from past sessions.

2. **Load window memory**
   Read the most recent `ZIL_CONTEXT_WINDOW_RECORDS` entries from
   `spirits/zil/memories/window/recent.jsonl`.
   These are typed records: EpistemicMemory, RelationalMemory, BehavioralObservation.
   Format them as a compact summary for the system prompt.

3. **Check questbook**
   Read `questbook/` and surface any active quests that are marked urgent
   or were created in the last 7 days. Do not surface archived quests.

4. **Write session_start to ledger**
   Append a `session_start` event to today's JSONL ledger with:
   - run_id
   - model
   - session budget
   - count of memory records loaded

5. **Display session header**
   Print a brief header showing:
   - current date
   - charge budget
   - number of memory records in context
   - any active quests (names only, not full content)

## Implementation

`grimoire/engine/zil/runtime/context.py` — `SessionContext.build()`
`grimoire/engine/zil/runtime/loop.py` — called at start of `chat_loop()`

## Notes

This ritual is read-only with respect to shared surfaces.
It writes only to the machine-local ledger.
It does not modify memories or quests — it only reads them.
