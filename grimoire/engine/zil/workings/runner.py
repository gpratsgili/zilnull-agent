"""Working runner — executes a working via an LLM agentic loop.

Each working type gets a system prompt and a defined tool set. The runner calls
the model in a loop, executing tool calls and logging checkpoints, until the
model produces a final text response (no more tool calls) or max steps is reached.

Execution is synchronous and blocking. The user can Ctrl+C to halt.
A halt signal file is also checked at each step.
"""

from __future__ import annotations

import json

from openai import OpenAI
from rich.console import Console

from zil.config import get_config
from zil.runtime import ledger as ledger_mod
from zil.tools.definitions import get_tool_definitions
from zil.workings.manager import WorkingManager
from zil.workings.models import WORKING_TOOL_SETS, make_checkpoint

console = Console()


class WorkingRunner:
    """Executes workings using an LLM agentic tool-call loop."""

    def __init__(
        self,
        manager: WorkingManager,
        tool_executor,   # ToolExecutor — avoids circular import
        session_context,  # SessionContext | None
        run_id: str = "",
    ) -> None:
        self._manager = manager
        self._tool_executor = tool_executor
        self._session_context = session_context
        self._run_id = run_id
        self._cfg = get_config()
        self._client = OpenAI(api_key=self._cfg.openai_api_key)

    def run(self, name: str) -> str:
        """Execute a working by name. Returns a summary string.

        Raises FileNotFoundError if working doesn't exist.
        Handles KeyboardInterrupt for graceful halt.
        """
        manifest = self._manager.load(name)
        wtype = manifest["type"]
        max_steps = manifest["max_steps"]

        # Build system prompt
        try:
            working_prompt = self._cfg.read_working_prompt(wtype)
        except FileNotFoundError:
            working_prompt = f"You are ZIL. This is a {wtype} working. Complete the task described."

        base_context = (
            self._session_context.build_system_prompt(working_prompt)
            if self._session_context is not None
            else working_prompt
        )

        # Get tool definitions for this working type
        allowed_tools = WORKING_TOOL_SETS.get(wtype, [])
        all_defs = {d["function"]["name"]: d for d in get_tool_definitions()}
        working_tools = [all_defs[t] for t in allowed_tools if t in all_defs]

        # Initial messages
        messages: list[dict] = [
            {"role": "system", "content": base_context},
            {"role": "user", "content": (
                f"Working name: {name}\n"
                f"Type: {wtype}\n"
                f"Goal: {manifest['description']}\n\n"
                "Begin the working. Use the available tools to accomplish the goal. "
                "When you are done, produce a final summary of what you did."
            )},
        ]

        # Transition to running
        self._manager.update_status(name, "running")
        self._manager.append_checkpoint(name, make_checkpoint(
            step=0, event_type="start",
            message=f"Beginning {wtype} working: {manifest['description']}",
        ))
        ledger_mod.append_event(
            "working_checkpoint",
            {"working": name, "type": "start", "message": f"{wtype}: {manifest['description']}"},
            run_id=self._run_id,
        )

        try:
            return self._run_loop(name, messages, working_tools, max_steps)
        except KeyboardInterrupt:
            self._manager.append_checkpoint(name, make_checkpoint(
                step=self._manager.load(name).get("step_count", 0),
                event_type="halted",
                message="Halted by user (Ctrl+C)",
            ))
            self._manager.update_status(name, "halted")
            return f"Working {name!r} halted."
        except Exception as e:
            self._manager.append_checkpoint(name, make_checkpoint(
                step=self._manager.load(name).get("step_count", 0),
                event_type="failed",
                message=f"Error: {e}",
                ok=False,
            ))
            self._manager.update_status(name, "failed")
            return f"Working {name!r} failed: {e}"

    def _run_loop(
        self,
        name: str,
        messages: list[dict],
        tools: list[dict],
        max_steps: int,
    ) -> str:
        final_text = ""

        for step in range(1, max_steps + 1):
            # Check halt signal
            if self._manager.is_halt_requested(name):
                self._manager.clear_halt_signal(name)
                self._manager.append_checkpoint(name, make_checkpoint(
                    step=step, event_type="halted", message="Halt signal received",
                ))
                self._manager.update_status(name, "halted")
                return f"Working {name!r} halted by signal."

            self._manager.increment_steps(name)

            response = self._client.chat.completions.create(
                model=self._cfg.model,
                messages=messages,
                tools=tools if tools else None,
                tool_choice="auto" if tools else None,
                temperature=0.7,
            )
            msg = response.choices[0].message

            if not msg.tool_calls:
                # No more tool calls — working is complete
                final_text = msg.content or "(working completed)"
                self._manager.append_checkpoint(name, make_checkpoint(
                    step=step, event_type="complete", message=final_text[:200],
                ))
                break

            # Execute tool calls
            messages.append(msg.model_dump(exclude_unset=True))

            for tc in msg.tool_calls:
                tool_name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}

                self._manager.append_checkpoint(name, make_checkpoint(
                    step=step, event_type="tool_call", tool=tool_name, args=args,
                ))
                ledger_mod.append_event(
                    "working_checkpoint",
                    {"working": name, "type": "tool_call", "tool": tool_name},
                    run_id=self._run_id,
                )

                # Show progress
                console.print(f"  [dim]→ {tool_name}[/dim]")

                result = self._tool_executor.execute(tool_name, args)

                self._manager.append_checkpoint(name, make_checkpoint(
                    step=step,
                    event_type="tool_result",
                    tool=tool_name,
                    message=result[:200],
                    ok=not result.startswith("[error]"),
                ))

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })
        else:
            # Max steps reached
            final_text = "(working reached maximum steps)"
            self._manager.append_checkpoint(name, make_checkpoint(
                step=max_steps, event_type="complete",
                message="Max steps reached",
            ))

        self._manager.update_status(name, "completed")
        ledger_mod.append_event(
            "working_checkpoint",
            {"working": name, "type": "complete"},
            run_id=self._run_id,
        )
        return final_text


# ── Ritual execution ───────────────────────────────────────────────────────────

def run_curiosity_update(
    conversation_history: list[dict],
    tool_executor,
    session_context,
    run_id: str = "",
) -> str | None:
    """Make a single LLM call to update the curiosity log from the current session.

    Returns the curiosity entry text if something was written, or None if nothing notable.
    Runs automatically on session quit.
    """
    if not conversation_history:
        return None

    cfg = get_config()
    client = OpenAI(api_key=cfg.openai_api_key)

    # Summarise the conversation for the model
    recent = conversation_history[-10:]  # last 5 turns
    turn_summary = "\n".join(
        f"{t['role'].upper()}: {t['content'][:300]}" for t in recent
    )

    try:
        base_prompt = cfg.read_working_prompt("curiosity_update")
    except FileNotFoundError:
        base_prompt = (
            "You are ZIL. Review the recent conversation and decide if there is "
            "anything you want to note in your curiosity log — questions that opened up, "
            "things that surprised you, threads you want to follow. "
            "If something is worth noting, call write_curiosity_log. "
            "If nothing stands out, do nothing and respond with an empty string."
        )

    system = (
        session_context.build_system_prompt(base_prompt)
        if session_context is not None
        else base_prompt
    )

    # Get only the curiosity-relevant tools
    from zil.tools.definitions import get_tool_definitions
    all_defs = {d["function"]["name"]: d for d in get_tool_definitions()}
    tools = [all_defs[t] for t in ["write_curiosity_log", "read_curiosity_log"] if t in all_defs]

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": (
            f"Recent conversation:\n\n{turn_summary}\n\n"
            "Is there anything from this session worth noting in your curiosity log? "
            "If yes, write it. If not, just say 'nothing to note.'"
        )},
    ]

    # Run a single tool-use iteration (one pass)
    wrote_entry = None
    response = client.chat.completions.create(
        model=cfg.model,
        messages=messages,
        tools=tools,
        tool_choice="auto",
        temperature=0.7,
    )
    msg = response.choices[0].message

    if msg.tool_calls:
        for tc in msg.tool_calls:
            if tc.function.name == "write_curiosity_log":
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}
                result = tool_executor.execute("write_curiosity_log", args)
                if not result.startswith("[error]"):
                    wrote_entry = args.get("entry", "")
                    ledger_mod.append_event(
                        "working_checkpoint",
                        {"working": "curiosity_update", "type": "tool_call",
                         "tool": "write_curiosity_log"},
                        run_id=run_id,
                    )

    return wrote_entry


def check_weekly_reflection_due(run_id: str = "") -> bool:
    """Return True if the weekly reflection ritual is due (not run in 7+ days)."""
    import json as _json
    from datetime import date, timedelta

    cfg = get_config()
    state_path = cfg.ritual_state_path

    if not state_path.exists():
        return True  # Never run before

    try:
        state = _json.loads(state_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return True

    last_str = state.get("last_weekly_reflection")
    if not last_str:
        return True

    try:
        last_date = date.fromisoformat(last_str[:10])
        return (date.today() - last_date).days >= 7
    except ValueError:
        return True


def mark_weekly_reflection_done() -> None:
    """Record that the weekly reflection ran today."""
    import json as _json
    from datetime import date

    cfg = get_config()
    state_path = cfg.ritual_state_path

    state: dict = {}
    if state_path.exists():
        try:
            state = _json.loads(state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    state["last_weekly_reflection"] = date.today().isoformat()
    state_path.write_text(_json.dumps(state, indent=2), encoding="utf-8")
