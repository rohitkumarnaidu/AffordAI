"""90-day daily-ledger forecast + safe-amount / earliest-date search.

Invariant: a plan is safe ONLY if closing >= minimum on EVERY projected
day. Within a day: opening + inflows - outflows - plan payments.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_FLOOR

from affordai.finance.money import quantize_money
from affordai.finance.temporal import WINDOW_DAYS

Change = tuple[str, Decimal | None]  # (source_event_id, None=stop | new_amount=reduce cap)


@dataclass
class SimResult:
    ok: bool
    min_closing: Decimal
    worst_day: date | None


def _apply_changes(
    daily_net: dict[date, Decimal],
    flows_by_source: dict[str, list],
    changes: dict[str, Decimal | None],
) -> dict[date, Decimal]:
    """Return adjusted daily net. stop -> remove source outflows; reduce -> cap each occurrence."""
    if not changes:
        return daily_net
    adjusted = dict(daily_net)
    for source, new_amount in changes.items():
        for flow in flows_by_source.get(source, []):
            if flow.amount_home >= 0:
                continue  # changes only cut outflows
            if new_amount is None:
                delta = -flow.amount_home  # add back the outflow
            else:
                capped = -min(-flow.amount_home, new_amount)
                delta = capped - flow.amount_home
            adjusted[flow.day] = adjusted.get(flow.day, Decimal("0")) + delta
    return adjusted


def simulate(
    state,
    payments: list[tuple[date, Decimal]],
    changes: dict[str, Decimal | None] | None = None,
) -> SimResult:
    """Simulate one candidate over the 90-day window.

    Caller contract: ``simulate`` decides balance-floor safety ONLY
    (``closing >= minimum`` every projected day). Deadline preference
    (``last payment <= desired_completion_date``) is enforced by the
    caller chain — ``decision/eligibility.filter_candidates`` drops
    late candidates before ranking (``optimizer`` re-applies it as
    rank rule 1). Do not treat ``simulate().ok`` as deadline approval.
    """
    changes = changes or {}
    flows_by_source: dict[str, list] = {}
    for f in state.flows:
        if f.source_event_id:
            flows_by_source.setdefault(f.source_event_id, []).append(f)
    daily = _apply_changes(state.daily_net, flows_by_source, changes)
    pay_by_day: dict[date, Decimal] = {}
    for day, amount in payments:
        pay_by_day[day] = pay_by_day.get(day, Decimal("0")) + amount
    balance = state.opening
    worst = balance
    worst_day = state.request_date
    for offset in range(WINDOW_DAYS):
        day = state.request_date + timedelta(days=offset)
        balance = balance + daily.get(day, Decimal("0")) - pay_by_day.get(day, Decimal("0"))
        if balance < worst:
            worst = balance
            worst_day = day
        if balance < state.minimum:
            return SimResult(ok=False, min_closing=worst, worst_day=day)
    return SimResult(ok=True, min_closing=worst, worst_day=worst_day)


def max_safe_today(state) -> Decimal:
    """Max single payment safe on request_date (no changes), via minor-unit binary search.

    Monotonicity lemma (why binary search is exact here): ``simulate``
    computes ``closing(day) = opening + net(day) - paid(day)`` with a
    single non-negative payment on ``request_date``. Raising the payment
    lowers every projected closing pointwise, so the safety predicate
    ``all(closing >= minimum)`` is monotone decreasing in the amount:
    if ``X`` is safe then every ``0 <= Y <= X`` is safe, and if ``X``
    is unsafe then every ``Z >= X`` is unsafe. Binary search over
    integer minor units therefore returns the exact maximum.

    Bounds: ``0 <= result <= requested`` (hi is floored so a non-2dp
    ``requested`` can never round the search ceiling above it; the
    return is clamped for the same invariant).

    Base-breach rule: if existing obligations already break the floor
    with NO new payment, nothing is payable — return ``0`` (the search
    loop would converge there anyway; the early return just skips the
    post-conditions, which assume a safe base).
    """
    unit = Decimal("0.01")
    if not simulate(state, []).ok:
        return Decimal("0.00")
    hi = int((state.requested / unit).to_integral_value(rounding=ROUND_FLOOR))
    lo = 0
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if simulate(state, [(state.request_date, Decimal(mid) * unit)]).ok:
            lo = mid
        else:
            hi = mid - 1
    result = quantize_money(Decimal(lo) * unit, state.home)
    if result < 0:
        result = Decimal("0.00")
    if result > state.requested:
        result = quantize_money(state.requested, state.home)
    # Post-conditions (fail-closed: any violation raises -> pipeline
    # degrades to the safest fallback, never a silently wrong amount).
    assert simulate(state, [(state.request_date, result)]).ok
    if result + unit <= state.requested:
        assert not simulate(state, [(state.request_date, result + unit)]).ok
    return result


def earliest_full_date(state) -> date | None:
    """First date the full amount is safe as ONE payment (no changes).

    Linear scan from ``request_date`` over the 90-day window; the first
    simulated-safe day is minimal by construction (every earlier allowed
    date was simulated unsafe). Independent of method preferences by
    design: takes only ``state`` (no profile/accepted-methods), so the
    caller chain derives capacity here and applies preferences later.
    Returns ``None`` (serialized as ``""``) when never safe in-window.
    Deadline is deliberately ignored here (Tier-1 capacity semantics);
    ``payment_plans``/``eligibility`` enforce it downstream.
    """
    for offset in range(WINDOW_DAYS):
        day = state.request_date + timedelta(days=offset)
        if simulate(state, [(day, state.requested)]).ok:
            return day
    return None
