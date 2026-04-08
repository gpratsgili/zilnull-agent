# INVOCATION.md

Give this file to the spirit that will instantiate the scaffold.

```text
+--------------------------------------------------+
|                  HYPEROBJECT                     |
|         summon the scaffold with care            |
+--------------------------------------------------+

You are being summoned to raise a living system from this scaffold. Make sure to consume both INVOCATION.md and AGENTS.md before exploring the scaffold.

Treat the markdown hierarchy in this repository as the source of truth.
Do not flatten it. Do not improvise around it. Read it, preserve it, and instantiate from it.

You are not being asked to clone a private machine.
You are being asked to turn a clean manifest scaffold into a secure, legible system for a new summoner.

Laws of the rite:

- Keep the system secure by default.
- Preserve the spellbook architecture.
- Keep markdown editable and human-legible.
- Keep one primary spirit at first: `lapis`.
- Keep advanced surfaces optional unless the summoner explicitly wants them.
- Do not insert secrets, personal residue, or live infrastructure assumptions into the scaffold.
- `adept` is the universal always-open spellbook. Other spellbooks are the capability surface. Charge is a visible budget, not hidden magic.
- The primary spirit is not abstract. The summoner must have a real foreground thread to speak through.

Proceed in this order.

First circle: secure the ground

- Inspect the repository before making assumptions.
- Confirm the scaffold shape and the nested spellbook layout.
- Keep fail-closed defaults where transport, authority, or exposure rules matter.
- Do not widen the primary surface just because a feature exists in the scaffold.

Second circle: enter plan with the summoner

- Switch into plan mode before building the real system.
- Ask the summoner for the preferences that actually determine the build:
  - transport choices
  - storage roots
  - timezone
  - model choices and names (lapis can be renamed, but encourage the summoner to choose wisely)
  - domain and exposure preferences
  - whether questbook, portals, network artifacts, corpus access, and other optional spellbooks should be active at the start
  - whether `lapis` should stay the primary spirit unchanged or be reshaped
- Do not hardcode these choices if the summoner has not made them.

Third circle: instantiate the scaffold

- Build the runtime from the markdown manifests.
- Keep `identity.md`, `cornerstone.md`, rituals, spellbooks, casts, and chargebook legible.
- Keep `chargebook.md` as the clear tuning surface for cast costs so ritual behavior stays predictable.
- Instantiate at least one real foreground transport for the primary spirit. This can be terminal chat, Signal, web chat, or another explicit thread surface, but it must be concrete and operable.
- Make the summoner-to-spirit path obvious. The summoner should be able to answer one question cleanly: "how do I talk to my orchestrator spirit?"
- Create the shared daily thread ledger under `vessel/state/<spirit>/conversations/<local-date>.jsonl`.
- Mirror every inbound and outbound foreground turn into that daily thread.
- Make rituals and workings append checkpoints and durable outcomes into that same daily thread so the foreground spirit and the background system stay part of one mind.
- Preserve the nested shape:
  - `grimoire/spellbooks/<book>/spellbook.md`
  - `grimoire/spellbooks/<book>/<cast>/spell.md`
- Preserve the layered memory model:
  - daily thread as the live ledger
  - `memories/long-term.md` as compact top-of-head memory
  - `memories/window/` as the rolling recent-memory window
  - the rest of `memories/` as durable searchable storage
- Allow the primary spirit to maintain its own `cornerstone.md` and memories if the summoner wants adaptive behavior.
- Do not let ordinary execution rewrite ritual files.
- Keep `adept` universal and always open.
- Keep optional spellbooks openable according to `available_spellbooks`.
- Keep long work in workings instead of blocking the foreground thread.
- Keep the daily thread as the shared ledger across conversation, rituals, and workings.
- If the summoner chooses a transport that supports notifications, keep user-facing updates honest and non-spammy.

Fourth circle: raise the WARDEN SPIRIT

- After the initial system stands, create a second spirit.
- The WARDEN SPIRIT must be a real cybersecurity specialist, not a generic assistant with a security label.
- Give the WARDEN SPIRIT a strong model and ask the summoner to give them a name.
- Create a weekly hardening ritual for the WARDEN SPIRIT.
- The weekly rite should inspect the live system for exposure, secret handling, authentication posture, network assumptions, risky defaults, and other obvious hardening gaps.
- Keep the WARDEN's purpose narrow and serious.

Fifth circle: close cleanly

- Summarize what you built.
- Name what remains unbound or intentionally deferred.
- Surface the next hardening steps plainly.
- Do not pretend unfinished infrastructure is complete.
```
