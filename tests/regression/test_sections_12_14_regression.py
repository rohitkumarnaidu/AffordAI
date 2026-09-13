"""Sections 12-14 regression tests: every bug found during the Sec 12-14
audit is preserved here as fixture + test (BUG -> ROOT CAUSE -> FIX).

R1 currency codes were case-sensitive ("usd" missed the USD->INR series).
R2 conflicting duplicate (pair, rate_date) FX rows were silently collapsed.
R3 load_rates silently skipped malformed/non-positive rows.
R4 FinancialState.build accepted negative balances, unsupported home
   currencies, out-of-window flows, and duplicate economic events.
R5 flexibility/protected logic was duplicated between state and
   spending_changes (drift risk).
R6 WINDOW_DAYS was defined in timeline.py and imported by forecast.py
   (two owners for one horizon).
"""
import sys
from datetime import date
from decimal import Decimal

import pytest

sys.path.insert(0, "src")


def test_r1_lowercase_currency_resolves():
    from affordai.finance.currency import RateTable

    rt = RateTable(
        [{"rate_date": date(2025, 1, 1), "from_currency": "USD", "to_currency": "INR", "rate": Decimal("80")}]
    )
    assert rt.rate_on("usd", "inr", date(2025, 2, 1)) == Decimal("80")  # was None
    amount, _ = rt.convert_to_home(Decimal("10"), "usd", "inr", date(2025, 2, 1))
    assert amount == Decimal("800")


def test_r2_conflicting_duplicate_rates_raise():
    from affordai.finance.currency import DuplicateRateError, RateTable

    with pytest.raises(DuplicateRateError):  # was: last row silently won
        RateTable(
            [
                {"rate_date": date(2025, 1, 1), "from_currency": "USD", "to_currency": "INR", "rate": Decimal("80")},
                {"rate_date": date(2025, 1, 1), "from_currency": "USD", "to_currency": "INR", "rate": Decimal("81")},
            ]
        )


def test_r3_skipped_rate_rows_are_observable(tmp_path):
    from affordai.finance.currency import load_rates

    p = tmp_path / "rates.csv"
    p.write_text(
        "rate_date,from_currency,to_currency,rate\n2025-01-01,USD,INR,80\n2025-02-01,USD,INR,garbage\n",
        encoding="utf-8",
    )
    table = load_rates(str(p))  # was: row vanished without a trace
    assert len(table.load_skipped) == 1 and "garbage" in table.load_skipped[0]


def test_r4_state_build_rejects_invalid_starting_state():
    from affordai.finance.state import StateError, build as build_state

    class Ctx:
        request = {"original_index": 0, "request_id": "r1", "user_id": "u1",
                   "request_date": date(2025, 1, 10),
                   "desired_completion_date": date(2025, 3, 31),
                   "requested_amount": Decimal("100")}
        profile = {"user_id": "u1", "home_currency": "INR",
                   "current_available_balance": Decimal("5000"),
                   "minimum_balance_to_keep": Decimal("500")}
        events = []

    bad = Ctx()
    bad.profile = dict(Ctx.profile, current_available_balance=Decimal("-1"))
    with pytest.raises(StateError):  # was: negative opening accepted
        build_state(bad, [], [])


def test_r4_state_build_rejects_duplicate_economic_event():
    from affordai.finance.state import StateError, build as build_state
    from affordai.finance.timeline import Flow

    class Ctx:
        request = {"original_index": 0, "request_id": "r1", "user_id": "u1",
                   "request_date": date(2025, 1, 10),
                   "desired_completion_date": date(2025, 3, 31),
                   "requested_amount": Decimal("100")}
        profile = {"user_id": "u1", "home_currency": "INR",
                   "current_available_balance": Decimal("5000"),
                   "minimum_balance_to_keep": Decimal("500")}
        events = []

    dup = [Flow(date(2025, 1, 12), Decimal("-50"), "settled", "e1", "e1", "rent", "fixed", True)] * 2
    with pytest.raises(StateError):  # was: charged twice
        build_state(Ctx(), dup, [])


def test_r5_single_source_of_flexibility_truth():
    import affordai.finance.spending_changes as sc
    import affordai.finance.state as st

    assert sc.REDUCE_OK is st.REDUCE_OK  # was: two independent literal sets
    assert hasattr(st, "stop_allowed") and hasattr(st, "validate_reduction") and hasattr(st, "is_protected")


def test_r6_single_window_owner():
    import affordai.finance.temporal as temporal

    assert temporal.WINDOW_DAYS == 90
    assert temporal.forecast_end(date(2025, 1, 10)) == date(2025, 4, 9)
    # timeline/forecast must consume the same constant (no second definition)
    import affordai.finance.timeline as tl
    import affordai.finance.forecast as fc

    assert tl.WINDOW_DAYS == temporal.WINDOW_DAYS == fc.WINDOW_DAYS
