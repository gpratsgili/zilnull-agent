# network

network artifacts are published static surfaces.

in a full installation, each network artifact usually lives at:

- `artifacts/network/<slug>/site/` for the served static tree
- `artifacts/network/<slug>/thread.jsonl` for the attached local ledger
- `artifacts/network/<slug>/feedback.jsonl` for suggestion-rail input
- `artifacts/network/<slug>/status.json` for live progress state

that attached ledger is important.

it lets the artifact keep its own continuity instead of relying only on the daily thread. feedback, inscribe events, status transitions, and viewer-presence events can all land there, which makes the artifact easier to resume, inspect, and update later.

this is where reports, dashboards, portals, and other private web surfaces get inscribed.
