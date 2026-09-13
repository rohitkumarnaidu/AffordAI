"""Grounded explanations: template over validated Decision facts only.

Never claims unsupported evidence, nonexistent transactions, dates, or
balances. When the LLM adapter drafts alternative wording (E3+), its output
must pass `validate()` here or the template below is used instead.
"""
from __future__ import annotations

from affordai.finance.money import format_amount


def build(decision, requested: str, request_date: str, home: str) -> str:
    safe = format_amount(decision.amount_safe_to_pay, home)
    earliest = decision.earliest_date_for_full_payment or "not in forecast"
    changes = decision.spending_changes_needed
    method = decision.recommended_payment_method
    status = decision.affordability_status
    base = (
        f"Requested {requested} {home} on {request_date}: {safe} {home} safe to pay "
        f"today while keeping the minimum balance across the 90-day forecast "
        f"(status {status}, method {method})."
    )
    if method == "not_recommended":
        return base + f" Full payment earliest safe: {earliest}."
    tail = f" Full payment earliest safe: {earliest}."
    if changes != "none":
        tail += f" Requires spending changes: {changes}."
    return base + tail


def validate(text: str, decision) -> bool:
    """Explanation consistency gate: must echo status/method, never contradict."""
    return (
        decision.affordability_status in text
        and decision.recommended_payment_method in text
    )
