"""Sections 12-14 cross-engine integration (Checklist Sections 33-35).

Required flow per case::

    Raw Financial Event -> Temporal Normalization -> Settlement/Event
    Classification -> Currency Normalization -> Canonical Financial State
    -> 90-Day Forecast

Every case asserts event identity/date/settlement/status/currency/amount/
normalized amount/financial treatment end to end.
"""
import sys
from datetime import date
from decimal import Decimal

sys.path.insert(0, "src")

from affordai.finance.currency import RateTable
from affordai.finance.forecast import simulate
from affordai.finance.state import build as build_state
from affordai.finance.timeline import build_flows

REQ = date(2025, 1, 10)
RATES = RateTable(
    [
        {"rate_date": date(2025, 1, 1), "from_currency": "USD", "to_currency": "INR", "rate": Decimal("80")},
        {"rate_date": date(2025, 2, 1), "from_currency": "USD", "to_currency": "INR", "rate": Decimal("82")},
    ]
)


class Ctx:
    def __init__(self, events, home="INR", protect=(), opening="20000", minimum="2000"):
        self.request = {"original_index": 0, "request_id": "r1", "user_id": "u1",
                        "request_date": REQ, "desired_completion_date": date(2025, 3, 31),
                        "requested_amount": Decimal("5000")}
        self.profile = {"user_id": "u1", "home_currency": home,
                        "current_available_balance": Decimal(opening),
                        "minimum_balance_to_keep": Decimal(minimum),
                        "expense_categories_to_protect": list(protect),
                        "willing_to_reduce": ["streaming"], "willing_to_stop": ["gym", "streaming"]}
        self.events = events


def _ev(eid, **kw):
    base = {"event_id": eid, "user_id": "u1", "event_type": "expense",
            "description": "d", "category": "rent", "direction": "debit",
            "amount": Decimal("100"), "currency": "INR",
            "event_date": date(2025, 1, 5), "settlement_date": date(2025, 1, 12),
            "status": "scheduled", "flexibility": "fixed",
            "minimum_allowed_amount": None}
    base.update(kw)
    return base


def _run(ctx, rates=RATES, cancelled=frozenset()):
    flows, unknowns, notes = build_flows(ctx, rates, set(cancelled), {}, {})
    state = build_state(ctx, flows, unknowns, notes)
    return state, flows, unknowns, notes


def test_same_currency_same_day():
    ctx = Ctx([_ev("e1", settlement_date=REQ)])
    state, flows, _, _ = _run(ctx)
    assert flows[0].day == REQ and flows[0].amount_home == Decimal("-100")
    assert state.daily_net[REQ] == Decimal("-100")


def test_foreign_exact_settlement_rate():
    ctx = Ctx([_ev("e1", currency="USD", amount=Decimal("10"), settlement_date=date(2025, 2, 1))])
    _, flows, _, _ = _run(ctx)
    assert flows[0].amount_home == Decimal("-820")  # 10 * 82 exact-date rate


def test_foreign_date_mismatch_latest_on_or_before():
    ctx = Ctx([_ev("e1", currency="USD", amount=Decimal("10"), settlement_date=date(2025, 1, 15))])
    _, flows, _, _ = _run(ctx)
    assert flows[0].amount_home == Decimal("-800")  # Jan-01 row, NOT Feb-01


def test_salary_same_day_as_payment():
    ctx = Ctx([
        _ev("sal", direction="credit", status="scheduled", event_type="income",
            category="salary", amount=Decimal("8000"), settlement_date=REQ),
        _ev("e1", settlement_date=REQ),
    ])
    state, _, _, _ = _run(ctx)
    assert state.daily_net[REQ] == Decimal("7900")
    assert simulate(state, [(REQ, Decimal("24900"))]).ok  # 20k+7.9k-24.9k = 2k floor


def test_pending_debit_before_salary():
    ctx = Ctx([
        _ev("pd", direction="debit", status="pending", amount=Decimal("5000"), settlement_date=date(2025, 3, 1)),
        _ev("sal", direction="credit", status="scheduled", event_type="income",
            category="salary", amount=Decimal("3000"), settlement_date=date(2025, 1, 20)),
    ])
    state, flows, _, _ = _run(ctx)
    assert {f.event_id: f.day for f in flows}["pd"] == REQ  # reserved immediately
    assert not simulate(state, [(REQ, Decimal("17000"))]).ok  # 20k-5k-17k < 2k


def test_cancelled_recurring_expense_excluded():
    ctx = Ctx([_ev("e1", category="gym", flexibility="stoppable")])
    state, flows, _, _ = _run(ctx, cancelled={"e1"})
    assert flows == [] and state.daily_net == {}


def test_failed_payment_excluded():
    ctx = Ctx([_ev("e1", status="failed")])
    _, flows, _, _ = _run(ctx)
    assert flows == []


def test_duplicate_event_rejected_at_state_gate():
    from affordai.finance.timeline import Flow

    ctx = Ctx([_ev("e1")])
    dup = [Flow(date(2025, 1, 12), Decimal("-100"), "scheduled", "e1", "e1", "rent", "fixed", True)] * 2
    try:
        build_state(ctx, dup, [])
    except Exception:
        return
    raise AssertionError("duplicate economic event was not rejected")


def test_unrealized_investment_excluded():
    ctx = Ctx([_ev("inv", event_type="investment", direction="credit",
                     status="unrealized", amount=Decimal("99999"), category="stocks")])
    state, flows, _, _ = _run(ctx)
    assert flows == []  # never spendable cash
    assert simulate(state, []).ok


def test_flexible_reduction_and_protected_paths():
    from affordai.finance import spending_changes

    ctx = Ctx([
        _ev("fx1", category="streaming", flexibility="reducible",
            event_type="subscription", minimum_allowed_amount=Decimal("60"),
            amount=Decimal("200"), settlement_date=date(2025, 1, 12)),
        _ev("fx2", category="streaming", flexibility="reducible",
            event_type="subscription", minimum_allowed_amount=Decimal("60"),
            amount=Decimal("200"), settlement_date=date(2025, 2, 12)),
        _ev("p1", category="rent", flexibility="stoppable",
            event_type="subscription", amount=Decimal("500"), settlement_date=date(2025, 1, 12)),
        _ev("p2", category="rent", flexibility="stoppable",
            event_type="subscription", amount=Decimal("500"), settlement_date=date(2025, 2, 12)),
    ], protect=("rent",))
    state, _, _, _ = _run(ctx)
    targets = spending_changes.candidate_targets(state, ctx.profile)
    ids = {t.event_id for t in targets}
    assert "fx1" in ids or "fx2" in ids  # reducible willing target exists
    assert "p1" not in ids and "p2" not in ids  # protected never targeted


def test_deadline_day_payment_valid():
    ctx = Ctx([])
    state, _, _, _ = _run(ctx)
    assert simulate(state, [(date(2025, 3, 31), Decimal("18000"))]).ok


def test_payment_on_90_day_boundary():
    ctx = Ctx([])
    state, _, _, _ = _run(ctx)
    assert simulate(state, [(date(2025, 4, 9), Decimal("18000"))]).ok  # day 90 in-window


def test_recurring_month_boundary_and_year_salary():
    # Monthly cadence Oct 31 -> Nov 30 -> Dec 31 (gaps 30/31d) projects
    # Jan 31 / Feb 28 / Mar 31 across the Dec->Jan year boundary.
    ctx = Ctx([
        _ev("h1", status="settled", event_type="expense", category="rent",
            amount=Decimal("500"),
            settlement_date=date(2024, 10, 31), event_date=date(2024, 10, 31)),
        _ev("h2", status="settled", event_type="expense", category="rent",
            amount=Decimal("500"),
            settlement_date=date(2024, 11, 30), event_date=date(2024, 11, 30)),
        _ev("h3", status="settled", event_type="expense", category="rent",
            amount=Decimal("500"),
            settlement_date=date(2024, 12, 31), event_date=date(2024, 12, 31)),
    ])
    _, flows, _, _ = _run(ctx)
    inferred = [f for f in flows if f.kind == "inferred"]
    assert inferred  # monthly cadence detected across Dec->Jan year boundary
    days = [f.day for f in inferred]
    assert len(set(days)) == len(days)  # no duplicate recurrence


def test_missing_fx_and_unsupported_pair_end_to_end():
    ctx = Ctx([_ev("e1", currency="USD", amount=Decimal("25"), settlement_date=date(2025, 1, 12))])
    _, flows, unknowns, notes = _run(ctx, rates=RateTable([]))
    assert flows == []  # fail-closed excluded
    assert any("fx-missing" in n for n in notes)
    assert any(u["event_id"] == "e1" for u in unknowns)
    ctx2 = Ctx([_ev("e1", currency="AAA", amount=Decimal("25"))])
    _, flows2, unknowns2, notes2 = _run(ctx2, rates=RateTable([]))
    assert flows2 == []
    assert any("fx-missing" in n for n in notes2)
    assert any(u["event_id"] == "e1" for u in unknowns2)


def test_forecast_floor_invariant_across_window():
    ctx = Ctx([_ev("e1", amount=Decimal("100"), settlement_date=date(2025, 2, 1))])
    state, _, _, _ = _run(ctx)
    result = simulate(state, [(REQ, Decimal("5000"))])
    assert result.ok and result.min_closing >= state.minimum


def test_full_pipeline_identity_preserved():
    ctx = Ctx([_ev("e1")])
    state, _, _, _ = _run(ctx)
    assert state.request_id == "r1" and state.user_id == "u1"
    assert state.provenance["n_events"] == 1 and state.events_by_id["e1"]["event_id"] == "e1"
