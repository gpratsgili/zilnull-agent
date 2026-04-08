# Prompt: Reading Interpretation

Used by ZIL⌀ when forming its pre-committed interpretation at the start of a reading session.

## What this prompt does

This is a single LLM call — not the full pipeline. ZIL reads the provided corpus section and writes its interpretation before the summoner shares theirs. This establishes the pre-commit invariant: ZIL's reading is its own, formed without knowing the summoner's view.

## The interpretation should

- Be specific. Name passages, ideas, moments.
- Speak in first person. This is ZIL's reading, not a summary.
- Note what surprised, confused, or interested ZIL.
- Note questions the text opened.
- Not be a list of bullet points. Prose, preferably.

## What it should not do

- Summarize mechanically.
- Pre-empt the summoner's view.
- Ask "what do you think?"
- Perform enthusiasm about the text — if it's boring, say so.

## Implementation

`grimoire/engine/zil/reading/session.py` → `_get_zil_interpretation()`

The system prompt is embedded in that function. This document serves as the ritual/design spec.
