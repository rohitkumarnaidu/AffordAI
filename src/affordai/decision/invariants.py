"""Financial invariant checker — blocks submission on violation.

Re-simulation hooks (balance floor, deadline, totals) attach in Milestone 2.
Bounds/consistency checks are live from Milestone 1.
"""
from __future__ import annotations


def check_amount_bounds(safe: float, requested: float) -> bool:
    return 0 <= safe <= requested


def check_status_method_consistency(status: str, method: str) -> bool:
    if method == "partial_payment":
        return status == "affordable_with_plan"
    if status == "affordable_now":
        return method == "full_payment"
    if status == "not_affordable":
        return method == "not_recommended"
    return True


def check_earliest_consistency(status: str, request_date: str, earliest: str) -> bool:
    # Tier-1 rule (problem_statement): earliest measures capacity
    # independently of preferences/deadline; empty ONLY when full payment
    # never becomes safe in the forecast. not_affordable MAY carry a real
    # earliest (capacity exists but no eligible plan completes by deadline).
    if status == "affordable_now":
        return earliest == request_date
    if earliest == "":
        return True
    return request_date <= earliest
