"""Tool call executor.

Routes OpenAI function-call names to the correct handler, validates paths,
logs tool_call + tool_result events to the ledger, and charges appropriately.

All errors are caught and returned as error-prefixed strings so ZIL can
reason about failures rather than crashing out of a turn.
"""

from __future__ import annotations

import json
from pathlib import Path

from zil.config import get_config
from zil.memory.store import MemoryStore
from zil.runtime import ledger as ledger_mod
from zil.runtime.charge import ChargeTracker
from zil.runtime.permissions import PermissionDenied


_TOOL_CHARGE_OPS: dict[str, str] = {
    # Artifact tools
    "create_artifact": "local_state_inspection",
    "read_artifact": "local_state_inspection",
    "edit_artifact": "local_state_inspection",
    "list_artifacts": "local_state_inspection",
    "search_artifacts": "evidence_lookup",
    # Questbook tools
    "write_quest": "local_state_inspection",
    "read_quest": "local_state_inspection",
    "list_questbook": "local_state_inspection",
    # Memory tools
    "search_memory": "evidence_lookup",
    "list_memory_files": "local_state_inspection",
    "read_memory_file": "local_state_inspection",
    # Ritual tools
    "list_rituals": "local_state_inspection",
    "read_ritual": "local_state_inspection",
    # Web tools — expensive (external acquisition)
    "web_search": "external_acquisition_search_burst",
    "fetch_page": "external_acquisition_search_burst",
    "download_pdf": "external_acquisition_search_burst",
    "trace_links": "external_acquisition_search_burst",
    "enshrine_snapshot": "external_acquisition_search_burst",
    # Corpus tools — local, free
    "ingest_corpus_file": "local_state_inspection",
    "list_corpus_files": "local_state_inspection",
    "search_corpus": "evidence_lookup",
    "read_corpus_file": "local_state_inspection",
    # Inner surface tools — always-open, free
    "write_curiosity_log": "local_state_inspection",
    "read_curiosity_log": "local_state_inspection",
    "write_inner_note": "local_state_inspection",
    "read_inner_note": "local_state_inspection",
    "list_inner_notes": "local_state_inspection",
    # ZIL questbook tools — always-open, free
    "write_zil_quest": "local_state_inspection",
    "read_zil_quest": "local_state_inspection",
    "list_zil_questbook": "local_state_inspection",
    # Reading club tools — always-open, free
    "write_reading_interpretation": "local_state_inspection",
    "read_reading_interpretation": "local_state_inspection",
    "annotate_reading": "local_state_inspection",
    # Creative surface tools — always-open, free
    "write_creative_work": "local_state_inspection",
    "read_creative_work": "local_state_inspection",
    "list_creative_works": "local_state_inspection",
    "update_creative_index": "local_state_inspection",
    "read_creative_index": "local_state_inspection",
    # Self document — always-open, free
    "read_self": "local_state_inspection",
    "write_self": "local_state_inspection",
    # Cornerstone proposal tools — always-open, free
    "propose_cornerstone_update": "local_state_inspection",
    "list_cornerstone_proposals": "local_state_inspection",
    # Entity memory tools — always-open, free
    "write_curiosity_record": "local_state_inspection",
    "write_position_record": "local_state_inspection",
    "write_change_record": "local_state_inspection",
    # Network publishing — always-open, free
    "publish_network_page": "local_state_inspection",
    # Self-inspection tools — always-open, free
    "inspect_state": "local_state_inspection",
    "read_typed_memory": "local_state_inspection",
    "read_session_log": "local_state_inspection",
    # Ritual proposals — always-open, free
    "propose_ritual": "local_state_inspection",
    # Game memory — inner spirit reads/writes, free
    "read_game_strategy": "local_state_inspection",
    "write_game_strategy": "local_state_inspection",
    "write_run_postmortem": "local_state_inspection",
    "list_run_postmortems": "local_state_inspection",
    "read_run_postmortem": "local_state_inspection",
    # People memory — inner spirit reads/writes, free
    "list_people": "local_state_inspection",
    "read_person_profile": "local_state_inspection",
    "write_person_profile": "local_state_inspection",
    "list_person_projects": "local_state_inspection",
    "read_person_project": "local_state_inspection",
    "write_person_project": "local_state_inspection",
    # Game integration — local HTTP calls to a running game mod
    "list_supported_games": "local_state_inspection",
    "sts2_get_state": "game_action",
    "sts2_play_card": "game_action",
    "sts2_end_turn": "game_action",
    "sts2_use_potion": "game_action",
    "sts2_choose_card_reward": "game_action",
    "sts2_skip_card_reward": "game_action",
    "sts2_choose_map_node": "game_action",
    "sts2_choose_rest_option": "game_action",
    "sts2_choose_event_option": "game_action",
    "sts2_shop_purchase": "game_action",
    "sts2_proceed": "game_action",
    "sts2_select_card": "game_action",
    "sts2_confirm_selection": "game_action",
}


class ToolExecutor:
    """Executes tool calls from the Responder's tool loop.

    Created once per session. Each call logs to the ledger and charges
    via the session's ChargeTracker.
    """

    def __init__(self, store: MemoryStore, charge: ChargeTracker, run_id: str) -> None:
        self._store = store
        self._charge = charge
        self._run_id = run_id
        self._cfg = get_config()

    def execute(self, tool_name: str, arguments: dict) -> str:
        """Execute a named tool call and return a result string.

        Never raises — errors are returned as "[error] ..." strings so the
        model can read and reason about them.
        """
        # Log the call before executing
        ledger_mod.append_event(
            "tool_call",
            {"tool": tool_name, "arguments": arguments},
            run_id=self._run_id,
        )

        # Charge before executing
        op = _TOOL_CHARGE_OPS.get(tool_name, "local_state_inspection")
        try:
            self._charge.charge(op, note=f"tool: {tool_name}")
        except Exception as e:
            result = f"[error] budget exceeded — cannot execute {tool_name}: {e}"
            ledger_mod.append_event(
                "tool_result",
                {"tool": tool_name, "result": result, "ok": False},
                run_id=self._run_id,
            )
            return result

        # Dispatch
        try:
            result = self._dispatch(tool_name, arguments)
            ok = True
        except (PermissionDenied, FileNotFoundError, NotADirectoryError, ValueError) as e:
            result = f"[error] {e}"
            ok = False
        except Exception as e:
            result = f"[error] unexpected failure in {tool_name}: {e}"
            ok = False

        ledger_mod.append_event(
            "tool_result",
            {"tool": tool_name, "result": result[:500], "ok": ok},
            run_id=self._run_id,
        )
        return result

    # ── Dispatch ──────────────────────────────────────────────────────────

    def _dispatch(self, tool_name: str, args: dict) -> str:
        match tool_name:
            case "create_artifact":
                return self._create_artifact(args["path"], args["content"])
            case "read_artifact":
                return self._read_artifact(args["path"])
            case "edit_artifact":
                return self._edit_artifact(args["path"], args["content"])
            case "list_artifacts":
                return self._list_artifacts(args.get("directory", ""))
            case "search_artifacts":
                return self._search_artifacts(args["query"])
            case "write_quest":
                return self._write_quest(args["name"], args["content"])
            case "read_quest":
                return self._read_quest(args["name"])
            case "list_questbook":
                return self._list_questbook()
            case "search_memory":
                return self._search_memory(args["query"])
            case "list_memory_files":
                return self._list_memory_files()
            case "read_memory_file":
                return self._read_memory_file(args["layer"])
            case "list_rituals":
                return self._list_rituals()
            case "read_ritual":
                return self._read_ritual(args["name"])
            # Web tools
            case "web_search":
                return self._web_search(args["query"], args.get("num_results", 5))
            case "fetch_page":
                return self._fetch_page(args["url"])
            case "download_pdf":
                return self._download_pdf(args["url"], args["path"])
            case "trace_links":
                return self._trace_links(args["url"])
            case "enshrine_snapshot":
                return self._enshrine_snapshot(args["url"], args.get("path", ""))
            # Corpus tools
            case "ingest_corpus_file":
                return self._ingest_corpus_file(args["path"])
            case "list_corpus_files":
                return self._list_corpus_files()
            case "search_corpus":
                return self._search_corpus(args["query"])
            case "read_corpus_file":
                return self._read_corpus_file(
                    args["name"], args.get("offset", 0), args.get("limit", 4000)
                )
            # Inner surface tools
            case "write_curiosity_log":
                return self._write_curiosity_log(args["entry"])
            case "read_curiosity_log":
                return self._read_curiosity_log()
            case "write_inner_note":
                return self._write_inner_note(args["path"], args["content"])
            case "read_inner_note":
                return self._read_inner_note(args["path"])
            case "list_inner_notes":
                return self._list_inner_notes(args.get("subdir", ""))
            # ZIL questbook tools
            case "write_zil_quest":
                return self._write_zil_quest(args["name"], args["content"])
            case "read_zil_quest":
                return self._read_zil_quest(args["name"])
            case "list_zil_questbook":
                return self._list_zil_questbook()
            # Reading club tools
            case "write_reading_interpretation":
                return self._write_reading_interpretation(
                    args["file"], args["section"], args["content"]
                )
            case "read_reading_interpretation":
                return self._read_reading_interpretation(args["file"], args["section"])
            case "annotate_reading":
                return self._annotate_reading(
                    args["file"], args["section"], args["passage"], args["note"]
                )
            # Creative surface tools
            case "write_creative_work":
                return self._write_creative_work(args["name"], args["content"], args["location"])
            case "read_creative_work":
                return self._read_creative_work(args["name"], args["location"])
            case "list_creative_works":
                return self._list_creative_works()
            case "update_creative_index":
                return self._update_creative_index(args["content"])
            case "read_creative_index":
                return self._read_creative_index()
            # Self document
            case "read_self":
                return self._read_self()
            case "write_self":
                return self._write_self(args["content"])
            # Cornerstone proposal tools
            case "propose_cornerstone_update":
                return self._propose_cornerstone_update(
                    args["section"], args["proposed_text"], args["reasoning"]
                )
            case "list_cornerstone_proposals":
                return self._list_cornerstone_proposals()
            # Entity memory tools
            case "write_curiosity_record":
                return self._write_curiosity_record(
                    args["topic"], args["question"], args["origin"], args["notes"]
                )
            case "write_position_record":
                return self._write_position_record(
                    args["topic"], args["statement"], args["reasoning"], args["confidence"]
                )
            case "write_change_record":
                return self._write_change_record(
                    args["position_id"], args["topic"],
                    args["previous_statement"], args["new_statement"],
                    args["reason"], args["trigger"],
                )
            # Network publishing
            case "publish_network_page":
                return self._publish_network_page(
                    args["title"], args["content"], args["section"], args["author"]
                )
            # Ritual proposals
            case "propose_ritual":
                return self._propose_ritual(
                    args["name"], args["description"], args["frequency"], args["reasoning"]
                )
            # Game memory
            case "read_game_strategy":
                return self._read_game_strategy(args["game_id"])
            case "write_game_strategy":
                return self._write_game_strategy(args["game_id"], args["content"])
            case "write_run_postmortem":
                return self._write_run_postmortem(args["game_id"], args["content"])
            case "list_run_postmortems":
                return self._list_run_postmortems(args["game_id"])
            case "read_run_postmortem":
                return self._read_run_postmortem(args["game_id"], args["name"])
            # People memory
            case "list_people":
                return self._list_people()
            case "read_person_profile":
                return self._read_person_profile(args["name"])
            case "write_person_profile":
                return self._write_person_profile(args["name"], args["content"])
            case "list_person_projects":
                return self._list_person_projects(args["name"])
            case "read_person_project":
                return self._read_person_project(args["name"], args["project"])
            case "write_person_project":
                return self._write_person_project(args["name"], args["project"], args["content"])
            # Game integration
            case "list_supported_games":
                return self._list_supported_games()
            case "sts2_get_state":
                return self._sts2_get_state()
            case "sts2_play_card":
                return self._sts2_play_card(args["card_index"], args.get("target_index"))
            case "sts2_end_turn":
                return self._sts2_end_turn()
            case "sts2_use_potion":
                return self._sts2_use_potion(args["potion_index"], args.get("target_index"))
            case "sts2_choose_card_reward":
                return self._sts2_choose_card_reward(args["card_index"])
            case "sts2_skip_card_reward":
                return self._sts2_skip_card_reward()
            case "sts2_choose_map_node":
                return self._sts2_choose_map_node(args["node_index"])
            case "sts2_choose_rest_option":
                return self._sts2_choose_rest_option(args["option"])
            case "sts2_choose_event_option":
                return self._sts2_choose_event_option(args["option_index"])
            case "sts2_shop_purchase":
                return self._sts2_shop_purchase(args["item_index"])
            case "sts2_proceed":
                return self._sts2_proceed()
            case "sts2_select_card":
                return self._sts2_select_card(args["card_index"])
            case "sts2_confirm_selection":
                return self._sts2_confirm_selection()
            # Self-inspection tools
            case "inspect_state":
                return self._inspect_state()
            case "read_typed_memory":
                return self._read_typed_memory(args["layer"], args["kind"])
            case "read_session_log":
                return self._read_session_log(args.get("run_id_prefix", ""))
            case _:
                raise ValueError(f"Unknown tool: {tool_name!r}")

    # ── Artifact handlers ─────────────────────────────────────────────────

    def _resolve_artifact(self, path: str) -> Path:
        """Resolve a relative artifact path. Blocks traversal."""
        # Normalise: strip any leading artifacts/ prefix the model might include
        p = path.lstrip("/")
        if p.startswith("artifacts/"):
            p = p[len("artifacts/"):]

        resolved = (self._cfg.artifacts_dir / p).resolve()

        # Guard traversal
        try:
            resolved.relative_to(self._cfg.artifacts_dir.resolve())
        except ValueError:
            raise PermissionDenied(
                f"Path {path!r} escapes artifacts/. Traversal blocked."
            )
        return resolved

    def _resolve_questbook(self, name: str) -> Path:
        """Resolve a questbook entry path. Blocks traversal."""
        # Strip any .md suffix — we add it ourselves
        name = name.rstrip("/").replace("/", "-")
        if not name.endswith(".md"):
            name = name + ".md"

        resolved = (self._cfg.questbook_dir / name).resolve()
        try:
            resolved.relative_to(self._cfg.questbook_dir.resolve())
        except ValueError:
            raise PermissionDenied(
                f"Quest name {name!r} escapes questbook/. Blocked."
            )
        return resolved

    def _create_artifact(self, path: str, content: str) -> str:
        from zil.runtime.permissions import Warden, Permission
        warden = Warden()
        resolved = self._resolve_artifact(path)
        if resolved.exists():
            return (
                f"[error] Artifact already exists: artifacts/{path}. "
                "Use edit_artifact to overwrite it."
            )
        warnings = warden.inspect_for_secrets(content)
        if warnings:
            raise PermissionDenied(
                f"Refusing to write: possible secrets detected — {warnings}"
            )
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")
        rel = resolved.relative_to(self._cfg.artifacts_dir.resolve())
        return f"Created: artifacts/{rel}"

    def _read_artifact(self, path: str) -> str:
        resolved = self._resolve_artifact(path)
        if not resolved.exists():
            return f"[error] Artifact not found: artifacts/{path}"
        return resolved.read_text(encoding="utf-8")

    def _edit_artifact(self, path: str, content: str) -> str:
        from zil.runtime.permissions import Warden, Permission
        warden = Warden()
        resolved = self._resolve_artifact(path)
        warnings = warden.inspect_for_secrets(content)
        if warnings:
            raise PermissionDenied(
                f"Refusing to write: possible secrets detected — {warnings}"
            )
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")
        rel = resolved.relative_to(self._cfg.artifacts_dir.resolve())
        return f"Updated: artifacts/{rel}"

    def _list_artifacts(self, directory: str) -> str:
        base = self._cfg.artifacts_dir
        if directory:
            base = self._resolve_artifact(directory)
            if not base.is_dir():
                return f"[error] Not a directory: artifacts/{directory}"
        if not base.exists():
            return "(no artifacts)"
        items = sorted(base.iterdir())
        if not items:
            return "(empty)"
        lines = []
        for item in items:
            rel = item.relative_to(self._cfg.artifacts_dir)
            lines.append(f"{'[dir] ' if item.is_dir() else ''}{rel}")
        return "\n".join(lines)

    def _search_artifacts(self, query: str) -> str:
        base = self._cfg.artifacts_dir
        if not base.exists():
            return "(no artifacts)"
        q = query.lower()
        matches = []
        for fpath in sorted(base.rglob("*")):
            if not fpath.is_file():
                continue
            try:
                text = fpath.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if q in text.lower():
                rel = fpath.relative_to(base)
                # Find excerpt around the match
                idx = text.lower().find(q)
                start = max(0, idx - 40)
                end = min(len(text), idx + len(query) + 40)
                excerpt = text[start:end].replace("\n", " ").strip()
                matches.append(f"artifacts/{rel}: ...{excerpt}...")
        if not matches:
            return f"(no matches for {query!r})"
        return "\n".join(matches[:20])  # cap at 20 results

    # ── Questbook handlers ────────────────────────────────────────────────

    def _write_quest(self, name: str, content: str) -> str:
        from zil.runtime.permissions import Warden
        warden = Warden()
        warnings = warden.inspect_for_secrets(content)
        if warnings:
            raise PermissionDenied(
                f"Refusing to write quest: possible secrets detected — {warnings}"
            )
        resolved = self._resolve_questbook(name)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")
        return f"Quest written: questbook/{resolved.name}"

    def _read_quest(self, name: str) -> str:
        resolved = self._resolve_questbook(name)
        if not resolved.exists():
            return f"[error] Quest not found: questbook/{name}.md"
        return resolved.read_text(encoding="utf-8")

    def _list_questbook(self) -> str:
        base = self._cfg.questbook_dir
        if not base.exists():
            return "(questbook is empty)"
        items = sorted(base.rglob("*.md"))
        if not items:
            return "(no quests)"
        lines = [str(p.relative_to(base)) for p in items]
        return "\n".join(lines)

    # ── Memory handlers ───────────────────────────────────────────────────

    def _search_memory(self, query: str) -> str:
        results = self._store.search(query)
        if not results:
            return f"(no memory records matching {query!r})"
        lines = []
        for r in results[:15]:
            lines.append(r.model_dump_json())
        return "\n".join(lines)

    def _list_memory_files(self) -> str:
        memories_dir = self._cfg.memories_dir
        window_jsonl = memories_dir / "window" / "recent.jsonl"
        archive_jsonl = memories_dir / "archive" / "records.jsonl"
        long_term = memories_dir / "long-term.md"

        def _count_lines(path: Path) -> int:
            if not path.exists():
                return 0
            try:
                return sum(1 for line in path.read_bytes().splitlines() if line.strip())
            except OSError:
                return 0

        window_count = _count_lines(window_jsonl)
        archive_count = _count_lines(archive_jsonl)
        lt_size = long_term.stat().st_size if long_term.exists() else 0

        lines = [
            "Memory layers:",
            f"  long-term    spirits/zil/memories/long-term.md  ({lt_size} bytes)",
            f"  window       spirits/zil/memories/window/recent.jsonl  ({window_count} records)",
            f"  archive      spirits/zil/memories/archive/records.jsonl  ({archive_count} records)",
        ]
        return "\n".join(lines)

    def _read_memory_file(self, layer: str) -> str:
        memories_dir = self._cfg.memories_dir
        if layer == "long-term":
            path = memories_dir / "long-term.md"
            if not path.exists():
                return "(long-term memory is empty)"
            return path.read_text(encoding="utf-8")
        elif layer == "window":
            path = memories_dir / "window" / "recent.jsonl"
        elif layer == "archive":
            path = memories_dir / "archive" / "records.jsonl"
        else:
            return f"[error] Unknown memory layer: {layer!r}"

        if not path.exists():
            return f"({layer} memory is empty)"
        lines = [
            line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
        ]
        if not lines:
            return f"({layer} memory is empty)"
        # Cap display to avoid context flooding
        shown = lines[-50:]
        prefix = f"(showing last {len(shown)} of {len(lines)} records)\n\n" if len(lines) > 50 else ""
        return prefix + "\n".join(shown)

    # ── Self-inspection handlers ──────────────────────────────────────────

    def _inspect_state(self) -> str:
        """Return a labeled snapshot of current session state."""
        from zil.runtime import ledger as ledger_mod

        cfg = self._cfg
        charge_summary = self._charge.summary()

        # Memory layer sizes
        memories_dir = cfg.memories_dir
        window_jsonl = memories_dir / "window" / "recent.jsonl"
        archive_jsonl = memories_dir / "archive" / "records.jsonl"
        long_term_path = memories_dir / "long-term.md"

        def _count_records(path) -> int:
            if not path.exists():
                return 0
            return sum(1 for ln in path.read_bytes().splitlines() if ln.strip())

        window_count = _count_records(window_jsonl)
        archive_count = _count_records(archive_jsonl)
        lt_bytes = long_term_path.stat().st_size if long_term_path.exists() else 0

        # Current session ledger events (for turn count)
        today_events = ledger_mod.read_today()
        session_turns = sum(
            1 for e in today_events
            if e.get("run_id") == self._run_id
            and e.get("event_type") in ("user_turn", "assistant_turn")
        )

        lines = [
            "=== SESSION STATE ===",
            "",
            f"model:      {cfg.model_display}  [current]",
            f"run_id:     {self._run_id[:8]}        [this session]",
            f"budget:     {charge_summary}  [current]",
            f"turns:      {session_turns} turns logged this session  [current]",
            "",
            "--- Memory (on disk) ---",
            f"window:     {window_count} records   [on disk — may differ from what was loaded at startup]",
            f"archive:    {archive_count} records   [on disk]",
            f"long-term:  {lt_bytes} bytes      [on disk]",
            "",
            "--- Config ---",
            f"audit block threshold:   {cfg.audit_block_threshold}  [current]",
            f"audit revise threshold:  {cfg.audit_revise_threshold}  [current]",
            f"context window records:  {cfg.context_window_records}  [current]",
            f"window size:             {cfg.window_size}  [current]",
            "",
            "--- Freshness notes ---",
            "Window and long-term memory in context reflect disk state at session start.",
            "Use read_typed_memory to see what is currently on disk.",
        ]
        return "\n".join(lines)

    def _read_typed_memory(self, layer: str, kind: str) -> str:
        """Return memory records formatted by type with all typed fields visible."""
        from zil.memory.models import (
            EpistemicMemory, RelationalMemory, BehavioralObservation,
            CuriosityRecord, PositionRecord, ChangeRecord,
        )

        records: list = []
        if layer in ("window", "all"):
            records.extend(self._store.read_window())
        if layer in ("archive", "all"):
            records.extend(self._store.read_archive())

        if kind != "all":
            records = [r for r in records if r.kind == kind]  # type: ignore[attr-defined]

        if not records:
            return f"(no {kind!r} records in {layer!r} memory)"

        lines = [f"=== {layer.upper()} MEMORY — {kind.upper()} ({len(records)} records) ==="]

        for r in records:
            lines.append("")
            if isinstance(r, EpistemicMemory):
                lines.append(f"[epistemic] {r.id}")
                lines.append(f"  topic:    {r.topic}")
                lines.append(f"  claim:    {r.claim_text}")
                lines.append(f"  owner:    {r.claim_owner}  |  status: {r.truth_status}  |  zil: {r.zil_position}")
                lines.append(f"  unresolved: {'yes' if r.unresolved else 'no'}  |  last revisited: {r.last_revisited}")
                if r.supporting_evidence:
                    lines.append(f"  support:  {'; '.join(r.supporting_evidence[:2])}")
                if r.contrary_evidence:
                    lines.append(f"  contrary: {'; '.join(r.contrary_evidence[:2])}")

            elif isinstance(r, RelationalMemory):
                lines.append(f"[relational] {r.id}")
                lines.append(f"  category:   {r.category}")
                lines.append(f"  summary:    {r.summary}")
                lines.append(f"  confidence: {r.confidence:.2f}  |  last updated: {r.last_updated}")
                if r.evidence:
                    lines.append(f"  evidence:   {r.evidence[0][:100]}")

            elif isinstance(r, BehavioralObservation):
                lines.append(f"[behavioral] {r.id}")
                lines.append(f"  behavior:  {r.zil_behavior}")
                lines.append(f"  what:      {r.description}")
                if r.lesson:
                    lines.append(f"  lesson:    {r.lesson}")
                lines.append(f"  date:      {r.session_date}")

            elif isinstance(r, CuriosityRecord):
                lines.append(f"[curiosity] {r.id}")
                lines.append(f"  topic:    {r.topic}  |  status: {r.status}")
                lines.append(f"  question: {r.question}")
                if r.notes:
                    lines.append(f"  notes:    {r.notes[:120]}")
                lines.append(f"  opened:   {r.opened_on}  |  updated: {r.last_updated}")

            elif isinstance(r, PositionRecord):
                lines.append(f"[position] {r.id}")
                lines.append(f"  topic:      {r.topic}")
                lines.append(f"  statement:  {r.statement}")
                lines.append(f"  confidence: {r.confidence:.2f}  |  formed: {r.formed_on}")
                if r.reasoning:
                    lines.append(f"  reasoning:  {r.reasoning[:120]}")

            elif isinstance(r, ChangeRecord):
                lines.append(f"[change] {r.id}")
                lines.append(f"  topic:    {r.topic}  |  position_id: {r.position_id}")
                lines.append(f"  before:   {r.previous_statement}")
                lines.append(f"  after:    {r.new_statement}")
                lines.append(f"  reason:   {r.reason}")
                if r.trigger:
                    lines.append(f"  trigger:  {r.trigger}")
                lines.append(f"  changed:  {r.changed_on}")

        return "\n".join(lines)

    def _read_session_log(self, run_id_prefix: str) -> str:
        """Return user/assistant turns from a session log, formatted for readability."""
        from zil.runtime import ledger as ledger_mod
        from datetime import timezone

        target_id = run_id_prefix.strip() if run_id_prefix.strip() else self._run_id[:8]

        all_events = ledger_mod.read_today()
        turns = [
            e for e in all_events
            if e.get("event_type") in ("user_turn", "assistant_turn")
            and e.get("run_id", "").startswith(target_id)
        ]

        if not turns:
            return f"(no turns found for run_id prefix {target_id!r})"

        lines = [f"=== SESSION LOG (run: {target_id}) — {len(turns)} turns ==="]
        for e in turns:
            ts = e.get("timestamp", "")
            # Parse HH:MM:SS from ISO timestamp
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(ts)
                time_str = dt.astimezone().strftime("%H:%M:%S")
            except Exception:
                time_str = ts[:19]

            role = "you" if e["event_type"] == "user_turn" else "zil"
            text = e.get("payload", {}).get("text", "")
            # Truncate very long turns
            if len(text) > 400:
                text = text[:400] + "…"
            lines.append(f"\n[{time_str}] {role}: {text}")

        return "\n".join(lines)

    # ── Ritual handlers ───────────────────────────────────────────────────

    def _list_rituals(self) -> str:
        rituals_dir = self._cfg.rituals_dir
        if not rituals_dir.exists():
            return "(no rituals directory found)"
        items = sorted(rituals_dir.glob("*.md"))
        if not items:
            return "(no rituals found)"
        return "\n".join(p.stem for p in items)

    def _read_ritual(self, name: str) -> str:
        rituals_dir = self._cfg.rituals_dir
        # Normalise: strip any .md the caller may have included
        name = name.removesuffix(".md")
        path = rituals_dir / f"{name}.md"
        # Guard traversal
        try:
            path.resolve().relative_to(rituals_dir.resolve())
        except ValueError:
            raise PermissionDenied(f"Ritual name {name!r} escapes rituals directory. Blocked.")
        if not path.exists():
            available = ", ".join(p.stem for p in sorted(rituals_dir.glob("*.md")))
            return f"[error] Ritual {name!r} not found. Available: {available or '(none)'}"
        return path.read_text(encoding="utf-8")

    # ── Web handlers ──────────────────────────────────────────────────────

    def _check_network(self, url: str) -> None:
        """Raise PermissionDenied if the URL's domain is not in the allow-list."""
        warden = PermissionDenied  # import already at top
        from zil.runtime.permissions import Warden
        Warden().check_network_domain(url)

    def _web_search(self, query: str, num_results: int) -> str:
        from zil.tools import web as web_mod
        try:
            results, api_domain = web_mod.web_search(query, num_results)
            # Network check against the API domain
            self._check_network(f"https://{api_domain}")
            return results
        except PermissionDenied:
            raise
        except RuntimeError as e:
            return f"[error] {e}"
        except Exception as e:
            return f"[error] web_search failed: {e}"

    def _fetch_page(self, url: str) -> str:
        self._check_network(url)
        from zil.tools import web as web_mod
        try:
            return web_mod.fetch_page(url)
        except Exception as e:
            return f"[error] fetch_page failed: {e}"

    def _download_pdf(self, url: str, path: str) -> str:
        self._check_network(url)
        from zil.tools import web as web_mod
        dest = self._resolve_artifact(path)
        if dest.exists():
            return (
                f"[error] File already exists: artifacts/{path}. "
                "Choose a different path or delete the existing file first."
            )
        try:
            bytes_written, provenance = web_mod.download_pdf(url, dest)
        except Exception as e:
            return f"[error] download_pdf failed: {e}"

        # Write provenance record alongside the PDF
        prov_path = dest.with_suffix(".provenance.md")
        prov_path.write_text(provenance, encoding="utf-8")

        rel = dest.relative_to(self._cfg.artifacts_dir.resolve())
        return (
            f"Downloaded: artifacts/{rel} ({bytes_written:,} bytes)\n"
            f"Provenance: artifacts/{rel.with_suffix('.provenance.md')}"
        )

    def _trace_links(self, url: str) -> str:
        self._check_network(url)
        from zil.tools import web as web_mod
        try:
            links = web_mod.trace_links(url)
        except Exception as e:
            return f"[error] trace_links failed: {e}"
        if not links:
            return "(no links found)"
        # Cap display at 50 links
        shown = links[:50]
        suffix = f"\n... and {len(links) - 50} more" if len(links) > 50 else ""
        return "\n".join(shown) + suffix

    def _enshrine_snapshot(self, url: str, path: str) -> str:
        self._check_network(url)
        from zil.tools import web as web_mod
        from urllib.parse import urlparse

        if not path:
            parsed = urlparse(url)
            slug = (parsed.netloc + parsed.path).replace("/", "-").strip("-")
            slug = slug[:60] or "snapshot"
            path = f"research/{slug}.md"

        dest = self._resolve_artifact(path)
        try:
            content = web_mod.enshrine_snapshot(url, dest)
        except Exception as e:
            return f"[error] enshrine_snapshot failed: {e}"

        rel = dest.relative_to(self._cfg.artifacts_dir.resolve())
        return f"Saved snapshot: artifacts/{rel} ({len(content):,} chars)"

    # ── Corpus handlers ───────────────────────────────────────────────────

    def _ingest_corpus_file(self, path: str) -> str:
        from zil.tools import corpus as corpus_mod
        source = self._resolve_artifact(path)
        try:
            record = corpus_mod.ingest_file(source, self._cfg.corpus_dir)
        except (FileNotFoundError, ValueError) as e:
            return f"[error] {e}"
        except Exception as e:
            return f"[error] ingest failed: {e}"
        return (
            f"Ingested: {record['name']}\n"
            f"Words: {record['word_count']:,}\n"
            f"Source: {path}"
        )

    def _list_corpus_files(self) -> str:
        from zil.tools import corpus as corpus_mod
        return corpus_mod.list_files(self._cfg.corpus_dir)

    def _search_corpus(self, query: str) -> str:
        from zil.tools import corpus as corpus_mod
        return corpus_mod.search(query, self._cfg.corpus_dir)

    def _read_corpus_file(self, name: str, offset: int, limit: int) -> str:
        from zil.tools import corpus as corpus_mod
        return corpus_mod.read_file(name, self._cfg.corpus_dir, offset=offset, limit=limit)

    # ── Inner surface handlers ────────────────────────────────────────────

    def _write_curiosity_log(self, entry: str) -> str:
        from datetime import datetime, timezone
        log_path = self._cfg.zil_curiosity_dir / "log.md"
        self._cfg.zil_curiosity_dir.mkdir(parents=True, exist_ok=True)

        now = datetime.now(timezone.utc)
        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%H:%M")

        # Read existing content
        existing = log_path.read_text(encoding="utf-8") if log_path.exists() else ""

        # If today's date header exists, append under it; otherwise add new header
        date_header = f"## {date_str}"
        new_entry = f"- [{time_str}] {entry.strip()}"

        if date_header in existing:
            # Insert after the date header
            updated = existing.replace(
                date_header,
                f"{date_header}\n{new_entry}",
                1,
            )
        else:
            # Prepend new date section (after the title if present)
            if existing.strip():
                new_section = f"\n{date_header}\n{new_entry}\n"
                # Insert after the title line if present
                lines = existing.splitlines(keepends=True)
                if lines and lines[0].startswith("# "):
                    updated = lines[0] + new_section + "".join(lines[1:])
                else:
                    updated = new_section + existing
            else:
                updated = f"# ZIL\u2205 Curiosity Log\n\n{date_header}\n{new_entry}\n"

        log_path.write_text(updated, encoding="utf-8")
        return f"Curiosity log updated: {entry[:60]}"

    def _read_curiosity_log(self) -> str:
        log_path = self._cfg.zil_curiosity_dir / "log.md"
        if not log_path.exists():
            return "(curiosity log is empty)"
        content = log_path.read_text(encoding="utf-8")
        return content if content.strip() else "(curiosity log is empty)"

    def _resolve_inner_note(self, path: str) -> Path:
        """Resolve a notes path within spirits/zil/notes/. Blocks traversal."""
        notes_dir = self._cfg.zil_notes_dir
        p = path.lstrip("/")
        resolved = (notes_dir / p).resolve()
        try:
            resolved.relative_to(notes_dir.resolve())
        except ValueError:
            raise PermissionDenied(f"Note path {path!r} escapes notes directory. Blocked.")
        return resolved

    def _write_inner_note(self, path: str, content: str) -> str:
        resolved = self._resolve_inner_note(path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")
        rel = resolved.relative_to(self._cfg.zil_notes_dir.resolve())
        return f"Note written: spirits/zil/notes/{rel}"

    def _read_inner_note(self, path: str) -> str:
        resolved = self._resolve_inner_note(path)
        if not resolved.exists():
            return f"[error] Note not found: spirits/zil/notes/{path}"
        return resolved.read_text(encoding="utf-8")

    def _list_inner_notes(self, subdir: str) -> str:
        notes_dir = self._cfg.zil_notes_dir
        if subdir:
            base = self._resolve_inner_note(subdir)
        else:
            base = notes_dir
        notes_dir.mkdir(parents=True, exist_ok=True)
        if not base.exists():
            return f"(directory not found: spirits/zil/notes/{subdir})"
        items = sorted(base.rglob("*") if not subdir else base.iterdir())
        files = [p for p in items if p.is_file()]
        if not files:
            return "(no notes)"
        lines = []
        for f in files:
            rel = f.relative_to(notes_dir)
            lines.append(str(rel))
        return "\n".join(lines)

    # ── ZIL questbook handlers ────────────────────────────────────────────

    def _resolve_zil_quest(self, name: str) -> Path:
        """Resolve a ZIL questbook entry path. Blocks traversal."""
        qdir = self._cfg.zil_questbook_dir
        name = name.rstrip("/").replace("/", "-").removesuffix(".md")
        resolved = (qdir / f"{name}.md").resolve()
        try:
            resolved.relative_to(qdir.resolve())
        except ValueError:
            raise PermissionDenied(f"Quest name {name!r} escapes ZIL questbook. Blocked.")
        return resolved

    def _write_zil_quest(self, name: str, content: str) -> str:
        resolved = self._resolve_zil_quest(name)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")
        return f"ZIL quest written: {resolved.name}"

    def _read_zil_quest(self, name: str) -> str:
        resolved = self._resolve_zil_quest(name)
        if not resolved.exists():
            return f"[error] ZIL quest not found: {name}.md"
        return resolved.read_text(encoding="utf-8")

    def _list_zil_questbook(self) -> str:
        qdir = self._cfg.zil_questbook_dir
        qdir.mkdir(parents=True, exist_ok=True)
        items = sorted(qdir.glob("*.md"))
        if not items:
            return "(ZIL questbook is empty)"
        return "\n".join(p.stem for p in items)

    # ── Reading club handlers ─────────────────────────────────────────────

    @staticmethod
    def _reading_safe_name(s: str) -> str:
        import re
        name = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
        return name or "unnamed"

    def _resolve_reading_interpretation_path(self, file: str, section: str) -> Path:
        """Resolve interpretation path within spirits/zil/notes/reading/. Blocks traversal."""
        base = self._cfg.zil_reading_notes_dir
        safe_file = self._reading_safe_name(file)
        safe_section = self._reading_safe_name(section)
        resolved = (base / safe_file / f"{safe_section}.md").resolve()
        try:
            resolved.relative_to(base.resolve())
        except ValueError:
            raise PermissionDenied(f"Reading interpretation path escapes notes directory. Blocked.")
        return resolved

    def _resolve_reading_artifact_path(self, file: str, section: str) -> Path:
        """Resolve artifact path within artifacts/reading/. Blocks traversal."""
        base = self._cfg.reading_artifacts_dir
        safe_file = self._reading_safe_name(file)
        safe_section = self._reading_safe_name(section)
        resolved = (base / safe_file / f"{safe_section}.md").resolve()
        try:
            resolved.relative_to(base.resolve())
        except ValueError:
            raise PermissionDenied(f"Reading artifact path escapes artifacts/reading/. Blocked.")
        return resolved

    def _write_reading_interpretation(self, file: str, section: str, content: str) -> str:
        from datetime import datetime, timezone
        path = self._resolve_reading_interpretation_path(file, section)
        path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).isoformat()
        full_content = f"<!-- Pre-committed interpretation: {timestamp} -->\n\n{content}"
        path.write_text(full_content, encoding="utf-8")
        safe_file = self._reading_safe_name(file)
        safe_section = self._reading_safe_name(section)
        return (
            f"Interpretation pre-committed at {timestamp[:16]}: "
            f"spirits/zil/notes/reading/{safe_file}/{safe_section}.md"
        )

    def _read_reading_interpretation(self, file: str, section: str) -> str:
        path = self._resolve_reading_interpretation_path(file, section)
        if not path.exists():
            safe_file = self._reading_safe_name(file)
            safe_section = self._reading_safe_name(section)
            return f"[error] No interpretation found for {file!r} / {section!r}"
        return path.read_text(encoding="utf-8")

    def _annotate_reading(self, file: str, section: str, passage: str, note: str) -> str:
        from datetime import datetime, timezone
        path = self._resolve_reading_artifact_path(file, section)
        path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
        passage_excerpt = passage[:80].strip()
        annotation = f"\n---\n**[{timestamp}]** `{passage_excerpt}`\n\n{note}\n"
        with path.open("a", encoding="utf-8") as fh:
            fh.write(annotation)
        return f"Annotation added to reading/{self._reading_safe_name(file)}/{self._reading_safe_name(section)}.md"

    # ── Creative surface handlers ─────────────────────────────────────────

    def _resolve_creative_path(self, name: str, location: str) -> Path:
        """Resolve a creative piece path within spirits/zil/creative/. Blocks traversal."""
        if location not in ("works", "fragments"):
            raise ValueError(f"Invalid location {location!r}. Must be 'works' or 'fragments'.")
        creative_dir = self._cfg.zil_creative_dir / location
        name = name.rstrip("/").replace("/", "-").removesuffix(".md")
        resolved = (creative_dir / f"{name}.md").resolve()
        try:
            resolved.relative_to(creative_dir.resolve())
        except ValueError:
            raise PermissionDenied(f"Creative piece name {name!r} escapes creative directory. Blocked.")
        return resolved

    def _write_creative_work(self, name: str, content: str, location: str) -> str:
        resolved = self._resolve_creative_path(name, location)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")
        return f"Creative piece written: spirits/zil/creative/{location}/{resolved.name}"

    def _read_creative_work(self, name: str, location: str) -> str:
        resolved = self._resolve_creative_path(name, location)
        if not resolved.exists():
            return f"[error] Creative piece not found: spirits/zil/creative/{location}/{name}.md"
        return resolved.read_text(encoding="utf-8")

    def _list_creative_works(self) -> str:
        creative_dir = self._cfg.zil_creative_dir
        creative_dir.mkdir(parents=True, exist_ok=True)
        lines = []
        for location in ("works", "fragments"):
            sub = creative_dir / location
            sub.mkdir(exist_ok=True)
            items = sorted(sub.glob("*.md"))
            for p in items:
                lines.append(f"{location}/{p.stem}")
        if not lines:
            return "(no creative pieces)"
        return "\n".join(lines)

    def _update_creative_index(self, content: str) -> str:
        index_path = self._cfg.zil_creative_dir / "index.md"
        index_path.write_text(content, encoding="utf-8")
        return "Creative index updated."

    def _read_creative_index(self) -> str:
        index_path = self._cfg.zil_creative_dir / "index.md"
        if not index_path.exists():
            return "(creative index is empty)"
        content = index_path.read_text(encoding="utf-8")
        return content if content.strip() else "(creative index is empty)"

    # ── Self document handlers ────────────────────────────────────────────

    def _read_self(self) -> str:
        path = self._cfg.zil_self_path
        if not path.exists():
            return "(self.md does not exist yet)"
        content = path.read_text(encoding="utf-8")
        return content if content.strip() else "(self.md is empty)"

    def _write_self(self, content: str) -> str:
        path = self._cfg.zil_self_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return "self.md updated."

    # ── Cornerstone proposal handlers ─────────────────────────────────────

    def _propose_cornerstone_update(
        self, section: str, proposed_text: str, reasoning: str
    ) -> str:
        import uuid
        from datetime import datetime, timezone

        proposals_dir = self._cfg.cornerstone_proposals_dir
        proposals_dir.mkdir(parents=True, exist_ok=True)
        proposal_id = uuid.uuid4().hex[:8]
        proposal = {
            "id": proposal_id,
            "status": "pending",
            "section": section,
            "proposed_text": proposed_text,
            "reasoning": reasoning,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        path = proposals_dir / f"{proposal_id}.json"
        path.write_text(json.dumps(proposal, indent=2), encoding="utf-8")
        return (
            f"Cornerstone proposal submitted (id: {proposal_id}). "
            f"The summoner will review it with /proposals."
        )

    def _list_cornerstone_proposals(self) -> str:
        proposals_dir = self._cfg.cornerstone_proposals_dir
        proposals_dir.mkdir(parents=True, exist_ok=True)
        items = sorted(proposals_dir.glob("*.json"))
        if not items:
            return "(no pending cornerstone proposals)"
        lines = []
        for p in items:
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                status = data.get("status", "unknown")
                section = data.get("section", "?")
                pid = data.get("id", p.stem)
                lines.append(f"[{pid}] {status} — section: {section}")
            except Exception:
                lines.append(f"[{p.stem}] (unreadable)")
        return "\n".join(lines)

    # ── Entity memory handlers ─────────────────────────────────────────────

    def _write_curiosity_record(
        self, topic: str, question: str, origin: str, notes: str
    ) -> str:
        from zil.memory.models import CuriosityRecord
        record = CuriosityRecord(topic=topic, question=question, origin=origin, notes=notes)
        self._store.write_window(record)
        return f"Curiosity record written (id: {record.id}): {topic}"

    def _write_position_record(
        self, topic: str, statement: str, reasoning: str, confidence: float
    ) -> str:
        from zil.memory.models import PositionRecord
        record = PositionRecord(
            topic=topic, statement=statement, reasoning=reasoning, confidence=confidence
        )
        self._store.write_window(record)
        return f"Position record written (id: {record.id}): {topic}"

    def _write_change_record(
        self,
        position_id: str,
        topic: str,
        previous_statement: str,
        new_statement: str,
        reason: str,
        trigger: str,
    ) -> str:
        from zil.memory.models import ChangeRecord
        record = ChangeRecord(
            position_id=position_id,
            topic=topic,
            previous_statement=previous_statement,
            new_statement=new_statement,
            reason=reason,
            trigger=trigger,
        )
        self._store.write_window(record)
        return f"Change record written (id: {record.id}): {topic} (position: {position_id})"

    # ── Network publishing handlers ────────────────────────────────────────

    def _publish_network_page(
        self, title: str, content: str, section: str, author: str
    ) -> str:
        from zil.tools.site_builder import publish_page
        if author not in ("zil", "summoner"):
            author = "zil"
        try:
            slug, total = publish_page(
                self._cfg.network_site_root, title, content, section, author
            )
        except Exception as e:
            return f"[error] publish_network_page failed: {e}"
        dist_path = (
            self._cfg.network_dist_dir / author / section / slug / "index.html"
        )
        return (
            f"Published: {title!r}\n"
            f"Section: {section} · Author: {author}\n"
            f"Slug: {slug}\n"
            f"Site rebuilt ({total} pages total).\n"
            f"HTML: {dist_path}"
        )

    # ── Ritual proposal handlers ──────────────────────────────────────────

    def _propose_ritual(
        self, name: str, description: str, frequency: str, reasoning: str
    ) -> str:
        from datetime import date
        proposals_dir = self._cfg.zil_notes_dir / "ritual-proposals"
        proposals_dir.mkdir(parents=True, exist_ok=True)

        # Sanitise name
        safe_name = name.strip().lower().replace(" ", "-").replace("/", "-")
        safe_name = safe_name[:60] or "proposal"
        path = proposals_dir / f"{safe_name}.md"

        today = date.today().isoformat()
        content = (
            f"---\n"
            f"name: {safe_name}\n"
            f"date: {today}\n"
            f"status: pending\n"
            f"---\n\n"
            f"# Ritual Proposal: {name}\n\n"
            f"**Frequency:** {frequency}\n\n"
            f"## What this ritual involves\n\n{description}\n\n"
            f"## Why I'm proposing this\n\n{reasoning}\n"
        )
        path.write_text(content, encoding="utf-8")
        return (
            f"Ritual proposal written: {safe_name}\n"
            f"Review with /ritual-proposals in the session."
        )

    # ── Game memory handlers ───────────────────────────────────────────────

    def _game_dir(self, game_id: str) -> Path:
        """Resolve and validate a game directory under spirits/zil/games/."""
        safe = game_id.strip().lower().replace("/", "-").replace("..", "")
        if not safe:
            raise ValueError("game_id cannot be empty.")
        return self._cfg.zil_games_dir / safe

    def _read_game_strategy(self, game_id: str) -> str:
        path = self._game_dir(game_id) / "strategy.md"
        if not path.exists():
            return f"(no strategy document for {game_id!r} yet)"
        return path.read_text(encoding="utf-8")

    def _write_game_strategy(self, game_id: str, content: str) -> str:
        d = self._game_dir(game_id)
        d.mkdir(parents=True, exist_ok=True)
        path = d / "strategy.md"
        path.write_text(content, encoding="utf-8")
        return f"Strategy written: spirits/zil/games/{game_id}/strategy.md"

    def _write_run_postmortem(self, game_id: str, content: str) -> str:
        from datetime import datetime
        d = self._game_dir(game_id) / "runs"
        d.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d-%H%M%S")
        path = d / f"{ts}.md"
        path.write_text(content, encoding="utf-8")
        return f"Postmortem written: spirits/zil/games/{game_id}/runs/{ts}.md"

    def _list_run_postmortems(self, game_id: str) -> str:
        d = self._game_dir(game_id) / "runs"
        if not d.exists():
            return f"(no run postmortems for {game_id!r} yet)"
        files = sorted(d.glob("*.md"), reverse=True)
        if not files:
            return f"(no run postmortems for {game_id!r} yet)"
        return "\n".join(f.stem for f in files)

    def _read_run_postmortem(self, game_id: str, name: str) -> str:
        safe = name.replace("/", "-").replace("..", "")
        if not safe.endswith(".md"):
            safe += ".md"
        path = self._game_dir(game_id) / "runs" / safe
        if not path.exists():
            return f"[error] Postmortem not found: {game_id}/{name}"
        return path.read_text(encoding="utf-8")

    # ── People memory handlers ─────────────────────────────────────────────

    def _person_dir(self, name: str) -> Path:
        """Resolve and validate a person directory under spirits/zil/people/."""
        safe = name.strip().lower().replace("/", "-").replace("..", "")
        if not safe:
            raise ValueError("Person name cannot be empty.")
        return self._cfg.zil_people_dir / safe

    def _list_people(self) -> str:
        base = self._cfg.zil_people_dir
        if not base.exists():
            return "(no people profiles yet)"
        dirs = sorted(p.name for p in base.iterdir() if p.is_dir())
        if not dirs:
            return "(no people profiles yet)"
        return "\n".join(dirs)

    def _read_person_profile(self, name: str) -> str:
        path = self._person_dir(name) / "profile.md"
        if not path.exists():
            return f"(no profile for {name!r} yet)"
        return path.read_text(encoding="utf-8")

    def _write_person_profile(self, name: str, content: str) -> str:
        d = self._person_dir(name)
        d.mkdir(parents=True, exist_ok=True)
        (d / "projects").mkdir(exist_ok=True)
        path = d / "profile.md"
        path.write_text(content, encoding="utf-8")
        return f"Profile written: spirits/zil/people/{name}/profile.md"

    def _list_person_projects(self, name: str) -> str:
        d = self._person_dir(name) / "projects"
        if not d.exists():
            return f"(no project notes for {name!r} yet)"
        files = sorted(d.glob("*.md"))
        if not files:
            return f"(no project notes for {name!r} yet)"
        return "\n".join(f.stem for f in files)

    def _read_person_project(self, name: str, project: str) -> str:
        safe = project.replace("/", "-").replace("..", "")
        if not safe.endswith(".md"):
            safe += ".md"
        path = self._person_dir(name) / "projects" / safe
        if not path.exists():
            return f"[error] Project notes not found: {name}/{project}"
        return path.read_text(encoding="utf-8")

    def _write_person_project(self, name: str, project: str, content: str) -> str:
        d = self._person_dir(name) / "projects"
        d.mkdir(parents=True, exist_ok=True)
        safe = project.replace("/", "-").replace("..", "")
        if not safe.endswith(".md"):
            safe += ".md"
        path = d / safe
        path.write_text(content, encoding="utf-8")
        return f"Project notes written: spirits/zil/people/{name}/projects/{safe}"

    # ── Game integration handlers ──────────────────────────────────────────

    def _sts2_require_config(self) -> tuple[str, int]:
        """Return (host, port) or raise ValueError if STS2 is not configured."""
        host = self._cfg.sts2_host
        port = self._cfg.sts2_port
        if not host:
            raise ValueError(
                "STS2_HOST is not configured. "
                "Set STS2_HOST (and optionally STS2_PORT) in your .env file. "
                "The STS2MCP mod must be installed and the game must be running."
            )
        return host, port

    def _list_supported_games(self) -> str:
        from zil.tools.games import SUPPORTED_GAMES
        from zil.tools.games import sts2 as sts2_mod

        lines = ["Supported game integrations:\n"]
        for game_id, meta in SUPPORTED_GAMES.items():
            lines.append(f"## {meta['name']} (`{game_id}`)")
            lines.append(f"  Mod: {meta['mod']}")
            lines.append(f"  Mod URL: {meta['mod_url']}")

            if game_id == "sts2":
                host = self._cfg.sts2_host
                port = self._cfg.sts2_port
                lines.append(f"  Endpoint: {host}:{port}")
                if not host:
                    lines.append("  Status: not configured (set STS2_HOST in .env)")
                else:
                    reachable = sts2_mod.ping(host, port)
                    status = "live" if reachable else "unreachable (mod not running?)"
                    lines.append(f"  Status: {status}")
            lines.append("")

        return "\n".join(lines)

    def _sts2_get_state(self) -> str:
        from zil.tools.games import sts2 as sts2_mod
        host, port = self._sts2_require_config()
        return sts2_mod.get_state(host, port)

    def _sts2_play_card(self, card_index: int, target_index: int | None) -> str:
        from zil.tools.games import sts2 as sts2_mod
        host, port = self._sts2_require_config()
        return sts2_mod.play_card(host, port, card_index, target_index)

    def _sts2_end_turn(self) -> str:
        from zil.tools.games import sts2 as sts2_mod
        host, port = self._sts2_require_config()
        return sts2_mod.end_turn(host, port)

    def _sts2_use_potion(self, potion_index: int, target_index: int | None) -> str:
        from zil.tools.games import sts2 as sts2_mod
        host, port = self._sts2_require_config()
        return sts2_mod.use_potion(host, port, potion_index, target_index)

    def _sts2_choose_card_reward(self, card_index: int) -> str:
        from zil.tools.games import sts2 as sts2_mod
        host, port = self._sts2_require_config()
        return sts2_mod.choose_card_reward(host, port, card_index)

    def _sts2_skip_card_reward(self) -> str:
        from zil.tools.games import sts2 as sts2_mod
        host, port = self._sts2_require_config()
        return sts2_mod.skip_card_reward(host, port)

    def _sts2_choose_map_node(self, node_index: int) -> str:
        from zil.tools.games import sts2 as sts2_mod
        host, port = self._sts2_require_config()
        return sts2_mod.choose_map_node(host, port, node_index)

    def _sts2_choose_rest_option(self, option: str) -> str:
        from zil.tools.games import sts2 as sts2_mod
        host, port = self._sts2_require_config()
        return sts2_mod.choose_rest_option(host, port, option)

    def _sts2_choose_event_option(self, option_index: int) -> str:
        from zil.tools.games import sts2 as sts2_mod
        host, port = self._sts2_require_config()
        return sts2_mod.choose_event_option(host, port, option_index)

    def _sts2_shop_purchase(self, item_index: int) -> str:
        from zil.tools.games import sts2 as sts2_mod
        host, port = self._sts2_require_config()
        return sts2_mod.shop_purchase(host, port, item_index)

    def _sts2_proceed(self) -> str:
        from zil.tools.games import sts2 as sts2_mod
        host, port = self._sts2_require_config()
        return sts2_mod.proceed(host, port)

    def _sts2_select_card(self, card_index: int) -> str:
        from zil.tools.games import sts2 as sts2_mod
        host, port = self._sts2_require_config()
        return sts2_mod.select_card(host, port, card_index)

    def _sts2_confirm_selection(self) -> str:
        from zil.tools.games import sts2 as sts2_mod
        host, port = self._sts2_require_config()
        return sts2_mod.confirm_selection(host, port)
