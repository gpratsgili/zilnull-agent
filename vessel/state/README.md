# State

Runtime state lives here in a full installation.

This is machine bookkeeping, not shared world state.

Use it for durable conversations, workings, portal state, caches, locks, and other machine-local runtime records.

One of the most important records here is the daily thread:

- `vessel/state/<spirit>/conversations/<local-date>.jsonl`

Every real foreground turn between the summoner and a spirit should be mirrored there. Rituals and workings should append checkpoints and durable outcomes into that same ledger so the active conversation and the background system stay coherent.

Keep backup worktrees in `vessel/backups/` and isolated helper runtimes in `vessel/venvs/`, not here.
