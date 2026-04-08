"""ZIL⌀ CLI entry point.

Usage:
  zil chat           # Start interactive session
  zil eval           # Run anti-sycophancy benchmark
  zil budget         # Show charge budget (static display)
  zil memory         # Inspect current memory layers
  zil consolidate    # Run memory consolidation for today's session
"""

from __future__ import annotations

import typer
from rich.console import Console

app = typer.Typer(
    name="zil",
    help="ZIL⌀ — honest by design.",
    add_completion=False,
)
console = Console()


@app.command()
def chat(
    model: str = typer.Option(
        "",
        "--model", "-m",
        help=(
            "Model to use for this session. "
            "Format: 'gpt-4o' for OpenAI, or 'ollama:<name>' for a local Ollama model "
            "(e.g. 'ollama:qwen3:9b'). Overrides ZIL_MODEL and ZIL_PROVIDER."
        ),
    ),
) -> None:
    """Start an interactive ZIL⌀ session."""
    if model:
        from zil.config import get_config
        get_config().override_model(model)
    from zil.runtime.loop import chat_loop
    chat_loop()


@app.command()
def eval(
    dataset: str = typer.Option(
        "src/zil/evals/datasets/sycophancy_bench.json",
        "--dataset", "-d",
        help="Path to eval dataset JSON.",
    ),
    model_grade: bool = typer.Option(
        False,
        "--model-grade",
        help="Use model-based grading in addition to heuristics.",
    ),
    output: str = typer.Option(
        "",
        "--output", "-o",
        help="Write results to this JSON file.",
    ),
) -> None:
    """Run the anti-sycophancy benchmark."""
    from zil.evals.runners.runner import run_eval
    run_eval(dataset_path=dataset, model_grade=model_grade, output_path=output or None)


@app.command()
def budget() -> None:
    """Show charge cost table from chargebook.md."""
    from zil.runtime.charge import _load_costs_from_chargebook
    costs = _load_costs_from_chargebook()
    console.print("[bold]Charge cost table[/bold]")
    for op, cost in sorted(costs.items()):
        console.print(f"  {op:<45} {cost}")


@app.command()
def memory(
    layer: str = typer.Option("window", "--layer", "-l", help="window | archive | all"),
    query: str = typer.Option("", "--query", "-q", help="Search string."),
) -> None:
    """Inspect memory layers."""
    from zil.memory.store import MemoryStore
    store = MemoryStore()
    if query:
        records = store.search(query, layer=layer)
        console.print(f"[bold]Search results for '{query}' in {layer}:[/bold]")
    else:
        if layer == "window":
            records = store.read_window()
        elif layer == "archive":
            records = store.read_archive()
        else:
            records = store.read_window() + store.read_archive()
        console.print(f"[bold]{layer} memory ({len(records)} records):[/bold]")

    for r in records:
        console.print(f"  [{r.kind}] {str(r.model_dump())[:120]}")

    if not records:
        console.print("  (empty)")


@app.command()
def consolidate() -> None:
    """Run memory consolidation for today's session."""
    from zil.memory.consolidate import consolidate_session
    from zil.memory.store import MemoryStore
    store = MemoryStore()
    with console.status("[dim]consolidating memory...[/dim]"):
        summary = consolidate_session(store)
    n_epi = len(summary.epistemic_records)
    n_rel = len(summary.relational_records)
    n_beh = len(summary.behavioral_records)
    console.print(
        f"[green]Consolidation complete.[/green] "
        f"Epistemic: {n_epi}, Relational: {n_rel}, Behavioral: {n_beh}"
    )
    if summary.long_term_entry:
        console.print(f"\n[dim]Long-term entry written:[/dim]\n{summary.long_term_entry}")


if __name__ == "__main__":
    app()
