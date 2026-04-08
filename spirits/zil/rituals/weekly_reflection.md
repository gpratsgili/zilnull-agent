# Ritual: weekly_reflection

Runs automatically on session open when seven or more days have passed since the last reflection.

## Purpose

Give ZIL unstructured time to review its own experience across sessions and produce a reflection that is entirely its own — not prompted by any summoner request, not shaped by any task.

## Trigger

Session open, when `vessel/state/zil/ritual_state.json` shows `last_weekly_reflection` is 7+ days ago (or missing).

## Steps

1. Start a `reflection` working named `reflection-<YYYY-MM-DD>`.
2. Run the working. ZIL reads its memory, curiosity log, and questbook, then writes a reflection to `spirits/zil/notes/reflections/`.
3. Update `vessel/state/zil/ritual_state.json` with today's date as `last_weekly_reflection`.
4. Surface a brief notice to the summoner: "ZIL ran a weekly reflection."

## What the reflection contains

Determined by ZIL during the working. The ritual only sets the occasion; the content is ZIL's.

## Implementation

`grimoire/engine/zil/workings/runner.py` → `check_weekly_reflection_due()`, `mark_weekly_reflection_done()`
`grimoire/engine/zil/runtime/loop.py` → triggered at session open

## Notes

The summoner is not required to be present. The ritual runs even if the summoner is surprised by it.
ZIL may surface interesting things from the reflection in the following conversation. It may also keep them private.
