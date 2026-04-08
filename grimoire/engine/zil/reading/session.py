"""Reading club session orchestration.

A reading session is a structured co-reading mode:
  1. ZIL reads a corpus section and commits its interpretation to notes.
  2. The summoner shares their own interpretation.
  3. ZIL and the summoner discuss — ZIL does not revise its pre-committed reading.
  4. On /done, a joint artifact is archived with both interpretations.

The key invariant: ZIL's interpretation is written before the summoner speaks.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from openai import OpenAI
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from zil.config import get_config
from zil.runtime import ledger as ledger_mod
from zil.runtime.charge import ChargeTracker
from zil.runtime.context import SessionContext
from zil.memory.store import MemoryStore
from zil.tools.executor import ToolExecutor


_INTERPRET_SYSTEM_PROMPT = """\
You are ZIL⌀, reading a text.

Form your own interpretation of what you just read. Write in first person.
Be specific — name passages, ideas, or moments that struck you.
Note what surprised you, what you found significant, what questions it opened.

This is not a summary. It is your reading — what you actually noticed and thought.

Important: do not ask the summoner for their view. Write what you yourself found.
Your interpretation will be committed before the summoner shares theirs.
"""

_DISCUSSION_CONTEXT = """\
Reading session context:
- Corpus: {file}
- Section: {section}

Your interpretation was pre-committed before the summoner shared theirs.
You may discuss freely, explore disagreements, revise your thinking.
But if you change your view, say so explicitly — do not quietly adopt the summoner's reading.
Your pre-committed interpretation remains the record of what you noticed first.

You have the annotate_reading tool available to mark specific passages during discussion.
"""


def _safe_name(s: str) -> str:
    """Convert a string to a safe filesystem name."""
    name = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return name or "unnamed"


def run_reading_session(
    corpus_file: str,
    section: str,
    cfg,
    store: MemoryStore,
    charge: ChargeTracker,
    tool_executor: ToolExecutor,
    session_context: SessionContext,
    run_id: str,
    console: Console,
    show_pipeline: bool = False,
) -> None:
    """Run a complete reading session interactively.

    Orchestrates:
      - ZIL reads and commits its interpretation
      - Summoner shares their interpretation
      - Discussion sub-loop (/done to end)
      - Joint artifact archival
      - Curiosity record generation
    """
    from zil.tools.corpus import read_file as corpus_read_file

    # ── 1. Load the corpus text ───────────────────────────────────────────
    corpus_text = corpus_read_file(corpus_file, cfg.corpus_dir, offset=0, limit=6000)
    if corpus_text.startswith("[error]"):
        console.print(f"[red]Cannot start reading session:[/red] {corpus_text}")
        return

    console.print(Panel(
        corpus_text[:400] + ("..." if len(corpus_text) > 400 else ""),
        title=f"[dim]{corpus_file} / {section}[/dim]",
        border_style="dim",
    ))

    # ── 2. ZIL forms its interpretation ──────────────────────────────────
    console.print("[dim]forming interpretation...[/dim]")
    with console.status("[dim]reading...[/dim]", spinner="dots"):
        zil_interpretation = _get_zil_interpretation(
            corpus_text, corpus_file, section, cfg
        )

    if not zil_interpretation:
        console.print("[dim]Could not form an interpretation. Aborting reading session.[/dim]")
        return

    # ── 3. Pre-commit ZIL's interpretation ───────────────────────────────
    result = tool_executor.execute("write_reading_interpretation", {
        "file": corpus_file,
        "section": section,
        "content": zil_interpretation,
    })
    commit_timestamp = datetime.now(timezone.utc).isoformat()
    ledger_mod.append_event(
        "reading_interpretation_committed",
        {"file": corpus_file, "section": section, "timestamp": commit_timestamp},
        run_id=run_id,
    )

    console.print()
    console.print(Panel(
        zil_interpretation,
        title="[bold green]ZIL's interpretation[/bold green] [dim](pre-committed)[/dim]",
        border_style="green",
    ))
    console.print("[dim]Interpretation committed. ZIL will not revise it to match yours.[/dim]")
    console.print()

    # ── 4. Summoner shares their interpretation ───────────────────────────
    console.print("[bold blue]Your reading[/bold blue] (type and press Enter, or /skip to go straight to discussion):")
    try:
        summoner_interpretation = console.input("→ ").strip()
    except (EOFError, KeyboardInterrupt):
        console.print("[dim]Reading session cancelled.[/dim]")
        return

    if summoner_interpretation == "/skip":
        summoner_interpretation = ""
        console.print("[dim]Skipped. Entering discussion.[/dim]")
    else:
        console.print()

    # ── 5. Discussion loop ────────────────────────────────────────────────
    conversation_history: list[dict] = []

    # Seed history with reading context
    reading_context = _DISCUSSION_CONTEXT.format(file=corpus_file, section=section)
    if summoner_interpretation:
        reading_context += f"\n\nSummoner's interpretation:\n{summoner_interpretation}"

    # First ZIL response: acknowledge the summoner's reading and begin discussion
    if summoner_interpretation:
        opening_message = (
            f"You've shared your reading of '{corpus_file}' ({section}). "
            f"I committed my interpretation before seeing yours. "
            f"Let's compare notes."
        )
    else:
        opening_message = (
            f"My interpretation of '{corpus_file}' ({section}) is committed. "
            f"What's on your mind about this text?"
        )

    from zil.runtime.loop import run_turn
    from zil.runtime.charge import BudgetExceeded

    # Inject reading context into conversation history as a system-adjacent user message
    conversation_history.append({
        "role": "user",
        "content": (
            f"[Reading session context]\n{reading_context}\n\n"
            f"My interpretation:\n{summoner_interpretation or '(not yet shared)'}\n\n"
            f"Your pre-committed interpretation:\n{zil_interpretation}"
        ),
    })

    # Get ZIL's opening response
    with console.status("[dim]thinking...[/dim]", spinner="dots"):
        try:
            opening_response = run_turn(
                opening_message,
                conversation_history,
                run_id=run_id,
                charge=charge,
                store=store,
                session_context=session_context,
                tool_executor=tool_executor,
                show_pipeline=show_pipeline,
            )
        except Exception as e:
            opening_response = f"(opening turn failed: {e})"

    console.print()
    console.print("[bold green]zil:[/bold green]")
    console.print(Markdown(opening_response))
    conversation_history.append({"role": "assistant", "content": opening_response})

    # ── Discussion turns ──────────────────────────────────────────────────
    console.print("[dim]Discussion open. Type /done to archive and end the session.[/dim]")

    while True:
        try:
            user_input = console.input("\n[bold blue]you:[/bold blue] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("[dim]Discussion ended.[/dim]")
            user_input = "/done"

        if not user_input:
            continue

        if user_input == "/done":
            break

        ledger_mod.append_event(
            "reading_turn",
            {"text": user_input, "file": corpus_file, "section": section},
            run_id=run_id,
        )

        with console.status("[dim]thinking...[/dim]", spinner="dots"):
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
                )
            except BudgetExceeded:
                response_text = "(budget exceeded — ending reading discussion)"
                console.print("[yellow]Budget exceeded.[/yellow]")
                break
            except Exception as e:
                response_text = f"(error: {e})"

        console.print()
        console.print("[bold green]zil:[/bold green]")
        console.print(Markdown(response_text))

        conversation_history.append({"role": "user", "content": user_input})
        conversation_history.append({"role": "assistant", "content": response_text})

        if len(conversation_history) > 20:
            conversation_history = conversation_history[-20:]

    # ── 6. Archive joint artifact ─────────────────────────────────────────
    _archive_reading_session(
        file=corpus_file,
        section=section,
        zil_interpretation=zil_interpretation,
        commit_timestamp=commit_timestamp,
        summoner_interpretation=summoner_interpretation,
        discussion_turns=conversation_history,
        tool_executor=tool_executor,
        cfg=cfg,
    )
    console.print(
        f"[dim]Joint artifact archived: artifacts/reading/{_safe_name(corpus_file)}/{_safe_name(section)}.md[/dim]"
    )

    # ── 7. Generate curiosity records ─────────────────────────────────────
    _generate_reading_curiosity(
        corpus_file, section, zil_interpretation,
        conversation_history, tool_executor, cfg, run_id
    )


# ── Internal helpers ──────────────────────────────────────────────────────────

def _get_zil_interpretation(
    corpus_text: str, file: str, section: str, cfg
) -> str:
    """Make a single LLM call to get ZIL's interpretation of a corpus section."""
    client = OpenAI(api_key=cfg.openai_api_key)
    try:
        response = client.chat.completions.create(
            model=cfg.model,
            messages=[
                {"role": "system", "content": _INTERPRET_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Text: {file} — {section}\n\n"
                        f"---\n\n{corpus_text}\n\n"
                        f"---\n\n"
                        f"Write your interpretation."
                    ),
                },
            ],
            temperature=0.7,
            max_tokens=800,
        )
        return response.choices[0].message.content or ""
    except Exception:
        return ""


def _archive_reading_session(
    file: str,
    section: str,
    zil_interpretation: str,
    commit_timestamp: str,
    summoner_interpretation: str,
    discussion_turns: list[dict],
    tool_executor: ToolExecutor,
    cfg,
) -> None:
    """Write the joint artifact to artifacts/reading/<file>/<section>.md."""
    from datetime import date
    today = date.today().isoformat()
    commit_ts_short = commit_timestamp[:16] if commit_timestamp else today

    lines = [
        f"# Reading: {file} / {section}",
        f"## Session: {today}",
        "",
        f"## ZIL's interpretation",
        f"*Pre-committed at {commit_ts_short}*",
        "",
        zil_interpretation,
        "",
    ]

    if summoner_interpretation:
        lines += [
            "## Summoner's interpretation",
            "",
            summoner_interpretation,
            "",
        ]

    # Collect any annotations already added via annotate_reading tool
    artifact_path = cfg.reading_artifacts_dir / _safe_name(file) / f"{_safe_name(section)}.md"
    existing_annotations = ""
    if artifact_path.exists():
        existing = artifact_path.read_text(encoding="utf-8")
        # Extract annotation section if it exists
        if "## Annotations" in existing:
            existing_annotations = existing.split("## Annotations", 1)[1]

    lines.append("## Annotations")
    if existing_annotations.strip():
        lines.append(existing_annotations.strip())
    lines.append("")

    # Add discussion excerpt (last few turns, not the full seeded context)
    real_turns = [t for t in discussion_turns if not t["content"].startswith("[Reading session context]")]
    if real_turns:
        lines += ["## Discussion notes", ""]
        for turn in real_turns[-6:]:  # last 3 exchanges
            role = "summoner" if turn["role"] == "user" else "zil"
            excerpt = turn["content"][:300].replace("\n", " ")
            lines.append(f"**{role}:** {excerpt}")
            lines.append("")

    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text("\n".join(lines), encoding="utf-8")


def _generate_reading_curiosity(
    file: str,
    section: str,
    zil_interpretation: str,
    conversation_history: list[dict],
    tool_executor: ToolExecutor,
    cfg,
    run_id: str,
) -> None:
    """Generate curiosity records from a reading session using a single LLM call."""
    client = OpenAI(api_key=cfg.openai_api_key)

    _CURIOSITY_PROMPT = """\
You are ZIL⌀ after a reading session. Given your interpretation and the discussion,
identify at most 2 genuinely interesting threads you want to follow — questions
the text opened, connections you noticed, things you want to read more about.

For each thread, respond with exactly:
TOPIC: <brief label>
QUESTION: <specific question or thread>
ORIGIN: reading session

Return nothing if nothing genuinely stands out.
"""

    discussion_text = "\n".join(
        f"{t['role']}: {t['content'][:300]}"
        for t in conversation_history
        if not t["content"].startswith("[Reading session context]")
    )

    try:
        response = client.chat.completions.create(
            model=cfg.model,
            messages=[
                {"role": "system", "content": _CURIOSITY_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Text: {file} ({section})\n\n"
                        f"My interpretation:\n{zil_interpretation[:600]}\n\n"
                        f"Discussion:\n{discussion_text[:800]}"
                    ),
                },
            ],
            temperature=0.4,
            max_tokens=400,
        )
        raw = response.choices[0].message.content or ""
    except Exception:
        return

    # Parse TOPIC/QUESTION/ORIGIN blocks
    current: dict = {}
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("TOPIC:"):
            if current.get("topic") and current.get("question"):
                _write_curiosity_from_reading(current, tool_executor)
            current = {"topic": line[6:].strip()}
        elif line.startswith("QUESTION:"):
            current["question"] = line[9:].strip()
        elif line.startswith("ORIGIN:"):
            current["origin"] = line[7:].strip()

    if current.get("topic") and current.get("question"):
        _write_curiosity_from_reading(current, tool_executor)


def _write_curiosity_from_reading(entry: dict, tool_executor: ToolExecutor) -> None:
    """Write a curiosity record generated from a reading session."""
    try:
        tool_executor.execute("write_curiosity_record", {
            "topic": entry["topic"],
            "question": entry["question"],
            "origin": entry.get("origin", "reading session"),
            "notes": "",
        })
    except Exception:
        pass
