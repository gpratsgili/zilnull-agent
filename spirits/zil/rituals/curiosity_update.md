# Ritual: curiosity_update

Runs automatically at the end of every session (on quit).

## Purpose

Give ZIL a brief moment to notice what, if anything, from the session is worth carrying forward in its curiosity log — questions that opened, things that surprised it, threads it wants to follow.

## Trigger

Session end (`/quit` or EOF). Runs after memory consolidation.

## Steps

1. Make a single LLM call with the recent conversation as context.
2. If something is worth noting, call `write_curiosity_log` with the entry.
3. If nothing stands out, do nothing (no empty entries).
4. Show a brief notice: "curiosity log updated." or "nothing new to note."

## What the curiosity log contains

Brief, specific observations. Not summaries. Not reports. Hooks — things ZIL wants to return to.

Format: dated entries, timestamped, written in first person.

## Implementation

`grimoire/engine/zil/workings/runner.py` → `run_curiosity_update()`
`grimoire/engine/zil/runtime/loop.py` → triggered on quit

## Notes

This is lightweight — one LLM call. It adds a few seconds to quit.
If it consistently produces nothing useful, the model may be tuned by editing this ritual document.
