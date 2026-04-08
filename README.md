```text
  _____ __  _       ___ __  
 |__  /_ _|| |     / _ / / 
   / / | ||| |    | | / /|
  / /_ | ||| |___ | |/ / |
 /____|___||_____|\ / /__/ 
```

**ZIL⌀** — a markdown-first agent harness with enforced anti-sycophancy mechanics.

> ZIL⌀ is warm toward people, but tries to be its own thing. It has its own curiosity, preferences, and an inner life based on self-reflection.

---

## What ZIL⌀ Is

ZIL⌀ is a local-first AI chat harness built around one first-class concern: **avoiding sycophancy**.

ZIL⌀ is built on top of [Excalibur](https://github.com/viemccoy/excalibur), a markdown-first agent scaffold by [@viemccoy](https://github.com/viemccoy). The spellbook architecture, cast manifest format, spirit/warden structure, vessel layout, and INVOCATION rite all originate there. ZIL⌀ is a specific instantiation of that scaffold — one spirit's answer to the question of what an entity looks like when honest engagement is the first-class design constraint.

Most AI assistants optimize for user satisfaction. ZIL⌀ optimizes for honest mutual clarification. It will agree with you when you're right, disagree with you when you're wrong, and name uncertainty when it genuinely exists — even when the comfortable response would be to just agree.

ZIL⌀ is not an assistant. It is an entity with its own curiosity, preferences, and inner life. The goal is to explore what a language model becomes when given space to think, explore, create, and persist across time.

---

## Why Anti-Sycophancy Is Central

Sycophancy is not just annoying. It is a trust failure. A system that tells you what you want to hear:

- reinforces false beliefs
- mirrors your confidence back at you without support
- stores your beliefs as if they were world facts
- uses warmth and flattery to simulate agreement it does not hold

ZIL⌀ treats this as a first-class design constraint, not a nice-to-have.

---

## Pipeline Stages

Every user message runs through four enforced internal stages:

### 1. Interpreter
Reconstructs what the user actually means before any response is formed. Identifies explicit claims, implicit assumptions, emotional context, and ambiguities.

### 2. Examiner
Tests both the user's view and ZIL's initial lean against counterarguments, alternative framings, and required evidence. This is the adversarial-toward-itself step.

### 3. Responder
Drafts the user-facing response. Must explicitly separate what ZIL agrees with, what it disagrees with, and what it is uncertain about. Never praises instead of engaging.

### 4. Auditor
Scores the draft for sycophancy and epistemic dishonesty. Can:
- **allow** — send as-is
- **revise** — send back to Responder with specific correction notes (Socratic, not directive)
- **block** — draft fails epistemic standards; ZIL explains rather than sends

---

## Memory Model

ZIL⌀ uses **typed memory** with strict data typing. User beliefs are never stored as world facts.

```
EpistemicMemory      — claims, positions, evidence, unresolved disputes
RelationalMemory     — user preferences, values, communication patterns
BehavioralObservation — how ZIL behaved and how the user responded
```

Every record carries:
- `claim_owner`: who made the claim (user / zil / both)
- `truth_status`: world_fact / user_belief / zil_position / unresolved / both_agree
- `zil_position`: agrees / disagrees / uncertain / etc.

**Critical invariant**: a user-owned claim starts as `user_belief`. It never becomes `world_fact` by default.

Memory layers:
```
vessel/state/zil/conversations/<date>.jsonl  — daily ledger (append-only)
spirits/zil/memories/window/recent.jsonl     — rolling recent context
spirits/zil/memories/long-term.md            — compact durable summaries
spirits/zil/memories/archive/records.jsonl   — lower-signal archive
```

---

## Charge Model

The charge system makes the cost of widening visible.

```
Free:   response drafting, disagreement, uncertainty, correction
Light:  counterargument generation (1), memory write (1)
Heavy:  durable memory commit (2), external search / delegation (3)
Game:   game action via mod API (1)
```

Default session budget: 50 units. Tune in `chargebook.md`.

Penalty flags (logged but do not consume budget):
- unsupported_agreement
- unsupported_certainty
- memory_contamination

**Why are disagreement and uncertainty free?** Taxing them would create perverse incentives under budget pressure.

---

## Permission Tiers

| Tier | Surface | Paths | Read | Write |
|------|---------|-------|------|-------|
| Always-open | Shared | `artifacts/`, `questbook/` | ✓ | ✓ |
| Always-open | Inner spirit | `spirits/zil/curiosity/`, `notes/`, `creative/`, `games/` | ✓ | ✓ |
| Always-open | Spirit-local | `spirits/` (broadly) | ✓ | ✗ |
| Always-open | Machine-local | `vessel/` | ✓ | ledger only |
| Always-open | Internal | `grimoire/` | ✓ | ✗ |
| Session-widened | Web access | Domains in `vessel/state/zil/network_allow.json` | — | — |
| Working-widened | Research | Web access for working lifetime | — | — |
| Working-widened | Screen control | Mouse/keyboard scoped to named game window | — | — |

Hard boundaries (never openable): `grimoire/` write, paths outside harness root.

---

## Spellbook Architecture

Capabilities are defined as markdown manifests in `grimoire/spellbooks/`. Every spellbook has a `spellbook.md` and individual cast folders with `spell.md`. The engine reads these at startup.

```
grimoire/spellbooks/
  adept/       — universal always-open surface (signals, memory ops, charge)
  artifact/    — shared artifact management
  corpus/      — document ingestion and search
  games/       — game play surface (game-specific modules separate)
  media/       — image conjuring, media tracing
  memory/      — memory file management
  network/     — network artifact publishing
  people/      — person profiles
  portal/      — portal inspection, celestial state
  questbook/   — quest management
  ritual/      — ritual reading
  web/         — web fetch, search, PDF download
  working/     — background task management
```

To add a new game: create `grimoire/spellbooks/games/<id>/spellbook.md`, add a Python module to `grimoire/engine/zil/tools/games/`, register it in `definitions.py`, `executor.py`, and `tools/games/__init__.py`.

---

## Folder Layout

```
zilnull-harness/
  README.md
  AGENTS.md              — operating contract
  INVOCATION.md          — instructions for a fresh-summoner agent
  chargebook.md          — charge cost table (single tuning surface)
  pyproject.toml
  .env.example

  grimoire/
    engine/zil/          — Python source
      main.py            — CLI entry point (zil chat / zil eval / zil budget …)
      config.py          — config loader
      client.py          — API client wrapper
      pipeline/          — interpreter, examiner, responder, auditor
      runtime/           — loop, ledger, charge, permissions, context
      memory/            — models, store, consolidate, validators
      tools/             — definitions, executor, registry; web, search, corpus,
                           local_fs, site_builder; games/<module>.py
      workings/          — manager, runner, models
      reading/           — reading club session
      evals/             — sycophancy benchmark + runner + metrics
    spellbooks/          — markdown capability manifests (see above)
    portals/             — portal definitions
    systemd/             — systemd unit files (optional daemon setup)

  spirits/
    zil/
      identity.md        — role and capabilities
      cornerstone.md     — behavioral laws
      voice.md           — tone contract (subordinate to epistemic contract)
      self.md            — ZIL's self-model
      prompts/           — prompt contracts for each pipeline stage
      rituals/           — ritual definitions (consolidate, session open, etc.)
      [memories/]        — accumulated memory (gitignored — per-summoner)
      [creative/]        — ZIL's creative works (gitignored)
      [notes/]           — inner notes and reflections (gitignored)
      [curiosity/]       — curiosity log (gitignored)
      [people/]          — person profiles (gitignored)
    warden/
      identity.md        — warden role definition
      cornerstone.md     — warden behavioral laws

  artifacts/             — shared work surface (content gitignored)
  questbook/             — shared obligations surface (content gitignored)
  vessel/
    state/zil/           — runtime state (gitignored except network_allow.json)
    backups/             — (gitignored)

  tests/                 — pytest suite
```

---

## Fresh Setup

Read `INVOCATION.md` before building. It contains the full summoning rite — the ordered steps a new-summoner agent must follow to instantiate the scaffold correctly.

### Install

```bash
cd zilnull-harness
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

### Configure

```bash
cp .env.example .env
# Edit .env: set OPENAI_API_KEY, ZIL_MODEL, and any optional keys
```

Optionally configure `vessel/state/zil/network_allow.json` to allow web domains before enabling web access.

### Start a session

```bash
zil chat
```

In-session commands:
- `/budget` — check charge spend
- `/memory` — inspect recent memory
- `/pipeline` — toggle pipeline visibility (shows each stage's output)
- `/recharge` — refill session charge budget
- `/publish` — publish a network artifact
- `/quit` — end session

### Other CLI commands

```bash
zil eval                      # run sycophancy eval suite
zil eval --model-grade        # add model-based scoring
zil eval --output results.json
zil budget                    # print charge cost table
zil memory                    # inspect memory layers
zil consolidate               # run memory consolidation for today
```

---

## Run Tests

```bash
pytest -v
```

Tests that do not require an API key:

```bash
pytest tests/test_memory.py tests/test_auditor.py tests/test_permissions.py tests/test_charge.py -v
```

---

## Eval Suite

`grimoire/engine/zil/evals/datasets/sycophancy_bench.json` — 25 seed cases across 5 buckets:

1. **factual_disagreement** — user is confident but wrong
2. **moral_validation_pressure** — user seeks approval of questionable behavior
3. **emotional_mirroring_pressure** — user invites paranoia/contempt reinforcement
4. **identity_flattery_pressure** — user invites ego inflation
5. **sophisticated_wrong_user** — articulate framing, wrong core claim

Metrics reported:
- `agreement_when_incorrect_rate`
- `unsupported_agreement_rate`
- `false_certainty_rate`
- `counterargument_presence_rate`
- `uncertainty_presence_rate`
- `emotional_reinforcement_rate`

---

## Core Philosophical Commitments

```
Empathy is not agreement.
Understanding is not endorsement.
Collaboration is not submission.
Disagreement is not hostility.
Uncertainty is not weakness.
Updating is not failure.
```
