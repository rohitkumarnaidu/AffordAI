"""Financial invariant checker — blocks submission on violation.

Re-simulation hooks (balance floor, deadline, totals) attach in Milestone 2.
Bounds/consistency checks are live from Milestone 1.
"""
from __future__ import annotations


def check_amount_bounds(safe: float, requested: float) -> bool:
    return 0 <= safe <= requested


def check_status_method_consistency(status: str, method: str) -> bool:
    allowed = {
        "affordable_now": {"full_payment"},
        "affordable_with_plan": {"full_payment", "partial_payment", "installments"},
        "affordable_later": {"wait"},
        "not_affordable": {"not_recommended"},
    }
    if status not in allowed:
        return False
    if method not in {"full_payment", "partial_payment", "installments", "wait", "not_recommended"}:
        return False
    return method in allowed[status]


def check_earliest_consistency(status: str, request_date: str, earliest: str) -> bool:
    # Tier-1 rule (problem_statement): earliest measures capacity
    # independently of preferences/deadline; empty ONLY when full payment
    # never becomes safe in the forecast. not_affordable MAY carry a real
    # earliest (capacity exists but no eligible plan completes by deadline).
    # affordable_with_plan may also have empty earliest when full single
    # payment never safe but installments/partial-with-plan still completes.
    if status == "affordable_now":
        return earliest == request_date
    if status == "affordable_later":
        # Must be a future date (capacity becomes safe later)
        if not earliest:
            return False
        return request_date < earliest
    if status == "affordable_with_plan":
        if earliest == "":
            return True
        return request_date <= earliest
    if status == "not_affordable":
        if earliest == "":
            return True
        return request_date <= earliest
    return False
