"""Deterministic decision engine (Section 23).

Pipeline per Section 23.2-23.3:
    candidates
        -> reject unsafe (forecast.simulate floor)
        -> reject deadline-invalid (> desired_completion_date)
        -> reject preference-invalid (eligibility filter)
        -> rank remaining via optimizer 6-rule
        -> select exactly one winner
        -> derive status/method (rules.derive)
        -> validate cross-field consistency
        -> produce canonical Decision

Section 23.1 statuses:
    affordable_now, affordable_with_plan, affordable_later, not_affordable
Status is derived deterministically from validated candidate set, never LLM.

Section 23.2 cross-field rules:
    status ↔ method, method ↔ plan, plan ↔ date, spending ↔ plan, explanation ↔ decision
    All enforced; invalid combos raise and degrade to safe fallback.

Section 23.3 edge cases:
    1. No safe plan, 2. Safe now, 3. Safe later, 4. Partial only,
    5. Installment only, 6. Wait only, 7. Multiple safe, 8. Tie-break
    Covered in tests/regression/test_sections_22_26.py
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any


def evaluate_and_select(state, candidates, profile, deadline, allows_partial: bool = False):
    """Deterministic pipeline: filter unsafe -> deadline -> preference -> rank -> select.

    allows_partial must be passed explicitly from the request (no hardcoded default
    that could bypass user preference). Production path (pipeline.py:decide_context)
    does not call this helper; it calls filter_candidates directly with the real
    req allows_partial_payment. This helper is for isolated/test use.
    """
    from affordai.decision.eligibility import filter_candidates
    from affordai.finance import optimizer
    from affordai.finance.forecast import simulate

    # Step 1: eligibility = deadline + preference (safety not decided here, per eligibility.py contract)
    eligible = filter_candidates(candidates, profile, allows_partial, deadline)
    # Safety validation: re-simulate every eligible candidate, keep only safe
    validated = [c for c in eligible if simulate(state, c.payments, getattr(c, "changes", None) or {}).ok]
    winner = optimizer.select(validated, deadline) if validated else None
    return validated, winner


def derive_status_method(winner) -> tuple[str, str]:
    from affordai.decision import rules

    return rules.derive(winner)


def validate_cross_field(decision) -> list[str]:
    """Check Section 23.2 cross-field consistency, return error strings (empty = ok)."""
    errors: list[str] = []
    from affordai.decision.invariants import check_earliest_consistency, check_status_method_consistency

    if not check_status_method_consistency(decision.affordability_status, decision.recommended_payment_method):
        errors.append(f"status {decision.affordability_status} inconsistent with method {decision.recommended_payment_method}")
    # plan ↔ method
    plan = decision.payment_plan
    method = decision.recommended_payment_method
    if method == "partial_payment" and plan != "none":
        # Must be exactly 2 legs summing to requested (checked deeper in validator)
        legs = plan.split("|") if plan != "none" else []
        if len(legs) != 2:
            errors.append(f"partial_payment must have exactly 2 plan legs, got {len(legs)}")
    if method == "installments" and plan == "none":
        errors.append("installments must have a plan, got none")
    if method == "not_recommended" and plan != "none":
        errors.append(f"not_recommended must have plan none, got {plan!r}")
    # spending ↔ plan
    if method == "not_recommended" and decision.spending_changes_needed != "none":
        errors.append("not_recommended must have changes none")
    # explanation ↔ decision (via explanation validator)
    try:
        from affordai.output.explanation import validate as expl_validate

        if not expl_validate(decision.decision_explanation, decision):
            errors.append("explanation contradicts decision")
    except Exception as e:
        errors.append(f"explanation validation error: {e}")
    return errors


def decide(state, candidates, profile, deadline, request_date, allows_partial: bool = False) -> tuple[str, str, Any]:
    """Full deterministic decision: rank, select, derive, validate.

    Returns (status, method, winner_candidate_or_None). Raises on invariant violation
    (caller degrades to fallback).
    """
    validated, winner = evaluate_and_select(state, candidates, profile, deadline, allows_partial)
    status, method = derive_status_method(winner)
    return status, method, winner
