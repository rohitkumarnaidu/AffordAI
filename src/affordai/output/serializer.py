"""Deterministic CSV serialization (exact columns/order/row identity)."""
from __future__ import annotations

from affordai.finance.money import format_amount


def format_plan(payments: list[tuple] | None, currency: str) -> str:
    if not payments:
        return "none"
    return "|".join(f"{d.isoformat()}:{format_amount(a, currency)}" for d, a in payments)


def format_changes(changes: dict[str, object], currency: str) -> str:
    if not changes:
        return "none"
    parts = []
    for event_id in sorted(changes):
        new_amount = changes[event_id]
        if new_amount is None:
            parts.append(f"stop:{event_id}")
        else:
            parts.append(f"reduce_to:{event_id}:{format_amount(new_amount, currency)}")
    return "|".join(parts)


def decisions_to_rows(decisions: list, home_by_request: dict[str, str]) -> list[dict]:
    """Decisions must already be sorted by original_index."""
    rows = []
    for d in decisions:
        home = home_by_request[d.request_id]
        plan = (
            d.payment_plan
            if isinstance(d.payment_plan, str)
            else format_plan(d.payment_plan, home)
        )
        changes = (
            d.spending_changes_needed
            if isinstance(d.spending_changes_needed, str)
            else format_changes(d.spending_changes_needed, home)
        )
        rows.append(
            {
                "request_id": d.request_id,
                "amount_safe_to_pay": format_amount(d.amount_safe_to_pay, home),
                "affordability_status": d.affordability_status,
                "recommended_payment_method": d.recommended_payment_method,
                "payment_plan": plan,
                "earliest_date_for_full_payment": d.earliest_date_for_full_payment,
                "spending_changes_needed": changes,
                "decision_explanation": d.decision_explanation,
            }
        )
    return rows
