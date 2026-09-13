"""Edge-case tests: boundaries the engine must get exactly right."""
import sys
from datetime import date
from decimal import Decimal

sys.path.insert(0, "src")

from affordai.finance.forecast import simulate
from affordai.finance.state import FinancialState


def _state(opening, minimum, net=None, requested="100"):
    return FinancialState(
        request_id="r", user_id="u", request_date=date(2025, 1, 10),
        deadline=date(2025, 4, 10), home="INR",
        opening=Decimal(opening), minimum=Decimal(minimum),
        requested=Decimal(requested), flows=[], unknowns=[], notes=[],
        events_by_id={}, daily_net=net or {},
    )


def test_zero_amount_always_safe():
    st = _state("1000", "900")
    assert simulate(st, [(date(2025, 1, 10), Decimal("0"))]).ok


def test_amount_equal_to_balance_minus_minimum():
    st = _state("1000", "900")
    assert simulate(st, [(date(2025, 1, 10), Decimal("100"))]).ok
    assert not simulate(st, [(date(2025, 1, 10), Decimal("100.01"))]).ok


def test_minimum_boundary_exact():
    st = _state("1000", "1000")  # opening == minimum: any positive payment fails
    assert not simulate(st, [(date(2025, 1, 10), Decimal("0.01"))]).ok
    assert simulate(st, []).ok


def test_same_day_flows_and_payment():
    st = _state("2000", "500", {date(2025, 1, 10): Decimal("-800")})
    assert simulate(st, [(date(2025, 1, 10), Decimal("700"))]).ok  # closes 500
    assert not simulate(st, [(date(2025, 1, 10), Decimal("700.01"))]).ok


def test_payment_on_deadline_day():
    st = _state("10000", "1000")
    assert simulate(st, [(date(2025, 4, 10), Decimal("9000"))]).ok


def test_window_end_boundary():
    # 90-day window from 2025-01-10 ends 2025-04-09; flows outside ignored.
    st = _state("1500", "1000", {date(2025, 4, 9): Decimal("-400")})
    assert simulate(st, []).ok  # closes 1100
    st2 = _state("1500", "1000", {date(2025, 4, 9): Decimal("-400"), date(2025, 4, 10): Decimal("-10000")})
    assert simulate(st2, []).ok  # day 91 ignored
