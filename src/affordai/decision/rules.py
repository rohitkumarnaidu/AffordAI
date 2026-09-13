"""Status/method derivation from the winning candidate (no LLM)."""
from __future__ import annotations


def derive(winner) -> tuple[str, str]:
    """Return (affordability_status, recommended_payment_method)."""
    if winner is None:
        return ("not_affordable", "not_recommended")
    if winner.kind == "full" and not winner.changes:
        return ("affordable_now", "full_payment")
    if winner.kind == "full":
        return ("affordable_with_plan", "full_payment")
    if winner.kind == "partial":
        return ("affordable_with_plan", "partial_payment")
    if winner.kind == "installments":
        return ("affordable_with_plan", "installments")
    if winner.kind == "wait":
        return ("affordable_later", "wait")
    return ("not_affordable", "not_recommended")
