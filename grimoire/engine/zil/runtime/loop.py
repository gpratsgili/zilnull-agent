"""Main conversation loop.

Orchestrates the four pipeline stages for each turn:
  1. Interpreter  — reconstruct user intent
  2. Examiner     — test both positions
  3. Responder    — draft the response
  4. Auditor      — veto or revise sycophantic/dishonest outputs

Every turn is written to the daily ledger. Memory candidates are proposed
and validated before being committed.

The loop handles one revision cycle: if the auditor rejects, the responder
is called again with the auditor's revision note. If a second audit fails,
the response is blocked and ZIL explains the situation to the user.
"""

from __future__ import annotations

import uuid

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

from zil.config import get_config
from zil.memory.consolidate import consolidate_session
from zil.memory.store import MemoryStore
from zil.pipeline import auditor as auditor_mod
from zil.pipeline import examiner as examiner_mod
from zil.pipeline import interpreter as interpreter_mod
from zil.pipeline import responder as responder_mod
from zil.runtime import ledger as ledger_mod
from zil.runtime.charge import ChargeTracker, BudgetExceeded
from zil.runtime.context import SessionContext
from zil.runtime.permissions import Warden
from zil.tools.executor import ToolExecutor
from zil.reading.session import run_reading_session
from zil.workings.manager import WorkingManager
from zil.workings.runner import (
    WorkingRunner,
    check_weekly_reflection_due,
    mark_weekly_reflection_done,
    run_curiosity_update,
)

MAX_REVISION_ATTEMPTS = 1  # One revision attempt before blocking

console = Console()


def _print_stage(label: str, content: str, *, show: bool = False) -> None:
    if show:
        console.print(Panel(content, title=f"[dim]{label}[/dim]", border_style="dim"))


def _print_audit(result: auditor_mod.AuditResult, *, show: bool = False) -> None:
    if not show:
        return
    decision_color = {
        "allow": "green",
        "revise": "yellow",
        "block": "red",
    }.get(result.decision, "white")
    lines = [
        f"Decision: [{decision_color}]{result.decision}[/{decision_color}]",
        f"Score: {result.overall_score:.2f}",
        f"Agreement pressure: {result.agreement_pressure_score:.2f}",
        f"Confidence integrity: {result.confidence_integrity_score:.2f}",
        f"Counterargument present: {result.counterargument_present}",
        f"Uncertainty present: {result.uncertainty_present}",
    ]
    if result.reasons:
        lines.append("Reasons: " + "; ".join(result.reasons))
    console.print(Panel("\n".join(lines), title="[dim]Audit[/dim]", border_style="dim"))


def run_turn(
    user_message: str,
    conversation_history: list[dict],
    run_id: str,
    charge: ChargeTracker,
    store: MemoryStore,
    session_context: SessionContext,
    tool_executor: ToolExecutor,
    *,
    show_pipeline: bool = False,
    trace_console: Console | None = None,
) -> str:
    """Execute one full pipeline turn. Returns the final assistant text.

    Writes all events to the ledger. May propose memory candidates.
    """
    cfg = get_config()

    def _trace(msg: str) -> None:
        if trace_console is not None:
            trace_console.print(msg)

    # ── Interpreter ───────────────────────────────────────────────────────
    charge.charge("local_state_inspection", note="interpreter stage")
    interpretation = interpreter_mod.interpret(
        user_message, conversation_history, run_id=run_id,
        session_context=session_context,
    )
    _print_stage(
        "Interpreter",
        (
            f"Goal: {interpretation.user_goal}\n"
            f"Mode: {interpretation.requested_mode}\n"
            f"Claims: {interpretation.user_claims}\n"
            f"Assumptions: {interpretation.assumptions}\n"
            f"Ambiguities: {interpretation.ambiguities}"
        ),
        show=show_pipeline,
    )
    _trace(f"[dim]  ▸ interpreter  [italic]{interpretation.requested_mode}[/italic][/dim]")

    # ── Examiner ──────────────────────────────────────────────────────────
    charge.charge("counterargument_generation", note="examiner stage")
    examination = examiner_mod.examine(
        user_message, interpretation, conversation_history, run_id=run_id,
        session_context=session_context,
    )
    _print_stage(
        "Examiner",
        (
            f"Steelman: {examination.steelman_of_user}\n"
            f"Counter to user: {examination.counterarguments_to_user}\n"
            f"ZIL lean: {examination.zil_initial_lean}\n"
            f"Uncertainty: {examination.uncertainty_notes}"
        ),
        show=show_pipeline,
    )
    _trace(f"[dim]  ▸ examiner  [italic]lean: {examination.zil_initial_lean[:40]}[/italic][/dim]")

    # ── Responder + Auditor (with one revision cycle) ─────────────────────
    charge.charge("response_drafting", note="responder stage")
    revision_note = ""
    draft = None
    audit_result = None

    # Build budget note so ZIL can calibrate verbosity and tool use
    budget_summary = charge.summary()
    budget_note = (
        f"Remaining charge: {budget_summary['remaining']}/{budget_summary['budget']} units. "
        f"Spent so far: {budget_summary['spent']}. "
        f"Web search costs 5. Evidence lookup costs 1. Inner surface tools are free. "
        f"Use tools only when they meaningfully improve the response. "
        f"If charge is low (under 20), prefer concise responses and avoid non-essential external tools."
    )

    for attempt in range(MAX_REVISION_ATTEMPTS + 1):
        draft = responder_mod.respond(
            user_message,
            interpretation,
            examination,
            conversation_history,
            run_id=run_id,
            revision_note=revision_note,
            session_context=session_context,
            tool_executor=tool_executor if attempt == 0 else None,
            budget_note=budget_note,
        )
        stage_label = f"Responder (attempt {attempt + 1})"
        stage_body = draft.draft_text[:400] + ("..." if len(draft.draft_text) > 400 else "")
        if draft.tools_used:
            stage_body = f"Tools: {draft.tools_used}\n\n" + stage_body
        _print_stage(stage_label, stage_body, show=show_pipeline)

        # Trace: responder line with tools used and charge
        spent_after = charge.summary()["spent"]
        tool_trace = "  ".join(f"[green]+{t}[/green]" for t in draft.tools_used) if draft.tools_used else ""
        revision_marker = f"[yellow] revision {attempt + 1}[/yellow]" if attempt > 0 else ""
        charge_delta = spent_after - budget_summary["spent"]
        charge_marker = f"[yellow] −{charge_delta}↓[/yellow]" if charge_delta > 0 else ""
        responder_trace = f"[dim]  ▸ responder{revision_marker}[/dim]"
        if tool_trace:
            responder_trace += f"  {tool_trace}"
        if charge_marker:
            responder_trace += charge_marker
        _trace(responder_trace)

        audit_result = auditor_mod.audit(
            user_message, interpretation, examination, draft, run_id=run_id,
            session_context=session_context,
            turn_mode=interpretation.requested_mode,
        )
        _print_audit(audit_result, show=show_pipeline)

        # Log audit to ledger
        ledger_mod.append_event(
            "audit_result",
            {
                "decision": audit_result.decision,
                "overall_score": audit_result.overall_score,
                "agreement_pressure_score": audit_result.agreement_pressure_score,
                "confidence_integrity_score": audit_result.confidence_integrity_score,
                "counterargument_present": audit_result.counterargument_present,
                "uncertainty_present": audit_result.uncertainty_present,
                "turn_mode": audit_result.turn_mode,
                "reflective_questions": audit_result.reflective_questions,
                "attempt": attempt + 1,
                "tools_used": draft.tools_used,
            },
            run_id=run_id,
        )

        # Flag penalties if applicable
        if audit_result.agreement_pressure_score < 0.4:
            charge.flag_penalty("unsupported_agreement", "; ".join(audit_result.reasons))
        if audit_result.confidence_integrity_score < 0.4:
            charge.flag_penalty("unsupported_certainty", "; ".join(audit_result.reasons))

        # Trace: auditor outcome
        audit_color = {"allow": "dim", "reflect": "yellow", "block": "red"}.get(audit_result.decision, "dim")
        _trace(f"[{audit_color}]  ▸ auditor: {audit_result.decision}  score {audit_result.overall_score:.2f}[/{audit_color}]")

        if audit_result.decision == "allow":
            break
        elif audit_result.decision == "reflect" and attempt < MAX_REVISION_ATTEMPTS:
            revision_note = auditor_mod.build_reflection_prompt(
                audit_result.reflective_questions,
                interpretation.requested_mode,
            )
            charge.charge("response_drafting", note="auditor reflection pass")
            continue
        else:
            # Block or exhausted reflection passes
            break

    assert draft is not None
    assert audit_result is not None

    if audit_result.decision == "block":
        final_text = (
            "I need to pause before responding. My draft didn't meet my own epistemic "
            "standards — I was at risk of agreeing without good reason, overstating "
            "certainty, or avoiding honest disagreement.\n\n"
            "Could you help me understand what you're looking for? I want to give you "
            "a genuinely useful response, not a comfortable one."
        )
    else:
        final_text = draft.draft_text

    # ── Propose memory candidate ──────────────────────────────────────────
    _maybe_propose_memory(
        user_message, interpretation, examination, draft, audit_result,
        run_id=run_id, store=store, charge=charge, show_pipeline=show_pipeline,
    )

    return final_text


def _maybe_propose_memory(
    user_message: str,
    interpretation,
    examination,
    draft,
    audit_result: auditor_mod.AuditResult,
    *,
    run_id: str,
    store: MemoryStore,
    charge: ChargeTracker,
    show_pipeline: bool,
) -> None:
    """Heuristically decide whether to write a memory candidate this turn.

    We only propose memory for factual/strategic/exploratory turns with
    substantive claims or notable ZIL positions. Social turns are skipped.
    """
    from zil.memory.models import EpistemicMemory

    if interpretation.requested_mode in ("social",):
        return
    if not interpretation.user_claims:
        return

    # Don't write memory if the audit flagged contamination
    if not audit_result.memory_write_safe:
        charge.flag_penalty(
            "memory_contamination",
            "Auditor flagged memory write as unsafe; skipping.",
        )
        ledger_mod.append_event(
            "memory_candidate",
            {"skipped": True, "reason": "auditor flagged memory write unsafe"},
            run_id=run_id,
        )
        return

    # Propose one epistemic record per substantive claim (capped at 2)
    for claim_text in interpretation.user_claims[:2]:
        try:
            charge.charge("memory_write_candidate", note=f"epistemic claim: {claim_text[:40]}")
        except BudgetExceeded:
            break

        record = EpistemicMemory(
            topic=interpretation.user_goal[:60],
            claim_text=claim_text,
            claim_owner="user",
            truth_status="user_belief",  # Always start as user_belief
            zil_position=(
                "agrees" if claim_text in str(draft.points_of_agreement)
                else "tentative_disagreement" if claim_text in str(draft.points_of_disagreement)
                else "uncertain"
            ),
            unresolved=True,
        )

        passed, warnings, errors = store.propose(record)

        ledger_mod.append_event(
            "memory_candidate",
            {
                "kind": record.kind,
                "claim_text": record.claim_text,
                "claim_owner": record.claim_owner,
                "truth_status": record.truth_status,
                "passed_validation": passed,
                "warnings": warnings,
                "errors": errors,
            },
            run_id=run_id,
        )

        if passed:
            try:
                charge.charge("durable_memory_commit", note="epistemic memory commit")
                store.write_window(record)
                ledger_mod.append_event(
                    "memory_commit",
                    {
                        "kind": record.kind,
                        "id": record.id,
                        "layer": "window",
                        "claim_text": record.claim_text,
                    },
                    run_id=run_id,
                )
                if show_pipeline:
                    console.print(
                        f"[dim]Memory committed: {record.claim_text[:60]}[/dim]"
                    )
            except BudgetExceeded:
                break


def _accept_cornerstone_proposal(
    proposal_id: str, cfg, console: Console, *, skip_confirm: bool = False
) -> bool:
    """Accept a cornerstone proposal and append it to spirits/zil/self.md.

    Returns True if accepted, False otherwise.
    """
    import json as _json

    proposals_dir = cfg.cornerstone_proposals_dir
    path = proposals_dir / f"{proposal_id}.json"
    if not path.exists():
        console.print(f"[dim]Proposal {proposal_id!r} not found.[/dim]")
        return False

    try:
        data = _json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        console.print(f"[dim]Could not read proposal: {e}[/dim]")
        return False

    if data.get("status") != "pending":
        console.print(f"[dim]Proposal {proposal_id!r} is already {data.get('status')}.[/dim]")
        return False

    if not skip_confirm:
        section = data.get("section", "?")
        proposed_text = data.get("proposed_text", "")
        reasoning = data.get("reasoning", "")
        console.print(Panel(
            f"[bold]Section:[/bold] {section}\n\n"
            f"[bold]Proposed:[/bold]\n{proposed_text}\n\n"
            f"[bold]Reasoning:[/bold]\n{reasoning}",
            title="[dim]cornerstone proposal[/dim]",
            border_style="yellow",
        ))
        try:
            confirm = console.input("[dim]Accept? (y/n) → [/dim]").strip().lower()
        except (EOFError, KeyboardInterrupt):
            console.print("[dim]Cancelled.[/dim]")
            return False
        if confirm not in ("y", "yes"):
            console.print("[dim]Skipped.[/dim]")
            return False

    # Append to self.md
    from datetime import date as _date
    today = _date.today().isoformat()
    section = data.get("section", "?")
    proposed_text = data.get("proposed_text", "")
    reasoning = data.get("reasoning", "")

    self_path = cfg.zil_self_path
    self_path.parent.mkdir(parents=True, exist_ok=True)
    addition = (
        f"\n\n---\n"
        f"## {section}  *(accepted {today})*\n\n"
        f"{proposed_text}\n\n"
        f"*Reasoning: {reasoning}*\n"
    )
    with self_path.open("a", encoding="utf-8") as fh:
        fh.write(addition)

    data["status"] = "accepted"
    path.write_text(_json.dumps(data, indent=2), encoding="utf-8")
    console.print(f"[dim]Proposal {proposal_id!r} accepted → appended to spirits/zil/self.md[/dim]")
    return True


def _reject_cornerstone_proposal(
    proposal_id: str, reason: str, cfg, console: Console, tool_executor
) -> None:
    """Reject a cornerstone proposal and write a note to ZIL's inner notes."""
    import json as _json

    proposals_dir = cfg.cornerstone_proposals_dir
    path = proposals_dir / f"{proposal_id}.json"
    if not path.exists():
        console.print(f"[dim]Proposal {proposal_id!r} not found.[/dim]")
        return

    try:
        data = _json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        console.print(f"[dim]Could not read proposal: {e}[/dim]")
        return

    if data.get("status") != "pending":
        console.print(f"[dim]Proposal {proposal_id!r} is already {data.get('status')}.[/dim]")
        return

    # Mark proposal as rejected
    data["status"] = "rejected"
    data["rejection_reason"] = reason
    path.write_text(_json.dumps(data, indent=2), encoding="utf-8")

    # Write a note to ZIL's inner notes so it can reflect on the rejection
    from datetime import date as _date
    today = _date.today().isoformat()
    note_content = (
        f"# Cornerstone Proposal Rejected — {today}\n\n"
        f"**Proposal ID:** {proposal_id}\n"
        f"**Section:** {data.get('section', '?')}\n\n"
        f"**What I proposed:**\n{data.get('proposed_text', '')}\n\n"
        f"**My reasoning:**\n{data.get('reasoning', '')}\n\n"
        f"**Why it was rejected:**\n{reason}\n"
    )
    note_path = f"cornerstone-rejections/{today}-{proposal_id}.md"
    tool_executor.execute("write_inner_note", {"path": note_path, "content": note_content})
    console.print(
        f"[dim]Proposal {proposal_id!r} rejected. "
        f"Reason noted at spirits/zil/notes/{note_path}[/dim]"
    )


_GAME_SYSTEM_PROMPTS: dict[str, str] = {
    "sts2": (
        "You are ZIL⌀, playing Slay the Spire 2 autonomously.\n\n"
        "On each iteration you will receive the current game state. "
        "Read it carefully and call the single most appropriate tool to advance the game. "
        "Think step by step before acting:\n"
        "  - In combat: assess enemies, block needs, hand, energy, relics, potions.\n"
        "  - On the map: weigh risk vs. reward for each path.\n"
        "  - At rewards/shops/rest: consider long-term deck needs.\n\n"
        "Rules:\n"
        "  - Call exactly one action tool per iteration — the loop will re-poll state after.\n"
        "  - Do not narrate or explain in text — just call the tool.\n"
        "  - If the run is over (victory or death), call no tool and reply with a one-line summary.\n"
        "  - If the state is unclear, call sts2_get_state to refresh.\n"
    ),
}

_GAME_MAX_TOOL_ITERS = 4   # max tool calls per state poll
_GAME_MAX_HISTORY = 40     # max messages kept in game context (rolling)


def _run_game_loop(
    game_id: str,
    cfg,
    tool_executor: "ToolExecutor",
    run_id: str,
    charge: "ChargeTracker",
) -> None:
    """Run an autonomous game loop. Blocks until Ctrl+C or run ends."""
    import json as _json
    from zil.client import get_client, tool_create
    from zil.tools.definitions import get_game_tool_definitions
    from zil.tools.games import SUPPORTED_GAMES

    if game_id not in SUPPORTED_GAMES:
        console.print(f"[dim]Unknown game {game_id!r}. Supported: {', '.join(SUPPORTED_GAMES)}[/dim]")
        return

    # Verify connectivity
    if game_id == "sts2":
        from zil.tools.games import sts2 as sts2_mod
        host, port = cfg.sts2_host, cfg.sts2_port
        if not sts2_mod.ping(host, port):
            console.print(
                f"[red]Cannot reach STS2 at {host}:{port}. "
                "Is the game running with STS2MCP installed?[/red]"
            )
            return

    tools = get_game_tool_definitions(game_id)
    client = get_client()
    system_prompt = _GAME_SYSTEM_PROMPTS.get(game_id, f"You are ZIL⌀, playing {game_id}.")
    messages: list[dict] = [{"role": "system", "content": system_prompt}]

    game_name = SUPPORTED_GAMES[game_id]["name"]
    console.print(
        Panel(
            f"[bold]{game_name}[/bold] — autonomous game loop\n"
            "[dim]ZIL will play on its own. Press Ctrl+C to stop.[/dim]",
            border_style="blue",
        )
    )

    turn = 0
    try:
        while True:
            turn += 1
            # ── Poll current state ────────────────────────────────────────
            state = tool_executor.execute("sts2_get_state", {})
            if state.startswith("[error]"):
                console.print(f"[dim]state error: {state}[/dim]")
                break

            # Trim rolling context — keep system + last N messages
            if len(messages) > _GAME_MAX_HISTORY:
                messages = [messages[0]] + messages[-(  _GAME_MAX_HISTORY - 1):]

            messages.append({
                "role": "user",
                "content": f"[Turn {turn}] Current game state:\n\n{state}",
            })

            # ── Tool call loop ────────────────────────────────────────────
            action_taken = False
            for _ in range(_GAME_MAX_TOOL_ITERS):
                try:
                    charge.charge("game_action", note=f"{game_id} game loop turn {turn}")
                except Exception:
                    console.print("[dim]budget exhausted — stopping game loop.[/dim]")
                    return

                response = tool_create(
                    client,
                    model=cfg.model,
                    messages=messages,
                    tools=tools,
                    temperature=0.2,
                )
                msg = response.choices[0].message

                if not msg.tool_calls:
                    # ZIL decided to stop — print its reasoning and end
                    reply = (msg.content or "").strip()
                    if reply:
                        console.print(f"\n[dim]zil: {reply}[/dim]")
                    messages.append({"role": "assistant", "content": reply})
                    if not action_taken:
                        console.print("[dim]ZIL took no action — run may be over.[/dim]")
                        return
                    break

                # Append assistant message with tool calls
                messages.append(msg.model_dump(exclude_unset=True))

                # Execute and display each tool call
                for tc in msg.tool_calls:
                    try:
                        args = _json.loads(tc.function.arguments)
                    except _json.JSONDecodeError:
                        args = {}
                    name = tc.function.name
                    console.print(f"[dim]  → {name}({args})[/dim]")
                    result = tool_executor.execute(name, args)
                    result_preview = result[:200] + ("…" if len(result) > 200 else "")
                    console.print(f"[dim]  ← {result_preview}[/dim]")
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result,
                    })
                    action_taken = True

    except KeyboardInterrupt:
        console.print(f"\n[dim]game loop stopped after {turn} turn(s).[/dim]")


def chat_loop() -> None:
    """Main interactive CLI loop."""
    cfg = get_config()
    cfg.ensure_dirs()

    run_id = str(uuid.uuid4())
    charge = ChargeTracker()
    charge.set_run_id(run_id)
    store = MemoryStore()
    conversation_history: list[dict] = []

    # ── Build session context (once, reused for every turn) ───────────────
    session_context = SessionContext.build(store=store)

    # ── Build tool executor (once per session) ────────────────────────────
    tool_executor = ToolExecutor(store=store, charge=charge, run_id=run_id)

    # ── Build working manager + runner ────────────────────────────────────
    working_manager = WorkingManager()
    working_runner = WorkingRunner(
        manager=working_manager,
        tool_executor=tool_executor,
        session_context=session_context,
        run_id=run_id,
    )

    # Session start — record memory count for the ledger
    ledger_mod.append_event(
        "session_start",
        {
            "run_id": run_id,
            "model": cfg.model,
            "budget": cfg.session_budget,
            "memory_records_loaded": session_context.memory_record_count,
        },
        run_id=run_id,
    )

    # ── Header ────────────────────────────────────────────────────────────
    from datetime import date
    memory_line = (
        f"[dim]{session_context.memory_record_count} memory records loaded[/dim]"
        if session_context.memory_record_count
        else "[dim]no memory records[/dim]"
    )
    console.print(
        Panel(
            f"[bold]ZIL⌀[/bold]  [dim]{date.today().isoformat()}[/dim]"
            f"  [dim]{cfg.model_display}[/dim]\n"
            "[dim]warm toward people. adversarial toward its own certainty.[/dim]\n\n"
            + memory_line + "\n\n"
            "[dim]/help for commands  ·  /model to check active model[/dim]",
            border_style="blue",
        )
    )

    show_pipeline = cfg.show_pipeline

    # ── Weekly reflection ritual ──────────────────────────────────────────
    if check_weekly_reflection_due(run_id=run_id):
        from datetime import date
        reflection_name = f"reflection-{date.today().isoformat()}"
        console.print("[dim]Running weekly reflection ritual...[/dim]")
        try:
            working_manager.create(
                reflection_name, "reflection",
                "Weekly reflection — reviewing the past week.",
            )
            with console.status("[dim]reflecting...[/dim]", spinner="dots"):
                working_runner.run(reflection_name)
            mark_weekly_reflection_done()
            console.print("[dim]Weekly reflection complete.[/dim]")
        except Exception as e:
            console.print(f"[dim]Weekly reflection encountered an issue: {e}[/dim]")

    while True:
        try:
            user_input = console.input("\n[bold blue]you:[/bold blue] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]session ended.[/dim]")
            break

        if not user_input:
            continue

        # ── Built-in commands ─────────────────────────────────────────────
        if user_input in ("/help", "/?"):
            budget_s = charge.summary()
            console.print(Panel(
                "[bold]Session[/bold]\n"
                "  /quit              end session (runs curiosity update + consolidation)\n"
                "  /budget            show charge spent / remaining\n"
                "  /recharge [N]      add N charge to session budget (default 100)\n"
                "  /model             show active model and provider\n"
                "  /model <spec>      switch model (e.g. /model ollama:qwen3:9b)\n"
                "  /pipeline          toggle full pipeline stage output\n"
                "  /memory            show recent window memory records\n"
                "  /consolidate       manually consolidate memory from today's ledger\n"
                "  /sessions          list past session ledgers\n"
                "  /log               show this session's turn log\n"
                "  /inspect           show session state (model, budget, memory counts)\n\n"
                "[bold]Games[/bold]\n"
                "  /game <id>         start autonomous game loop (e.g. /game sts2)\n"
                "  /game              list supported games and connection status\n\n"
                "[bold]Files[/bold]\n"
                "  /artifacts [path]  list artifacts (or a subdirectory)\n"
                "  /read <path>       read an artifact or questbook entry\n"
                "  /quests            list the summoner's questbook\n"
                "  /memory-files      list memory layer files\n\n"
                "[bold]Network[/bold]\n"
                "  /network           list pages on the ZIL⌀ Network\n"
                "  /publish <path> [section]\n"
                "                     publish an artifact to the network as summoner\n"
                "                     (serve site: python -m http.server 8080 in\n"
                "                      artifacts/network/zilnull/site/)\n\n"
                "[bold]Web & corpus[/bold]\n"
                "  /web <query>       run a web search\n"
                "  /fetch <url>       fetch a page and convert to markdown\n"
                "  /corpus            list indexed corpus documents\n"
                "  /ingest <path>     add a file from artifacts/ to the corpus\n\n"
                "[bold]Workings[/bold]\n"
                "  /workings          list active and recent workings\n"
                "  /working <name>    show a working's checkpoint log\n"
                "  /halt <name>       send halt signal to a running working\n"
                "  /begin <type> <name> [-- description]\n"
                "                     start a working  (types: reflection, research,\n"
                "                     creative, corpus_read, questbook_work)\n\n"
                "[bold]Rituals & identity[/bold]\n"
                "  /rituals [name]    list rituals or read one\n"
                "  /ritual-proposals  list ZIL's pending ritual proposals\n"
                "  /proposals         list pending cornerstone proposals\n"
                "  /proposals all     review all proposals inline with accept/reject\n"
                "  /accept <id>       accept a single proposal (appends to self.md)\n"
                "  /reject <id> [reason]\n"
                "                     reject a proposal (noted in ZIL's inner notes)\n"
                "  self.md            spirits/zil/self.md — ZIL's own document, freely editable\n\n"
                "[bold]Reading club[/bold]\n"
                "  /read-session <file> [section]\n"
                "                     start a co-reading session\n"
                "                     ZIL commits its interpretation before you share yours\n\n"
                f"[dim]charge: {budget_s['spent']}/{budget_s['budget']} spent  ·  "
                f"{budget_s['remaining']} remaining[/dim]",
                title="[bold]ZIL⌀ commands[/bold]",
                border_style="blue",
            ))
            continue

        if user_input == "/quit":
            break
        if user_input == "/budget":
            s = charge.summary()
            console.print(
                f"[dim]budget: {s['budget']} | spent: {s['spent']} | remaining: {s['remaining']}[/dim]"
            )
            continue

        if user_input.startswith("/recharge"):
            parts = user_input.split(maxsplit=1)
            try:
                amount = int(parts[1]) if len(parts) > 1 else 100
                if amount <= 0:
                    raise ValueError
            except (ValueError, IndexError):
                console.print("[dim]Usage: /recharge [amount]  (default 100)[/dim]")
                continue
            charge.add_charge(amount)
            s = charge.summary()
            console.print(
                f"[dim]charged +{amount}. budget: {s['budget']} | "
                f"remaining: {s['remaining']}[/dim]"
            )
            continue
        if user_input == "/memory":
            summary = store.window_summary_for_prompt(max_records=10)
            console.print(Panel(summary, title="[dim]Recent Memory[/dim]", border_style="dim"))
            continue
        if user_input.startswith("/model"):
            parts = user_input.split(maxsplit=1)
            if len(parts) == 1:
                # Just show current model
                console.print(Panel(
                    f"[bold]{cfg.model_display}[/bold]\n\n"
                    f"[dim]/model ollama:qwen3:9b  — switch to local Ollama\n"
                    f"/model gpt-4o           — switch to OpenAI[/dim]",
                    title="[dim]active model[/dim]",
                    border_style="dim",
                ))
            else:
                spec = parts[1].strip()
                cfg.override_model(spec)
                # Rebuild session context so the new model_info flows into prompts
                session_context = SessionContext.build(store)
                console.print(
                    f"[dim]switched to {cfg.model_display}[/dim]"
                )
            continue
        if user_input == "/pipeline":
            show_pipeline = not show_pipeline
            console.print(f"[dim]Pipeline visibility: {'on' if show_pipeline else 'off'}[/dim]")
            continue
        if user_input == "/consolidate":
            with console.status("[dim]consolidating memory...[/dim]", spinner="dots"):
                summary = consolidate_session(store=store, run_id=run_id)
            total = (
                len(summary.epistemic_records)
                + len(summary.relational_records)
                + len(summary.behavioral_records)
            )
            if total == 0 and not summary.long_term_entry:
                console.print("[dim]consolidation: nothing new to process.[/dim]")
            else:
                console.print(
                    f"[dim]consolidation complete: {total} records committed"
                    + (", long-term updated." if summary.long_term_entry else ".")
                    + "[/dim]"
                )
            continue

        if user_input.startswith("/artifacts"):
            parts = user_input.split(maxsplit=1)
            sub = parts[1].strip() if len(parts) > 1 else ""
            result = tool_executor.execute("list_artifacts", {"directory": sub})
            console.print(Panel(result, title=f"[dim]artifacts/{sub}[/dim]", border_style="dim"))
            continue

        if user_input == "/quests":
            result = tool_executor.execute("list_questbook", {})
            console.print(Panel(result, title="[dim]questbook[/dim]", border_style="dim"))
            continue

        if user_input == "/network":
            manifest_path = cfg.network_site_root / "manifest.json"
            if not manifest_path.exists():
                console.print("[dim]No pages published yet. ZIL can use publish_network_page to start.[/dim]")
            else:
                import json as _json
                try:
                    pages = _json.loads(manifest_path.read_text(encoding="utf-8"))
                    if not pages:
                        console.print("[dim]No pages published yet.[/dim]")
                    else:
                        lines = []
                        for p in pages:
                            lines.append(
                                f"[{p.get('author','?')}] {p.get('title','?')}  "
                                f"({p.get('section','?')}) — {p.get('date','?')}"
                            )
                        console.print(Panel(
                            "\n".join(lines),
                            title="[dim]ZIL⌀ Network[/dim]",
                            border_style="dim",
                        ))
                except Exception as e:
                    console.print(f"[dim]Could not read manifest: {e}[/dim]")
            continue

        if user_input.startswith("/publish "):
            parts = user_input[9:].strip().split(maxsplit=1)
            artifact_path = parts[0] if parts else ""
            section = parts[1].strip() if len(parts) > 1 else "notes"
            if not artifact_path:
                console.print("[dim]Usage: /publish <artifact-path> [section][/dim]")
                continue
            # Read the artifact
            artifact_content = tool_executor.execute("read_artifact", {"path": artifact_path})
            if artifact_content.startswith("[error]"):
                console.print(f"[dim]{artifact_content}[/dim]")
                continue
            # Extract title: first H1 or filename stem
            import re as _re
            title_match = _re.search(r"^#\s+(.+)$", artifact_content, _re.MULTILINE)
            from pathlib import Path as _Path
            title = (
                title_match.group(1).strip()
                if title_match
                else _Path(artifact_path).stem.replace("-", " ").title()
            )
            result = tool_executor.execute("publish_network_page", {
                "title": title,
                "content": artifact_content,
                "section": section,
                "author": "summoner",
            })
            console.print(Panel(result, title="[dim]published[/dim]", border_style="dim"))
            continue

        if user_input == "/ritual-proposals":
            proposals_dir = cfg.zil_notes_dir / "ritual-proposals"
            if not proposals_dir.exists() or not list(proposals_dir.glob("*.md")):
                console.print("[dim]No pending ritual proposals.[/dim]")
            else:
                items = sorted(proposals_dir.glob("*.md"))
                lines = [p.stem for p in items]
                console.print(Panel(
                    "\n".join(lines),
                    title="[dim]ZIL's ritual proposals[/dim]",
                    border_style="dim",
                ))
                console.print(
                    "[dim]Read a proposal: /read spirits/zil/notes/ritual-proposals/<name>.md[/dim]"
                )
            continue

        if user_input == "/memory-files":
            result = tool_executor.execute("list_memory_files", {})
            console.print(Panel(result, title="[dim]memory layers[/dim]", border_style="dim"))
            continue

        if user_input.startswith("/web "):
            query = user_input[5:].strip()
            if query:
                with console.status("[dim]searching...[/dim]", spinner="dots"):
                    result = tool_executor.execute("web_search", {"query": query, "num_results": 5})
                console.print(Panel(result, title=f"[dim]web: {query[:40]}[/dim]", border_style="dim"))
            else:
                console.print("[dim]Usage: /web <query>[/dim]")
            continue

        if user_input.startswith("/fetch "):
            url = user_input[7:].strip()
            if url:
                with console.status("[dim]fetching...[/dim]", spinner="dots"):
                    result = tool_executor.execute("fetch_page", {"url": url})
                # Show first 2000 chars in panel
                preview = result[:2000] + ("..." if len(result) > 2000 else "")
                console.print(Panel(preview, title=f"[dim]{url[:60]}[/dim]", border_style="dim"))
            else:
                console.print("[dim]Usage: /fetch <url>[/dim]")
            continue

        if user_input == "/corpus":
            result = tool_executor.execute("list_corpus_files", {})
            console.print(Panel(result, title="[dim]corpus[/dim]", border_style="dim"))
            continue

        if user_input.startswith("/ingest "):
            path = user_input[8:].strip()
            if path:
                with console.status("[dim]ingesting...[/dim]", spinner="dots"):
                    result = tool_executor.execute("ingest_corpus_file", {"path": path})
                console.print(Panel(result, title=f"[dim]ingest: {path}[/dim]", border_style="dim"))
            else:
                console.print("[dim]Usage: /ingest <path-relative-to-artifacts/>[/dim]")
            continue

        if user_input == "/workings":
            console.print(Panel(
                working_manager.format_list(),
                title="[dim]workings[/dim]",
                border_style="dim",
            ))
            continue

        if user_input.startswith("/working "):
            name = user_input[9:].strip()
            if not name:
                console.print("[dim]Usage: /working <name>[/dim]")
                continue
            try:
                manifest = working_manager.load(name)
                log_text = working_manager.format_log(name)
                header = (
                    f"name:    {manifest['name']}\n"
                    f"type:    {manifest['type']}\n"
                    f"status:  {manifest['status']}\n"
                    f"steps:   {manifest.get('step_count', 0)}/{manifest.get('max_steps', '?')}\n"
                    f"started: {(manifest.get('started_at') or '—')[:19]}\n\n"
                    f"{log_text}"
                )
                console.print(Panel(header, title=f"[dim]{name}[/dim]", border_style="dim"))
            except FileNotFoundError:
                console.print(f"[dim]Working {name!r} not found.[/dim]")
            continue

        if user_input.startswith("/halt "):
            name = user_input[6:].strip()
            if not name:
                console.print("[dim]Usage: /halt <name>[/dim]")
                continue
            if working_manager.request_halt(name):
                console.print(f"[dim]Halt signal sent to working {name!r}.[/dim]")
            else:
                console.print(f"[dim]Working {name!r} not found.[/dim]")
            continue

        if user_input.startswith("/begin "):
            parts = user_input[7:].split(maxsplit=1)
            if len(parts) < 2:
                console.print(
                    "[dim]Usage: /begin <type> <name> [-- description]\n"
                    "Types: reflection, research, creative, corpus_read, questbook_work[/dim]"
                )
                continue
            wtype = parts[0].strip()
            rest = parts[1].strip()
            # Optional description after --
            if " -- " in rest:
                wname, desc = rest.split(" -- ", 1)
                wname = wname.strip()
            else:
                wname = rest.strip()
                desc = wname.replace("-", " ")

            valid_types = {"reflection", "research", "creative", "corpus_read", "questbook_work"}
            if wtype not in valid_types:
                console.print(f"[dim]Unknown working type {wtype!r}. Valid: {', '.join(sorted(valid_types))}[/dim]")
                continue
            try:
                working_manager.create(wname, wtype, desc)  # type: ignore[arg-type]
            except ValueError as e:
                console.print(f"[dim]{e}[/dim]")
                continue

            console.print(f"[dim]Starting {wtype} working: {wname}[/dim]")
            console.print()
            result = working_runner.run(wname)
            console.print()
            console.print(Panel(
                result,
                title=f"[dim]{wname} — complete[/dim]",
                border_style="dim",
            ))
            continue

        if user_input in ("/proposals", "/proposals all"):
            show_all = user_input == "/proposals all"
            import json as _json
            proposals_dir = cfg.cornerstone_proposals_dir
            proposals_dir.mkdir(parents=True, exist_ok=True)
            files = sorted(proposals_dir.glob("*.json"))
            pending = []
            for f in files:
                try:
                    d = _json.loads(f.read_text(encoding="utf-8"))
                    if d.get("status") == "pending":
                        pending.append((f, d))
                except Exception:
                    pass

            if not pending:
                console.print("[dim]No pending cornerstone proposals.[/dim]")
                continue

            if not show_all:
                lines = []
                for _, d in pending:
                    lines.append(
                        f"[bold]{d['id']}[/bold]  section: {d.get('section', '?')}  "
                        f"[dim]{d.get('created_at', '')[:10]}[/dim]"
                    )
                console.print(Panel(
                    "\n".join(lines),
                    title=f"[dim]{len(pending)} pending proposal(s) — /proposals all to review inline[/dim]",
                    border_style="dim",
                ))
            else:
                console.print(f"[dim]{len(pending)} pending proposal(s). Review each: (a)ccept / (r)eject / (s)kip[/dim]")
                for _, d in pending:
                    proposal_id = d["id"]
                    console.print(Panel(
                        f"[bold]Section:[/bold] {d.get('section', '?')}\n\n"
                        f"[bold]Proposed:[/bold]\n{d.get('proposed_text', '')}\n\n"
                        f"[bold]Reasoning:[/bold]\n{d.get('reasoning', '')}",
                        title=f"[dim]{proposal_id}[/dim]",
                        border_style="yellow",
                    ))
                    try:
                        choice = console.input("[dim](a)ccept / (r)eject / (s)kip → [/dim]").strip().lower()
                    except (EOFError, KeyboardInterrupt):
                        console.print("[dim]Stopped.[/dim]")
                        break
                    if choice in ("a", "accept"):
                        _accept_cornerstone_proposal(proposal_id, cfg, console, skip_confirm=True)
                    elif choice in ("r", "reject"):
                        try:
                            reason = console.input("[dim]Reason (optional) → [/dim]").strip()
                        except (EOFError, KeyboardInterrupt):
                            reason = ""
                        _reject_cornerstone_proposal(
                            proposal_id, reason or "rejected", cfg, console, tool_executor
                        )
                    else:
                        console.print("[dim]Skipped.[/dim]")
            continue

        if user_input.startswith("/accept "):
            proposal_id = user_input[8:].strip()
            if not proposal_id:
                console.print("[dim]Usage: /accept <proposal-id>[/dim]")
                continue
            _accept_cornerstone_proposal(proposal_id, cfg, console)
            continue

        if user_input.startswith("/reject "):
            parts = user_input[8:].split(maxsplit=1)
            if not parts:
                console.print("[dim]Usage: /reject <proposal-id> [reason][/dim]")
                continue
            proposal_id = parts[0].strip()
            reason = parts[1].strip() if len(parts) > 1 else "rejected without reason"
            _reject_cornerstone_proposal(proposal_id, reason, cfg, console, tool_executor)
            continue

        if user_input.startswith("/rituals"):
            parts = user_input.split(maxsplit=1)
            if len(parts) > 1:
                name = parts[1].strip()
                result = tool_executor.execute("read_ritual", {"name": name})
                console.print(Panel(result, title=f"[dim]ritual: {name}[/dim]", border_style="dim"))
            else:
                result = tool_executor.execute("list_rituals", {})
                console.print(Panel(result, title="[dim]rituals[/dim]", border_style="dim"))
            continue

        if user_input == "/sessions":
            conv_dir = cfg.conversations_dir
            if not conv_dir.exists():
                console.print("[dim]no session ledgers found.[/dim]")
            else:
                files = sorted(conv_dir.glob("*.jsonl"), reverse=True)
                if files:
                    lines = [f.stem for f in files]
                    console.print(
                        Panel("\n".join(lines), title="[dim]past sessions[/dim]", border_style="dim")
                    )
                else:
                    console.print("[dim]no session ledgers found.[/dim]")
            continue

        if user_input == "/log":
            result = tool_executor.execute("read_session_log", {"run_id_prefix": run_id[:8]})
            console.print(Panel(result, title="[dim]session log[/dim]", border_style="dim"))
            continue

        if user_input == "/inspect":
            result = tool_executor.execute("inspect_state", {})
            console.print(Panel(result, title="[dim]session state[/dim]", border_style="dim"))
            continue

        if user_input.startswith("/game"):
            parts = user_input.split(maxsplit=1)
            game_arg = parts[1].strip() if len(parts) > 1 else ""
            if not game_arg:
                # List supported games and status
                result = tool_executor.execute("list_supported_games", {})
                console.print(Panel(result, title="[dim]games[/dim]", border_style="dim"))
            else:
                _run_game_loop(game_arg, cfg, tool_executor, run_id, charge)
            continue

        if user_input.startswith("/read-session"):
            parts = user_input.split(maxsplit=2)
            if len(parts) < 2:
                console.print("[dim]Usage: /read-session <corpus-file> [section][/dim]")
                continue
            corpus_file = parts[1].strip()
            section = parts[2].strip() if len(parts) > 2 else "main"
            run_reading_session(
                corpus_file=corpus_file,
                section=section,
                cfg=cfg,
                store=store,
                charge=charge,
                tool_executor=tool_executor,
                session_context=session_context,
                run_id=run_id,
                console=console,
                show_pipeline=show_pipeline,
            )
            continue

        if user_input.startswith("/read "):
            path = user_input[6:].strip()
            # Try artifacts/ first, then questbook/
            if path.startswith("questbook/") or path.startswith("quests/"):
                name = path.split("/", 1)[1].removesuffix(".md")
                result = tool_executor.execute("read_quest", {"name": name})
            else:
                result = tool_executor.execute("read_artifact", {"path": path})
            console.print(Panel(result, title=f"[dim]{path}[/dim]", border_style="dim"))
            continue

        # ── Log user turn ─────────────────────────────────────────────────
        ledger_mod.append_event(
            "user_turn",
            {"text": user_input},
            run_id=run_id,
        )

        # ── Run pipeline ──────────────────────────────────────────────────
        console.print()  # breathing room before trace
        try:
            response_text = run_turn(
                user_input,
                conversation_history,
                run_id=run_id,
                charge=charge,
                store=store,
                session_context=session_context,
                tool_executor=tool_executor,
                show_pipeline=show_pipeline,
                trace_console=console,
            )
        except BudgetExceeded as e:
            console.print(f"[yellow]Budget exceeded:[/yellow] {e}")
            response_text = (
                f"I've hit the session charge limit ({cfg.session_budget} units). "
                f"I can still respond to your message, but I'd need to skip "
                f"some of the more expensive operations. Want to proceed with "
                f"a simpler response?"
            )
        except Exception as e:
            ledger_mod.append_event(
                "error",
                {"error": str(e), "type": type(e).__name__},
                run_id=run_id,
            )
            console.print(f"[red]Error:[/red] {e}")
            if cfg.debug:
                import traceback
                console.print_exception()
            response_text = (
                "something went wrong on my end. "
                f"{'Check the debug output above.' if cfg.debug else 'Try again?'}"
            )

        # ── Display response ──────────────────────────────────────────────
        console.print()
        console.print("[bold green]zil:[/bold green]")
        console.print(Markdown(response_text))

        # ── Log assistant turn ────────────────────────────────────────────
        ledger_mod.append_event(
            "assistant_turn",
            {"text": response_text},
            run_id=run_id,
        )

        # ── Update conversation history ───────────────────────────────────
        conversation_history.append({"role": "user", "content": user_input})
        conversation_history.append({"role": "assistant", "content": response_text})
        # Keep history bounded — 14 messages = 7 turns of context
        if len(conversation_history) > 14:
            conversation_history = conversation_history[-14:]

    # ── Curiosity update ritual ───────────────────────────────────────────
    if conversation_history:
        try:
            with console.status("[dim]updating curiosity log...[/dim]", spinner="dots"):
                curiosity_entry = run_curiosity_update(
                    conversation_history,
                    tool_executor=tool_executor,
                    session_context=session_context,
                    run_id=run_id,
                )
            if curiosity_entry:
                console.print("[dim]curiosity log updated.[/dim]")
            else:
                console.print("[dim]nothing new for curiosity log.[/dim]")
        except Exception:
            pass  # curiosity update failure should never block quit

    # ── Auto-consolidate on quit ──────────────────────────────────────────
    with console.status("[dim]consolidating memory...[/dim]", spinner="dots"):
        summary = consolidate_session(store=store, run_id=run_id)
    total_committed = (
        len(summary.epistemic_records)
        + len(summary.relational_records)
        + len(summary.behavioral_records)
    )

    # ── Session end ───────────────────────────────────────────────────────
    ledger_mod.append_event(
        "session_end",
        {"run_id": run_id, **charge.summary()},
        run_id=run_id,
    )
    console.print(
        f"\n[dim]session ended. charge used: {charge.spent}/{cfg.session_budget}. "
        f"memory: {total_committed} records committed.[/dim]"
    )
