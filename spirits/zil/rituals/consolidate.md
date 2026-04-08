# Ritual: consolidate

Runs automatically on session end (quit). Can also be triggered mid-session
via `/consolidate` in chat or `zil consolidate` from the CLI.

## Purpose

Distill today's unprocessed conversation turns into typed memory records and
a compact long-term summary. This is how raw conversation becomes persistent knowledge.

## Idempotency guarantee

A consolidation cursor is stored at `vessel/state/zil/consolidation_cursor.json`:

```json
{
  "last_date": "2026-04-05",
  "last_event_index": 42
}
```

Each run only processes ledger events *after* this cursor position.
After a successful run, the cursor advances to the last processed event.

Running consolidate twice in a row (including on quit after a mid-session run)
produces no new records. The second run finds no unprocessed events and exits cleanly.

## Steps

1. **Read the cursor**
   Load `vessel/state/zil/consolidation_cursor.json`.
   If missing, start from the beginning of today's ledger.

2. **Read unprocessed turns**
   Read `vessel/state/zil/conversations/<today>.jsonl` from `last_event_index` onward.
   Collect only `user_turn` and `assistant_turn` events — skip audits, charges, etc.
   If no new turns exist, exit cleanly with no writes.

3. **Extract typed records via LLM**
   Call the consolidation model (same as `ZIL_MODEL`) with the unprocessed turns.
   Request:
   - `EpistemicMemory` records for claims and positions discussed
   - `RelationalMemory` records for new observations about user preferences
   - `BehavioralObservation` records for notable ZIL behaviors
   - A compact markdown paragraph for `long-term.md` (2–4 sentences)

4. **Validate each record**
   Pass every extracted record through `memory/validators.py`.
   Reject records that fail (contamination, secrets, empty summaries).
   Log validation results to the ledger as `memory_candidate` events.

5. **Write passing records to window memory**
   Append validated records to `spirits/zil/memories/window/recent.jsonl`.
   Charge: `durable_memory_commit` (2 units) per committed record.

6. **Append to long-term memory**
   If the session produced a meaningful long-term entry, append it to
   `spirits/zil/memories/long-term.md`.

7. **Advance the cursor**
   Update `vessel/state/zil/consolidation_cursor.json` to the index of the
   last processed event.

8. **Log completion**
   Append a `memory_commit` event to the ledger summarizing what was written.

## Rules

- Never re-process events before the cursor. Idempotency is non-negotiable.
- User beliefs extracted from conversation must be stored as `truth_status: user_belief`.
- If the LLM call fails, do not advance the cursor. Try again next time.
- If there are no unprocessed turns, report this and exit without writing anything.
- Long-term.md must not grow unboundedly. If it exceeds 4000 words, a separate
  compression ritual should be run (future work — not in scope for v1).

## Implementation

`grimoire/engine/zil/memory/consolidate.py` — `consolidate_session()`
`grimoire/engine/zil/runtime/loop.py` — called on quit and via `/consolidate`
