"""Charge / budget tracking system.

Reads cost values from chargebook.md at startup. Tracks session spend.
Raises BudgetExceeded when a charged operation would exceed the session limit.
Penalty flags are logged to the ledger but do not consume budget.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

import yaml

from zil.config import get_config
from zil.runtime import ledger as ledger_mod

PenaltyFlag = Literal[
    "unsupported_agreement",
    "unsupported_certainty",
    "memory_contamination",
]

# Hard-coded fallback costs in case chargebook parsing fails.
_FALLBACK_COSTS: dict[str, int] = {
    "local_state_inspection": 0,
    "response_drafting": 0,
    "uncertainty_statement": 0,
    "explicit_update_or_correction": 0,
    "named_disagreement": 0,
    "counterargument_generation": 0,
    "evidence_lookup": 1,
    "memory_write_candidate": 1,
    "durable_memory_commit": 2,
    "delegation_subtask_spawn": 5,
    "external_acquisition_search_burst": 5,
    "game_action": 1,
}


def _load_costs_from_chargebook() -> dict[str, int]:
    """Parse the costs.yaml block embedded in chargebook.md."""
    cfg = get_config()
    path = cfg.project_root / "chargebook.md"
    if not path.exists():
        return _FALLBACK_COSTS.copy()
    text = path.read_text(encoding="utf-8")
    # Find the yaml block after "```yaml"
    match = re.search(r"```yaml\s*(costs:.*?)```", text, re.DOTALL)
    if not match:
        return _FALLBACK_COSTS.copy()
    try:
        data = yaml.safe_load(match.group(1))
        costs_raw = data.get("costs", {})
        # Keep only integer costs; penalty entries are strings ("flag")
        return {k: int(v) for k, v in costs_raw.items() if isinstance(v, int)}
    except Exception:
        return _FALLBACK_COSTS.copy()


class ChargeTracker:
    """Tracks charge spend for a single session."""

    def __init__(self) -> None:
        cfg = get_config()
        self._budget = cfg.session_budget
        self._spent = 0
        self._costs = _load_costs_from_chargebook()
        self._run_id: str = ""

    def set_run_id(self, run_id: str) -> None:
        self._run_id = run_id

    @property
    def remaining(self) -> int:
        return self._budget - self._spent

    @property
    def spent(self) -> int:
        return self._spent

    def cost_of(self, operation: str) -> int:
        return self._costs.get(operation, 0)

    def charge(self, operation: str, *, note: str = "") -> int:
        """Consume charge for an operation. Returns the amount charged.

        Raises BudgetExceeded if the operation would exceed session budget.
        Free operations (cost 0) always proceed.
        """
        cost = self.cost_of(operation)
        if cost == 0:
            return 0
        if self._spent + cost > self._budget:
            raise BudgetExceeded(
                f"Operation '{operation}' costs {cost} but only "
                f"{self.remaining} charge remains (budget: {self._budget})."
            )
        self._spent += cost
        ledger_mod.append_event(
            "charge_event",
            {
                "operation": operation,
                "cost": cost,
                "spent_total": self._spent,
                "remaining": self.remaining,
                "note": note,
            },
            run_id=self._run_id,
        )
        return cost

    def flag_penalty(self, flag: PenaltyFlag, reason: str) -> None:
        """Record a penalty flag. Does not consume budget but is logged."""
        ledger_mod.append_event(
            "charge_event",
            {
                "operation": "penalty_flag",
                "flag": flag,
                "reason": reason,
                "note": "Penalty flags do not consume budget but are recorded.",
            },
            run_id=self._run_id,
        )

    def add_charge(self, amount: int) -> None:
        """Add charge to the session budget. Logged to the ledger."""
        if amount <= 0:
            return
        self._budget += amount
        ledger_mod.append_event(
            "charge_event",
            {
                "operation": "recharge",
                "amount": amount,
                "new_budget": self._budget,
                "spent_total": self._spent,
                "remaining": self.remaining,
                "note": "Summoner added charge.",
            },
            run_id=self._run_id,
        )

    def summary(self) -> dict:
        return {
            "budget": self._budget,
            "spent": self._spent,
            "remaining": self.remaining,
        }


class BudgetExceeded(Exception):
    """Raised when a charged operation would exceed the session budget."""
