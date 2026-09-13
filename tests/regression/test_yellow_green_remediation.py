"""YELLOW->GREEN remediation proof (F1/F2/A1/31d/+89).

Tier-1: problem_statement.md (upstream/main) specifies 8 cols, 4+5 enums,
0<=safe<=requested, partial 5-conds/2-legs, installment exact-match, <=3
spending, 6-rule ranking, 90-day safety, FX matched by rate date + pair.
Tier-1 is SILENT on: FX latest-on-before vs exact-date, inverse synthesis,
missing-rate behavior, month-to-day conversion, +89 vs +90 inclusivity.
Those specifics are marked UNKNOWN and implemented with the safest
contract-compliant behavior (no invention, fail-closed), proven below.
"""
import sys
from datetime import date, timedelta
from decimal import Decimal

sys.path.insert(0, "src")

from affordai.decision.eligibility import filter_candidates
from affordai.finance.currency import MissingRateError, RateTable
from affordai.finance.forecast import simulate
from affordai.finance.payment_plans import Candidate
from affordai.finance.state import FinancialState
from affordai.finance.temporal import WINDOW_DAYS, forecast_end, in_window


def _rt():
    return RateTable([
        {"rate_date": date(2025, 1, 1), "from_currency": "USD", "to_currency": "INR", "rate": Decimal("80")},
        {"rate_date": date(2025, 2, 1), "from_currency": "USD", "to_currency": "INR", "rate": Decimal("82")},
    ])


# ---- A1 FX (official silent on specifics; safest: exact pair, latest on-before, fail-closed) ----
def test_a1_exact_directed_pair_latest_on_before():
    rt = _rt()
    assert rt.get_rate("USD", "INR", date(2025, 1, 15)).rate == Decimal("80")
    assert rt.get_rate("USD", "INR", date(2025, 2, 1)).rate == Decimal("82")


def test_a1_no_inverse_synthesis():
    rt = _rt()
    try:
        rt.get_rate("INR", "USD", date(2025, 2, 1))
        raise AssertionError("inverse synthesis must not exist")
    except MissingRateError:
        pass


def test_a1_missing_rate_fail_closed():
    rt = RateTable([])
    try:
        rt.get_rate("USD", "INR", date(2025, 1, 12))
        raise AssertionError("missing rate must raise")
    except MissingRateError:
        pass
    assert rt.rate_on("USD", "INR", date(2025, 1, 12)) is None


# ---- 31-day term (official silent on conversion; documented approximation, deterministic) ----
def _cand_span(first, freq, n):
    from affordai.ingestion.payment_options import expand_schedule

    opt = {"payment_option_id": "o", "request_id": "r", "payment_method": "installments",
           "payment_amount": Decimal("10"), "number_of_payments": n,
           "first_payment_date": first, "payment_frequency_days": freq,
           "financing_fee": Decimal("0"), "total_payable_amount": Decimal(str(10 * n))}
    sched = expand_schedule(opt)
    return (sched[-1][0] - sched[0][0]).days


def test_term_30_31_deadline_boundaries():
    # span 30 days with max 1 month: accepted under both 30 and 31 conventions
    assert _cand_span(date(2025, 1, 10), 30, 2) == 30
    st_dl = date(2025, 3, 10)
    c_ok = Candidate("installments", [(date(2025, 1, 10), Decimal("10")), (date(2025, 2, 9), Decimal("10"))],
                     option_id="o", total_paid=Decimal("20"))
    prof = {"methods_will_consider": ["installments"], "max_installment_months": 1}
    assert filter_candidates([c_ok], prof, True, st_dl) == [c_ok]
    # span 62 days with max 2 months: rejected under 30-day (60) but accepted under 31-day (62);
    # current code uses 31 (documents UNKNOWN). Prove determinism either way:
    c62 = Candidate("installments", [(date(2025, 1, 10), Decimal("10")), (date(2025, 3, 13), Decimal("10"))],
                    option_id="o", total_paid=Decimal("20"))
    got = filter_candidates([c62], {"methods_will_consider": ["installments"], "max_installment_months": 2}, True, st_dl)
    # 62 <= 62 (31d) so accepted; deadline 2025-03-13 > 2025-03-10 so rejected on deadline instead.
    # Use deadline far enough to isolate term decision:
    got2 = filter_candidates([c62], {"methods_will_consider": ["installments"], "max_installment_months": 2}, True, date(2025, 6, 10))
    assert got2 == [c62], "31d convention accepts 62-day span for 2 months (documented UNKNOWN)"
    c63 = Candidate("installments", [(date(2025, 1, 10), Decimal("10")), (date(2025, 3, 14), Decimal("10"))],
                    option_id="o", total_paid=Decimal("20"))
    assert filter_candidates([c63], {"methods_will_consider": ["installments"], "max_installment_months": 2}, True, date(2025, 6, 10)) == []


# ---- +89 bound (official: next 90 days; implementation: [request_date, +89] inclusive = 90 days) ----
def test_window_89_inclusive_90_exclusive():
    req = date(2025, 1, 10)
    assert WINDOW_DAYS == 90
    assert forecast_end(req) == req + timedelta(days=89)
    assert in_window(req + timedelta(days=89), req) is True
    assert in_window(req + timedelta(days=90), req) is False


def test_payment_on_boundary_day89_valid():
    req = date(2025, 1, 10)
    st = FinancialState(request_id="r", user_id="u", request_date=req, deadline=date(2025, 4, 10),
                        home="INR", opening=Decimal("20000"), minimum=Decimal("2000"),
                        requested=Decimal("5000"), flows=[], unknowns=[], notes=[],
                        events_by_id={}, daily_net={})
    assert simulate(st, [(req + timedelta(days=89), Decimal("18000"))]).ok
