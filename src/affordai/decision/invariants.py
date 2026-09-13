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
    if status == "affordable_now":
        return earliest == request_date
    if status == "not_affordable":
        return earliest == ""
    return True
