"""Sections 12-14 edge-case tests (Checklist 12.3, 13.x edges, 14.2)."""
import sys
from datetime import date, timedelta
from decimal import Decimal

import pytest

sys.path.insert(0, "src")

from affordai.finance.currency import (
    DuplicateRateError,
    MissingRateError,
    RateTable,
    UnsupportedCurrencyError,
    load_rates,
)
from affordai.finance.forecast import earliest_full_date, max_safe_today, simulate
from affordai.finance.state import FinancialState, StateError, build as build_state
from affordai.finance.temporal import (
    TemporalError,
    clamp_month_day,
    forecast_end,
    generate_interval_occurrences,
    generate_monthly_occurrences,
    in_window,
    meets_deadline,
)
from affordai.finance.timeline import build_flows


def _rt():
    return RateTable(
        [
            {"rate_date": date(2025, 1, 31), "from_currency": "USD", "to_currency": "INR", "rate": Decimal("83.5")},
            {"rate_date": date(2025, 3, 31), "from_currency": "USD", "to_currency": "INR", "rate": Decimal("84.5")},
        ]
    )


# ---------- 12.3 currency edges --------------------------------------------------
def test_missing_rate_later_only_date():
    rt = _rt()
    assert rt.rate_on("USD", "INR", date(2025, 1, 30)) is None  # pre-window: no fallback
    with pytest.raises(MissingRateError):
        rt.get_rate("USD", "INR", date(2025, 1, 30))


def test_pre_window_event_uses_no_unrelated_rate():
    rt = _rt()  # earliest supplied 2025-01-31; settlement 2024-12-01 must NOT reuse it
    assert rt.rate_on("USD", "INR", date(2024, 12, 1)) is None


def test_unsupported_pair_controlled_failure():
    rt = _rt()
    with pytest.raises((MissingRateError, UnsupportedCurrencyError)):
        rt.get_rate("AAA", "BBB", date(2025, 6, 1))
    amount, trace = rt.convert_to_home(Decimal("10"), "AAA", "BBB", date(2025, 6, 1))
    assert amount is None and "fail-closed" in trace.reason


def test_date_mismatch_uses_latest_on_or_before():
    rt = _rt()
    assert rt.get_rate("USD", "INR", date(2025, 2, 15)).rate_date == date(2025, 1, 31)
    assert rt.get_rate("USD", "INR", date(2025, 3, 31)).rate_date == date(2025, 3, 31)


def test_duplicate_rate_conflict_and_load_skipped_observable(tmp_path):
    with pytest.raises(DuplicateRateError):
        RateTable(
            [
                {"rate_date": date(2025, 1, 1), "from_currency": "USD", "to_currency": "INR", "rate": Decimal("1")},
                {"rate_date": date(2025, 1, 1), "from_currency": "USD", "to_currency": "INR", "rate": Decimal("2")},
            ]
        )
    p = tmp_path / "rates.csv"
    p.write_text(
        "rate_date,from_currency,to_currency,rate\n"
        "2025-01-01,USD,INR,83.5\n"
        "2025-02-01,USD,INR,not-a-rate\n"
        "2025-03-01,USD,INR,-4\n",
        encoding="utf-8",
    )
    table = load_rates(str(p))
    assert table.rate_on("USD", "INR", date(2025, 6, 1)) == Decimal("83.5")
    assert len(table.load_skipped) == 2  # malformed + non-positive recorded, not silent


# ---------- 14.2 temporal edges --------------------------------------------------
def _state(opening="10000", minimum="1000", net=None, req="2025-01-10", dl="2025-04-10", requested="1000"):
    y, m, d = int(req[:4]), int(req[5:7]), int(req[8:10])
    yy, mm, dd = int(dl[:4]), int(dl[5:7]), int(dl[8:10])
    return FinancialState(
        request_id="r", user_id="u", request_date=date(y, m, d),
        deadline=date(yy, mm, dd), home="INR",
        opening=Decimal(opening), minimum=Decimal(minimum),
        requested=Decimal(requested), flows=[], unknowns=[], notes=[],
        events_by_id={}, daily_net=net or {},
    )


def test_same_day_income_before_payment_simulated_together():
    st = _state(net={date(2025, 1, 10): Decimal("5000") - Decimal("2000")})
    assert simulate(st, [(date(2025, 1, 10), Decimal("12000"))]).ok  # 10k+5k-2k-12k = 1k floor
    assert not simulate(st, [(date(2025, 1, 10), Decimal("12000.01"))]).ok


def test_deadline_day_trilogy():
    st = _state()
    assert simulate(st, [(date(2025, 4, 9), Decimal("9000"))]).ok
    assert simulate(st, [(date(2025, 4, 10), Decimal("9000"))]).ok  # == deadline valid
    assert meets_deadline(date(2025, 4, 10), date(2025, 4, 10))
    assert not meets_deadline(date(2025, 4, 11), date(2025, 4, 10))


def test_first_future_day_separation():
    st = _state(requested="9000",
                net={date(2025, 1, 10): Decimal("-500"), date(2025, 1, 11): Decimal("5000")})
    assert max_safe_today(st) == Decimal("8500")  # tomorrow's salary NOT counted today
    assert earliest_full_date(st) == date(2025, 1, 11)


def test_90_day_boundary_vs_91st_day():
    req = date(2025, 1, 10)
    assert forecast_end(req) == date(2025, 4, 9)
    assert in_window(date(2025, 4, 9), req) and not in_window(date(2025, 4, 10), req)
    st = _state(net={date(2025, 4, 9): Decimal("-9000")})
    assert simulate(st, []).ok  # boundary expense counts: 10k-9k = 1k floor, exact-safe
    st2 = _state(net={date(2025, 4, 9): Decimal("-9000.01")})
    assert not simulate(st2, []).ok  # one unit over the floor fails


def test_month_boundaries_calendar_aware():
    assert clamp_month_day(2025, 2, 31) == date(2025, 2, 28)
    assert clamp_month_day(2024, 2, 31) == date(2024, 2, 29)
    assert date(2025, 1, 31) + timedelta(days=1) == date(2025, 2, 1)
    occ = generate_monthly_occurrences(date(2025, 4, 30), date(2025, 5, 31), 30)
    assert occ == [date(2025, 4, 30), date(2025, 5, 30)]


def test_year_boundary_recurrence():
    occ = generate_interval_occurrences(date(2024, 12, 31), date(2025, 1, 1), date(2025, 3, 31), 30)
    assert date(2025, 1, 30) in occ and all(d.year == 2025 for d in occ)
    occ_m = generate_monthly_occurrences(date(2024, 12, 15), date(2025, 2, 15), 15)
    assert occ_m == [date(2024, 12, 15), date(2025, 1, 15), date(2025, 2, 15)]


def test_recurrence_anomalies_handled():
    assert generate_monthly_occurrences(date(2025, 3, 1), date(2025, 1, 1), 10) == []  # end<start
    assert generate_interval_occurrences(date(2026, 1, 1), date(2025, 1, 10), date(2025, 4, 9), 30) == []  # outside
    with pytest.raises(TemporalError):
        generate_interval_occurrences(date(2025, 1, 1), date(2025, 1, 10), date(2025, 4, 9), -7)
    with pytest.raises(TemporalError):
        clamp_month_day(2025, 13, 10)


# ---------- timeline inclusion edges (13.2/13.3) ---------------------------------
class _MiniCtx:
    def __init__(self, req_date, home="INR", events=(), protect=()):
        self.request = {"request_id": "r1", "user_id": "u1", "request_date": req_date,
                        "desired_completion_date": date(2025, 6, 1),
                        "requested_amount": Decimal("100"),
                        "original_index": 0}
        self.profile = {"user_id": "u1", "home_currency": home,
                        "current_available_balance": Decimal("5000"),
                        "minimum_balance_to_keep": Decimal("500"),
                        "expense_categories_to_protect": list(protect)}
        self.events = list(events)


def _ev(eid, **kw):
    base = {"event_id": eid, "user_id": "u1", "event_type": "expense",
            "description": "d", "category": "rent", "direction": "debit",
            "amount": Decimal("100"), "currency": "INR",
            "event_date": date(2025, 1, 5), "settlement_date": date(2025, 1, 12),
            "status": "scheduled", "flexibility": "fixed",
            "minimum_allowed_amount": None}
    base.update(kw)
    return base


def test_cancelled_failed_unrealized_noncash_excluded():
    ctx = _MiniCtx(date(2025, 1, 10), events=[
        _ev("e1", status="cancelled"), _ev("e2", status="failed"),
        _ev("e3", status="unrealized"),
        _ev("e4", direction="non_cash", status="settled"),
        _ev("e5"),  # control: scheduled, kept
    ])
    flows, _, _ = build_flows(ctx, _rt(), set(), {}, {})
    assert {f.event_id for f in flows} == {"e5"}


def test_pending_credit_ignored_pending_debit_reserved():
    ctx = _MiniCtx(date(2025, 1, 10), events=[
        _ev("c1", direction="credit", status="pending", amount=Decimal("9999"), category="bonus"),
        _ev("d1", direction="debit", status="pending", amount=Decimal("200"), category="rent"),
    ])
    flows, _, _ = build_flows(ctx, _rt(), set(), {}, {})
    by_id = {f.event_id: f for f in flows}
    assert "c1" not in by_id and by_id["d1"].day == date(2025, 1, 10)


def test_evidence_cancelled_and_duplicates_excluded():
    ctx = _MiniCtx(date(2025, 1, 10), events=[_ev("e1"), _ev("e2")])
    flows, _, _ = build_flows(ctx, _rt(), {"e1"}, {}, {})
    assert {f.event_id for f in flows} == {"e2"}
    # duplicate economic event reaching state.build must raise, not double-count
    from affordai.finance.timeline import Flow

    dup = [Flow(date(2025, 1, 12), Decimal("-100"), "scheduled", "e2", "e2", "rent", "fixed", True)] * 2
    with pytest.raises(StateError):
        build_state(ctx, dup, [])


def test_blank_amount_is_unknown_never_zero():
    ctx = _MiniCtx(date(2025, 1, 10), events=[_ev("b1", amount=None)])
    flows, unknowns, _ = build_flows(ctx, _rt(), set(), {}, {})
    assert not [f for f in flows if f.event_id == "b1"]
    assert any(u["event_id"] == "b1" for u in unknowns)


def test_missing_fx_credit_excluded_debit_excluded_fail_closed():
    rt = RateTable([])  # no rates at all
    ctx = _MiniCtx(date(2025, 1, 10), events=[
        _ev("fc", direction="credit", status="scheduled", currency="USD", amount=Decimal("500"), category="salary"),
        _ev("fd", direction="debit", status="scheduled", currency="USD", amount=Decimal("50"), category="rent"),
    ])
    flows, unknowns, notes = build_flows(ctx, rt, set(), {}, {})
    by_id = {f.event_id: f for f in flows}
    assert "fc" not in by_id and "fd" not in by_id
    assert any("fx-missing" in n for n in notes)
    assert any(u["event_id"] == "fd" for u in unknowns)
