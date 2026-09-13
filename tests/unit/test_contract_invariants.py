import sys

sys.path.insert(0, "src")

from affordai.decision.invariants import (
    check_amount_bounds,
    check_earliest_consistency,
    check_status_method_consistency,
)


def test_bounds():
    assert check_amount_bounds(0, 100)
    assert check_amount_bounds(100, 100)
    assert not check_amount_bounds(-1, 100)
    assert not check_amount_bounds(101, 100)


def test_status_method():
    assert check_status_method_consistency("affordable_with_plan", "partial_payment")
    assert not check_status_method_consistency("affordable_later", "partial_payment")
    assert check_status_method_consistency("affordable_now", "full_payment")
    assert not check_status_method_consistency("affordable_now", "installments")


def test_earliest():
    assert check_earliest_consistency("affordable_now", "2024-03-03", "2024-03-03")
    assert not check_earliest_consistency("affordable_now", "2024-03-03", "2024-03-04")
    assert check_earliest_consistency("not_affordable", "2024-03-03", "")
    # Tier-1 regression: not_affordable MAY carry a real earliest (capacity
    # exists past the deadline, but no eligible plan completes safely).
    assert check_earliest_consistency("not_affordable", "2025-11-06", "2026-01-15")
    assert not check_earliest_consistency("not_affordable", "2025-11-06", "2025-01-01")
