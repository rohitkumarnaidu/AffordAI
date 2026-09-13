"""Sections 12-14 unit tests: currency / financial-state / temporal engines.

Covers Checklist 12.1-12.2, 13.1, 13.5 (validators), 14.1, 14.3 plus
property-style invariants and determinism. Edge/adversarial/integration
cases live in their own layers.
"""
import sys
from datetime import date, datetime
from decimal import Decimal

import pytest

sys.path.insert(0, "src")

from affordai.finance.currency import (
    SUPPORTED_CURRENCIES,
    ConversionTrace,
    DuplicateRateError,
    MissingRateError,
    RateTable,
    UnsupportedCurrencyError,
    normalize_currency,
    validate_currency,
)
from affordai.finance.state import (
    FinancialState,
    StateError,
    build as build_state,
    is_protected,
    stop_allowed,
    validate_reduction,
)
from affordai.finance.temporal import (
    WINDOW_DAYS,
    TemporalError,
    add_days,
    clamp_month_day,
    first_future_day,
    forecast_end,
    forecast_start,
    generate_interval_occurrences,
    generate_monthly_occurrences,
    in_window,
    is_deadline_day,
    meets_deadline,
    normalize_date,
)


def _rates():
    return RateTable(
        [
            {"rate_date": date(2025, 1, 15), "from_currency": "USD", "to_currency": "INR", "rate": Decimal("83")},
            {"rate_date": date(2025, 2, 15), "from_currency": "USD", "to_currency": "INR", "rate": Decimal("84")},
            {"rate_date": date(2025, 2, 15), "from_currency": "EUR", "to_currency": "USD", "rate": Decimal("1.08")},
        ]
    )


# ---------- 12.1 inputs ------------------------------------------------------
def test_normalize_currency_casing_whitespace():
    assert normalize_currency(" usd ") == "USD"
    assert normalize_currency("inr") == "INR"
    with pytest.raises(UnsupportedCurrencyError):
        normalize_currency("")
    with pytest.raises(UnsupportedCurrencyError):
        normalize_currency(None)


def test_validate_currency_supported_set():
    for code in ("INR", "ZAR", "IDR", "USD", "EUR"):
        assert validate_currency(code) == code
    assert SUPPORTED_CURRENCIES == frozenset({"INR", "ZAR", "IDR", "USD", "EUR"})
    with pytest.raises(UnsupportedCurrencyError):
        validate_currency("AAA")
    with pytest.raises(UnsupportedCurrencyError):
        validate_currency("usdollar")


def test_home_event_payment_currencies_are_distinct_inputs():
    rt = _rates()
    lookup = rt.get_rate("USD", "INR", date(2025, 2, 20))
    assert (lookup.source_currency, lookup.target_currency) == ("USD", "INR")
    assert lookup.rate == Decimal("84") and lookup.rate_date == date(2025, 2, 15)
    assert lookup.rate_id == "USD->INR@2025-02-15"
    assert lookup.source_dataset == "exchange_rates.csv"


def test_settlement_date_drives_lookup():
    rt = _rates()
    assert rt.get_rate("USD", "INR", date(2025, 2, 15)).rate == Decimal("84")
    assert rt.get_rate("USD", "INR", date(2025, 2, 14)).rate == Decimal("83")


def test_directed_pair_no_inverse_synthesis():
    rt = _rates()
    assert rt.rate_on("USD", "INR", date(2025, 3, 1)) == Decimal("84")
    assert rt.rate_on("INR", "USD", date(2025, 3, 1)) is None
    with pytest.raises(MissingRateError):
        rt.get_rate("INR", "USD", date(2025, 3, 1))


# ---------- 12.2 calculation --------------------------------------------------
def test_supplied_rates_only_no_network():
    import affordai.finance.currency as cur_mod
    import inspect

    src = inspect.getsource(cur_mod)
    for token in ("requests.get", "urllib", "http.client", "urlopen", "socket"):
        assert token not in src


def test_rate_lookup_case_insensitive():
    rt = _rates()
    assert rt.rate_on("usd", "inr", date(2025, 3, 1)) == Decimal("84")


def test_same_currency_path_needs_no_rate():
    rt = RateTable([])
    amount, trace = rt.convert_to_home(Decimal("123.45"), "INR", "INR", date(2025, 1, 1))
    assert amount == Decimal("123.45")
    assert trace.same_currency and trace.rate == Decimal(1)
    assert trace.converted_amount == Decimal("123.45")
    assert rt.rate_on("USD", "USD", date(2020, 1, 1)) == Decimal(1)


def test_foreign_path_quantized_half_up():
    rt = RateTable(
        [{"rate_date": date(2025, 1, 1), "from_currency": "USD", "to_currency": "INR", "rate": Decimal("83.4567")}]
    )
    amount, trace = rt.convert_to_home(Decimal("100"), "USD", "INR", date(2025, 6, 1))
    assert amount == Decimal("8345.67")  # 8345.6700 -> HALF_UP 2dp
    assert isinstance(trace, ConversionTrace)
    assert trace.source_amount == Decimal("100") and trace.rate == Decimal("83.4567")
    assert trace.rate_date == date(2025, 1, 1) and trace.rounding_policy


def test_decimal_precision_no_float_error():
    rt = RateTable(
        [{"rate_date": date(2025, 1, 1), "from_currency": "USD", "to_currency": "INR", "rate": Decimal("0.1")}]
    )
    amount, _ = rt.convert_to_home(Decimal("0.2"), "USD", "INR", date(2025, 1, 2))
    assert amount == Decimal("0.02")  # exact; float would give 0.020000000000000004
    # property: conversion never produces NaN
    assert amount.is_finite()


def test_small_large_and_repeating_conversions():
    rt = RateTable(
        [{"rate_date": date(2025, 1, 1), "from_currency": "USD", "to_currency": "IDR", "rate": Decimal("15833.33")}]
    )
    tiny, _ = rt.convert_to_home(Decimal("0.01"), "USD", "IDR", date(2025, 1, 2))
    assert tiny == Decimal("158.33")
    huge, _ = rt.convert_to_home(Decimal("1000000"), "USD", "IDR", date(2025, 1, 2))
    assert huge == Decimal("15833330000.00").quantize(Decimal("0.01"))
    again, _ = rt.convert_to_home(Decimal("0.01"), "USD", "IDR", date(2025, 1, 2))
    assert again == tiny  # repeating conversion is stable


def test_missing_rate_fail_closed_not_zero_or_one():
    rt = RateTable([])
    assert rt.to_home(Decimal("50"), "USD", "INR", date(2025, 1, 1)) is None
    amount, trace = rt.convert_to_home(Decimal("50"), "USD", "INR", date(2025, 1, 1))
    assert amount is None and trace.converted_amount is None and trace.rate is None


def test_rate_table_rejects_conflicting_duplicates():
    rows = [
        {"rate_date": date(2025, 1, 1), "from_currency": "USD", "to_currency": "INR", "rate": Decimal("83")},
        {"rate_date": date(2025, 1, 1), "from_currency": "USD", "to_currency": "INR", "rate": Decimal("84")},
    ]
    with pytest.raises(DuplicateRateError):
        RateTable(rows)


def test_rate_table_dedupes_identical_duplicates_observably():
    rows = [
        {"rate_date": date(2025, 1, 1), "from_currency": "USD", "to_currency": "INR", "rate": Decimal("83")},
        {"rate_date": date(2025, 1, 1), "from_currency": "USD", "to_currency": "INR", "rate": Decimal("83")},
    ]
    rt = RateTable(rows)
    assert rt.duplicates_deduped == 1
    assert rt.rate_on("USD", "INR", date(2025, 1, 2)) == Decimal("83")


# ---------- 13.1 starting state ----------------------------------------------
class _Ctx:
    def __init__(self, request, profile, events):
        self.request = request
        self.profile = profile
        self.events = events


def _good_ctx():
    return _Ctx(
        {"original_index": 0, "request_id": "r1", "user_id": "u1",
         "request_date": date(2025, 1, 10), "desired_completion_date": date(2025, 3, 10),
         "requested_amount": Decimal("3000")},
        {"user_id": "u1", "home_currency": "INR",
         "current_available_balance": Decimal("10000"),
         "minimum_balance_to_keep": Decimal("1000")},
        [],
    )


def test_build_state_validates_starting_state():
    st = build_state(_good_ctx(), [], [])
    assert st.opening == Decimal("10000") and st.minimum == Decimal("1000")
    assert st.home == "INR" and st.request_date == date(2025, 1, 10)
    assert st.provenance["request_id"] == "r1" and st.provenance["n_flows"] == 0
    assert st.daily_net == {}


def test_build_state_rejects_bad_starting_state():
    import copy

    for mutate, _why in [
        (lambda c: c.profile.update(home_currency="AAA"), "unsupported home"),
        (lambda c: c.profile.update(current_available_balance=Decimal("-1")), "negative opening"),
        (lambda c: c.profile.update(minimum_balance_to_keep=Decimal("-1")), "negative minimum"),
        (lambda c: c.request.update(requested_amount=Decimal("0")), "non-positive requested"),
        (lambda c: c.request.update(request_date="2025-01-10"), "non-date request_date"),
    ]:
        ctx = _good_ctx()
        mutate(ctx)
        with pytest.raises(StateError):
            build_state(ctx, [], [])


def test_build_state_rejects_out_of_window_and_duplicate_flows():
    from affordai.finance.timeline import Flow

    ctx = _good_ctx()
    with pytest.raises(StateError):  # day 91 outside [req, req+89]
        build_state(ctx, [Flow(date(2025, 4, 11), Decimal("-10"), "settled", "e1", "e1", "rent", "fixed", True)], [])
    dup = [
        Flow(date(2025, 1, 12), Decimal("-10"), "settled", "e1", "e1", "rent", "fixed", True),
        Flow(date(2025, 1, 12), Decimal("-10"), "settled", "e1", "e1", "rent", "fixed", True),
    ]
    with pytest.raises(StateError):
        build_state(ctx, dup, [])


# ---------- 13.5 flexibility ---------------------------------------------------
def _row(flex="reducible", cat="streaming", floor=Decimal("100")):
    return {"event_id": "e1", "flexibility": flex, "category": cat, "minimum_allowed_amount": floor}


def _prof():
    return {"expense_categories_to_protect": ["rent"],
            "willing_to_reduce": ["streaming"], "willing_to_stop": ["gym"]}


def test_flexibility_matrix():
    prof = _prof()
    assert stop_allowed(_row("stoppable", "gym", None), prof)[0]
    assert stop_allowed(_row("reducible_or_stoppable", "gym", Decimal("10")), prof)[0]
    assert not stop_allowed(_row("reducible", "streaming"), prof)[0]  # not stoppable
    assert not stop_allowed(_row("fixed", "gym", None), prof)[0]
    assert not stop_allowed(_row("stoppable", "rent", None), prof)[0]  # protected
    assert not stop_allowed(_row("stoppable", "travel", None), prof)[0]  # unwilling
    assert validate_reduction(_row("reducible", "streaming", Decimal("100")), prof, Decimal("100")) == Decimal("100")
    for bad in (Decimal("99.99"), Decimal("0"), Decimal("-5")):
        with pytest.raises(StateError):
            validate_reduction(_row("reducible", "streaming", Decimal("100")), prof, bad)
    with pytest.raises(StateError):  # protected reduce rejected
        validate_reduction(_row("reducible", "rent", Decimal("10")), _prof(), Decimal("50"))


def test_is_protected():
    assert is_protected("rent", _prof()) and not is_protected("streaming", _prof())


# ---------- 14.1 / 14.3 temporal ----------------------------------------------
def test_temporal_window_and_deadline():
    req = date(2025, 1, 10)
    assert WINDOW_DAYS == 90
    assert forecast_start(req) == req
    assert forecast_end(req) == date(2025, 4, 9)  # +89 inclusive
    assert in_window(req, req) and in_window(date(2025, 4, 9), req)
    assert not in_window(date(2025, 4, 10), req)  # 91st day
    assert not in_window(date(2025, 1, 9), req)
    assert meets_deadline(date(2025, 3, 10), date(2025, 3, 10))  # deadline day valid
    assert is_deadline_day(date(2025, 3, 10), date(2025, 3, 10))
    assert not meets_deadline(date(2025, 3, 11), date(2025, 3, 10))
    assert first_future_day(req) == date(2025, 1, 11)
    assert add_days(date(2025, 1, 31), 1) == date(2025, 2, 1)


def test_normalize_date_rejects_silent_today():
    assert normalize_date(date(2025, 1, 1)) == date(2025, 1, 1)
    assert normalize_date(datetime(2025, 1, 1, 15, 30)) == date(2025, 1, 1)
    with pytest.raises(TemporalError):
        normalize_date("2025-01-01")
    with pytest.raises(TemporalError):
        normalize_date(None)


def test_month_year_boundaries():
    assert clamp_month_day(2025, 1, 31) == date(2025, 1, 31)
    assert clamp_month_day(2025, 2, 31) == date(2025, 2, 28)  # clamp, not +30d
    assert clamp_month_day(2024, 2, 30) == date(2024, 2, 29)  # leap year
    assert clamp_month_day(2025, 4, 31) == date(2025, 4, 30)
    assert clamp_month_day(2025, 12, 31) == date(2025, 12, 31)
    with pytest.raises(TemporalError):
        clamp_month_day(2025, 2, 0)
    # monthly schedule across Feb clamp keeps one occurrence per month, no dupes
    occ = generate_monthly_occurrences(date(2025, 1, 31), date(2025, 4, 30), 31)
    assert occ == [date(2025, 1, 31), date(2025, 2, 28), date(2025, 3, 31), date(2025, 4, 30)]
    assert generate_monthly_occurrences(date(2025, 5, 1), date(2025, 4, 1), 15) == []


def test_interval_recurrence_unique_and_terminating():
    occ = generate_interval_occurrences(date(2025, 1, 1), date(2025, 1, 10), date(2025, 4, 9), 7)
    assert len(set(occ)) == len(occ) and all(date(2025, 1, 10) <= d <= date(2025, 4, 9) for d in occ)
    assert generate_interval_occurrences(date(2025, 6, 1), date(2025, 1, 10), date(2025, 4, 9), 7) == []
    with pytest.raises(TemporalError):
        generate_interval_occurrences(date(2025, 1, 1), date(2025, 1, 10), date(2025, 4, 9), 0)


def test_temporal_determinism_repeat_runs():
    args = (date(2025, 1, 10), date(2025, 4, 9), 15)
    assert generate_monthly_occurrences(*args) == generate_monthly_occurrences(*args)
    anchor = (date(2024, 12, 31), date(2025, 1, 10), date(2025, 4, 9), 30)
    assert generate_interval_occurrences(*anchor) == generate_interval_occurrences(*anchor)
    # year boundary: Dec 31 anchor projects into January deterministically
    assert date(2025, 1, 30) in generate_interval_occurrences(*anchor)
